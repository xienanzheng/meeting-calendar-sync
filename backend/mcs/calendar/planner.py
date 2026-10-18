"""Decide which calendar writes a send needs. Pure: no I/O."""
from dataclasses import dataclass
from typing import Mapping, Sequence

from mcs.calendar.content import EventContent, build_event
from mcs.models import Analyst, Conference, Meeting, SyncRecord


@dataclass(frozen=True)
class SyncAction:
    kind: str  # create | update | cancel
    meeting_id: int
    analyst_id: int
    analyst_email: str
    analyst_name: str
    content: EventContent | None
    sequence: int
    external_id: str | None


@dataclass(frozen=True)
class SyncOutcome:
    action: SyncAction
    ok: bool
    external_id: str | None = None
    error: str | None = None


def plan_sync(conference: Conference, meetings: Sequence[Meeting], attendees: Mapping[int, Sequence[int]],
              analysts: Mapping[int, Analyst], records: Sequence[SyncRecord]) -> list[SyncAction]:
    by_key = {(r.meeting_id, r.analyst_id): r for r in records}
    actions: list[SyncAction] = []
    current: set[tuple[int, int]] = set()

    for meeting in sorted(meetings, key=lambda x: x.id):
        if meeting.status != "confirmed":
            continue
        ids = list(attendees.get(meeting.id, []))
        for analyst_id in ids:
            current.add((meeting.id, analyst_id))
            analyst = analysts[analyst_id]
            others = [analysts[x].name for x in ids if x != analyst_id]
            content = build_event(conference, meeting, others)
            rec = by_key.get((meeting.id, analyst_id))
            if rec is None or rec.external_id is None or rec.state == "cancelled":
                sequence = 0 if rec is None or rec.external_id is None else rec.sequence + 1
                actions.append(SyncAction("create", meeting.id, analyst_id, analyst.email, analyst.name, content,
                                          sequence, rec.external_id if rec else None))
            elif rec.state == "failed" or rec.content_hash != content.content_hash():
                actions.append(SyncAction("update", meeting.id, analyst_id, analyst.email, analyst.name, content,
                                          rec.sequence + 1, rec.external_id))

    meetings_by_id = {x.id: x for x in meetings}
    for rec in sorted(records, key=lambda r: (r.meeting_id, r.analyst_id)):
        key = (rec.meeting_id, rec.analyst_id)
        if key in current or rec.external_id is None or rec.state == "cancelled":
            continue
        meeting = meetings_by_id.get(rec.meeting_id)
        if meeting is None:
            continue
        removed = meeting.status == "confirmed" and rec.analyst_id not in attendees.get(meeting.id, [])
        if meeting.status == "cancelled" or removed:
            analyst = analysts[rec.analyst_id]
            content = EventContent.from_json(rec.content_json) if rec.content_json else None
            actions.append(SyncAction("cancel", meeting.id, rec.analyst_id, analyst.email, analyst.name, content,
                                      rec.sequence + 1, rec.external_id))
    return actions
