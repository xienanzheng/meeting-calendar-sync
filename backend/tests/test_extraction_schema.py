import copy

import pytest

from mcs.extraction.schema import (
    EXTRACTION_JSON_SCHEMA, EXTRACTION_OUTPUT_SCHEMA, EXTRACTION_PROMPT, ExtractedMeeting, ExtractionError,
    ExtractionResult, parse_extraction, strict_json_schema,
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


def _object_nodes(node):
    """Yield every object-typed schema node (dict with type == 'object') reachable from node."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            yield from _object_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _object_nodes(item)


def test_strict_json_schema_marks_every_object_fully_required_and_closed():
    nodes = list(_object_nodes(EXTRACTION_OUTPUT_SCHEMA))
    assert nodes, "expected at least one object node in the strict schema"
    for node in nodes:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])


def test_strict_json_schema_makes_optional_scalars_nullable():
    assert EXTRACTION_OUTPUT_SCHEMA["properties"]["hotel"]["type"] == ["string", "null"]
    meeting_props = EXTRACTION_OUTPUT_SCHEMA["properties"]["meetings"]["items"]["properties"]
    assert meeting_props["page"]["type"] == ["integer", "null"]
    assert meeting_props["company"]["type"] == "string"


def test_strict_json_schema_keeps_enum_required_and_non_nullable():
    meeting_props = EXTRACTION_OUTPUT_SCHEMA["properties"]["meetings"]["items"]["properties"]
    fmt = meeting_props["format"]
    assert fmt["type"] == "string"
    assert fmt["enum"] == EXTRACTION_JSON_SCHEMA["properties"]["meetings"]["items"]["properties"]["format"]["enum"]
    assert "format" in EXTRACTION_OUTPUT_SCHEMA["properties"]["meetings"]["items"]["required"]


def test_strict_json_schema_keeps_arrays_as_arrays():
    meeting_props = EXTRACTION_OUTPUT_SCHEMA["properties"]["meetings"]["items"]["properties"]
    assert meeting_props["firm_attendees"]["type"] == "array"
    assert meeting_props["company_attendees"]["type"] == "array"
    assert EXTRACTION_OUTPUT_SCHEMA["properties"]["meetings"]["type"] == "array"


def test_strict_json_schema_does_not_mutate_input():
    before = copy.deepcopy(EXTRACTION_JSON_SCHEMA)
    strict_json_schema(EXTRACTION_JSON_SCHEMA)
    assert EXTRACTION_JSON_SCHEMA == before


def test_extraction_json_schema_is_still_the_original_shape():
    # Guards against the fix accidentally rewriting the Claude Code CLI schema.
    assert EXTRACTION_JSON_SCHEMA["required"] == ["meetings"]
    assert EXTRACTION_JSON_SCHEMA["properties"]["meetings"]["items"]["required"] == ["company"]
    assert EXTRACTION_JSON_SCHEMA["properties"]["hotel"]["type"] == "string"
