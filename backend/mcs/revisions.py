"""Diff a revised broker schedule against the broker's last applied version (never against CR's edits)."""
import datetime as dt
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Collection, Sequence

from mcs.extraction.schema import ExtractedMeeting
from mcs.normalize import parse_date, parse_time
from mcs.roster import normalize_name

COMPARED_FIELDS = ("date", "start", "end", "room", "format", "ticker", "company", "company_attendees", "firm_attendees")
COMPANY_SIMILARITY = 0.85
FORMAT_LABELS = {"one_on_one": "1x1", "group": "Group", "meal": "Meal", "other": "Meeting"}


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: Any
    after: Any


@dataclass(frozen=True)
class Change:
    id: str
    kind: str  # "changed" | "added" | "removed"
    meeting_id: int | None
    company: str
    summary: str
    fields: tuple[FieldChange, ...] = ()
    new: ExtractedMeeting | None = None


@dataclass(frozen=True)
class RevisionDiff:
    changes: tuple[Change, ...]
    unchanged: tuple[tuple[int, ExtractedMeeting], ...]
    # Meetings CR cancelled, with the broker's row for each now (None: the broker dropped it too). CR's
    # cancellation wins, so these are never offered as changes; they take part in pairing only so the
    # broker's row for one is never mistaken for a new meeting.
    cancelled: tuple[tuple[int, ExtractedMeeting | None], ...] = ()


def _norm(value: Any):
    if isinstance(value, (list, tuple)):
        return frozenset(n for n in (normalize_name(v) for v in value) if n)
    return normalize_name(value or "")


def same_value(field: str, a: Any, b: Any) -> bool:
    if field == "date":
        return parse_date(a) == parse_date(b)
    if field in ("start", "end"):
        return parse_time(a) == parse_time(b)
    return _norm(a) == _norm(b)


def _company(m: ExtractedMeeting) -> str:
    return normalize_name(m.company)


def _sort_key(m: ExtractedMeeting):
    d, t = parse_date(m.date), parse_time(m.start)
    return (d is None, d or dt.date.max, t is None, t or dt.time.max, _company(m))


def _pair_unique(old: list, new: list, key: Callable):
    old_counts = Counter(key(m) for _, m in old)
    new_counts = Counter(key(m) for m in new)
    new_by_key = {key(m): m for m in new if new_counts[key(m)] == 1}
    pairs, old_left = [], []
    for mid, m in old:
        k = key(m)
        if old_counts[k] == 1 and new_counts.get(k) == 1:
            pairs.append((mid, m, new_by_key[k]))
        else:
            old_left.append((mid, m))
    used = {id(n) for _, _, n in pairs}
    return pairs, old_left, [m for m in new if id(m) not in used]


def _pair_fuzzy(old: list, new: list):
    def similar(a: ExtractedMeeting, b: ExtractedMeeting) -> bool:
        return (parse_date(a.date) == parse_date(b.date)
                and SequenceMatcher(None, _company(a), _company(b)).ratio() >= COMPANY_SIMILARITY)

    old_cands = {i: [j for j, n in enumerate(new) if similar(o, n)] for i, (_, o) in enumerate(old)}
    new_cands = {j: [i for i in old_cands if j in old_cands[i]] for j in range(len(new))}
    pairs, used_old, used_new = [], set(), set()
    for i, js in old_cands.items():
        if len(js) == 1 and len(new_cands[js[0]]) == 1:
            pairs.append((old[i][0], old[i][1], new[js[0]]))
            used_old.add(i)
            used_new.add(js[0])
    return (pairs, [o for i, o in enumerate(old) if i not in used_old],
            [n for j, n in enumerate(new) if j not in used_new])


def _when(m: ExtractedMeeting) -> str:
    return (f" on {m.date}" if m.date else "") + (f" at {m.start}" if m.start else "")


def _describe_changed(before: ExtractedMeeting, after: ExtractedMeeting, fields: tuple[FieldChange, ...]) -> str:
    changed = {f.field for f in fields}
    parts = []
    if "date" in changed:
        parts.append(f"date {before.date or '?'} → {after.date or '?'}")
    if changed & {"start", "end"}:
        parts.append(f"time {before.start or '?'}–{before.end or '?'} → {after.start or '?'}–{after.end or '?'}")
    if "room" in changed:
        parts.append(f"room {before.room or '—'} → {after.room or '—'}")
    if "format" in changed:
        parts.append(f"format {FORMAT_LABELS.get(before.format, before.format)} → {FORMAT_LABELS.get(after.format, after.format)}")
    if "firm_attendees" in changed:
        old_names = {normalize_name(n) for n in before.firm_attendees}
        new_names = {normalize_name(n) for n in after.firm_attendees}
        added = [f"+{n}" for n in after.firm_attendees if normalize_name(n) not in old_names]
        removed = [f"-{n}" for n in before.firm_attendees if normalize_name(n) not in new_names]
        parts.append("colleagues " + ", ".join(added + removed))
    if "company_attendees" in changed:
        parts.append("executives updated")
    if "ticker" in changed:
        parts.append(f"ticker {before.ticker or '—'} → {after.ticker or '—'}")
    if "company" in changed:
        parts.append(f"name {before.company} → {after.company}")
    return f"{after.company}: " + "; ".join(parts)


def diff_revision(baseline: Sequence[tuple[int, ExtractedMeeting]], new_rows: Sequence[ExtractedMeeting],
                  cancelled: Collection[int] = ()) -> RevisionDiff:
    """`cancelled` names baseline meetings CR cancelled: they're paired like any other, then set aside
    before change ids are numbered, so the ids stay the same wherever the diff is used."""
    old, new = list(baseline), list(new_rows)
    pairs = []
    for key in (lambda m: (parse_date(m.date), _company(m)), _company):
        found, old, new = _pair_unique(old, new, key)
        pairs += found
    found, old, new = _pair_fuzzy(old, new)
    pairs += found

    skip = set(cancelled)
    kept = [(mid, after) for mid, _, after in pairs if mid in skip] + [(mid, None) for mid, _ in old if mid in skip]
    pairs = [p for p in pairs if p[0] not in skip]
    old = [o for o in old if o[0] not in skip]

    entries, unchanged = [], []
    for mid, before, after in pairs:
        fields = tuple(FieldChange(f, getattr(before, f), getattr(after, f))
                       for f in COMPARED_FIELDS if not same_value(f, getattr(before, f), getattr(after, f)))
        if not fields:
            unchanged.append((mid, after))
            continue
        entries.append((_sort_key(before), dict(kind="changed", meeting_id=mid, company=after.company,
                                                summary=_describe_changed(before, after, fields),
                                                fields=fields, new=after)))
    for mid, before in old:
        entries.append((_sort_key(before), dict(kind="removed", meeting_id=mid, company=before.company,
                                                summary=f"Dropped: {before.company}{_when(before)}")))
    for after in new:
        entries.append((_sort_key(after), dict(kind="added", meeting_id=None, company=after.company,
                                               summary=f"New: {after.company}{_when(after)}", new=after)))
    entries.sort(key=lambda e: e[0])
    changes = tuple(Change(id=f"c{i}", **entry) for i, (_, entry) in enumerate(entries, start=1))
    return RevisionDiff(changes=changes, unchanged=tuple(unchanged), cancelled=tuple(kept))
