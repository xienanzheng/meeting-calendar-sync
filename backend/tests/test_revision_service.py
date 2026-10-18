import json

import pytest
from sqlmodel import select

from mcs import revision_service as rs
from mcs import service
from mcs.calendar.ics import IcsSink
from mcs.config import REPO_ROOT
from mcs.extraction.schema import ExtractedMeeting, parse_extraction
from mcs.models import Meeting, Revision, SyncRecord
from mcs.schemas import ConferenceUpdate, MeetingCreate, MeetingUpdate

SAMPLES = REPO_ROOT / "samples"


def sample(name):
    return parse_extraction(json.loads((SAMPLES / f"{name}.expected.json").read_text()))


@pytest.fixture
def seeded(session):
    service.seed_roster(session, SAMPLES / "roster.sample.json")
    return session


def conf_a(s):
    return service.create_conference(s, sample("broker_a_grid"), pdf_filename="broker_a_grid.pdf",
                                     pdf_path="/tmp/a.pdf", extractor="fake")


def revise(s, conf, name="broker_a_grid_v2"):
    return rs.create_revision(s, conf, sample(name), pdf_filename=f"{name}.pdf", pdf_path=f"/tmp/{name}.pdf",
                              extractor="fake")


def meeting(s, company):
    return s.exec(select(Meeting).where(Meeting.company == company)).one()


def attendee_names(s, conf_id, company):
    detail = service.conference_detail(s, conf_id, "ics")
    return [a.name for a in next(m for m in detail.meetings if m.company == company).attendees]


def ids(s):
    return {a.name: a.id for a in service.list_analysts(s)}


def test_new_conferences_record_the_broker_baseline(seeded):
    conf = conf_a(seeded)
    cobalt = meeting(seeded, "Cobalt Freight Lines")
    assert ExtractedMeeting.model_validate_json(cobalt.source_json).start == "10:00"
    assert len(rs.baseline_rows(seeded, conf.id)) == 12


def test_revised_pdf_matches_its_conference(seeded):
    conf = conf_a(seeded)
    service.create_conference(seeded, sample("broker_b_by_company"), pdf_filename="b.pdf", pdf_path="/tmp/b.pdf",
                              extractor="fake")
    assert rs.find_matching_conference(seeded, sample("broker_a_grid_v2")).id == conf.id
    assert rs.find_matching_conference(seeded, sample("broker_c_itinerary")) is None


def test_match_by_hotel_and_dates_after_rename(seeded):
    conf = conf_a(seeded)
    service.update_conference(seeded, conf.id, ConferenceUpdate(name="NYC industrials trip"))
    assert rs.find_matching_conference(seeded, sample("broker_a_grid_v2")).id == conf.id


def test_pending_revision_lists_the_five_changes(seeded):
    conf = conf_a(seeded)
    rev, superseded = revise(seeded, conf)
    assert (rev.number, rev.status, superseded) == (2, "pending", [])
    out = rs.revision_out(seeded, rev)
    assert [c.kind for c in out.changes] == ["changed", "changed", "changed", "removed", "added"]
    assert out.unchanged_count == 8
    assert out.changes[0].fields[0].field in ("start", "end")
    assert out.changes[4].new.company == "Atlas Rail Systems"
    detail = service.conference_detail(seeded, conf.id, "ics")
    assert detail.pending_revision.id == rev.id and detail.revision_number == 1


def test_apply_all_updates_meetings_and_keeps_verification(seeded):
    conf = conf_a(seeded)
    service.confirm_ready(seeded, conf.id)
    service.send_conference(seeded, conf.id, IcsSink())
    rev, _ = revise(seeded, conf)
    conference, old_pdf = rs.apply_revision(seeded, rev.id, None, 45)
    assert old_pdf == "/tmp/a.pdf" and conference.pdf_filename == "broker_a_grid_v2.pdf"
    cobalt = meeting(seeded, "Cobalt Freight Lines")
    assert (cobalt.start_time.strftime("%H:%M"), cobalt.end_time.strftime("%H:%M"), cobalt.status) == (
        "14:30", "15:15", "confirmed")
    assert meeting(seeded, "Meridian Rail Holdings").room == "Suite 1505"
    assert attendee_names(seeded, conf.id, "Halcyon Aerostructures") == ["Jordan Lee", "Taylor Brooks"]
    assert seeded.exec(select(Meeting).where(Meeting.company == "Tidewater Pumps")).first() is None  # never sent
    assert meeting(seeded, "Atlas Rail Systems").status == "confirmed"
    assert attendee_names(seeded, conf.id, "Atlas Rail Systems") == ["Avery Kim"]
    assert seeded.get(Revision, rev.id).status == "applied"
    plan = service.plan_conference(seeded, conf.id, "ics")
    assert sorted((a.kind, a.analyst_name) for a in plan) == [
        ("create", "Avery Kim"), ("create", "Jordan Lee"), ("update", "Avery Kim"),
        ("update", "Morgan Diaz"), ("update", "Riley Chen"), ("update", "Taylor Brooks")]
    detail = service.conference_detail(seeded, conf.id, "ics")
    assert detail.revision_number == 2 and detail.pending_revision is None


def test_rejected_changes_come_back_next_time(seeded):
    conf = conf_a(seeded)
    rev, _ = revise(seeded, conf)
    rs.apply_revision(seeded, rev.id, ["c1"], 45)
    assert meeting(seeded, "Meridian Rail Holdings").room == "TBD"
    rev2, _ = revise(seeded, conf)
    assert rev2.number == 3
    assert [c.company for c in rs.revision_out(seeded, rev2).changes] == [
        "Halcyon Aerostructures", "Meridian Rail Holdings", "Tidewater Pumps", "Atlas Rail Systems"]


def test_manual_edits_are_not_broker_changes(seeded):
    conf = conf_a(seeded)
    lumen = meeting(seeded, "Lumen Sensor Works")
    service.update_meeting(seeded, lumen.id, MeetingUpdate(room="Salon 9"), 45)
    manual = service.add_meeting(seeded, conf.id, MeetingCreate(company="Coffee with IR", date="2026-11-10",
                                                                start="17:00"), 45)
    rev, _ = revise(seeded, conf)
    companies = [c.company for c in rs.revision_out(seeded, rev).changes]
    assert "Lumen Sensor Works" not in companies and "Coffee with IR" not in companies
    rs.apply_revision(seeded, rev.id, None, 45)
    assert meeting(seeded, "Lumen Sensor Works").room == "Salon 9"
    assert seeded.get(Meeting, manual.id) is not None


def test_removed_sent_meeting_is_cancelled(seeded):
    conf = conf_a(seeded)
    tide = meeting(seeded, "Tidewater Pumps")
    service.update_meeting(seeded, tide.id, MeetingUpdate(attendee_ids=[ids(seeded)["Jordan Lee"]],
                                                          ignored_names=["Chris Wong"]), 45)
    service.confirm_meeting(seeded, tide.id)
    service.send_conference(seeded, conf.id, IcsSink())
    rev, _ = revise(seeded, conf)
    rs.apply_revision(seeded, rev.id, ["c4"], 45)
    assert meeting(seeded, "Tidewater Pumps").status == "cancelled"
    assert [(a.kind, a.analyst_name) for a in service.plan_conference(seeded, conf.id, "ics")] == [
        ("cancel", "Jordan Lee")]


def test_revision_rules(seeded):
    conf = conf_a(seeded)
    rev, _ = revise(seeded, conf)
    rev2, superseded = revise(seeded, conf)
    assert superseded == ["/tmp/broker_a_grid_v2.pdf"]
    assert seeded.get(Revision, rev.id).status == "discarded"
    with pytest.raises(service.Conflict):
        rs.apply_revision(seeded, rev.id, None, 45)
    with pytest.raises(service.InvalidInput):
        rs.apply_revision(seeded, rev2.id, ["c99"], 45)
    assert rs.discard_revision(seeded, rev2.id) == "/tmp/broker_a_grid_v2.pdf"
    assert service.conference_detail(seeded, conf.id, "ics").pending_revision is None
    with pytest.raises(service.NotFound):
        rs.get_revision(seeded, 999)


def test_revision_can_become_a_new_conference(seeded):
    conf = conf_a(seeded)
    rev, _ = revise(seeded, conf)
    new_conf = rs.revision_as_new_conference(seeded, rev.id, 45)
    assert new_conf.id != conf.id and new_conf.pdf_path == "/tmp/broker_a_grid_v2.pdf"
    assert len(service.conference_detail(seeded, new_conf.id, "ics").meetings) == 12
    assert seeded.get(Revision, rev.id).status == "discarded"


def test_delete_conference_removes_revisions(seeded):
    conf = conf_a(seeded)
    revise(seeded, conf)
    assert rs.revision_pdf_paths(seeded, conf.id) == ["/tmp/broker_a_grid_v2.pdf"]
    service.delete_conference(seeded, conf.id)
    assert seeded.exec(select(Revision)).all() == []


def test_dismissed_names_stay_dismissed(seeded):
    conf = conf_a(seeded)
    halcyon = meeting(seeded, "Halcyon Aerostructures")
    service.update_meeting(seeded, halcyon.id, MeetingUpdate(attendee_ids=[], ignored_names=["Taylor Brooks"]), 45)
    rev, _ = revise(seeded, conf)
    rs.apply_revision(seeded, rev.id, None, 45)
    assert attendee_names(seeded, conf.id, "Halcyon Aerostructures") == ["Jordan Lee"]


def test_dismissed_addressee_is_not_the_fallback(seeded):
    itinerary = sample("broker_c_itinerary")  # addressed to Sam Patel; rows list nobody
    first = itinerary.meetings[0]
    base = itinerary.model_copy(update={"meetings": [first.model_copy(update={"firm_attendees": ["Avery Kim"]}),
                                                     *itinerary.meetings[1:]]})
    conf = service.create_conference(seeded, base, pdf_filename="c.pdf", pdf_path="/tmp/c.pdf", extractor="fake")
    row = meeting(seeded, first.company)
    service.update_meeting(seeded, row.id, MeetingUpdate(ignored_names=["Sam Patel"]), 45)
    rev, _ = rs.create_revision(seeded, conf, itinerary, pdf_filename="c2.pdf", pdf_path="/tmp/c2.pdf",
                                extractor="fake")
    rs.apply_revision(seeded, rev.id, None, 45)
    assert attendee_names(seeded, conf.id, first.company) == []


def sent_conf_a(s):
    conf = conf_a(s)
    service.confirm_ready(s, conf.id)
    service.send_conference(s, conf.id, IcsSink())
    return conf


def planned_for(s, conf_id, company):
    mid = meeting(s, company).id
    return sorted((a.kind, a.analyst_name) for a in service.plan_conference(s, conf_id, "ics") if a.meeting_id == mid)


def test_unsynced_manual_edit_still_updates_after_apply(seeded):
    conf = sent_conf_a(seeded)
    lumen = meeting(seeded, "Lumen Sensor Works")
    service.update_meeting(seeded, lumen.id, MeetingUpdate(room="Salon 9"), 45)  # not synced yet
    rev, _ = revise(seeded, conf)
    rs.apply_revision(seeded, rev.id, None, 45)
    assert planned_for(seeded, conf.id, "Lumen Sensor Works") == [("update", "Jordan Lee")]


def test_source_page_or_pdf_name_alone_plans_nothing(seeded):
    conf = sent_conf_a(seeded)
    revised = sample("broker_a_grid_v2")
    rows = [m.model_copy(update={"page": 3}) if m.company == "Northwind Robotics" else m for m in revised.meetings]
    rev, _ = rs.create_revision(seeded, conf, revised.model_copy(update={"meetings": rows}),
                                pdf_filename="broker_a_grid_v2.pdf", pdf_path="/tmp/v2.pdf", extractor="fake")
    rs.apply_revision(seeded, rev.id, None, 45)
    northwind = meeting(seeded, "Northwind Robotics")
    assert northwind.source_page == 3
    assert planned_for(seeded, conf.id, "Northwind Robotics") == []  # page and PDF name changed
    assert planned_for(seeded, conf.id, "Borealis Grid Systems") == []  # PDF name changed
    record = seeded.exec(select(SyncRecord).where(SyncRecord.meeting_id == northwind.id)).first()
    assert "Source: broker_a_grid.pdf, page 1" in record.content_json  # still what was actually sent


def test_real_changes_update_every_colleague(seeded):
    conf = sent_conf_a(seeded)
    rev, _ = revise(seeded, conf)
    rs.apply_revision(seeded, rev.id, None, 45)
    assert planned_for(seeded, conf.id, "Cobalt Freight Lines") == [("update", "Avery Kim"), ("update", "Riley Chen")]
    cobalt = meeting(seeded, "Cobalt Freight Lines").id
    bodies = {a.content.body for a in service.plan_conference(seeded, conf.id, "ics") if a.meeting_id == cobalt}
    assert all(b.endswith("Source: broker_a_grid_v2.pdf, page 1") for b in bodies)
