"""Own-account demo: persist and reuse one secondary Outlook calendar. No invitations."""
import hashlib
import json
import threading
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from mcs.calendar.graph import GRAPH_BASE, GraphSink
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.planner import SyncOutcome

DEMO_CALENDAR_NAME = "Meeting Calendar Sync Demo"
_binding_lock = threading.Lock()


class OutlookDemoSink:
    name = "outlook-demo"

    def __init__(self, token_provider, client: httpx.Client, data_dir: Path, account: str, client_id: str):
        self.token_provider, self.client = token_provider, client
        self.path = data_dir / "outlook-demo-target.json"
        self.account, self.client_id = account.casefold(), client_id

    def apply(self, conference, actions):
        if not actions:
            return []
        try:
            token = self.token_provider()  # GraphAuth enforces the selected account.
            with _binding_lock:
                calendar_id = self._calendar(token)
            # Stable retries, distinct transaction IDs even if a fresh DB reuses numerical IDs.
            namespace = hashlib.sha256(f"{calendar_id}:{conference.created_at.isoformat()}".encode()).hexdigest()[:24]
            return GraphSink(lambda: token, self.client, calendar_id=calendar_id,
                             transaction_namespace=namespace).apply(conference, actions)
        except (GraphAuthError, httpx.HTTPError, OSError, ValueError) as exc:
            if isinstance(exc, httpx.HTTPError):
                message = f"Could not reach Microsoft Graph ({exc.__class__.__name__})."
            elif isinstance(exc, (OSError, ValueError)):
                message = "Could not read or save the demo calendar binding. Check the local data folder."
            else:
                message = str(exc)
            return [SyncOutcome(a, ok=False, external_id=a.external_id, error=message) for a in actions]

    def _request(self, method, path, token, body=None):
        response = self.client.request(method, path, headers={"Authorization": f"Bearer {token}"}, json=body)
        if response.status_code not in (200, 201):
            raise GraphAuthError(f"Outlook demo calendar returned {response.status_code}. Check sign-in and calendar access, then Retry.")
        data = response.json()
        if not isinstance(data, dict):
            raise GraphAuthError("Microsoft returned an invalid demo calendar response.")
        return data

    @staticmethod
    def _validate(calendar):
        if (not isinstance(calendar, dict) or calendar.get("name") != DEMO_CALENDAR_NAME or
                calendar.get("isDefaultCalendar") is not False or
                not isinstance(calendar.get("id"), str) or not calendar["id"]):
            raise GraphAuthError("The demo requires its named secondary calendar; the default calendar cannot be used.")
        return calendar["id"]

    def _calendar(self, token):
        if self.path.exists():
            binding = json.loads(self.path.read_text())
            if (not isinstance(binding, dict) or binding.get("account") != self.account or
                    binding.get("client_id") != self.client_id):
                raise GraphAuthError("This data folder belongs to another demo account or app. Use a separate demo data folder.")
            calendar_id = binding.get("calendar_id")
            if not isinstance(calendar_id, str) or not calendar_id:
                raise GraphAuthError("The saved demo calendar binding is invalid.")
            calendar = self._request("GET", f"/me/calendars/{quote(calendar_id, safe='')}?$select=id,name,isDefaultCalendar", token)
            if self._validate(calendar) != calendar_id:
                raise GraphAuthError("Microsoft returned a different demo calendar. Sync stopped.")
            return calendar_id

        matches, path, visited = [], "/me/calendars?$select=id,name,isDefaultCalendar", set()
        while path:
            if path in visited or len(visited) >= 100:
                raise GraphAuthError("Could not finish listing Outlook calendars. Try again.")
            visited.add(path)
            page = self._request("GET", path, token)
            values = page.get("value")
            if not isinstance(values, list):
                raise GraphAuthError("Microsoft returned an invalid calendar list.")
            matches.extend(c for c in values if isinstance(c, dict) and c.get("name") == DEMO_CALENDAR_NAME)
            path = page.get("@odata.nextLink")
            if path:
                parsed = urlparse(path)
                base = urlparse(GRAPH_BASE)
                if (parsed.scheme != base.scheme or parsed.netloc != base.netloc or
                        parsed.path != base.path + "/me/calendars"):
                    raise GraphAuthError("Microsoft returned an unexpected calendar-list link. Sync stopped.")
        if len(matches) > 1:
            raise GraphAuthError(f"More than one calendar is named {DEMO_CALENDAR_NAME}. Rename the duplicate before retrying.")
        calendar = matches[0] if matches else self._request("POST", "/me/calendars", token, {"name": DEMO_CALENDAR_NAME})
        if "isDefaultCalendar" not in calendar and isinstance(calendar.get("id"), str) and calendar["id"]:
            calendar = self._request("GET", f"/me/calendars/{quote(calendar['id'], safe='')}?$select=id,name,isDefaultCalendar", token)
        calendar_id = self._validate(calendar)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"account": self.account, "client_id": self.client_id, "calendar_id": calendar_id}))
        temp.replace(self.path)
        return calendar_id
