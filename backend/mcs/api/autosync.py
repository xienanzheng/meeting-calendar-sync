"""Approval sends: after CR approves or edits, bring calendars up to date in the same request.

A sync problem never fails her action; it is reported in `last_sync` instead.
"""
from fastapi import Request
from sqlmodel import Session

from mcs import service
from mcs.calendar import SinkNotConfigured
from mcs.calendar.graph_auth import GraphAuthError
from mcs.schemas import SyncSummary


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
        if sink.name == "graph" and not request.app.state.graph_auth.status()["signed_in"]:
            return SyncSummary(ok=0, failed=0, message="Sign in to Microsoft to update calendars.")
        outcomes = service.send_conference(session, conference_id, sink)
    except (SinkNotConfigured, GraphAuthError) as exc:
        return SyncSummary(ok=0, failed=0, message=str(exc))
    ok = sum(1 for o in outcomes if o.ok)
    failed = len(outcomes) - ok
    if failed:
        return SyncSummary(ok=ok, failed=failed,
                           message=f"{failed} calendar {_plural(failed, 'update', 'updates')} failed — use Retry.")
    return SyncSummary(ok=ok, failed=0, message=f"Updated {ok} calendar {_plural(ok, 'entry', 'entries')}.")
