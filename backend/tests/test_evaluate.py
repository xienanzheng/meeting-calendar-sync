import json

from mcs.config import REPO_ROOT
from mcs.evaluate import format_score, score
from mcs.extraction.schema import parse_extraction

A = parse_extraction(json.loads((REPO_ROOT / "samples" / "broker_a_grid.expected.json").read_text()))


def test_perfect_score():
    s = score(A, A)
    assert (s.expected, s.found, s.matched) == (12, 12, 12)
    assert s.missed == [] and s.extra == []
    assert all(v == 1.0 for v in s.field_accuracy.values())
    assert all(s.header_accuracy.values())


def test_missed_extra_and_wrong_field():
    raw = json.loads((REPO_ROOT / "samples" / "broker_a_grid.expected.json").read_text())
    raw["meetings"] = raw["meetings"][1:]                                  # miss Northwind
    raw["meetings"][0]["room"] = "Wrong Room"                              # Borealis room wrong
    raw["meetings"].append({"company": "Ghost Corp", "date": "2026-11-10", "start": "17:00"})
    raw["hotel"] = "Another Hotel"
    s = score(A, parse_extraction(raw))
    assert (s.expected, s.found, s.matched) == (12, 12, 11)
    assert s.missed == ["2026-11-10 08:00 Northwind Robotics"]
    assert s.extra == ["2026-11-10 17:00 Ghost Corp"]
    assert s.field_accuracy["room"] == 10 / 11
    assert s.header_accuracy["hotel"] is False
    text = format_score("broker_a_grid", s)
    assert "11/12 meetings matched" in text and "room" in text


def test_names_compare_as_normalized_sets():
    raw = json.loads((REPO_ROOT / "samples" / "broker_a_grid.expected.json").read_text())
    raw["meetings"][0]["firm_attendees"] = ["jordan lee", "AVERY KIM"]
    assert score(A, parse_extraction(raw)).field_accuracy["firm_attendees"] == 1.0
