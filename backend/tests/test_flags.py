import datetime as dt

from mcs.normalize import BLOCK_CODES, Flag, MeetingView, compute_flags, has_block
from mcs.roster import RosterEntry

ROSTER = [RosterEntry(1, "Avery Kim"), RosterEntry(4, "Riley Chen")]
TZ = "America/New_York"
D = dt.date(2026, 12, 2)


def mv(id, start=(9, 0), end=(9, 45), date=D, company="Co", status="draft", attendees=((1, "exact"),), **kw):
    return MeetingView(id=id, date=date, start_time=dt.time(*start) if start else None,
                       end_time=dt.time(*end) if end else None, end_assumed=kw.pop("end_assumed", False),
                       company=company, status=status, attendees=tuple(attendees), **kw)


def codes(flags):
    return sorted(f.code for f in flags)


def test_clean_meeting_has_no_flags():
    assert compute_flags(TZ, [mv(1)], ROSTER) == {1: []}


def test_block_flags():
    out = compute_flags(None, [mv(1, date=None), mv(2, start=None), mv(3, start=(10, 0), end=(10, 0)), mv(4, attendees=())], ROSTER)
    assert codes(out[1]) == ["missing_date", "no_timezone"]
    assert codes(out[2]) == ["missing_time", "no_timezone"]
    assert codes(out[3]) == ["end_before_start", "no_timezone"]
    assert codes(out[4]) == ["no_attendee", "no_timezone"]
    assert all(f.severity == "block" for fl in out.values() for f in fl)


def test_assumed_end_and_fuzzy_are_warnings():
    out = compute_flags(TZ, [mv(1, end_assumed=True, attendees=((4, "fuzzy"),))], ROSTER)
    assert codes(out[1]) == ["assumed_end", "fuzzy_match"]
    assert not has_block(out[1])
    assert "Riley Chen" in next(f.message for f in out[1] if f.code == "fuzzy_match")


def test_unmatched_name_rules():
    out = compute_flags(TZ, [
        mv(1, raw_attendee_names=("Chris Wong",), attendees=((1, "default"),)),
        mv(2, start=(11, 0), end=(11, 30), raw_attendee_names=("Chris Wong",), ignored_names=("chris  WONG",)),
        mv(3, start=(12, 0), end=(12, 30), raw_attendee_names=("A. Kim",)),
        mv(4, start=(13, 0), end=(13, 30), raw_attendee_names=("A. Kim",), attendees=((4, "manual"),)),
    ], ROSTER)
    assert codes(out[1]) == ["unmatched_name"]
    assert "Chris Wong" in out[1][0].message
    assert out[2] == [] and out[3] == []
    assert codes(out[4]) == ["unmatched_name"]


def test_double_booking_flags_both_meetings():
    pix = mv(1, start=(9, 30), end=(10, 30), company="Pixelmint Studios", attendees=((1, "initial"), (4, "fuzzy")))
    orb = mv(2, start=(9, 45), end=(10, 30), company="Orbital Data Networks", attendees=((4, "fuzzy"),))
    out = compute_flags(TZ, [pix, orb], ROSTER)
    assert "double_booked" in codes(out[1]) and "double_booked" in codes(out[2])
    msg = next(f.message for f in out[1] if f.code == "double_booked")
    assert "Riley Chen" in msg and "Orbital Data Networks" in msg


def test_double_booking_message_reads_like_the_table():
    # The review table prints 12-hour times ("9:45 AM", "1:05 PM"), so the flag does too.
    pix = mv(1, start=(9, 30), end=(10, 30), company="Pixelmint Studios", attendees=((4, "exact"),))
    orb = mv(2, start=(9, 45), end=(10, 30), company="Orbital Data Networks", attendees=((4, "exact"),))
    lunch = mv(3, start=(13, 5), end=(14, 0), company="Keystone Valve", attendees=((1, "exact"),))
    noon = mv(4, start=(12, 0), end=(13, 30), company="Lumen Sensor", attendees=((1, "exact"),))
    out = compute_flags(TZ, [pix, orb, lunch, noon], ROSTER)
    message = lambda i: next(f.message for f in out[i] if f.code == "double_booked")
    assert message(1) == "Riley Chen is also in Orbital Data Networks at 9:45 AM."
    assert message(2) == "Riley Chen is also in Pixelmint Studios at 9:30 AM."
    assert message(3) == "Avery Kim is also in Lumen Sensor at 12:00 PM."
    assert message(4) == "Avery Kim is also in Keystone Valve at 1:05 PM."


def test_adjacent_and_other_day_meetings_do_not_clash():
    out = compute_flags(TZ, [mv(1, start=(9, 0), end=(9, 45)), mv(2, start=(9, 45), end=(10, 30)),
                             mv(3, date=dt.date(2026, 12, 3))], ROSTER)
    assert out == {1: [], 2: [], 3: []}


def test_duplicate_rows_warn_without_double_booking():
    out = compute_flags(TZ, [mv(1, company="Kestrel Security"), mv(2, company="kestrel security ")], ROSTER)
    assert codes(out[1]) == ["duplicate"] and codes(out[2]) == ["duplicate"]


def test_cancelled_meetings_are_ignored():
    out = compute_flags(None, [mv(1, status="cancelled"), mv(2, start=(9, 0), end=(9, 45))], ROSTER)
    assert out[1] == []
    assert codes(out[2]) == ["no_timezone"]


def test_block_codes_and_has_block():
    assert BLOCK_CODES == {"no_timezone", "missing_date", "missing_time", "end_before_start", "no_attendee"}
    assert has_block([Flag("assumed_end", "warn", "x"), Flag("no_attendee", "block", "y")])
    assert not has_block([Flag("assumed_end", "warn", "x")])


def test_a_meeting_timezone_satisfies_the_timezone_check():
    out = compute_flags(None, [mv(1, timezone="America/Chicago"), mv(2, company="Other", start=(13, 0), end=(13, 30))],
                        ROSTER)
    assert codes(out[1]) == [] and codes(out[2]) == ["no_timezone"]


def test_clashes_compare_real_times_across_timezones():
    chicago = "America/Chicago"
    # 9:00 Eastern and 9:00 Central are an hour apart, and not the same printed row either.
    out = compute_flags(TZ, [mv(1, company="A"), mv(2, company="B", timezone=chicago),
                             mv(3, company="A", timezone=chicago, attendees=((4, "exact"),))], ROSTER)
    assert codes(out[1]) == [] and codes(out[2]) == [] and codes(out[3]) == []
    # 10:00 Eastern and 9:00 Central are the same moment.
    out = compute_flags(TZ, [mv(1, company="A", start=(10, 0), end=(10, 45)), mv(2, company="B", timezone=chicago)],
                        ROSTER)
    assert codes(out[1]) == ["double_booked"] and codes(out[2]) == ["double_booked"]
    assert out[1][0].message == "Avery Kim is also in B at 9:00 AM Chicago time."
    assert out[2][0].message == "Avery Kim is also in A at 10:00 AM New York time."
