import datetime as dt

import pytest

from mcs.calendar.content import EventContent, build_event
from mcs.models import Conference, Meeting

UTC = dt.timezone.utc


def conf(**kw):
    base = dict(id=1, name="Industrials Conference 2026", hotel="The Example Grand Hotel",
                timezone="America/New_York", pdf_filename="broker_a_grid.pdf")
    return Conference(**{**base, **kw})


def meeting(**kw):
    base = dict(id=1, conference_id=1, date=dt.date(2026, 11, 10), start_time=dt.time(8, 0), end_time=dt.time(8, 45),
                room="Salon 4", company="Northwind Robotics", ticker="NWRB", format="one_on_one",
                company_attendees=["Dana Shore, CFO"], notes="", source_page=1)
    return Meeting(**{**base, **kw})


def test_subject_location_body():
    e = build_event(conf(), meeting(), ["Jordan Lee"])
    assert e.subject == "NWRB – Northwind Robotics (1x1)"
    assert e.location == "The Example Grand Hotel – Salon 4"
    assert e.body == ("Industrials Conference 2026\nCompany: Dana Shore, CFO\nAlso attending: Jordan Lee\n"
                      "Source: broker_a_grid.pdf, page 1")


@pytest.mark.parametrize("fmt,label", [("group", "Group"), ("meal", "Meal"), ("other", "Meeting")])
def test_labels_and_no_ticker(fmt, label):
    assert build_event(conf(), meeting(ticker=None, format=fmt), []).subject == f"Northwind Robotics ({label})"


def test_location_and_body_drop_empty_parts():
    e = build_event(conf(hotel="", pdf_filename=""), meeting(room="Suite 1201", company_attendees=[], notes="Bring model"), [])
    assert e.location == "Suite 1201"
    assert e.body == "Industrials Conference 2026\nBring model"
    assert build_event(conf(), meeting(room=""), []).location == "The Example Grand Hotel"
    assert build_event(conf(), meeting(source_page=None), []).body.endswith("Source: broker_a_grid.pdf")


@pytest.mark.parametrize("tz,date,time,expected", [
    ("America/New_York", dt.date(2026, 11, 10), dt.time(8, 0), dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC)),
    ("America/New_York", dt.date(2026, 7, 1), dt.time(8, 0), dt.datetime(2026, 7, 1, 12, 0, tzinfo=UTC)),
    ("Europe/London", dt.date(2026, 11, 17), dt.time(9, 30), dt.datetime(2026, 11, 17, 9, 30, tzinfo=UTC)),
    ("America/Los_Angeles", dt.date(2026, 12, 2), dt.time(8, 30), dt.datetime(2026, 12, 2, 16, 30, tzinfo=UTC)),
])
def test_utc_conversion(tz, date, time, expected):
    e = build_event(conf(timezone=tz), meeting(date=date, start_time=time, end_time=dt.time(23, 0)), [])
    assert e.start_utc == expected
    assert e.start_utc.tzinfo is not None


@pytest.mark.parametrize("bad", [dict(timezone=None)])
def test_missing_timezone_raises(bad):
    with pytest.raises(ValueError):
        build_event(conf(**bad), meeting(), [])


@pytest.mark.parametrize("field", ["date", "start_time", "end_time"])
def test_missing_meeting_time_raises(field):
    with pytest.raises(ValueError):
        build_event(conf(), meeting(**{field: None}), [])


def test_hash_and_json_roundtrip():
    a = build_event(conf(), meeting(), ["Jordan Lee"])
    b = build_event(conf(), meeting(), ["Jordan Lee"])
    assert a.content_hash() == b.content_hash()
    assert build_event(conf(), meeting(room="Salon 2"), ["Jordan Lee"]).content_hash() != a.content_hash()
    assert EventContent.from_json(a.to_json()) == a
