import datetime as dt
import json

import pytest

from mcs.config import REPO_ROOT
from mcs.extraction.schema import ExtractedMeeting, ExtractionResult, parse_extraction
from mcs.normalize import add_minutes, build_meetings, parse_date, parse_time, valid_timezone
from mcs.roster import RosterEntry

ROSTER = [RosterEntry(1, "Avery Kim"), RosterEntry(2, "Sam Patel", ("Samir Patel",)), RosterEntry(3, "Jordan Lee"),
          RosterEntry(4, "Riley Chen"), RosterEntry(5, "Morgan Diaz"), RosterEntry(6, "Taylor Brooks", ("Tay Brooks",)),
          RosterEntry(7, "Former Analyst", active=False)]


def sample(name):
    return parse_extraction(json.loads((REPO_ROOT / "samples" / f"{name}.expected.json").read_text()))


@pytest.mark.parametrize("raw,expected", [
    ("08:00", dt.time(8, 0)), ("8:00", dt.time(8, 0)), ("08:00:00", dt.time(8, 0)), ("23:59", dt.time(23, 59)),
    ("8:00 AM", dt.time(8, 0)), ("8am", dt.time(8, 0)), ("8:00am", dt.time(8, 0)), ("8:00 a.m.", dt.time(8, 0)),
    ("1:30 PM", dt.time(13, 30)), ("12:00pm", dt.time(12, 0)), ("12pm", dt.time(12, 0)), ("12:00am", dt.time(0, 0)),
    ("12:30 AM", dt.time(0, 30)), ("TBD", None), ("", None), (None, None), ("25:00", None), ("13:00 PM", None),
    ("noon", None),
])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-11-10", dt.date(2026, 11, 10)), ("2026-11-10T00:00:00", dt.date(2026, 11, 10)),
    (" 2026-11-10 ", dt.date(2026, 11, 10)), ("Nov 10", None), ("", None), (None, None), ("2026-13-01", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_valid_timezone():
    assert valid_timezone("America/New_York") == "America/New_York"
    assert valid_timezone("Eastern") is None
    assert valid_timezone("") is None
    assert valid_timezone(None) is None
    assert valid_timezone("../etc/passwd") is None


def test_add_minutes():
    assert add_minutes(dt.time(8, 0), 45) == dt.time(8, 45)
    assert add_minutes(dt.time(23, 30), 45) == dt.time(0, 15)


def test_sample_a():
    drafts = build_meetings(sample("broker_a_grid"), ROSTER)
    assert len(drafts) == 12
    first = drafts[0]
    assert (first.date, first.start_time, first.end_time, first.end_assumed) == (
        dt.date(2026, 11, 10), dt.time(8, 0), dt.time(8, 45), False)
    assert first.attendees == [(1, "exact"), (3, "exact")]
    assert first.company_attendees == ["Dana Shore, CFO"]
    assert first.source_page == 1
    tidewater = next(d for d in drafts if d.company == "Tidewater Pumps")
    assert tidewater.attendees == []
    assert tidewater.raw_attendee_names == ["Chris Wong"]
    assert next(d for d in drafts if d.company == "Keystone Valve Corp").format == "meal"


def test_sample_b_match_kinds():
    drafts = {d.company: d for d in build_meetings(sample("broker_b_by_company"), ROSTER)}
    assert drafts["Vantage Cloud Software"].attendees == [(1, "initial")]
    assert drafts["Pixelmint Studios"].attendees == [(1, "initial"), (4, "fuzzy")]
    assert drafts["Brightpath Payments"].attendees == [(5, "initial"), (6, "alias")]
    assert drafts["Nimbus Health Tech"].attendees == [(2, "alias")]


def test_sample_c_uses_schedule_for_and_assumes_end():
    drafts = build_meetings(sample("broker_c_itinerary"), ROSTER, default_minutes=30)
    assert len(drafts) == 6
    assert all(d.attendees == [(2, "exact")] for d in drafts)
    assert all(d.end_assumed for d in drafts)
    assert drafts[1].start_time == dt.time(9, 30) and drafts[1].end_time == dt.time(10, 0)
    assert all(d.raw_attendee_names == [] for d in drafts)


def _one(**kw):
    return ExtractionResult(meetings=[ExtractedMeeting(company="Cobalt Freight Lines", **kw)])


def test_default_attendees_added_once_and_inactive_ignored():
    drafts = build_meetings(_one(firm_attendees=["Avery Kim"]), ROSTER, default_attendee_ids=[3, 1, 7])
    assert drafts[0].attendees == [(1, "exact"), (3, "default")]


def test_two_raw_names_for_same_colleague_give_one_attendee():
    drafts = build_meetings(_one(firm_attendees=["Avery Kim", "A. Kim"]), ROSTER)
    assert drafts[0].attendees == [(1, "exact")]
    assert drafts[0].raw_attendee_names == ["Avery Kim", "A. Kim"]


def test_blank_fields_are_cleaned():
    d = build_meetings(_one(room="  ", ticker=" ", notes=None, start="TBD"), ROSTER)[0]
    assert (d.room, d.ticker, d.notes) == ("", None, "")
    assert (d.start_time, d.end_time, d.end_assumed) == (None, None, False)
