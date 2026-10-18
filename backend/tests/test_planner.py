import datetime as dt

from mcs.calendar.content import build_event
from mcs.calendar.planner import plan_sync
from mcs.models import Analyst, Conference, Meeting, SyncRecord

CONF = Conference(id=1, name="Industrials Conference 2026", hotel="The Example Grand Hotel",
                  timezone="America/New_York", pdf_filename="a.pdf")
AVERY = Analyst(id=1, name="Avery Kim", email="avery.kim@example.com")
JORDAN = Analyst(id=3, name="Jordan Lee", email="jordan.lee@example.com")
ANALYSTS = {1: AVERY, 3: JORDAN}


def m(id=10, status="confirmed", room="Salon 4"):
    return Meeting(id=id, conference_id=1, date=dt.date(2026, 11, 10), start_time=dt.time(8, 0),
                   end_time=dt.time(8, 45), room=room, company="Northwind Robotics", ticker="NWRB", status=status)


def rec(meeting_id=10, analyst_id=1, state="active", external_id="ext-1", content=None, sequence=0):
    content = content or build_event(CONF, m(), ["Jordan Lee"])
    return SyncRecord(meeting_id=meeting_id, analyst_id=analyst_id, sink="ics", external_id=external_id,
                      content_hash=content.content_hash(), content_json=content.to_json(), sequence=sequence, state=state)


def kinds(actions):
    return [(a.kind, a.meeting_id, a.analyst_id, a.sequence, a.external_id) for a in actions]


def test_new_confirmed_meeting_creates_per_attendee():
    actions = plan_sync(CONF, [m()], {10: [1, 3]}, ANALYSTS, [])
    assert kinds(actions) == [("create", 10, 1, 0, None), ("create", 10, 3, 0, None)]
    assert actions[0].analyst_email == "avery.kim@example.com"
    assert "Also attending: Jordan Lee" in actions[0].content.body
    assert "Also attending: Avery Kim" in actions[1].content.body


def test_drafts_are_never_sent():
    assert plan_sync(CONF, [m(status="draft")], {10: [1]}, ANALYSTS, []) == []


def test_unchanged_active_record_is_skipped():
    assert plan_sync(CONF, [m()], {10: [1, 3]}, ANALYSTS,
                     [rec(), rec(analyst_id=3, content=build_event(CONF, m(), ["Avery Kim"]))]) == []


def test_changed_content_updates_with_next_sequence():
    actions = plan_sync(CONF, [m(room="Salon 2")], {10: [1]}, ANALYSTS, [rec(sequence=2)])
    assert kinds(actions) == [("update", 10, 1, 3, "ext-1")]
    assert "Salon 2" in actions[0].content.location


def test_failed_record_with_event_is_updated_even_if_unchanged():
    content = build_event(CONF, m(), [])
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS, [rec(state="failed", content=content)])
    assert kinds(actions) == [("update", 10, 1, 1, "ext-1")]


def test_failed_create_is_created_again():
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS, [rec(state="failed", external_id=None)])
    assert kinds(actions) == [("create", 10, 1, 0, None)]


def test_reconfirmed_after_cancel_recreates_with_same_id_and_higher_sequence():
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS, [rec(state="cancelled", sequence=4)])
    assert kinds(actions) == [("create", 10, 1, 5, "ext-1")]


def test_cancelled_meeting_cancels_active_records():
    actions = plan_sync(CONF, [m(status="cancelled")], {10: [1]}, ANALYSTS, [rec(sequence=1)])
    assert kinds(actions) == [("cancel", 10, 1, 2, "ext-1")]
    assert actions[0].content.subject.startswith("NWRB")


def test_removed_attendee_is_cancelled_only_for_them():
    content_j = build_event(CONF, m(), ["Avery Kim"])
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS,
                        [rec(content=build_event(CONF, m(), [])), rec(analyst_id=3, external_id="ext-3", content=content_j)])
    assert kinds(actions) == [("cancel", 10, 3, 1, "ext-3")]


def test_draft_with_removed_attendee_leaves_record_alone():
    assert plan_sync(CONF, [m(status="draft")], {10: []}, ANALYSTS, [rec()]) == []


def test_already_cancelled_record_is_left_alone():
    assert plan_sync(CONF, [m(status="cancelled")], {10: [1]}, ANALYSTS, [rec(state="cancelled")]) == []
