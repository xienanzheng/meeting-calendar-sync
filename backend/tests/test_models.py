import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from mcs.models import Analyst, Conference, Meeting, MeetingAttendee, SyncRecord


def _conference(session):
    c = Conference(name="Industrials Conference 2026", timezone="America/New_York")
    session.add(c)
    session.commit()
    return c


def test_roundtrip_all_tables(session):
    a = Analyst(name="Avery Kim", email="avery.kim@example.com", aliases=["A. Kim"])
    session.add(a)
    c = _conference(session)
    m = Meeting(
        conference_id=c.id, date=dt.date(2026, 11, 10), start_time=dt.time(8, 0), end_time=dt.time(8, 45),
        company="Northwind Robotics", company_attendees=["Dana Shore, CFO"], raw_attendee_names=["Avery Kim"],
    )
    session.add(m)
    session.commit()
    session.add(MeetingAttendee(meeting_id=m.id, analyst_id=a.id, match="exact"))
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="ics", external_id="uid-1",
                           content_hash="h", content_json="{}"))
    session.commit()
    session.expire_all()

    got = session.get(Meeting, m.id)
    assert got.company_attendees == ["Dana Shore, CFO"]
    assert got.raw_attendee_names == ["Avery Kim"]
    assert got.ignored_names == []
    assert (got.status, got.format, got.end_assumed, got.room) == ("draft", "one_on_one", False, "")
    assert session.get(Analyst, a.id).aliases == ["A. Kim"]
    assert session.get(Analyst, a.id).active is True
    rec = session.exec(select(SyncRecord)).one()
    assert (rec.sequence, rec.state, rec.last_error) == (0, "active", None)


def test_analyst_email_unique(session):
    session.add(Analyst(name="A", email="a@example.com"))
    session.commit()
    session.add(Analyst(name="B", email="a@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_sync_record_unique_per_meeting_analyst_sink(session):
    a = Analyst(name="A", email="a@example.com")
    session.add(a)
    c = _conference(session)
    m = Meeting(conference_id=c.id, company="X")
    session.add(m)
    session.commit()
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="ics"))
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="graph"))
    session.commit()
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="ics"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_keys_enforced(session):
    session.add(Meeting(conference_id=999, company="X"))
    with pytest.raises(IntegrityError):
        session.commit()
