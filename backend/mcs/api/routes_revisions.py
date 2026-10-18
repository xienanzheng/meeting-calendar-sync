from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from mcs import revision_service, service
from mcs.api.autosync import auto_sync
from mcs.api.deps import get_app_settings, get_session
from mcs.api.routes_conferences import _remove_upload
from mcs.config import Settings
from mcs.schemas import ApplyRevisionIn, ConferenceDetail

router = APIRouter(prefix="/api/revisions")


@router.get("/{revision_id}/pdf")
def get_pdf(revision_id: int, session: Session = Depends(get_session)):
    revision = revision_service.get_revision(session, revision_id)
    path = Path(revision.pdf_path)
    if not path.is_file():
        raise service.NotFound("The uploaded PDF is no longer on disk.")
    return FileResponse(path, media_type="application/pdf", filename=revision.pdf_filename,
                        content_disposition_type="inline")


@router.post("/{revision_id}/apply", response_model=ConferenceDetail)
def apply(revision_id: int, request: Request, body: ApplyRevisionIn | None = None,
         session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    conference, old_pdf = revision_service.apply_revision(
        session, revision_id, body.accepted if body else None, settings.default_meeting_minutes)
    _remove_upload(old_pdf, settings)
    summary = auto_sync(request, session, conference.id)
    detail = service.conference_detail(session, conference.id, settings.calendar_sink)
    detail.last_sync = summary
    return detail


@router.post("/{revision_id}/discard", response_model=ConferenceDetail)
def discard(revision_id: int, session: Session = Depends(get_session),
           settings: Settings = Depends(get_app_settings)):
    conference_id = revision_service.get_revision(session, revision_id).conference_id
    pdf_path = revision_service.discard_revision(session, revision_id)
    _remove_upload(pdf_path, settings)
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.post("/{revision_id}/as-new-conference", response_model=ConferenceDetail, status_code=201)
def as_new_conference(revision_id: int, session: Session = Depends(get_session),
                      settings: Settings = Depends(get_app_settings)):
    conference = revision_service.revision_as_new_conference(session, revision_id, settings.default_meeting_minutes)
    return service.conference_detail(session, conference.id, settings.calendar_sink)
