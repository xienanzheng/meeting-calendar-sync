import hashlib
import importlib.util
import json
import re
from zoneinfo import ZoneInfo

import pytest

from mcs.config import REPO_ROOT
from mcs.extraction.schema import parse_extraction

SAMPLES = REPO_ROOT / "samples"
EXPECTED_COUNTS = {"broker_a_grid": 12, "broker_a_grid_v2": 12, "broker_b_by_company": 8, "broker_c_itinerary": 6}


def _load_script():
    path = REPO_ROOT / "backend" / "scripts" / "make_sample_pdfs.py"
    spec = importlib.util.spec_from_file_location("make_sample_pdfs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected(name):
    return parse_extraction(json.loads((SAMPLES / f"{name}.expected.json").read_text()))


@pytest.mark.parametrize("name,count", EXPECTED_COUNTS.items())
def test_expected_json_is_valid(name, count):
    result = _expected(name)
    assert len(result.meetings) == count
    assert result.skipped_items == 0
    ZoneInfo(result.timezone)  # raises if invalid


@pytest.mark.parametrize("name", EXPECTED_COUNTS)
def test_pdf_page_count_matches_expected_pages(name):
    data = (SAMPLES / f"{name}.pdf").read_bytes()
    pages = len(re.findall(rb"/Type /Page[^s]", data))
    assert pages == max(m.page for m in _expected(name).meetings)


def test_regenerating_samples_is_byte_identical(tmp_path):
    _load_script().main(tmp_path)
    for path in sorted(SAMPLES.glob("*")):
        if path.suffix in (".pdf", ".json"):
            regenerated = tmp_path / path.name
            assert hashlib.sha256(regenerated.read_bytes()).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest(), path.name


def test_roster_sample():
    roster = json.loads((SAMPLES / "roster.sample.json").read_text())
    assert [a["name"] for a in roster] == ["Avery Kim", "Sam Patel", "Jordan Lee", "Riley Chen", "Morgan Diaz", "Taylor Brooks"]
    assert all(a["email"].endswith("@example.com") for a in roster)


def test_sample_b_contains_the_double_booking():
    b = _expected("broker_b_by_company")
    rows = {m.company: m for m in b.meetings}
    pix, orb = rows["Pixelmint Studios"], rows["Orbital Data Networks"]
    assert pix.date == orb.date == "2026-12-02"
    assert (pix.start, pix.end, orb.start, orb.end) == ("09:30", "10:30", "09:45", "10:30")
    assert "Rilay Chen" in pix.firm_attendees and "Rilay Chen" in orb.firm_attendees


def test_sample_c_is_an_itinerary_without_end_times():
    c = _expected("broker_c_itinerary")
    assert c.schedule_for == "Sam Patel"
    assert all(m.end is None and m.firm_attendees == [] for m in c.meetings)
