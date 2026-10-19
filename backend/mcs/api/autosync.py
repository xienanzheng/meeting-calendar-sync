"""Approval sends: after CR approves or edits, bring calendars up to date in the same request.

A sync problem never fails her action; it is reported in `last_sync` instead.
"""
import logging

from fastapi import Request
from sqlmodel import Session

from mcs import service
from mcs.calendar import SinkNotConfigured
from mcs.calendar.graph_auth import GraphAuthError
from mcs.schemas import SyncSummary

log = logging.getLogger(__name__)
UNEXPECTED = "Calendar sync hit an unexpected error — use Retry."


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def auto_sync(request: Request, session: Session, conference_id: int) -> SyncSummary | None:
    settings = request.app.state.settings
    if not settings.auto_sync:
        return None
    if not service.plan_conference(session, conference_id, settings.calendar_sink):
        return SyncSummary(ok=0, failed=0, message="Calendars are up to date.")
    try:
        sink = request.app.state.sink_factory()
        if sink.name in ("graph", "outlook-demo"):
            status = request.app.state.graph_auth.status()
            if not status["signed_in"]:
                return SyncSummary(ok=0, failed=0, message=status["error"] or "Sign in to Microsoft to update calendars.")
        outcomes = service.send_conference(session, conference_id, sink)
    except (SinkNotConfigured, GraphAuthError) as exc:
        return SyncSummary(ok=0, failed=0, message=str(exc))
    except Exception:
        # The approval is already committed; drop any half-recorded sync work so the response can still be
        # read. The log gets the traceback only: no locals or request headers, so no token.
        session.rollback()
        log.exception("Calendar sync failed unexpectedly for conference %s", conference_id)
        return SyncSummary(ok=0, failed=0, message=UNEXPECTED)
    ok = sum(1 for o in outcomes if o.ok)
    failed = len(outcomes) - ok
    if failed:
        return SyncSummary(ok=ok, failed=failed,
                           message=f"{failed} calendar {_plural(failed, 'update', 'updates')} failed — use Retry.")
    return SyncSummary(ok=ok, failed=0, message=f"Updated {ok} calendar {_plural(ok, 'entry', 'entries')}.")
