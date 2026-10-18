"""Database-backed operations and the verification rules. Routes stay thin; this is the app's logic."""
import datetime as dt
import json
from pathlib import Path
from typing import Sequence

from sqlalchemy import delete
from sqlmodel import Session, select

from mcs.calendar.content import build_event
from mcs.calendar.planner import SyncAction, SyncOutcome, plan_sync
from mcs.extraction.schema import ExtractedMeeting, ExtractionResult
from mcs.models import Analyst, Conference, Meeting, MeetingAttendee, Revision, SyncRecord, utcnow
from mcs.normalize import (
    DraftMeeting, MeetingView, add_minutes, build_meetings, compute_flags, has_block, parse_date, parse_time,
    valid_timezone,
)
from mcs.roster import RosterEntry, match_name, normalize_name, roster_entries
from mcs.schemas import (
    AnalystIn, AnalystSendSummary, AnalystUpdate, AttendeeOut, ConferenceDetail, ConferenceSummary,
    ConferenceUpdate, Counts, FlagOut, MeetingCreate, MeetingOut, MeetingUpdate, SendResult, SyncActionOut,
)


class NotFound(Exception):
    pass


class InvalidInput(Exception):
    pass


class Conflict(Exception):
    def __init__(self, message: str, flags=()):
        super().__init__(message)
        self.flags = [FlagOut(code=f.code, severity=f.severity, message=f.message) for f in flags]


# ---------- helpers ----------

def _strict_time(value: str | None) -> dt.time | None:
    if value is None or not value.strip():
        return None
    parsed = parse_time(value)
    if parsed is None:
        raise InvalidInput(f"Couldn't read the time {value!r}. Enter it like 2:30 PM or 14:30.")
    return parsed


def _strict_date(value: str | None) -> dt.date | None:
    if value is None or not value.strip():
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise InvalidInput(f"Couldn't read the date {value!r}. Use YYYY-MM-DD.")
    return parsed


def _hhmm(t: dt.time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def _analysts(session: Session) -> dict[int, Analyst]:
    return {a.id: a for a in session.exec(select(Analyst)).all()}


def _roster(session: Session) -> list[RosterEntry]:
    return roster_entries(session.exec(select(Analyst)).all())


def roster_for(session: Session) -> list[RosterEntry]:
    return _roster(session)


def _meetings(session: Session, conference_id: int) -> list[Meeting]:
    return list(session.exec(select(Meeting).where(Meeting.conference_id == conference_id)).all())


def _attendee_map(session: Session, meeting_ids: Sequence[int]) -> dict[int, list[tuple[int, str]]]:
    out: dict[int, list[tuple[int, str]]] = {mid: [] for mid in meeting_ids}
    if meeting_ids:
        rows = session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meeting_ids))
                            .order_by(MeetingAttendee.analyst_id)).all()
        for row in rows:
            out[row.meeting_id].append((row.analyst_id, row.match))
    return out


def _records(session: Session, meeting_ids: Sequence[int], sink_name: str) -> list[SyncRecord]:
    if not meeting_ids:
        return []
    return list(session.exec(select(SyncRecord).where(SyncRecord.meeting_id.in_(meeting_ids),
                                                     SyncRecord.sink == sink_name)).all())


def _views(meetings: Sequence[Meeting], att: dict[int, list[tuple[int, str]]]) -> list[MeetingView]:
    return [MeetingView(id=m.id, date=m.date, start_time=m.start_time, end_time=m.end_time,
                        end_assumed=m.end_assumed, company=m.company, status=m.status,
                        attendees=tuple(att.get(m.id, [])), raw_attendee_names=tuple(m.raw_attendee_names),
                        ignored_names=tuple(m.ignored_names)) for m in meetings]


def _flags(session: Session, conference: Conference, meetings: Sequence[Meeting]):
    att = _attendee_map(session, [m.id for m in meetings])
    return compute_flags(conference.timezone, _views(meetings, att), _roster(session)), att


def _sort_key(m: Meeting):
    return (m.date is None, m.date or dt.date.max, m.start_time is None, m.start_time or dt.time.max,
            m.company.casefold(), m.id)


def _enforce_status(session: Session, conference: Conference) -> None:
    meetings = _meetings(session, conference.id)
    flags, _ = _flags(session, conference, meetings)
    changed = False
    for m in meetings:
        if m.status == "confirmed" and has_block(flags[m.id]):
            m.status = "draft"
            m.updated_at = utcnow()
            session.add(m)
            changed = True
    if changed:
        session.commit()


def enforce_status(session: Session, conference: Conference) -> None:
    """A verified meeting never carries a block flag: drop any that do back to draft."""
    _enforce_status(session, conference)


def _active_ids(session: Session, analyst_ids: Sequence[int]) -> list[int]:
    analysts = _analysts(session)
    for aid in analyst_ids:
        if aid not in analysts or not analysts[aid].active:
            raise InvalidInput(f"Unknown or inactive colleague id {aid}.")
    return list(dict.fromkeys(analyst_ids))


def check_attendee_ids(session: Session, ids: Sequence[int]) -> list[int]:
    return _active_ids(session, ids)


# ---------- roster ----------

def list_analysts(session: Session) -> list[Analyst]:
    return list(session.exec(select(Analyst).order_by(Analyst.name)).all())


def _email_taken(session: Session, email: str, exclude_id: int | None = None) -> bool:
    found = session.exec(select(Analyst).where(Analyst.email == email)).first()
    return found is not None and found.id != exclude_id


def create_analyst(session: Session, data: AnalystIn) -> Analyst:
    email = data.email.strip().lower()
    if _email_taken(session, email):
        raise InvalidInput(f"{email} is already on the roster.")
    analyst = Analyst(name=data.name.strip(), email=email, aliases=[a.strip() for a in data.aliases if a.strip()],
                      active=data.active)
    session.add(analyst)
    session.commit()
    session.refresh(analyst)
    return analyst


def update_analyst(session: Session, analyst_id: int, data: AnalystUpdate) -> Analyst:
    analyst = session.get(Analyst, analyst_id)
    if analyst is None:
        raise NotFound("Colleague not found.")
    fields = data.model_fields_set
    if "name" in fields and data.name:
        analyst.name = data.name.strip()
    if "email" in fields and data.email:
        email = data.email.strip().lower()
        if _email_taken(session, email, analyst_id):
            raise InvalidInput(f"{email} is already on the roster.")
        analyst.email = email
    if "aliases" in fields and data.aliases is not None:
        analyst.aliases = [a.strip() for a in data.aliases if a.strip()]
    if "active" in fields and data.active is not None:
        analyst.active = data.active
    session.add(analyst)
    session.commit()
    session.refresh(analyst)
    return analyst


def delete_analyst(session: Session, analyst_id: int) -> None:
    analyst = session.get(Analyst, analyst_id)
    if analyst is None:
        raise NotFound("Colleague not found.")
    used = session.exec(select(MeetingAttendee).where(MeetingAttendee.analyst_id == analyst_id)).first()
    synced = session.exec(select(SyncRecord).where(SyncRecord.analyst_id == analyst_id)).first()
    if used or synced:
        raise Conflict("This colleague is on meetings. Mark them inactive instead.")
    session.delete(analyst)
    session.commit()


def seed_roster(session: Session, path: Path) -> int:
    added = 0
    for item in json.loads(Path(path).read_text()):
        email = item["email"].strip().lower()
        if not _email_taken(session, email):
            session.add(Analyst(name=item["name"], email=email, aliases=list(item.get("aliases", []))))
            added += 1
    session.commit()
    return added


# ---------- conferences ----------

def get_conference(session: Session, conference_id: int) -> Conference:
    conference = session.get(Conference, conference_id)
    if conference is None:
        raise NotFound("Conference not found.")
    return conference


def create_conference(session: Session, result: ExtractionResult, *, pdf_filename: str, pdf_path: str,
                      extractor: str, default_attendee_ids: Sequence[int] = (), default_minutes: int = 45) -> Conference:
    defaults = _active_ids(session, default_attendee_ids)
    conference = Conference(
        name=result.conference_name or Path(pdf_filename).stem, broker=result.broker or "",
        hotel=result.hotel or "", city=result.city or "", timezone=valid_timezone(result.timezone),
        schedule_for=result.schedule_for or "", pdf_filename=pdf_filename, pdf_path=pdf_path, extractor=extractor,
    )
    session.add(conference)
    session.flush()
    drafts = build_meetings(result, _roster(session), defaults, default_minutes)
    for draft, source in zip(drafts, result.meetings, strict=True):
        insert_draft(session, conference.id, draft, source)
    session.commit()
    session.refresh(conference)
    return conference


def insert_draft(session: Session, conference_id: int, draft: DraftMeeting, source: ExtractedMeeting) -> Meeting:
    """Add one meeting built from a broker row, with that row as its baseline. Flushes, doesn't commit."""
    meeting = Meeting(
        conference_id=conference_id, date=draft.date, start_time=draft.start_time, end_time=draft.end_time,
        end_assumed=draft.end_assumed, room=draft.room, company=draft.company, ticker=draft.ticker,
        format=draft.format, company_attendees=draft.company_attendees,
        raw_attendee_names=draft.raw_attendee_names, notes=draft.notes, source_page=draft.source_page,
        source_json=source.model_dump_json(),
    )
    session.add(meeting)
    session.flush()
    for analyst_id, kind in draft.attendees:
        session.add(MeetingAttendee(meeting_id=meeting.id, analyst_id=analyst_id, match=kind))
    return meeting


def update_conference(session: Session, conference_id: int, data: ConferenceUpdate) -> Conference:
    conference = get_conference(session, conference_id)
    fields = data.model_fields_set
    for name in ("name", "broker", "hotel", "city"):
        if name in fields and getattr(data, name) is not None:
            setattr(conference, name, getattr(data, name).strip())
    if "timezone" in fields:
        if data.timezone is None or not data.timezone.strip():
            conference.timezone = None
        elif valid_timezone(data.timezone.strip()) is None:
            raise InvalidInput(f"Unknown timezone {data.timezone!r}. Use an IANA name like America/New_York.")
        else:
            conference.timezone = data.timezone.strip()
    session.add(conference)
    session.commit()
    _enforce_status(session, conference)
    session.refresh(conference)
    return conference


def delete_conference(session: Session, conference_id: int) -> str:
    conference = get_conference(session, conference_id)
    meeting_ids = [m.id for m in _meetings(session, conference_id)]
    if meeting_ids:
        session.execute(delete(SyncRecord).where(SyncRecord.meeting_id.in_(meeting_ids)))
        session.execute(delete(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meeting_ids)))
        session.execute(delete(Meeting).where(Meeting.id.in_(meeting_ids)))
    session.execute(delete(Revision).where(Revision.conference_id == conference_id))
    pdf_path = conference.pdf_path
    session.delete(conference)
    session.commit()
    return pdf_path


# ---------- meetings ----------

def get_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise NotFound("Meeting not found.")
    return meeting


def _set_attendees(session: Session, meeting: Meeting, analyst_ids: Sequence[int]) -> None:
    """Only colleagues being added must be active: the picker sends the full list, so someone deactivated
    while already on the meeting stays on it as they are."""
    existing = {row.analyst_id: row for row in
                session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting.id)).all()}
    wanted = list(dict.fromkeys(analyst_ids))
    _active_ids(session, [aid for aid in wanted if aid not in existing])
    for aid, row in existing.items():
        if aid not in wanted:
            session.delete(row)
    for aid in wanted:
        if aid not in existing:
            session.add(MeetingAttendee(meeting_id=meeting.id, analyst_id=aid, match="manual"))


def add_meeting(session: Session, conference_id: int, data: MeetingCreate, default_minutes: int) -> Meeting:
    get_conference(session, conference_id)
    start, end = _strict_time(data.start), _strict_time(data.end)
    end_assumed = False
    if start and not end:
        end, end_assumed = add_minutes(start, default_minutes), True
    meeting = Meeting(conference_id=conference_id, date=_strict_date(data.date), start_time=start, end_time=end,
                      end_assumed=end_assumed, room=data.room.strip(), company=data.company.strip(),
                      ticker=(data.ticker or "").strip() or None, format=data.format, notes=data.notes.strip())
    session.add(meeting)
    session.flush()
    _set_attendees(session, meeting, data.attendee_ids)
    session.commit()
    session.refresh(meeting)
    return meeting


def update_meeting(session: Session, meeting_id: int, data: MeetingUpdate, default_minutes: int) -> Meeting:
    meeting = get_meeting(session, meeting_id)
    if meeting.status == "cancelled":
        raise Conflict("This meeting was cancelled and can't be edited.")
    fields = data.model_fields_set
    if "date" in fields:
        meeting.date = _strict_date(data.date)
    if "start" in fields:
        meeting.start_time = _strict_time(data.start)
    if "end" in fields:
        meeting.end_time = _strict_time(data.end)
        meeting.end_assumed = False
    elif "start" in fields and meeting.end_assumed and meeting.start_time:
        meeting.end_time = add_minutes(meeting.start_time, default_minutes)
    if "company" in fields:
        if not (data.company or "").strip():
            raise InvalidInput("Company can't be empty.")
        meeting.company = data.company.strip()
    if "room" in fields:
        meeting.room = (data.room or "").strip()
    if "ticker" in fields:
        meeting.ticker = (data.ticker or "").strip() or None
    if "format" in fields and data.format:
        meeting.format = data.format
    if "notes" in fields:
        meeting.notes = (data.notes or "").strip()
    if "company_attendees" in fields:
        meeting.company_attendees = [s.strip() for s in (data.company_attendees or []) if s.strip()]
    if "ignored_names" in fields:
        meeting.ignored_names = [s.strip() for s in (data.ignored_names or []) if s.strip()]
    if "attendee_ids" in fields:
        _set_attendees(session, meeting, data.attendee_ids or [])
    meeting.updated_at = utcnow()
    session.add(meeting)
    session.commit()
    _enforce_status(session, get_conference(session, meeting.conference_id))
    session.refresh(meeting)
    return meeting


def confirm_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = get_meeting(session, meeting_id)
    if meeting.status == "cancelled":
        raise Conflict("This meeting was cancelled.")
    conference = get_conference(session, meeting.conference_id)
    flags, _ = _flags(session, conference, _meetings(session, conference.id))
    if has_block(flags[meeting.id]):
        raise Conflict("Fix the problems on this meeting before verifying it.",
                       [f for f in flags[meeting.id] if f.severity == "block"])
    meeting.status = "confirmed"
    meeting.updated_at = utcnow()
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def unconfirm_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = get_meeting(session, meeting_id)
    if meeting.status == "cancelled":
        raise Conflict("This meeting was cancelled.")
    meeting.status = "draft"
    meeting.updated_at = utcnow()
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def confirm_ready(session: Session, conference_id: int, meeting_ids: Sequence[int] | None = None) -> int:
    conference = get_conference(session, conference_id)
    meetings = _meetings(session, conference_id)
    flags, _ = _flags(session, conference, meetings)
    wanted = set(meeting_ids) if meeting_ids is not None else None
    count = 0
    for m in meetings:
        if m.status == "draft" and not has_block(flags[m.id]) and (wanted is None or m.id in wanted):
            m.status = "confirmed"
            m.updated_at = utcnow()
            session.add(m)
            count += 1
    session.commit()
    return count


def delete_meeting(session: Session, meeting_id: int) -> str:
    meeting = get_meeting(session, meeting_id)
    records = session.exec(select(SyncRecord).where(SyncRecord.meeting_id == meeting_id)).all()
    if any(r.external_id and r.state != "cancelled" for r in records):
        meeting.status = "cancelled"
        meeting.updated_at = utcnow()
        session.add(meeting)
        session.commit()
        return "cancelled"
    session.execute(delete(SyncRecord).where(SyncRecord.meeting_id == meeting_id))
    session.execute(delete(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting_id))
    session.delete(meeting)
    session.commit()
    return "deleted"


# ---------- sync ----------

def plan_conference(session: Session, conference_id: int, sink_name: str) -> list[SyncAction]:
    conference = get_conference(session, conference_id)
    meetings = _meetings(session, conference_id)
    flags, att = _flags(session, conference, meetings)
    eligible = [m for m in meetings if not (m.status == "confirmed" and has_block(flags[m.id]))]
    attendee_ids = {mid: [aid for aid, _ in rows] for mid, rows in att.items()}
    records = _records(session, [m.id for m in meetings], sink_name)
    return plan_sync(conference, eligible, attendee_ids, _analysts(session), records)


def _record_outcome(session: Session, sink_name: str, outcome: SyncOutcome) -> None:
    a = outcome.action
    rec = session.exec(select(SyncRecord).where(SyncRecord.meeting_id == a.meeting_id,
                                                SyncRecord.analyst_id == a.analyst_id,
                                                SyncRecord.sink == sink_name)).first()
    if rec is None:
        rec = SyncRecord(meeting_id=a.meeting_id, analyst_id=a.analyst_id, sink=sink_name)
    if outcome.ok:
        rec.external_id = outcome.external_id or rec.external_id
        rec.sequence = a.sequence
        rec.last_error = None
        if a.kind == "cancel":
            rec.state = "cancelled"
        else:
            rec.state = "active"
            rec.content_hash = a.content.content_hash()
            rec.content_json = a.content.to_json()
    else:
        rec.last_error = outcome.error or "Unknown error"
        if not (a.kind == "create" and rec.state == "cancelled"):
            rec.state = "failed"
    rec.updated_at = utcnow()
    session.add(rec)


def send_conference(session: Session, conference_id: int, sink) -> list[SyncOutcome]:
    conference = get_conference(session, conference_id)
    actions = plan_conference(session, conference_id, sink.name)
    outcomes = sink.apply(conference, actions) if actions else []
    for outcome in outcomes:
        _record_outcome(session, sink.name, outcome)
    session.commit()
    return outcomes


def ics_records_for(session: Session, conference_id: int, analyst_id: int) -> list[SyncRecord]:
    meeting_ids = [m.id for m in _meetings(session, conference_id)]
    return [r for r in _records(session, meeting_ids, "ics") if r.analyst_id == analyst_id]


def send_result(session: Session, conference_id: int, sink_name: str, items, dry_run: bool) -> SendResult:
    analysts = _analysts(session)
    rows: list[SyncActionOut] = []
    summary: dict[int, AnalystSendSummary] = {}
    for item in items:
        action, ok, error = (item, None, None) if isinstance(item, SyncAction) else (item.action, item.ok, item.error)
        rows.append(SyncActionOut(kind=action.kind, meeting_id=action.meeting_id, analyst_id=action.analyst_id,
                                  analyst_name=action.analyst_name,
                                  subject=action.content.subject if action.content else None, ok=ok, error=error))
        s = summary.setdefault(action.analyst_id, AnalystSendSummary(analyst_id=action.analyst_id,
                                                                     name=analysts[action.analyst_id].name))
        setattr(s, action.kind, getattr(s, action.kind) + 1)
        if ok is False:
            s.failed += 1
    result = SendResult(sink=sink_name, dry_run=dry_run, actions=rows,
                        by_analyst=sorted(summary.values(), key=lambda s: s.name),
                        ok_count=sum(1 for r in rows if r.ok), failed_count=sum(1 for r in rows if r.ok is False))
    if sink_name == "ics" and not dry_run:
        for s in result.by_analyst:
            s.download_url = f"/api/conferences/{conference_id}/ics/{s.analyst_id}"
        result.zip_url = f"/api/conferences/{conference_id}/ics.zip"
    return result


# ---------- read models ----------

def _sync_state(conference, meeting, analyst_id, attendee_ids, analysts, rec) -> tuple[str, str | None]:
    if rec is None:
        return "not_sent", None
    if rec.last_error:
        return "failed", rec.last_error
    if rec.external_id is None:
        return "not_sent", None
    if rec.state == "cancelled":
        return ("not_sent", None) if meeting.status == "confirmed" else ("cancelled", None)
    if meeting.status == "confirmed":
        others = [analysts[x].name for x in attendee_ids if x != analyst_id]
        try:
            current = build_event(conference, meeting, others).content_hash()
        except ValueError:
            return "changed", None
        if current != rec.content_hash:
            return "changed", None
    return "sent", None


def _unmatched(meeting: Meeting, attendee_ids: set[int], roster: list[RosterEntry]) -> list[str]:
    ignored = {normalize_name(n) for n in meeting.ignored_names}
    out = []
    for raw in meeting.raw_attendee_names:
        if normalize_name(raw) in ignored:
            continue
        match = match_name(raw, roster)
        if match.analyst_id is None or match.analyst_id not in attendee_ids:
            out.append(raw)
    return out


def conference_detail(session: Session, conference_id: int, sink_name: str, skipped_items: int = 0) -> ConferenceDetail:
    from mcs import revision_service  # imported here: revision_service builds on this module

    conference = get_conference(session, conference_id)
    meetings = sorted(_meetings(session, conference_id), key=_sort_key)
    flags, att = _flags(session, conference, meetings)
    analysts = _analysts(session)
    roster = roster_entries(analysts.values())
    records = _records(session, [m.id for m in meetings], sink_name)
    rec_by = {(r.meeting_id, r.analyst_id): r for r in records}

    out: list[MeetingOut] = []
    for m in meetings:
        ids = [aid for aid, _ in att[m.id]]
        attendees = []
        for aid, kind in att[m.id]:
            sync, err = _sync_state(conference, m, aid, ids, analysts, rec_by.get((m.id, aid)))
            a = analysts[aid]
            attendees.append(AttendeeOut(analyst_id=aid, name=a.name, email=a.email, match=kind, sync=sync, sync_error=err))
        removed = [AttendeeOut(analyst_id=r.analyst_id, name=analysts[r.analyst_id].name,
                               email=analysts[r.analyst_id].email, match="removed",
                               sync="failed" if r.state == "failed" else "sent", sync_error=r.last_error)
                   for r in records if r.meeting_id == m.id and r.analyst_id not in ids
                   and r.external_id and r.state != "cancelled"]
        meeting_flags = flags[m.id]
        if m.status == "cancelled":
            state = "cancelled"
        elif m.status == "draft":
            state = "needs_attention" if has_block(meeting_flags) else "ready"
        else:
            all_sent = bool(attendees) and all(a.sync == "sent" for a in attendees) and not removed
            state = "sent" if all_sent else "verified"
        out.append(MeetingOut(
            id=m.id, conference_id=m.conference_id, date=m.date.isoformat() if m.date else None,
            start=_hhmm(m.start_time), end=_hhmm(m.end_time), end_assumed=m.end_assumed, room=m.room,
            company=m.company, ticker=m.ticker, format=m.format, company_attendees=list(m.company_attendees),
            raw_attendee_names=list(m.raw_attendee_names), ignored_names=list(m.ignored_names),
            unmatched_names=_unmatched(m, set(ids), roster), notes=m.notes, source_page=m.source_page,
            status=m.status, review_state=state, attendees=attendees, removed=removed,
            flags=[FlagOut(code=f.code, severity=f.severity, message=f.message) for f in meeting_flags],
        ))

    live = [o for o in out if o.review_state != "cancelled"]
    counts = Counts(
        total=len(live),
        needs_attention=sum(o.review_state == "needs_attention" for o in live),
        ready=sum(o.review_state == "ready" for o in live),
        verified=sum(o.review_state == "verified" for o in live),
        sent=sum(o.review_state == "sent" for o in live),
        cancelled=len(out) - len(live),
        warnings=sum(any(f.severity == "warn" for f in o.flags) for o in live),
        changed=sum(any(a.sync == "changed" for a in o.attendees) for o in live),
        failed=sum(any(a.sync == "failed" for a in o.attendees + o.removed) for o in out),
        pending_actions=len(plan_conference(session, conference_id, sink_name)),
    )
    dates = [m.date for m in meetings if m.date]
    pending = revision_service.pending_revision(session, conference_id)
    return ConferenceDetail(
        id=conference.id, name=conference.name, broker=conference.broker, hotel=conference.hotel,
        city=conference.city, timezone=conference.timezone, created_at=conference.created_at,
        first_date=min(dates).isoformat() if dates else None, last_date=max(dates).isoformat() if dates else None,
        counts=counts, schedule_for=conference.schedule_for, pdf_filename=conference.pdf_filename,
        extractor=conference.extractor, meetings=out, skipped_items=skipped_items,
        pending_revision=revision_service.revision_out(session, pending) if pending else None,
        revision_number=1 + revision_service.applied_count(session, conference_id),
    )


def list_conference_summaries(session: Session, sink_name: str) -> list[ConferenceSummary]:
    conferences = session.exec(select(Conference).order_by(Conference.created_at.desc(), Conference.id.desc())).all()
    summaries = []
    for c in conferences:
        d = conference_detail(session, c.id, sink_name)
        summaries.append(ConferenceSummary(**d.model_dump(include=set(ConferenceSummary.model_fields))))
    return summaries
