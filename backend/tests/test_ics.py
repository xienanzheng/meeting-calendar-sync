import datetime as dt
import io
import zipfile

from icalendar import Calendar

from mcs.calendar.content import EventContent
from mcs.calendar.ics import IcsSink, analyst_slug, ics_uid, render_ics, zip_files
from mcs.calendar.planner import SyncAction
from mcs.models import Conference, SyncRecord

UTC = dt.timezone.utc


def content(subject="NWRB – Northwind Robotics (1x1)", location="The Example Grand Hotel – Salon 4", hour=13):
    return EventContent(subject, location, "Industrials Conference 2026\nSource: a.pdf, page 1",
                        dt.datetime(2026, 11, 10, hour, 0, tzinfo=UTC), dt.datetime(2026, 11, 10, hour, 45, tzinfo=UTC))


def test_uid_format():
    assert ics_uid(10, 3) == "mcs-10-3@meeting-calendar-sync"


def test_apply_assigns_uids_and_keeps_existing():
    actions = [SyncAction("create", 10, 1, "a@example.com", "A", content(), 0, None),
               SyncAction("update", 11, 1, "a@example.com", "A", content(), 1, "kept-uid")]
    outcomes = IcsSink().apply(Conference(id=1), actions)
    assert [(o.ok, o.external_id) for o in outcomes] == [(True, "mcs-10-1@meeting-calendar-sync"), (True, "kept-uid")]
    assert IcsSink.name == "ics"


def test_render_round_trip():
    records = [
        SyncRecord(meeting_id=11, analyst_id=1, sink="ics", external_id="uid-b", content_json=content(hour=15).to_json(),
                   sequence=2, state="cancelled"),
        SyncRecord(meeting_id=10, analyst_id=1, sink="ics", external_id="uid-a", content_json=content().to_json(),
                   sequence=0, state="active"),
        SyncRecord(meeting_id=12, analyst_id=1, sink="ics", external_id=None, content_json="", state="failed"),
    ]
    cal = Calendar.from_ical(render_ics(records, now=dt.datetime(2026, 10, 18, tzinfo=UTC)))
    assert str(cal["METHOD"]) == "PUBLISH"
    events = cal.walk("VEVENT")
    assert [str(e["UID"]) for e in events] == ["uid-a", "uid-b"]  # sorted by start
    first, second = events
    assert str(first["SUMMARY"]) == "NWRB – Northwind Robotics (1x1)"
    assert first["DTSTART"].dt == dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC)
    assert int(first["SEQUENCE"]) == 0 and str(first["STATUS"]) == "CONFIRMED"
    assert int(second["SEQUENCE"]) == 2 and str(second["STATUS"]) == "CANCELLED"
    assert "Source: a.pdf, page 1" in str(first["DESCRIPTION"])


def test_location_omitted_when_empty():
    rec = SyncRecord(meeting_id=1, analyst_id=1, sink="ics", external_id="u", content_json=content(location="").to_json())
    event = Calendar.from_ical(render_ics([rec])).walk("VEVENT")[0]
    assert "LOCATION" not in event


def test_slug_and_zip():
    assert analyst_slug("Avery Kim") == "avery-kim"
    assert analyst_slug("José Núñez") == "jose-nunez"
    assert analyst_slug("!!!") == "colleague"
    data = zip_files({"avery-kim.ics": b"A", "jordan-lee.ics": b"B"})
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sorted(z.namelist()) == ["avery-kim.ics", "jordan-lee.ics"]
        assert z.read("jordan-lee.ics") == b"B"
