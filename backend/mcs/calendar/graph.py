"""Graph sink: writes events straight into each colleague's calendar via delegate access."""
import datetime as dt
import time
from typing import Callable, Sequence
from urllib.parse import quote

import httpx

from mcs.calendar.content import EventContent
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.planner import SyncAction, SyncOutcome

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RETRY_AFTER = 10.0


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def event_payload(content: EventContent) -> dict:
    return {
        "subject": content.subject,
        "body": {"contentType": "text", "content": content.body},
        "start": {"dateTime": _utc(content.start_utc), "timeZone": "UTC"},
        "end": {"dateTime": _utc(content.end_utc), "timeZone": "UTC"},
        "location": {"displayName": content.location},
        "showAs": "busy",
    }


class GraphSink:
    name = "graph"

    def __init__(self, token_provider: Callable[[], str], client: httpx.Client,
                 sleep: Callable[[float], None] = time.sleep):
        self.token_provider = token_provider
        self.client = client
        self.sleep = sleep

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]:
        try:
            token = self.token_provider()
        except GraphAuthError as exc:
            return [SyncOutcome(a, ok=False, external_id=a.external_id, error=str(exc)) for a in actions]
        headers = {"Authorization": f"Bearer {token}"}
        return [self._apply_one(a, headers) for a in actions]

    def _apply_one(self, action: SyncAction, headers: dict) -> SyncOutcome:
        user = quote(action.analyst_email, safe="@")
        try:
            if action.kind == "create":
                body = {**event_payload(action.content),
                        "transactionId": f"mcs-{action.meeting_id}-{action.analyst_id}-{action.sequence}"}
                resp = self._send("POST", f"/users/{user}/calendar/events", headers, body)
                if resp.status_code in (200, 201):
                    event_id = self._event_id(resp)
                    if event_id is None:
                        return SyncOutcome(action, ok=False, external_id=action.external_id,
                                           error="Graph error: no event id in the response")
                    return SyncOutcome(action, ok=True, external_id=event_id)
            elif action.kind == "update":
                resp = self._send("PATCH", f"/users/{user}/events/{quote(action.external_id, safe='')}",
                                  headers, event_payload(action.content))
                if resp.status_code == 200:
                    return SyncOutcome(action, ok=True, external_id=action.external_id)
            else:
                resp = self._send("DELETE", f"/users/{user}/events/{quote(action.external_id, safe='')}", headers)
                if resp.status_code in (200, 204, 404):
                    return SyncOutcome(action, ok=True, external_id=action.external_id)
        except httpx.HTTPError as exc:
            return SyncOutcome(action, ok=False, external_id=action.external_id,
                               error=f"Could not reach Microsoft Graph ({exc.__class__.__name__}).")
        return SyncOutcome(action, ok=False, external_id=action.external_id, error=self._error(resp, action))

    def _send(self, method: str, path: str, headers: dict, body: dict | None = None) -> httpx.Response:
        resp = self.client.request(method, path, headers=headers, json=body)
        if resp.status_code == 429:
            try:
                wait = float(resp.headers.get("Retry-After", "1"))
            except ValueError:
                wait = 1.0
            self.sleep(min(wait, MAX_RETRY_AFTER))
            resp = self.client.request(method, path, headers=headers, json=body)
        return resp

    @staticmethod
    def _event_id(resp: httpx.Response) -> str | None:
        """The created event's id, or None when the body isn't JSON or has no usable id."""
        try:
            data = resp.json()
        except ValueError:
            return None
        event_id = data.get("id") if isinstance(data, dict) else None
        return event_id if isinstance(event_id, str) and event_id else None

    @staticmethod
    def _error(resp: httpx.Response, action: SyncAction) -> str:
        if resp.status_code == 401:
            return "Sign in to Microsoft again."
        if resp.status_code == 403:
            return f"No delegate access to {action.analyst_email}'s calendar."
        try:
            message = resp.json().get("error", {}).get("message", "")
        except ValueError:
            message = ""
        return f"Graph error {resp.status_code}: {message}".strip().rstrip(":")
