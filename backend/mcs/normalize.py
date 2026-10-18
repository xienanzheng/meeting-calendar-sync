"""Turn an extraction into draft meetings, and compute review flags."""
import datetime as dt
import re
from dataclasses import dataclass
from typing import Sequence
from zoneinfo import ZoneInfo

from mcs.extraction.schema import ExtractionResult
from mcs.roster import NO_MATCH, RosterEntry, match_name, normalize_name

_H24 = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")
_H12 = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m?\.?\s*$", re.IGNORECASE)


def parse_time(value: str | None) -> dt.time | None:
    if not value:
        return None
    m = _H24.match(value)
    if m:
        hour, minute = int(m[1]), int(m[2])
        return dt.time(hour, minute) if hour < 24 and minute < 60 else None
    m = _H12.match(value)
    if m:
        hour, minute = int(m[1]), int(m[2] or 0)
        if not (1 <= hour <= 12 and minute < 60):
            return None
        return dt.time(hour % 12 + (12 if m[3].lower() == "p" else 0), minute)
    return None


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def valid_timezone(tz: str | None) -> str | None:
    if not tz:
        return None
    try:
        ZoneInfo(tz)
    except (ValueError, KeyError, OSError):  # ZoneInfoNotFoundError subclasses KeyError
        return None
    return tz


def clock_12h(t: dt.time) -> str:
    """09:45 -> "9:45 AM", 13:05 -> "1:05 PM": how the review table prints times."""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def add_minutes(t: dt.time, minutes: int) -> dt.time:
    return (dt.datetime.combine(dt.date(2000, 1, 1), t) + dt.timedelta(minutes=minutes)).time()


@dataclass
class DraftMeeting:
    date: dt.date | None
    start_time: dt.time | None
    end_time: dt.time | None
    end_assumed: bool
    room: str
    company: str
    ticker: str | None
    format: str
    company_attendees: list[str]
    raw_attendee_names: list[str]
    notes: str
    source_page: int | None
    attendees: list[tuple[int, str]]


def build_meetings(result: ExtractionResult, roster: Sequence[RosterEntry],
                   default_attendee_ids: Sequence[int] = (), default_minutes: int = 45) -> list[DraftMeeting]:
    active_ids = {r.id for r in roster if r.active}
    addressee = match_name(result.schedule_for, roster) if result.schedule_for else NO_MATCH
    drafts: list[DraftMeeting] = []
    for em in result.meetings:
        start, end = parse_time(em.start), parse_time(em.end)
        end_assumed = False
        if start is not None and end is None:
            end, end_assumed = add_minutes(start, default_minutes), True
        attendees: dict[int, str] = {}
        for raw in em.firm_attendees:
            match = match_name(raw, roster)
            if match.analyst_id is not None and match.analyst_id not in attendees:
                attendees[match.analyst_id] = match.kind
        if not em.firm_attendees and addressee.analyst_id is not None:
            attendees[addressee.analyst_id] = addressee.kind
        for analyst_id in default_attendee_ids:
            if analyst_id in active_ids and analyst_id not in attendees:
                attendees[analyst_id] = "default"
        drafts.append(DraftMeeting(
            date=parse_date(em.date), start_time=start, end_time=end, end_assumed=end_assumed,
            room=(em.room or "").strip(), company=em.company, ticker=(em.ticker or "").strip() or None,
            format=em.format, company_attendees=list(em.company_attendees),
            raw_attendee_names=list(em.firm_attendees), notes=(em.notes or "").strip(),
            source_page=em.page, attendees=list(attendees.items()),
        ))
    return drafts


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str  # "block" | "warn"
    message: str


@dataclass(frozen=True)
class MeetingView:
    id: int
    date: dt.date | None
    start_time: dt.time | None
    end_time: dt.time | None
    end_assumed: bool
    company: str
    status: str
    attendees: tuple[tuple[int, str], ...] = ()
    raw_attendee_names: tuple[str, ...] = ()
    ignored_names: tuple[str, ...] = ()


BLOCK_CODES = frozenset({"no_timezone", "missing_date", "missing_time", "end_before_start", "no_attendee"})


def has_block(flags: Sequence[Flag]) -> bool:
    return any(f.severity == "block" for f in flags)


def _times_ok(m: MeetingView) -> bool:
    return m.start_time is not None and m.end_time is not None and m.end_time > m.start_time


def compute_flags(timezone: str | None, meetings: Sequence[MeetingView],
                  roster: Sequence[RosterEntry]) -> dict[int, list[Flag]]:
    names = {r.id: r.name for r in roster}
    out: dict[int, list[Flag]] = {m.id: [] for m in meetings}
    live = [m for m in meetings if m.status != "cancelled"]

    for m in live:
        flags = out[m.id]
        if not timezone:
            flags.append(Flag("no_timezone", "block", "Set the conference timezone."))
        if m.date is None:
            flags.append(Flag("missing_date", "block", "The date is missing."))
        if m.start_time is None or m.end_time is None:
            flags.append(Flag("missing_time", "block", "The start or end time is missing."))
        elif m.end_time <= m.start_time:
            flags.append(Flag("end_before_start", "block", "The meeting ends before it starts."))
        if not m.attendees:
            flags.append(Flag("no_attendee", "block", "No colleague is assigned."))
        if m.end_assumed:
            flags.append(Flag("assumed_end", "warn", "The end time wasn't printed, so it was assumed."))
        attendee_ids = {aid for aid, _ in m.attendees}
        ignored = {normalize_name(n) for n in m.ignored_names}
        for raw in m.raw_attendee_names:
            if normalize_name(raw) in ignored:
                continue
            match = match_name(raw, roster)
            if match.analyst_id is None or match.analyst_id not in attendee_ids:
                flags.append(Flag("unmatched_name", "warn", f'"{raw}" isn\'t matched to a colleague.'))
        for aid, kind in m.attendees:
            if kind == "fuzzy":
                flags.append(Flag("fuzzy_match", "warn",
                                  f"Matched to {names.get(aid, 'a colleague')} by similar spelling. Check it."))

    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.date is None or a.date != b.date:
                continue
            if (a.start_time is not None and a.start_time == b.start_time
                    and a.company.casefold().strip() == b.company.casefold().strip()):
                out[a.id].append(Flag("duplicate", "warn", "Same company, date and time as another row."))
                out[b.id].append(Flag("duplicate", "warn", "Same company, date and time as another row."))
                continue
            if not (_times_ok(a) and _times_ok(b)):
                continue
            if a.start_time < b.end_time and b.start_time < a.end_time:
                shared = sorted({x for x, _ in a.attendees} & {x for x, _ in b.attendees})
                for aid in shared:
                    who = names.get(aid, "A colleague")
                    out[a.id].append(Flag("double_booked", "warn",
                                          f"{who} is also in {b.company} at {clock_12h(b.start_time)}."))
                    out[b.id].append(Flag("double_booked", "warn",
                                          f"{who} is also in {a.company} at {clock_12h(a.start_time)}."))
    return out
