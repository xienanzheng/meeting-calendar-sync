"""Match names as printed in broker PDFs to roster colleagues."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Sequence

FUZZY_THRESHOLD = 0.85
FUZZY_MARGIN = 0.05


@dataclass(frozen=True)
class RosterEntry:
    id: int
    name: str
    aliases: tuple[str, ...] = ()
    active: bool = True


@dataclass(frozen=True)
class MatchResult:
    analyst_id: int | None
    kind: str | None


NO_MATCH = MatchResult(None, None)


def normalize_name(s: str) -> str:
    """Casefold, turn punctuation into spaces, collapse whitespace. Accented letters are kept."""
    s = re.sub(r"[^\w\s]", " ", s.casefold()).replace("_", " ")
    return " ".join(s.split())


def roster_entries(analysts: Iterable) -> list[RosterEntry]:
    return [RosterEntry(a.id, a.name, tuple(a.aliases or ()), a.active) for a in analysts]


def _single(ids: set[int], kind: str) -> MatchResult:
    return MatchResult(next(iter(ids)), kind) if len(ids) == 1 else NO_MATCH


def match_name(raw: str | None, roster: Sequence[RosterEntry]) -> MatchResult:
    target = normalize_name(raw or "")
    if not target:
        return NO_MATCH
    active = [r for r in roster if r.active]

    ids = {r.id for r in active if normalize_name(r.name) == target}
    if ids:
        return _single(ids, "exact")

    ids = {r.id for r in active if any(normalize_name(a) == target for a in r.aliases)}
    if ids:
        return _single(ids, "alias")

    tokens = target.split()
    if len(tokens) == 2:
        first, last = tokens
        ids = set()
        for r in active:
            parts = normalize_name(r.name).split()
            if len(parts) < 2:
                continue
            r_first, r_last = parts[0], parts[-1]
            if len(first) == 1 and r_last == last and r_first.startswith(first):
                ids.add(r.id)
            elif len(last) == 1 and r_first == first and r_last.startswith(last):
                ids.add(r.id)
        if ids:
            return _single(ids, "initial")

    scores = sorted(
        ((max(SequenceMatcher(None, target, normalize_name(n)).ratio() for n in (r.name, *r.aliases)), r.id)
         for r in active),
        reverse=True,
    )
    if scores and scores[0][0] >= FUZZY_THRESHOLD:
        if len(scores) == 1 or scores[1][0] < scores[0][0] - FUZZY_MARGIN:
            return MatchResult(scores[0][1], "fuzzy")
    return NO_MATCH
