import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Format = Literal["one_on_one", "group", "meal", "other"]
SyncState = Literal["not_sent", "sent", "changed", "failed", "cancelled"]
ReviewState = Literal["needs_attention", "ready", "verified", "sent", "cancelled"]


class FlagOut(BaseModel):
    code: str
    severity: str
    message: str


class AttendeeOut(BaseModel):
    analyst_id: int
    name: str
    email: str
    match: str
    sync: SyncState
    sync_error: str | None = None


class MeetingOut(BaseModel):
    id: int
    conference_id: int
    date: str | None
    start: str | None
    end: str | None
    end_assumed: bool
    room: str
    company: str
    ticker: str | None
    format: str
    company_attendees: list[str]
    raw_attendee_names: list[str]
    ignored_names: list[str]
    unmatched_names: list[str]
    notes: str
    source_page: int | None
    status: str
    review_state: ReviewState
    attendees: list[AttendeeOut]
    removed: list[AttendeeOut]  # colleagues taken off a sent meeting; removed from their calendar on next send
    flags: list[FlagOut]


class Counts(BaseModel):
    total: int = 0
    needs_attention: int = 0
    ready: int = 0
    verified: int = 0
    sent: int = 0
    cancelled: int = 0
    warnings: int = 0
    changed: int = 0
    failed: int = 0
    pending_actions: int = 0


class SyncSummary(BaseModel):
    ok: int
    failed: int
    message: str


class ConferenceSummary(BaseModel):
    id: int
    name: str
    broker: str
    hotel: str
    city: str
    timezone: str | None
    created_at: dt.datetime
    first_date: str | None
    last_date: str | None
    counts: Counts


class ConferenceDetail(ConferenceSummary):
    schedule_for: str
    pdf_filename: str
    extractor: str
    meetings: list[MeetingOut]
    skipped_items: int = 0
    last_sync: SyncSummary | None = None


class AnalystIn(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    aliases: list[str] = Field(default_factory=list)
    active: bool = True


class AnalystUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    aliases: list[str] | None = None
    active: bool | None = None


class AnalystOut(BaseModel):
    id: int
    name: str
    email: str
    aliases: list[str]
    active: bool


class MeetingCreate(BaseModel):
    company: str = Field(min_length=1)
    date: str | None = None
    start: str | None = None
    end: str | None = None
    room: str = ""
    ticker: str | None = None
    format: Format = "one_on_one"
    attendee_ids: list[int] = Field(default_factory=list)
    notes: str = ""


class MeetingUpdate(BaseModel):
    date: str | None = None
    start: str | None = None
    end: str | None = None
    room: str | None = None
    company: str | None = None
    ticker: str | None = None
    format: Format | None = None
    company_attendees: list[str] | None = None
    notes: str | None = None
    attendee_ids: list[int] | None = None
    ignored_names: list[str] | None = None


class ConferenceUpdate(BaseModel):
    name: str | None = None
    broker: str | None = None
    hotel: str | None = None
    city: str | None = None
    timezone: str | None = None


class ConfirmReadyIn(BaseModel):
    meeting_ids: list[int] | None = None


class SyncActionOut(BaseModel):
    kind: str
    meeting_id: int
    analyst_id: int
    analyst_name: str
    subject: str | None
    ok: bool | None = None
    error: str | None = None


class AnalystSendSummary(BaseModel):
    analyst_id: int
    name: str
    create: int = 0
    update: int = 0
    cancel: int = 0
    failed: int = 0
    download_url: str | None = None


class SendResult(BaseModel):
    sink: str
    dry_run: bool
    actions: list[SyncActionOut]
    by_analyst: list[AnalystSendSummary]
    ok_count: int = 0
    failed_count: int = 0
    zip_url: str | None = None
