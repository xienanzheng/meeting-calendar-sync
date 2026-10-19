"""ICS sink: 'sending' assigns stable UIDs; files are rendered on demand from SyncRecords."""
import datetime as dt
import io
import re
import unicodedata
import zipfile
from typing import Mapping, Sequence

from icalendar import Calendar, Event

from mcs.calendar.content import EventContent
from mcs.calendar.planner import SyncAction, SyncOutcome
from mcs.models import SyncRecord, utcnow

PRODID = "-//Meeting Calendar Sync//EN"


def ics_uid(meeting_id: int, analyst_id: int) -> str:
    return f"mcs-{meeting_id}-{analyst_id}@meeting-calendar-sync"


class IcsSink:
    name = "ics"

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]:
        return [SyncOutcome(a, ok=True, external_id=a.external_id or ics_uid(a.meeting_id, a.analyst_id))
                for a in actions]


def render_ics(records: Sequence[SyncRecord], now: dt.datetime | None = None) -> bytes:
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    stamp = now or utcnow()
    usable = [(EventContent.from_json(r.content_json), r) for r in records if r.external_id and r.content_json]
    for content, rec in sorted(usable, key=lambda pair: (pair[0].start_utc, pair[1].external_id)):
        event = Event()
        event.add("uid", rec.external_id)
        event.add("summary", content.subject)
        if content.location:
            event.add("location", content.location)
        event.add("description", content.body)
        event.add("dtstart", content.start_utc)
        event.add("dtend", content.end_utc)
        event.add("dtstamp", stamp)
        event.add("sequence", rec.sequence)
        event.add("status", "CANCELLED" if rec.state == "cancelled" else "CONFIRMED")
        if content.categories:
            event.add("categories", list(content.categories))
        cal.add_component(event)
    return cal.to_ical()


def analyst_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "colleague"


def zip_files(files: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()
