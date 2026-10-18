"""Score an extraction against the expected result (field-level)."""
from dataclasses import dataclass, field

from mcs.extraction.schema import ExtractedMeeting, ExtractionResult
from mcs.roster import normalize_name

MEETING_FIELDS = ("end", "room", "ticker", "format", "firm_attendees", "company_attendees", "page")
HEADER_FIELDS = ("conference_name", "broker", "hotel", "city", "timezone", "schedule_for")


@dataclass
class Score:
    expected: int
    found: int
    matched: int
    missed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    field_accuracy: dict[str, float] = field(default_factory=dict)
    header_accuracy: dict[str, bool] = field(default_factory=dict)


def _key(m: ExtractedMeeting) -> tuple:
    return (m.date, m.start, normalize_name(m.company))


def _label(m: ExtractedMeeting) -> str:
    return f"{m.date} {m.start} {m.company}"


def _same(a, b) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return {normalize_name(x) for x in a or []} == {normalize_name(x) for x in b or []}
    if isinstance(a, str) or isinstance(b, str):
        return normalize_name(a or "") == normalize_name(b or "")
    return a == b


def score(expected: ExtractionResult, actual: ExtractionResult) -> Score:
    exp = {_key(m): m for m in expected.meetings}
    act = {_key(m): m for m in actual.meetings}
    matched = [k for k in exp if k in act]
    s = Score(expected=len(exp), found=len(act), matched=len(matched),
              missed=[_label(exp[k]) for k in exp if k not in act],
              extra=[_label(act[k]) for k in act if k not in exp])
    for name in MEETING_FIELDS:
        good = sum(_same(getattr(exp[k], name), getattr(act[k], name)) for k in matched)
        s.field_accuracy[name] = good / len(matched) if matched else 0.0
    for name in HEADER_FIELDS:
        s.header_accuracy[name] = _same(getattr(expected, name), getattr(actual, name))
    return s


def format_score(name: str, s: Score) -> str:
    lines = [f"{name}: {s.matched}/{s.expected} meetings matched ({s.found} found)"]
    lines += [f"  {f:<18} {acc:6.1%}" for f, acc in s.field_accuracy.items()]
    wrong = [f for f, ok in s.header_accuracy.items() if not ok]
    lines.append(f"  header mismatches: {', '.join(wrong) or 'none'}")
    lines += [f"  missed: {x}" for x in s.missed] + [f"  extra:  {x}" for x in s.extra]
    return "\n".join(lines)
