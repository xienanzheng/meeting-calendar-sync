from fastapi import APIRouter, Depends
from sqlmodel import Session

from mcs import service
from mcs.api.deps import get_app_settings, get_session
from mcs.config import Settings
from mcs.schemas import ConferenceDetail, MeetingUpdate

router = APIRouter(prefix="/api/meetings")


def _detail(session: Session, conference_id: int, settings: Settings) -> ConferenceDetail:
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.patch("/{meeting_id}", response_model=ConferenceDetail)
def patch_meeting(meeting_id: int, body: MeetingUpdate, session: Session = Depends(get_session),
                  settings: Settings = Depends(get_app_settings)):
    meeting = service.update_meeting(session, meeting_id, body, settings.default_meeting_minutes)
    return _detail(session, meeting.conference_id, settings)


@router.post("/{meeting_id}/confirm", response_model=ConferenceDetail)
def confirm(meeting_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    meeting = service.confirm_meeting(session, meeting_id)
    return _detail(session, meeting.conference_id, settings)


@router.post("/{meeting_id}/unconfirm", response_model=ConferenceDetail)
def unconfirm(meeting_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    meeting = service.unconfirm_meeting(session, meeting_id)
    return _detail(session, meeting.conference_id, settings)


@router.delete("/{meeting_id}", response_model=ConferenceDetail)
def delete(meeting_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    conference_id = service.get_meeting(session, meeting_id).conference_id
    service.delete_meeting(session, meeting_id)
    return _detail(session, conference_id, settings)
