"""Broker revisions (spec §15.2): baselines, detection, review, apply and discard.

A revision is diffed against each meeting's broker baseline (`Meeting.source_json`), never against CR's
edits. Accepting changes is CR's approval; the API syncs calendars afterwards.
"""
import datetime as dt
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlmodel import Session, select

from mcs import service
from mcs.calendar.content import build_event
from mcs.extraction.schema import ExtractedMeeting, ExtractionResult
from mcs.models import Analyst, Conference, Meeting, MeetingAttendee, Revision, SyncRecord, utcnow
from mcs.normalize import add_minutes, build_meetings, parse_date, parse_time
from mcs.revisions import Change, RevisionDiff, diff_revision
from mcs.roster import RosterEntry, match_name, normalize_name
from mcs.schemas import ChangeOut, FieldChangeOut, ProposedMeeting, RevisionOut


# ---------- lookups ----------

def get_revision(session: Session, revision_id: int) -> Revision:
    revision = session.get(Revision, revision_id)
    if revision is None:
        raise service.NotFound("Revision not found.")
    return revision


def _pending(revision: Revision) -> None:
    if revision.status != "pending":
        raise service.Conflict(f"This revision was already {revision.status}.")


def _result(revision: Revision) -> ExtractionResult:
    return ExtractionResult.model_validate_json(revision.result_json)


def baseline_rows(session: Session, conference_id: int) -> list[tuple[int, ExtractedMeeting]]:
    """Meetings that came from the broker, with the broker's last applied version of each row. Cancelled and
    dismissed ones are included so the broker's row for one pairs with it instead of looking new (see `_diff`)."""
    meetings = session.exec(select(Meeting).where(Meeting.conference_id == conference_id, Meeting.source_json != "")
                            .order_by(Meeting.id)).all()
    return [(m.id, ExtractedMeeting.model_validate_json(m.source_json)) for m in meetings]


def _set_aside_ids(session: Session, conference_id: int) -> set[int]:
    """Meetings CR cancelled (sent) or deleted (never sent, kept as "dismissed")."""
    return set(session.exec(select(Meeting.id).where(Meeting.conference_id == conference_id,
                                                     Meeting.status.in_(("cancelled", "dismissed")))).all())


def pending_revision(session: Session, conference_id: int) -> Revision | None:
    return session.exec(select(Revision).where(Revision.conference_id == conference_id,
                                               Revision.status == "pending")
                        .order_by(Revision.id.desc())).first()


def applied_count(session: Session, conference_id: int) -> int:
    return session.exec(select(func.count()).select_from(Revision)
                        .where(Revision.conference_id == conference_id, Revision.status == "applied")).one()


def revision_pdf_paths(session: Session, conference_id: int) -> list[str]:
    """PDFs this conference's revisions still own. A discarded revision's PDF is already gone, or belongs to
    the conference it was split off into, so it's left out."""
    rows = session.exec(select(Revision.pdf_path).where(Revision.conference_id == conference_id,
                                                        Revision.status != "discarded")
                        .order_by(Revision.id)).all()
    return list(dict.fromkeys(p for p in rows if p))


# ---------- detection ----------

def _date_range(dates: Iterable[dt.date | None]) -> tuple[dt.date, dt.date] | None:
    found = [d for d in dates if d is not None]
    return (min(found), max(found)) if found else None


def find_matching_conference(session: Session, result: ExtractionResult) -> Conference | None:
    """The newest conference this upload revises: same name, or same hotel with overlapping dates."""
    name = normalize_name(result.conference_name or "")
    hotel = normalize_name(result.hotel or "")
    new_range = _date_range(parse_date(m.date) for m in result.meetings)
    conferences = session.exec(select(Conference).order_by(Conference.created_at.desc(), Conference.id.desc())).all()
    for conference in conferences:
        if name and name == normalize_name(conference.name):
            return conference
        if hotel and hotel == normalize_name(conference.hotel) and new_range:
            old_range = _date_range(session.exec(select(Meeting.date)
                                                 .where(Meeting.conference_id == conference.id)).all())
            if old_range and new_range[0] <= old_range[1] and old_range[0] <= new_range[1]:
                return conference
    return None


# ---------- create and review ----------

def create_revision(session: Session, conference: Conference, result: ExtractionResult, *, pdf_filename: str,
                    pdf_path: str, extractor: str) -> tuple[Revision, list[str]]:
    """Store a pending revision. Older pending revisions are superseded; their PDF paths are returned."""
    superseded = []
    for old in session.exec(select(Revision).where(Revision.conference_id == conference.id,
                                                   Revision.status == "pending")).all():
        old.status = "discarded"
        session.add(old)
        if old.pdf_path:
            superseded.append(old.pdf_path)
    numbers = session.exec(select(Revision.number).where(Revision.conference_id == conference.id)).all()
    revision = Revision(conference_id=conference.id, number=max(numbers, default=1) + 1, pdf_filename=pdf_filename,
                        pdf_path=pdf_path, extractor=extractor, result_json=result.model_dump_json())
    session.add(revision)
    session.commit()
    session.refresh(revision)
    return revision, superseded


def _diff(session: Session, revision: Revision, result: ExtractionResult) -> RevisionDiff:
    """The one diff both review and apply use, so change ids agree. A meeting CR cancelled or deleted is
    never offered as a change: no "changed" or "removed" for it, and its broker row never counts as "added"."""
    return diff_revision(baseline_rows(session, revision.conference_id), result.meetings,
                         set_aside=_set_aside_ids(session, revision.conference_id))


def _change_out(change: Change) -> ChangeOut:
    new = None
    if change.new is not None:
        new = ProposedMeeting(**change.new.model_dump(include=set(ProposedMeeting.model_fields)))
    return ChangeOut(id=change.id, kind=change.kind, meeting_id=change.meeting_id, company=change.company,
                     summary=change.summary,
                     fields=[FieldChangeOut(field=f.field, before=f.before, after=f.after) for f in change.fields],
                     new=new)


def revision_out(session: Session, revision: Revision) -> RevisionOut:
    diff = _diff(session, revision, _result(revision))
    return RevisionOut(id=revision.id, number=revision.number, pdf_filename=revision.pdf_filename,
                       created_at=revision.created_at, changes=[_change_out(c) for c in diff.changes],
                       unchanged_count=len(diff.unchanged))


# ---------- apply ----------

def _refresh_baseline(meeting: Meeting, row: ExtractedMeeting) -> None:
    meeting.source_json = row.model_dump_json()
    meeting.source_page = row.page


def _drop_baseline(meeting: Meeting) -> None:
    """The broker no longer lists this cancelled or dismissed meeting, so it stops pairing: if the broker
    lists it again later, that is a new meeting for CR to review."""
    meeting.source_json = ""


def _set_matched_attendees(session: Session, meeting: Meeting, names: Sequence[str], schedule_for: str | None,
                           roster: Sequence[RosterEntry]) -> None:
    """Re-match name-matched colleagues to the broker's new names; manual and default colleagues stay, and
    names CR dismissed (ignored_names) are never matched again. Rows are updated in place so the same
    (meeting_id, analyst_id) key is never deleted and re-added."""
    existing = {row.analyst_id: row for row in
                session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting.id)).all()}
    ignored = {normalize_name(n) for n in meeting.ignored_names}
    matched: dict[int, str] = {}
    for raw in names:
        if normalize_name(raw) in ignored:
            continue
        match = match_name(raw, roster)
        if match.analyst_id is not None and match.analyst_id not in matched:
            matched[match.analyst_id] = match.kind
    if not names and schedule_for and normalize_name(schedule_for) not in ignored:
        addressee = match_name(schedule_for, roster)
        if addressee.analyst_id is not None:
            matched[addressee.analyst_id] = addressee.kind
    # CR's manual picks win; a name match beats a default, as when the meeting was first built.
    desired = dict(matched)
    for aid, row in existing.items():
        if row.match == "manual" or (row.match == "default" and aid not in matched):
            desired[aid] = row.match
    for aid, row in existing.items():
        if aid not in desired:
            session.delete(row)
        elif row.match != desired[aid]:
            row.match = desired[aid]
            session.add(row)
    for aid, kind in desired.items():
        if aid not in existing:
            session.add(MeetingAttendee(meeting_id=meeting.id, analyst_id=aid, match=kind))


def _apply_changed(session: Session, meeting: Meeting, change: Change, schedule_for: str | None,
                   roster: Sequence[RosterEntry], default_minutes: int) -> None:
    """Apply the broker's new values to the changed fields only."""
    new, fields = change.new, {f.field for f in change.fields}
    if "date" in fields:
        meeting.date = parse_date(new.date)
    if "start" in fields:
        meeting.start_time = parse_time(new.start)
    if "end" in fields:
        end = parse_time(new.end)
        if end is not None:
            meeting.end_time, meeting.end_assumed = end, False
        elif meeting.start_time is not None:
            meeting.end_time, meeting.end_assumed = add_minutes(meeting.start_time, default_minutes), True
        else:
            meeting.end_time, meeting.end_assumed = None, False
    elif "start" in fields and meeting.end_assumed and meeting.start_time is not None:
        meeting.end_time = add_minutes(meeting.start_time, default_minutes)
    if "room" in fields:
        meeting.room = (new.room or "").strip()
    if "ticker" in fields:
        meeting.ticker = (new.ticker or "").strip() or None
    if "notes" in fields:  # not a compared field today; kept so the rule holds if it becomes one
        meeting.notes = (new.notes or "").strip()
    if "format" in fields:
        meeting.format = new.format
    if "company" in fields:
        meeting.company = new.company
    if "company_attendees" in fields:
        meeting.company_attendees = list(new.company_attendees)
    if "firm_attendees" in fields:
        meeting.raw_attendee_names = list(new.firm_attendees)
        _set_matched_attendees(session, meeting, new.firm_attendees, schedule_for, roster)
    _refresh_baseline(meeting, new)
    meeting.updated_at = utcnow()
    session.add(meeting)


def _create_added(session: Session, conference: Conference, result: ExtractionResult, row: ExtractedMeeting,
                  roster: Sequence[RosterEntry], default_minutes: int) -> Meeting:
    """Build one meeting from the revision's header and this row, as an upload would."""
    draft = build_meetings(result.model_copy(update={"meetings": [row]}), roster, (), default_minutes)[0]
    return service.insert_draft(session, conference.id, draft, row)


def _keep_synced_events(session: Session, conference: Conference, old_pdf_filename: str,
                        old_pages: dict[int, int | None]) -> None:
    """Applying swaps the conference's PDF and refreshes source pages, and both only touch the event's
    "Source:" line. An event that was current and differs only in that line isn't rewritten: its record's
    content_hash is moved to the new content (content_json keeps what was actually sent). Without this, every
    sent meeting would be re-sent after a revision, not just the ones the broker changed."""
    meetings = {m.id: m for m in session.exec(select(Meeting).where(Meeting.conference_id == conference.id,
                                                                    Meeting.status == "confirmed")).all()}
    if not meetings:
        return
    attendees: dict[int, list[int]] = {}
    for row in session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meetings))
                            .order_by(MeetingAttendee.analyst_id)).all():
        attendees.setdefault(row.meeting_id, []).append(row.analyst_id)
    names = {a.id: a.name for a in session.exec(select(Analyst)).all()}
    as_sent_conf = Conference(name=conference.name, hotel=conference.hotel, timezone=conference.timezone,
                              pdf_filename=old_pdf_filename)
    records = session.exec(select(SyncRecord).where(SyncRecord.meeting_id.in_(meetings), SyncRecord.state == "active",
                                                    SyncRecord.external_id.is_not(None))).all()
    for rec in records:
        meeting, ids = meetings[rec.meeting_id], attendees.get(rec.meeting_id, [])
        if rec.analyst_id not in ids or meeting.id not in old_pages:
            continue
        others = [names[x] for x in ids if x != rec.analyst_id]
        as_sent_meeting = Meeting(**meeting.model_dump(exclude={"source_page"}), source_page=old_pages[meeting.id])
        try:
            unchanged = build_event(as_sent_conf, as_sent_meeting, others).content_hash() == rec.content_hash
            current = build_event(conference, meeting, others).content_hash()
        except ValueError:
            continue
        if unchanged and current != rec.content_hash:
            rec.content_hash = current
            session.add(rec)


def apply_revision(session: Session, revision_id: int, accepted: Sequence[str] | None,
                   default_minutes: int) -> tuple[Conference, str]:
    """Apply the accepted changes (None = all). Returns the conference and its previous PDF path."""
    revision = get_revision(session, revision_id)
    _pending(revision)
    conference = service.get_conference(session, revision.conference_id)
    result = _result(revision)
    diff = _diff(session, revision, result)
    known = {c.id for c in diff.changes}
    chosen = known if accepted is None else set(accepted)
    unknown = sorted(chosen - known)
    if unknown:
        raise service.InvalidInput(f"Unknown change ids: {', '.join(unknown)}.")

    old_pdf_filename = conference.pdf_filename
    old_pages = {m.id: m.source_page for m in
                 session.exec(select(Meeting).where(Meeting.conference_id == conference.id)).all()}
    roster = service.roster_for(session)
    added_ids = []
    for change in diff.changes:
        if change.id not in chosen:
            continue  # rejected: the old baseline stays, so it shows up again next time
        if change.kind == "changed":
            _apply_changed(session, session.get(Meeting, change.meeting_id), change, result.schedule_for, roster,
                           default_minutes)
        elif change.kind == "removed":
            service.delete_meeting(session, change.meeting_id, broker_dropped=True)
        else:
            added_ids.append(_create_added(session, conference, result, change.new, roster, default_minutes).id)
    for meeting_id, row in diff.unchanged:
        meeting = session.get(Meeting, meeting_id)
        _refresh_baseline(meeting, row)
        session.add(meeting)
    for meeting_id, row in diff.set_aside:
        # Silent: a cancelled or dismissed meeting is never planned for (pending cancels use what was sent),
        # so this keeps later pairing accurate without touching its status or any calendar.
        meeting = session.get(Meeting, meeting_id)
        if row is None:
            _drop_baseline(meeting)
        else:
            _refresh_baseline(meeting, row)
        session.add(meeting)
    if added_ids:
        service.confirm_ready(session, conference.id, added_ids)

    previous_pdf = conference.pdf_path
    conference.pdf_path, conference.pdf_filename = revision.pdf_path, revision.pdf_filename
    revision.status = "applied"
    session.add(conference)
    session.add(revision)
    _keep_synced_events(session, conference, old_pdf_filename, old_pages)
    session.commit()
    service.enforce_status(session, conference)
    session.refresh(conference)
    return conference, previous_pdf


# ---------- discard ----------

def discard_revision(session: Session, revision_id: int) -> str:
    """Drop a pending revision. Returns its PDF path for deletion."""
    revision = get_revision(session, revision_id)
    _pending(revision)
    revision.status = "discarded"
    session.add(revision)
    session.commit()
    return revision.pdf_path


def revision_as_new_conference(session: Session, revision_id: int, default_minutes: int) -> Conference:
    """Split a wrongly matched revision off into its own conference, which takes over the revision's PDF."""
    revision = get_revision(session, revision_id)
    _pending(revision)
    revision.status = "discarded"
    session.add(revision)
    return service.create_conference(session, _result(revision), pdf_filename=revision.pdf_filename,
                                     pdf_path=revision.pdf_path, extractor=revision.extractor,
                                     default_minutes=default_minutes)  # commits the status change too
