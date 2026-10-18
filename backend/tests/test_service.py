import json

import pytest
from sqlmodel import select

from mcs import service
from mcs.calendar.ics import IcsSink
from mcs.calendar.planner import SyncOutcome
from mcs.config import REPO_ROOT
from mcs.extraction.schema import parse_extraction
from mcs.models import Meeting, MeetingAttendee, SyncRecord
from mcs.schemas import AnalystIn, AnalystUpdate, ConferenceUpdate, MeetingCreate, MeetingUpdate

SAMPLES = REPO_ROOT / "samples"


def sample(name):
    return parse_extraction(json.loads((SAMPLES / f"{name}.expected.json").read_text()))


@pytest.fixture
def seeded(session):
    service.seed_roster(session, SAMPLES / "roster.sample.json")
    return session


def ids(session):
    return {a.name: a.id for a in service.list_analysts(session)}


def make_conf(session, name="broker_a_grid"):
    return service.create_conference(session, sample(name), pdf_filename=f"{name}.pdf",
                                     pdf_path=f"/tmp/{name}.pdf", extractor="fake")


def detail(session, conf):
    return service.conference_detail(session, conf.id, "ics")


def by_company(d, company):
    return next(m for m in d.meetings if m.company == company)


def test_seed_roster_is_idempotent(session):
    assert service.seed_roster(session, SAMPLES / "roster.sample.json") == 6
    assert service.seed_roster(session, SAMPLES / "roster.sample.json") == 0
    assert [a.name for a in service.list_analysts(session)][:2] == ["Avery Kim", "Jordan Lee"]  # sorted by name


def test_create_conference_from_sample(seeded):
    conf = make_conf(seeded)
    assert (conf.name, conf.timezone, conf.hotel, conf.extractor) == (
        "Industrials Conference 2026", "America/New_York", "The Example Grand Hotel", "fake")
    d = detail(seeded, conf)
    assert len(d.meetings) == 12
    assert (d.first_date, d.last_date) == ("2026-11-10", "2026-11-11")
    first = d.meetings[0]
    assert (first.date, first.start, first.end, first.company) == ("2026-11-10", "08:00", "08:45", "Northwind Robotics")
    assert [(a.name, a.match, a.sync) for a in first.attendees] == [("Avery Kim", "exact", "not_sent"), ("Jordan Lee", "exact", "not_sent")]
    tide = by_company(d, "Tidewater Pumps")
    assert tide.review_state == "needs_attention"
    assert {f.code for f in tide.flags} == {"no_attendee", "unmatched_name"}
    assert tide.unmatched_names == ["Chris Wong"]
    assert d.counts.total == 12 and d.counts.needs_attention == 1 and d.counts.ready == 11
    assert d.counts.warnings == 1 and d.counts.pending_actions == 0


def test_itinerary_sample_assumes_ends_and_uses_addressee(seeded):
    d = detail(seeded, make_conf(seeded, "broker_c_itinerary"))
    assert d.timezone == "Europe/London"
    assert all(m.end_assumed and [a.name for a in m.attendees] == ["Sam Patel"] for m in d.meetings)
    assert all({f.code for f in m.flags} == {"assumed_end"} for m in d.meetings)


def test_verify_rules(seeded):
    conf = make_conf(seeded)
    d = detail(seeded, conf)
    tide = by_company(d, "Tidewater Pumps")
    with pytest.raises(service.Conflict) as info:
        service.confirm_meeting(seeded, tide.id)
    assert "no_attendee" in {f.code for f in info.value.flags}
    first = d.meetings[0]
    assert service.confirm_meeting(seeded, first.id).status == "confirmed"
    assert by_company(detail(seeded, conf), "Northwind Robotics").review_state == "verified"
    subset = [d.meetings[1].id, d.meetings[2].id, tide.id]
    assert service.confirm_ready(seeded, conf.id, subset) == 2
    assert service.confirm_ready(seeded, conf.id) == 8
    assert service.unconfirm_meeting(seeded, first.id).status == "draft"


def test_assign_and_dismiss_clear_flags(seeded):
    conf = make_conf(seeded)
    tide = by_company(detail(seeded, conf), "Tidewater Pumps")
    service.update_meeting(seeded, tide.id, MeetingUpdate(attendee_ids=[ids(seeded)["Jordan Lee"]]), 45)
    tide = by_company(detail(seeded, conf), "Tidewater Pumps")
    assert [(a.name, a.match) for a in tide.attendees] == [("Jordan Lee", "manual")]
    assert {f.code for f in tide.flags} == {"unmatched_name"}
    service.update_meeting(seeded, tide.id, MeetingUpdate(ignored_names=["Chris Wong"]), 45)
    assert by_company(detail(seeded, conf), "Tidewater Pumps").flags == []


def test_attendee_edit_keeps_existing_match_kinds(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    people = ids(seeded)
    service.update_meeting(seeded, first.id, MeetingUpdate(attendee_ids=[people["Avery Kim"], people["Sam Patel"]]), 45)
    got = [(a.name, a.match) for a in by_company(detail(seeded, conf), "Northwind Robotics").attendees]
    assert got == [("Avery Kim", "exact"), ("Sam Patel", "manual")]


def test_time_edits_and_status_rule(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    service.update_meeting(seeded, first.id, MeetingUpdate(start="9:15 AM", end="10:00"), 45)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert (m.start, m.end, m.end_assumed) == ("09:15", "10:00", False)
    with pytest.raises(service.InvalidInput):
        service.update_meeting(seeded, first.id, MeetingUpdate(start="nonsense"), 45)
    service.confirm_meeting(seeded, first.id)
    service.update_meeting(seeded, first.id, MeetingUpdate(end=None), 45)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert m.status == "draft" and "missing_time" in {f.code for f in m.flags}


def test_assumed_end_follows_start(seeded):
    conf = make_conf(seeded, "broker_c_itinerary")
    m = detail(seeded, conf).meetings[0]
    service.update_meeting(seeded, m.id, MeetingUpdate(start="08:30"), 45)
    m = detail(seeded, conf).meetings[0]
    assert (m.start, m.end, m.end_assumed) == ("08:30", "09:15", True)


def test_clearing_timezone_unverifies_and_blocks_sending(seeded):
    conf = make_conf(seeded)
    service.confirm_ready(seeded, conf.id)
    with pytest.raises(service.InvalidInput):
        service.update_conference(seeded, conf.id, ConferenceUpdate(timezone="Eastern"))
    service.update_conference(seeded, conf.id, ConferenceUpdate(timezone=None))
    d = detail(seeded, conf)
    assert all(m.status == "draft" for m in d.meetings)
    assert service.plan_conference(seeded, conf.id, "ics") == []


def test_send_update_remove_cancel_cycle(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]  # Northwind: Avery + Jordan
    service.confirm_meeting(seeded, first.id)
    assert [a.kind for a in service.plan_conference(seeded, conf.id, "ics")] == ["create", "create"]
    outcomes = service.send_conference(seeded, conf.id, IcsSink())
    assert all(o.ok for o in outcomes)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert m.review_state == "sent" and {a.sync for a in m.attendees} == {"sent"}
    recs = seeded.exec(select(SyncRecord)).all()
    assert {r.external_id for r in recs} == {f"mcs-{first.id}-{a.analyst_id}@meeting-calendar-sync" for a in m.attendees}

    service.update_meeting(seeded, first.id, MeetingUpdate(room="Salon 2"), 45)
    d = detail(seeded, conf)
    assert {a.sync for a in by_company(d, "Northwind Robotics").attendees} == {"changed"}
    assert d.counts.pending_actions == 2
    service.send_conference(seeded, conf.id, IcsSink())
    assert {r.sequence for r in seeded.exec(select(SyncRecord)).all()} == {1}

    service.update_meeting(seeded, first.id, MeetingUpdate(attendee_ids=[ids(seeded)["Avery Kim"]]), 45)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert [r.name for r in m.removed] == ["Jordan Lee"]
    plan = service.plan_conference(seeded, conf.id, "ics")
    assert sorted(a.kind for a in plan) == ["cancel", "update"]  # Jordan cancelled; Avery's "Also attending" changed
    service.send_conference(seeded, conf.id, IcsSink())

    assert service.delete_meeting(seeded, first.id) == "cancelled"
    assert [a.kind for a in service.plan_conference(seeded, conf.id, "ics")] == ["cancel"]
    service.send_conference(seeded, conf.id, IcsSink())
    d = detail(seeded, conf)
    assert by_company(d, "Northwind Robotics").review_state == "cancelled"
    assert d.counts.cancelled == 1 and d.counts.total == 11
    avery_recs = service.ics_records_for(seeded, conf.id, ids(seeded)["Avery Kim"])
    assert [r.state for r in avery_recs] == ["cancelled"]


class FailFor:
    name = "ics"

    def __init__(self, email):
        self.email = email

    def apply(self, conference, actions):
        return [SyncOutcome(a, ok=a.analyst_email != self.email,
                            external_id=None if a.analyst_email == self.email else f"x-{a.analyst_id}",
                            error="Graph error 500: boom" if a.analyst_email == self.email else None)
                for a in actions]


def test_partial_failure_retries_only_failed_item(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    service.confirm_meeting(seeded, first.id)
    outcomes = service.send_conference(seeded, conf.id, FailFor("jordan.lee@example.com"))
    assert sorted(o.ok for o in outcomes) == [False, True]
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    syncs = {a.name: (a.sync, a.sync_error) for a in m.attendees}
    assert syncs == {"Avery Kim": ("sent", None), "Jordan Lee": ("failed", "Graph error 500: boom")}
    retry = service.plan_conference(seeded, conf.id, "ics")
    assert [(a.kind, a.analyst_name) for a in retry] == [("create", "Jordan Lee")]
    assert detail(seeded, conf).counts.failed == 1


def test_failed_recreate_after_cancel_stays_cancelled_for_retry(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]  # Northwind: Avery + Jordan
    jordan_id = ids(seeded)["Jordan Lee"]
    service.confirm_meeting(seeded, first.id)
    service.send_conference(seeded, conf.id, IcsSink())

    service.update_meeting(seeded, first.id, MeetingUpdate(attendee_ids=[ids(seeded)["Avery Kim"]]), 45)
    service.send_conference(seeded, conf.id, IcsSink())  # Jordan's record -> cancelled
    before = service.ics_records_for(seeded, conf.id, jordan_id)[0]
    assert before.state == "cancelled"
    before_sequence = before.sequence  # snapshot now: `before` is session-tracked and mutates in place later

    service.update_meeting(seeded, first.id,
                           MeetingUpdate(attendee_ids=[ids(seeded)["Avery Kim"], jordan_id]), 45)
    service.send_conference(seeded, conf.id, FailFor("jordan.lee@example.com"))
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    jordan = next(a for a in m.attendees if a.name == "Jordan Lee")
    assert jordan.sync == "failed" and jordan.sync_error == "Graph error 500: boom"
    retry = service.plan_conference(seeded, conf.id, "ics")
    assert [(a.kind, a.analyst_name) for a in retry if a.analyst_id == jordan_id] == [("create", "Jordan Lee")]

    service.send_conference(seeded, conf.id, IcsSink())
    after = service.ics_records_for(seeded, conf.id, jordan_id)[0]
    assert after.state == "active" and after.last_error is None
    assert after.sequence > before_sequence


def test_delete_unsent_meeting_removes_it(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    assert service.delete_meeting(seeded, first.id) == "deleted"
    assert seeded.get(Meeting, first.id) is None
    assert seeded.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id == first.id)).all() == []


def test_add_meeting_manual(seeded):
    conf = make_conf(seeded)
    m = service.add_meeting(seeded, conf.id, MeetingCreate(company="Atlas Rail Systems", date="2026-11-10",
                                                           start="16:00", attendee_ids=[ids(seeded)["Riley Chen"]]), 45)
    out = by_company(detail(seeded, conf), "Atlas Rail Systems")
    assert (out.start, out.end, out.end_assumed, out.status) == ("16:00", "16:45", True, "draft")
    assert out.attendees[0].match == "manual"
    assert m.conference_id == conf.id


def test_cancelled_meeting_cannot_be_edited(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    service.confirm_meeting(seeded, first.id)
    service.send_conference(seeded, conf.id, IcsSink())
    service.delete_meeting(seeded, first.id)
    with pytest.raises(service.Conflict):
        service.update_meeting(seeded, first.id, MeetingUpdate(room="X"), 45)


def test_delete_conference_removes_everything(seeded):
    conf = make_conf(seeded)
    service.confirm_ready(seeded, conf.id)
    service.send_conference(seeded, conf.id, IcsSink())
    assert service.delete_conference(seeded, conf.id) == "/tmp/broker_a_grid.pdf"
    assert seeded.exec(select(Meeting)).all() == []
    assert seeded.exec(select(SyncRecord)).all() == []
    with pytest.raises(service.NotFound):
        service.get_conference(seeded, conf.id)


def test_roster_crud_rules(seeded):
    with pytest.raises(service.InvalidInput):
        service.create_analyst(seeded, AnalystIn(name="Dup", email="avery.kim@example.com"))
    new = service.create_analyst(seeded, AnalystIn(name="Casey Fox", email="casey.fox@example.com", aliases=["C. Fox"]))
    assert service.update_analyst(seeded, new.id, AnalystUpdate(active=False)).active is False
    service.delete_analyst(seeded, new.id)
    conf = make_conf(seeded)
    with pytest.raises(service.Conflict):
        service.delete_analyst(seeded, ids(seeded)["Avery Kim"])  # referenced by meetings


def test_summaries(seeded):
    make_conf(seeded)
    make_conf(seeded, "broker_b_by_company")
    summaries = service.list_conference_summaries(seeded, "ics")
    assert [s.name for s in summaries] == ["Technology Summit 2026", "Industrials Conference 2026"]  # newest first
    assert summaries[0].counts.total == 8


def test_send_result_shapes(seeded):
    conf = make_conf(seeded)
    service.confirm_meeting(seeded, detail(seeded, conf).meetings[0].id)
    plan = service.plan_conference(seeded, conf.id, "ics")
    preview = service.send_result(seeded, conf.id, "ics", plan, dry_run=True)
    assert preview.dry_run and [a.ok for a in preview.actions] == [None, None]
    assert {(s.name, s.create) for s in preview.by_analyst} == {("Avery Kim", 1), ("Jordan Lee", 1)}
    outcomes = service.send_conference(seeded, conf.id, IcsSink())
    done = service.send_result(seeded, conf.id, "ics", outcomes, dry_run=False)
    assert done.ok_count == 2 and done.failed_count == 0
    assert done.zip_url == f"/api/conferences/{conf.id}/ics.zip"
    assert all(s.download_url == f"/api/conferences/{conf.id}/ics/{s.analyst_id}" for s in done.by_analyst)
