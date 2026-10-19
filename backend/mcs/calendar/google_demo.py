"""Google Calendar fallback for the personal demo, isolated from the primary calendar."""
import hashlib
import json
import threading
from urllib.parse import quote

import httpx

from mcs.calendar.google_auth import GoogleAuthError
from mcs.calendar.outlook_demo import DEMO_CALENDAR_NAME
from mcs.calendar.planner import SyncOutcome

GOOGLE_BASE = "https://www.googleapis.com/calendar/v3"
_lock = threading.Lock()

GOOGLE_GREEN = "10"  # "Basil"


class GoogleDemoSink:
    name = "google-demo"

    def __init__(self, auth, client, data_dir, account):
        self.auth, self.client = auth, client
        self.path = data_dir / "google-demo-target.json"
        self.account = account.casefold()

    def _request(self, method, path, token, body=None, params=None):
        return self.client.request(method, path, headers={"Authorization": f"Bearer {token}"}, json=body, params=params)

    @staticmethod
    def _json(response):
        if response.status_code not in (200, 201):
            raise GoogleAuthError(f"Google Calendar returned {response.status_code}. Check authorization, then Retry.")
        result = response.json()
        if not isinstance(result, dict):
            raise GoogleAuthError("Google returned an invalid calendar response.")
        return result

    def _calendar(self, token):
        calendars, page, visited = [], None, set()
        while True:
            result = self._json(self._request("GET", "/users/me/calendarList", token,
                                             params={"minAccessRole": "owner", **({"pageToken": page} if page else {})}))
            items = result.get("items")
            if not isinstance(items, list):
                raise GoogleAuthError("Google returned an invalid calendar list.")
            calendars.extend(items)
            page = result.get("nextPageToken")
            if not page:
                break
            if page in visited or len(visited) >= 100:
                raise GoogleAuthError("Could not finish listing Google calendars.")
            visited.add(page)
        if not any(c.get("primary") and c.get("id", "").casefold() == self.account for c in calendars):
            raise GoogleAuthError(f"Sign in as {self.account}; this authorization belongs to a different Google account.")
        if self.path.exists():
            binding = json.loads(self.path.read_text())
            if binding.get("account") != self.account:
                raise GoogleAuthError("The demo data belongs to another Google account. Use a separate data folder.")
            calendar_id = binding.get("calendar_id")
            if not isinstance(calendar_id, str) or not calendar_id:
                raise GoogleAuthError("The Google demo calendar binding is invalid.")
            calendar = self._json(self._request("GET", "/users/me/calendarList/" + quote(calendar_id, safe=""), token))
            if calendar.get("id") != calendar_id:
                raise GoogleAuthError("Google returned a different calendar. Sync stopped.")
        else:
            matches = [c for c in calendars if c.get("summary") == DEMO_CALENDAR_NAME]
            if len(matches) > 1:
                raise GoogleAuthError("Multiple Google calendars have the demo name. Rename the duplicate before retrying.")
            if matches:
                calendar = matches[0]
            else:
                created = self._json(self._request("POST", "/calendars", token,
                                    {"summary": DEMO_CALENDAR_NAME, "timeZone": "America/Los_Angeles"}))
                calendar_id = created.get("id")
                if not isinstance(calendar_id, str) or not calendar_id:
                    raise GoogleAuthError("Google did not return the new calendar's ID.")
                calendar = self._json(self._request("GET", "/users/me/calendarList/" + quote(calendar_id, safe=""), token))
        calendar_id = calendar.get("id")
        owner = calendar.get("dataOwner")
        if (not isinstance(calendar_id, str) or not calendar_id or calendar_id.casefold() in ("primary", self.account)
                or calendar.get("primary") or calendar.get("accessRole") != "owner"
                or not isinstance(owner, str) or owner.casefold() != self.account
                or calendar.get("summary") != DEMO_CALENDAR_NAME):
            raise GoogleAuthError("The demo requires its own secondary Google calendar; primary and shared calendars cannot be used.")
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps({"account": self.account, "calendar_id": calendar_id}))
            temp.replace(self.path)
        return calendar_id

    def apply(self, conference, actions):
        if not actions:
            return []
        try:
            token = self.auth.token()
            with _lock:
                calendar_id = self._calendar(token)
        except (GoogleAuthError, httpx.HTTPError, ValueError, OSError) as exc:
            message = str(exc) if isinstance(exc, GoogleAuthError) else "Could not prepare the Google demo calendar. Check connection and local data, then Retry."
            return [SyncOutcome(a, False, a.external_id, message) for a in actions]
        return [self._apply_one(conference, calendar_id, token, a) for a in actions]

    def _apply_one(self, conference, calendar_id, token, action):
        root = f"/calendars/{quote(calendar_id, safe='')}/events"
        event_id = action.external_id
        try:
            if action.kind == "cancel":
                response = self._request("DELETE", f"{root}/{quote(event_id, safe='')}", token, params={"sendUpdates": "none"})
                if response.status_code in (200, 204, 404, 410):
                    return SyncOutcome(action, True, event_id)
            else:
                content = action.content
                body = {"summary": f"[Demo · {action.analyst_name}] {content.subject}",
                        "description": content.body, "location": content.location,
                        "start": {"dateTime": content.start_utc.isoformat()},
                        "end": {"dateTime": content.end_utc.isoformat()}}
                if content.categories:
                    body["colorId"] = GOOGLE_GREEN  # Google has no categories; its green stands in for the label
                if action.kind == "create":
                    identity = f"{calendar_id}:{conference.created_at.isoformat()}:{action.meeting_id}:{action.analyst_id}:{action.sequence}"
                    event_id = hashlib.sha256(identity.encode()).hexdigest()
                    response = self._request("POST", root, token, {**body, "id": event_id}, {"sendUpdates": "none"})
                    if response.status_code == 409:
                        response = self._request("PATCH", f"{root}/{event_id}", token, body, {"sendUpdates": "none"})
                else:
                    response = self._request("PATCH", f"{root}/{quote(event_id, safe='')}", token, body, {"sendUpdates": "none"})
                result = self._json(response)
                if result.get("id") == event_id:
                    return SyncOutcome(action, True, event_id)
                raise GoogleAuthError("Google returned a different event ID. Sync stopped.")
            raise GoogleAuthError(f"Google calendar update returned {response.status_code}. Use Retry.")
        except (GoogleAuthError, httpx.HTTPError, ValueError) as exc:
            message = str(exc) if isinstance(exc, GoogleAuthError) else "Could not update Google Calendar. Use Retry."
            return SyncOutcome(action, False, action.external_id, message)
