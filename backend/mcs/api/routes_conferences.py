import re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from mcs import revision_service, service
from mcs.api.autosync import auto_sync
from mcs.api.deps import get_app_settings, get_session
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.ics import analyst_slug, render_ics, zip_files
from mcs.config import Settings
from mcs.extraction import ExtractionResult
from mcs.models import Analyst
from mcs.schemas import (
    ConferenceDetail, ConferenceSummary, ConferenceUpdate, ConfirmReadyIn, MeetingCreate, SendResult,
)

router = APIRouter(prefix="/api/conferences")


def _synced_detail(request: Request, session: Session, conference_id: int, settings: Settings) -> ConferenceDetail:
    summary = auto_sync(request, session, conference_id)
    detail = service.conference_detail(session, conference_id, settings.calendar_sink)
    detail.last_sync = summary
    return detail


def _remove_upload(path: str | None, settings: Settings) -> None:
    """Delete a stored upload. Only files whose resolved path is inside settings.uploads_dir are ever
    touched, and a file that's already missing is tolerated."""
    if not path:
        return
    resolved = Path(path).resolve()
    if settings.uploads_dir.resolve() not in resolved.parents:
        return
    resolved.unlink(missing_ok=True)


def _parse_ids(raw: str) -> list[int]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise service.InvalidInput("default_attendee_ids must be a comma-separated list of ids.") from None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "conference"


def _read_pdf(file: UploadFile, settings: Settings) -> tuple[bytes, str]:
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if not data:
        raise service.InvalidInput("The file is empty.")
    if len(data) > limit:
        raise service.InvalidInput(f"The file is larger than {settings.max_upload_mb} MB.")
    name = Path(file.filename or "schedule.pdf").name
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise service.InvalidInput("Upload a PDF file.")
    return data, name


def _extract(request: Request, data: bytes) -> tuple[ExtractionResult, str]:
    extractor = request.app.state.extractor_factory()
    with tempfile.TemporaryDirectory(prefix="mcs-upload-") as tmp:
        tmp_pdf = Path(tmp) / "upload.pdf"
        tmp_pdf.write_bytes(data)
        result = extractor.extract(tmp_pdf)
    return result, extractor.name


@router.post("", response_model=ConferenceDetail, status_code=201)
def upload(request: Request, file: UploadFile = File(...), default_attendee_ids: str = Form(""),
           mode: str = Form("auto"), session: Session = Depends(get_session),
           settings: Settings = Depends(get_app_settings)):
    if mode not in ("auto", "new"):
        raise service.InvalidInput("mode must be 'auto' or 'new'.")
    data, name = _read_pdf(file, settings)
    ids = service.check_attendee_ids(session, _parse_ids(default_attendee_ids))
    result, extractor_name = _extract(request, data)
    match = revision_service.find_matching_conference(session, result) if mode == "auto" else None
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    stored = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
    stored.write_bytes(data)
    if match is not None:
        _, superseded = revision_service.create_revision(
            session, match, result, pdf_filename=name, pdf_path=str(stored), extractor=extractor_name)
        for path in superseded:
            _remove_upload(path, settings)
        return service.conference_detail(session, match.id, settings.calendar_sink)
    conference = service.create_conference(
        session, result, pdf_filename=name, pdf_path=str(stored), extractor=extractor_name,
        default_attendee_ids=ids, default_minutes=settings.default_meeting_minutes,
    )
    return service.conference_detail(session, conference.id, settings.calendar_sink, skipped_items=result.skipped_items)


@router.get("", response_model=list[ConferenceSummary])
def list_conferences(session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    return service.list_conference_summaries(session, settings.calendar_sink)


@router.get("/{conference_id}", response_model=ConferenceDetail)
def get_conference(conference_id: int, session: Session = Depends(get_session),
                   settings: Settings = Depends(get_app_settings)):
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.patch("/{conference_id}", response_model=ConferenceDetail)
def patch_conference(conference_id: int, body: ConferenceUpdate, request: Request,
                     session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    service.update_conference(session, conference_id, body)
    return _synced_detail(request, session, conference_id, settings)


@router.delete("/{conference_id}", status_code=204)
def delete_conference(conference_id: int, session: Session = Depends(get_session),
                      settings: Settings = Depends(get_app_settings)):
    revision_paths = revision_service.revision_pdf_paths(session, conference_id)
    pdf_path = service.delete_conference(session, conference_id)
    _remove_upload(pdf_path, settings)
    for path in revision_paths:
        _remove_upload(path, settings)
    return Response(status_code=204)


@router.get("/{conference_id}/pdf")
def get_pdf(conference_id: int, session: Session = Depends(get_session)):
    conference = service.get_conference(session, conference_id)
    path = Path(conference.pdf_path)
    if not path.is_file():
        raise service.NotFound("The uploaded PDF is no longer on disk.")
    # no-cache: applying a revision swaps the file behind this same URL.
    return FileResponse(path, media_type="application/pdf", filename=conference.pdf_filename,
                        content_disposition_type="inline", headers={"Cache-Control": "no-cache"})


@router.post("/{conference_id}/revisions", response_model=ConferenceDetail, status_code=201)
def upload_revision(conference_id: int, request: Request, file: UploadFile = File(...),
                    session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    conference = service.get_conference(session, conference_id)
    data, name = _read_pdf(file, settings)
    result, extractor_name = _extract(request, data)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    stored = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
    stored.write_bytes(data)
    _, superseded = revision_service.create_revision(
        session, conference, result, pdf_filename=name, pdf_path=str(stored), extractor=extractor_name)
    for path in superseded:
        _remove_upload(path, settings)
    return service.conference_detail(session, conference.id, settings.calendar_sink)


@router.post("/{conference_id}/meetings", response_model=ConferenceDetail, status_code=201)
def add_meeting(conference_id: int, body: MeetingCreate, request: Request,
                session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    service.add_meeting(session, conference_id, body, settings.default_meeting_minutes)
    return _synced_detail(request, session, conference_id, settings)


@router.post("/{conference_id}/confirm-ready", response_model=ConferenceDetail)
def confirm_ready(conference_id: int, request: Request, body: ConfirmReadyIn | None = None,
                  session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    service.confirm_ready(session, conference_id, body.meeting_ids if body else None)
    return _synced_detail(request, session, conference_id, settings)


@router.post("/{conference_id}/send", response_model=SendResult)
def send(conference_id: int, request: Request, dry_run: bool = True, session: Session = Depends(get_session),
         settings: Settings = Depends(get_app_settings)):
    if dry_run:
        plan = service.plan_conference(session, conference_id, settings.calendar_sink)
        return service.send_result(session, conference_id, settings.calendar_sink, plan, dry_run=True)
    sink = request.app.state.sink_factory()
    if sink.name in ("graph", "outlook-demo") and not request.app.state.graph_auth.status()["signed_in"]:
        raise GraphAuthError("Sign in to Microsoft first.")
    outcomes = service.send_conference(session, conference_id, sink)
    return service.send_result(session, conference_id, sink.name, outcomes, dry_run=False)


@router.get("/{conference_id}/ics.zip")
def ics_zip(conference_id: int, session: Session = Depends(get_session)):
    conference = service.get_conference(session, conference_id)
    files = {}
    for analyst in service.list_analysts(session):
        records = service.ics_records_for(session, conference_id, analyst.id)
        if records:
            files[f"{analyst_slug(analyst.name)}.ics"] = render_ics(records)
    if not files:
        raise service.NotFound("Nothing has been sent yet.")
    return Response(zip_files(files), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{_slug(conference.name)}-calendars.zip"'})


@router.get("/{conference_id}/ics/{analyst_id}")
def ics_one(conference_id: int, analyst_id: int, session: Session = Depends(get_session)):
    conference = service.get_conference(session, conference_id)
    analyst = session.get(Analyst, analyst_id)
    if analyst is None:
        raise service.NotFound("Colleague not found.")
    records = service.ics_records_for(session, conference_id, analyst_id)
    if not records:
        raise service.NotFound("Nothing has been sent to this colleague yet.")
    filename = f"{analyst_slug(analyst.name)}-{_slug(conference.name)}.ics"
    return Response(render_ics(records), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
