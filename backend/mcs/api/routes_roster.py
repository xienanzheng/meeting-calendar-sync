from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from mcs import service
from mcs.api.deps import get_session
from mcs.schemas import AnalystIn, AnalystOut, AnalystUpdate

router = APIRouter(prefix="/api/roster")


@router.get("", response_model=list[AnalystOut])
def list_roster(session: Session = Depends(get_session)):
    return service.list_analysts(session)


@router.post("", response_model=AnalystOut, status_code=201)
def create(body: AnalystIn, session: Session = Depends(get_session)):
    return service.create_analyst(session, body)


@router.patch("/{analyst_id}", response_model=AnalystOut)
def update(analyst_id: int, body: AnalystUpdate, session: Session = Depends(get_session)):
    return service.update_analyst(session, analyst_id, body)


@router.delete("/{analyst_id}", status_code=204)
def remove(analyst_id: int, session: Session = Depends(get_session)):
    service.delete_analyst(session, analyst_id)
    return Response(status_code=204)
