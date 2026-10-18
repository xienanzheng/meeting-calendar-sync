import pytest

from mcs.extraction.schema import (
    EXTRACTION_JSON_SCHEMA, EXTRACTION_PROMPT, ExtractedMeeting, ExtractionError, ExtractionResult, parse_extraction,
)


def test_schema_properties_match_models():
    meeting_props = set(EXTRACTION_JSON_SCHEMA["properties"]["meetings"]["items"]["properties"])
    assert meeting_props == set(ExtractedMeeting.model_fields)
    top_props = set(EXTRACTION_JSON_SCHEMA["properties"])
    assert top_props == set(ExtractionResult.model_fields) - {"skipped_items"}
    assert EXTRACTION_JSON_SCHEMA["required"] == ["meetings"]
    assert EXTRACTION_JSON_SCHEMA["properties"]["meetings"]["items"]["required"] == ["company"]


def test_invalid_items_are_skipped_and_counted():
    raw = {"meetings": [{"company": "Northwind Robotics"}, {"company": "   "}, {"room": "Salon 4"}, "junk", {"company": "Cobalt"}]}
    result = parse_extraction(raw)
    assert [m.company for m in result.meetings] == ["Northwind Robotics", "Cobalt"]
    assert result.skipped_items == 3


@pytest.mark.parametrize("given,expected", [
    ("1x1", "one_on_one"), ("One-on-One", "one_on_one"), ("one_on_one", "one_on_one"),
    ("Lunch", "meal"), ("breakfast", "meal"), ("Small Group", "group"), ("group", "group"),
    ("presentation", "other"), (None, "one_on_one"),
])
def test_format_synonyms(given, expected):
    assert ExtractedMeeting(company="X", format=given).format == expected


def test_names_are_cleaned():
    m = ExtractedMeeting(company=" Cobalt ", firm_attendees=[" A. Kim ", "", None, "Jordan Lee"], company_attendees=None)
    assert m.company == "Cobalt"
    assert m.firm_attendees == ["A. Kim", "Jordan Lee"]
    assert m.company_attendees == []


def test_top_level_blanks_become_none_and_extras_are_ignored():
    result = parse_extraction({"hotel": "  ", "city": "London", "surprise": 1, "meetings": []})
    assert result.hotel is None
    assert result.city == "London"
    assert result.meetings == []
    assert result.skipped_items == 0


def test_missing_meetings_key_means_no_meetings():
    assert parse_extraction({"hotel": "X"}).meetings == []


def test_non_object_raises_extraction_error():
    with pytest.raises(ExtractionError):
        parse_extraction(["not", "an", "object"])


def test_prompt_covers_key_rules():
    for phrase in ("firm_attendees", "schedule_for", "IANA", "24-hour", "Never guess", "page"):
        assert phrase in EXTRACTION_PROMPT
