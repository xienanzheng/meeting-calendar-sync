import datetime as dt

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Analyst(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    active: bool = True


class Conference(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    broker: str = ""
    hotel: str = ""
    city: str = ""
    timezone: str | None = None
    schedule_for: str = ""
    pdf_filename: str = ""
    pdf_path: str = ""
    extractor: str = ""
    created_at: dt.datetime = Field(default_factory=utcnow)


class Meeting(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conference_id: int = Field(foreign_key="conference.id", index=True)
    date: dt.date | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    end_assumed: bool = False
    room: str = ""
    company: str
    ticker: str | None = None
    format: str = "one_on_one"  # one_on_one | group | meal | other
    company_attendees: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    raw_attendee_names: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    ignored_names: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    notes: str = ""
    source_page: int | None = None
    source_json: str = ""  # the broker's last applied row (ExtractedMeeting JSON); empty for manual meetings
    status: str = "draft"  # draft | confirmed | cancelled
    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)


class Revision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conference_id: int = Field(foreign_key="conference.id", index=True)
    number: int
    pdf_filename: str = ""
    pdf_path: str = ""
    extractor: str = ""
    status: str = "pending"  # pending | applied | discarded
    result_json: str = ""  # the full revised ExtractionResult as JSON
    created_at: dt.datetime = Field(default_factory=utcnow)


class MeetingAttendee(SQLModel, table=True):
    meeting_id: int = Field(foreign_key="meeting.id", primary_key=True)
    analyst_id: int = Field(foreign_key="analyst.id", primary_key=True)
    match: str = "manual"  # exact | alias | initial | fuzzy | manual | default


class SyncRecord(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("meeting_id", "analyst_id", "sink"),)

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", index=True)
    analyst_id: int = Field(foreign_key="analyst.id")
    sink: str  # ics | graph
    external_id: str | None = None  # ICS UID or Graph event id; None until a create succeeds
    content_hash: str = ""
    content_json: str = ""  # last successfully sent EventContent as JSON
    sequence: int = 0
    state: str = "active"  # active | cancelled | failed
    last_error: str | None = None
    updated_at: dt.datetime = Field(default_factory=utcnow)
