from typing import Iterator

from fastapi import Request
from sqlmodel import Session

from mcs.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
