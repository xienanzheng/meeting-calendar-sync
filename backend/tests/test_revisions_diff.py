import json

from mcs.config import REPO_ROOT
from mcs.extraction.schema import ExtractedMeeting, parse_extraction
from mcs.revisions import diff_revision, same_value


def sample(name):
    return parse_extraction(json.loads((REPO_ROOT / "samples" / f"{name}.expected.json").read_text()))


A = sample("broker_a_grid")
V2 = sample("broker_a_grid_v2")
BASE = [(i, m) for i, m in enumerate(A.meetings, start=1)]


def row(**kw):
    base = dict(company="Northwind Robotics", date="2026-11-10", start="08:00", end="08:45", room="Salon 4",
                firm_attendees=["Avery Kim"])
    return ExtractedMeeting(**{**base, **kw})


def test_identical_schedule_has_no_changes():
    d = diff_revision(BASE, A.meetings)
    assert d.changes == ()
    assert len(d.unchanged) == 12


def test_v2_sample_has_exactly_five_changes():
    d = diff_revision(BASE, V2.meetings)
    assert [(c.id, c.kind, c.company) for c in d.changes] == [
        ("c1", "changed", "Cobalt Freight Lines"),
        ("c2", "changed", "Halcyon Aerostructures"),
        ("c3", "changed", "Meridian Rail Holdings"),
        ("c4", "removed", "Tidewater Pumps"),
        ("c5", "added", "Atlas Rail Systems"),
    ]
    assert [c.summary for c in d.changes] == [
        "Cobalt Freight Lines: time 10:00–10:45 → 14:30–15:15",
        "Halcyon Aerostructures: colleagues +Jordan Lee",
        "Meridian Rail Holdings: room TBD → Suite 1505",
        "Dropped: Tidewater Pumps on 2026-11-11 at 10:00",
        "New: Atlas Rail Systems on 2026-11-11 at 16:00",
    ]
    assert len(d.unchanged) == 8
    cobalt, _, _, tidewater, atlas = d.changes
    assert cobalt.meeting_id == 3 and {f.field for f in cobalt.fields} == {"start", "end"}
    assert cobalt.new.start == "14:30"
    assert tidewater.meeting_id == 9 and tidewater.new is None
    assert atlas.meeting_id is None and atlas.new.ticker == "ATRL"


def test_moved_to_another_day_is_one_change():
    [c] = diff_revision([(1, row())], [row(date="2026-11-11")]).changes
    assert (c.kind, c.meeting_id) == ("changed", 1)
    assert c.summary == "Northwind Robotics: date 2026-11-10 → 2026-11-11"


def test_slightly_renamed_company_matches_on_the_same_day():
    [c] = diff_revision([(1, row())], [row(company="Northwind Robotic")]).changes
    assert c.kind == "changed"
    assert c.summary == "Northwind Robotic: name Northwind Robotics → Northwind Robotic"


def test_names_case_and_punctuation_are_normalized():
    d = diff_revision([(1, row(firm_attendees=["A. Kim"]))], [row(firm_attendees=["a kim"], room="SALON 4")])
    assert d.changes == () and [mid for mid, _ in d.unchanged] == [1]


def test_ambiguous_duplicates_are_conservative():
    old = [(1, row()), (2, row(start="09:00", end="09:45"))]
    d = diff_revision(old, [row(start="10:00", end="10:45")])
    assert sorted(c.kind for c in d.changes) == ["added", "removed", "removed"]


def test_missing_end_reads_as_question_mark():
    [c] = diff_revision([(1, row(end=None))], [row()]).changes
    assert c.summary == "Northwind Robotics: time 08:00–? → 08:00–08:45"


def test_colleague_removed_and_added():
    [c] = diff_revision([(1, row(firm_attendees=["Avery Kim", "Jordan Lee"]))],
                        [row(firm_attendees=["Avery Kim", "Riley Chen"])]).changes
    assert c.summary == "Northwind Robotics: colleagues +Riley Chen, -Jordan Lee"


def test_same_value_rules():
    assert same_value("start", "8:00 AM", "08:00")
    assert same_value("date", "2026-11-10", "2026-11-10T00:00:00")
    assert same_value("firm_attendees", ["Avery Kim", "Jordan Lee"], ["jordan lee", "avery kim"])
    assert same_value("room", None, "")
    assert not same_value("room", "Salon 4", "Salon 2")
