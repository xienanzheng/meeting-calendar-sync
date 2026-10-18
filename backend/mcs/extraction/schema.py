"""Shared extraction contract: result models, the JSON schema given to Claude, and the prompt."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ExtractionError(Exception):
    """Extraction failed; the message is shown to the coordinator."""


MeetingFormat = Literal["one_on_one", "group", "meal", "other"]

_FORMAT_SYNONYMS = {
    "one_on_one": "one_on_one", "1x1": "one_on_one", "1:1": "one_on_one", "one-on-one": "one_on_one",
    "one on one": "one_on_one", "group": "group", "small group": "group", "meal": "meal", "lunch": "meal",
    "breakfast": "meal", "dinner": "meal", "other": "other",
}


class ExtractedMeeting(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str | None = None
    start: str | None = None
    end: str | None = None
    room: str | None = None
    company: str = Field(min_length=1)
    ticker: str | None = None
    format: MeetingFormat = "one_on_one"
    company_attendees: list[str] = Field(default_factory=list)
    firm_attendees: list[str] = Field(default_factory=list)
    notes: str | None = None
    page: int | None = None

    @field_validator("company", mode="before")
    @classmethod
    def _strip_company(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("format", mode="before")
    @classmethod
    def _normalise_format(cls, v):
        if v is None:
            return "one_on_one"
        return _FORMAT_SYNONYMS.get(str(v).strip().lower(), "other")

    @field_validator("company_attendees", "firm_attendees", mode="before")
    @classmethod
    def _clean_names(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conference_name: str | None = None
    broker: str | None = None
    hotel: str | None = None
    city: str | None = None
    timezone: str | None = None
    schedule_for: str | None = None
    meetings: list[ExtractedMeeting] = Field(default_factory=list)
    skipped_items: int = 0


_TOP_LEVEL_TEXT_FIELDS = ("conference_name", "broker", "hotel", "city", "timezone", "schedule_for")


def parse_extraction(raw: Any) -> ExtractionResult:
    """Validate provider output leniently: invalid meeting items are skipped and counted."""
    if not isinstance(raw, dict):
        raise ExtractionError("Claude returned something other than a JSON object.")
    items = raw.get("meetings") or []
    if not isinstance(items, list):
        items = []
    meetings: list[ExtractedMeeting] = []
    skipped = 0
    for item in items:
        try:
            meetings.append(ExtractedMeeting.model_validate(item))
        except ValidationError:
            skipped += 1
    top = {}
    for key in _TOP_LEVEL_TEXT_FIELDS:
        value = raw.get(key)
        top[key] = value.strip() if isinstance(value, str) and value.strip() else None
    return ExtractionResult(**top, meetings=meetings, skipped_items=skipped)


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "conference_name": {**_STR, "description": "Conference title as printed"},
        "broker": {**_STR, "description": "Hosting bank or broker"},
        "hotel": {**_STR, "description": "Venue or hotel name"},
        "city": _STR,
        "timezone": {**_STR, "description": "IANA timezone of the venue, e.g. America/New_York"},
        "schedule_for": {**_STR, "description": "Firm or person this schedule is addressed to, as printed"},
        "meetings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {**_STR, "description": "YYYY-MM-DD"},
                    "start": {**_STR, "description": "HH:MM 24-hour, venue local time"},
                    "end": {**_STR, "description": "HH:MM 24-hour, venue local time; omit if not printed"},
                    "room": _STR,
                    "company": _STR,
                    "ticker": _STR,
                    "format": {"type": "string", "enum": ["one_on_one", "group", "meal", "other"]},
                    "company_attendees": {**_STR_LIST, "description": "The company's executives as printed (name, title)"},
                    "firm_attendees": {**_STR_LIST, "description": "People from the schedule's firm printed on this row; empty if none"},
                    "notes": _STR,
                    "page": {"type": "integer", "description": "1-based PDF page number"},
                },
                "required": ["company"],
            },
        },
    },
    "required": ["meetings"],
}

SYSTEM_PROMPT = (
    "You extract meeting schedules from broker conference PDFs into structured data. "
    "Read the whole document, then return the structured result. Never invent values."
)

EXTRACTION_PROMPT = """Extract every scheduled meeting from this broker conference schedule.

Rules:
- One entry per meeting row. Include group meetings, meals and presentations the schedule lists.
- Copy names exactly as printed (do not expand initials or fix spelling).
- company: the company being met, without the ticker. ticker: its ticker symbol if printed.
- company_attendees: the company's executives as printed, e.g. "Dana Shore, CFO".
- firm_attendees: the people from the firm this schedule is for, printed on that row. Leave it empty if the row lists nobody.
- schedule_for: who the whole schedule is addressed to ("Schedule for: ...", "Itinerary for: ...").
- date: YYYY-MM-DD. Infer the year from the document header if a row omits it.
- start / end: 24-hour HH:MM in the venue's local time, exactly as printed. Omit end if only a start time is printed.
- format: one_on_one for 1x1 or one-on-one; group for group or small-group meetings; meal for breakfast, lunch or dinner; otherwise other.
- room: the room, suite or location as printed (e.g. "Suite 1201", "TBD").
- timezone: the IANA timezone of the venue's city (e.g. America/New_York, Europe/London).
- page: the 1-based PDF page number the meeting appears on.
- Omit any field you cannot find. Never guess."""
