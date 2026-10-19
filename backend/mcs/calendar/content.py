"""What a calendar event says: shared by every sink."""
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Sequence
from zoneinfo import ZoneInfo

from mcs.models import Conference, Meeting

FORMAT_LABELS = {"one_on_one": "1x1", "group": "Group", "meal": "Meal", "other": "Meeting"}
EVENT_CATEGORY = "Conference"  # the Outlook category every event carries; colleagues colour it green once


@dataclass(frozen=True)
class EventContent:
    subject: str
    location: str
    body: str
    start_utc: dt.datetime
    end_utc: dt.datetime
    categories: tuple[str, ...] = ()

    def _as_dict(self) -> dict:
        d = {"subject": self.subject, "location": self.location, "body": self.body,
             "start": self.start_utc.isoformat(), "end": self.end_utc.isoformat()}
        if self.categories:  # left out when empty, so content saved before categories keeps its hash
            d["categories"] = list(self.categories)
        return d

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self._as_dict(), sort_keys=True).encode()).hexdigest()

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "EventContent":
        d = json.loads(s)
        return cls(d["subject"], d["location"], d["body"],
                   dt.datetime.fromisoformat(d["start"]), dt.datetime.fromisoformat(d["end"]),
                   tuple(d.get("categories", ())))


def meeting_timezone(conference: Conference, meeting: Meeting) -> str | None:
    """The zone a meeting's times are read in: its own, else the conference's."""
    return meeting.timezone or conference.timezone


def build_event(conference: Conference, meeting: Meeting, other_attendee_names: Sequence[str]) -> EventContent:
    zone = meeting_timezone(conference, meeting)
    if not (zone and meeting.date and meeting.start_time and meeting.end_time):
        raise ValueError("The meeting needs a timezone, date, start and end before it can be sent.")
    tz = ZoneInfo(zone)
    start = dt.datetime.combine(meeting.date, meeting.start_time, tzinfo=tz).astimezone(dt.timezone.utc)
    end = dt.datetime.combine(meeting.date, meeting.end_time, tzinfo=tz).astimezone(dt.timezone.utc)
    label = FORMAT_LABELS.get(meeting.format, "Meeting")
    subject = f"{meeting.ticker} – {meeting.company} ({label})" if meeting.ticker else f"{meeting.company} ({label})"
    location = " – ".join(p for p in (conference.hotel, meeting.room) if p)
    lines = []
    if conference.name:
        lines.append(conference.name)
    if meeting.company_attendees:
        lines.append("Company: " + ", ".join(meeting.company_attendees))
    if other_attendee_names:
        lines.append("Also attending: " + ", ".join(other_attendee_names))
    if meeting.notes:
        lines.append(meeting.notes)
    if conference.pdf_filename:
        source = f"Source: {conference.pdf_filename}"
        lines.append(f"{source}, page {meeting.source_page}" if meeting.source_page else source)
    return EventContent(subject, location, "\n".join(lines), start, end, (EVENT_CATEGORY,))
