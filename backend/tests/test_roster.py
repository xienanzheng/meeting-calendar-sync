import pytest

from mcs.models import Analyst
from mcs.roster import MatchResult, RosterEntry, match_name, normalize_name, roster_entries

ROSTER = [
    RosterEntry(1, "Avery Kim"),
    RosterEntry(2, "Sam Patel", ("Samir Patel",)),
    RosterEntry(3, "Jordan Lee"),
    RosterEntry(4, "Riley Chen"),
    RosterEntry(5, "Morgan Diaz"),
    RosterEntry(6, "Taylor Brooks", ("Tay Brooks",)),
]


@pytest.mark.parametrize("raw,expected", [
    ("Avery Kim", (1, "exact")),
    ("  avery   KIM ", (1, "exact")),
    ("Samir Patel", (2, "alias")),
    ("Tay Brooks", (6, "alias")),
    ("A. Kim", (1, "initial")),
    ("A Kim", (1, "initial")),
    ("Morgan D.", (5, "initial")),
    ("Morgan D", (5, "initial")),
    ("Rilay Chen", (4, "fuzzy")),
    ("Chris Wong", (None, None)),
    ("", (None, None)),
    ("   ", (None, None)),
    (None, (None, None)),
])
def test_match_kinds(raw, expected):
    assert match_name(raw, ROSTER) == MatchResult(*expected)


def test_ambiguous_initial_is_no_match():
    roster = ROSTER + [RosterEntry(7, "Alex Kim")]
    assert match_name("A. Kim", roster) == MatchResult(None, None)


def test_ambiguous_exact_is_no_match():
    roster = [RosterEntry(1, "Jordan Lee"), RosterEntry(2, "Jordan Lee")]
    assert match_name("Jordan Lee", roster) == MatchResult(None, None)


def test_fuzzy_tie_is_no_match():
    roster = [RosterEntry(1, "Jon Lee"), RosterEntry(2, "Jan Lee")]
    assert match_name("Jen Lee", roster) == MatchResult(None, None)


def test_inactive_never_matched():
    roster = [RosterEntry(1, "Avery Kim", active=False)]
    assert match_name("Avery Kim", roster) == MatchResult(None, None)
    assert match_name("A. Kim", roster) == MatchResult(None, None)


def test_accents_and_apostrophes():
    assert normalize_name("José Núñez") == "josé núñez"
    assert normalize_name("Liam O'Neil") == "liam o neil"
    roster = [RosterEntry(1, "José Núñez"), RosterEntry(2, "Liam O'Neil")]
    assert match_name("JOSÉ NÚÑEZ", roster) == MatchResult(1, "exact")
    assert match_name("Liam O’Neil", roster) == MatchResult(2, "exact")
    assert match_name("J. Núñez", roster) == MatchResult(1, "initial")


def test_roster_entries_from_models():
    a = Analyst(id=3, name="Jordan Lee", email="jordan.lee@example.com", aliases=["J. Lee"], active=True)
    assert roster_entries([a]) == [RosterEntry(3, "Jordan Lee", ("J. Lee",), True)]
