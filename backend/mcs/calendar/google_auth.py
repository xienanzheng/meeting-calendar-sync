"""Local installed-app Google authorization; credentials stay in the ignored data folder."""
import json
import os
import threading
from pathlib import Path

import httpx
from google.auth.exceptions import GoogleAuthError as ProviderError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_lock = threading.Lock()


class GoogleAuthError(Exception):
    pass


class GoogleAuth:
    def __init__(self, path: Path):
        self.path = path

    def save_json(self, value: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as out:
                out.write(value)
            temp.replace(self.path)
        finally:
            temp.unlink(missing_ok=True)

    def token(self):
        with _lock:
            if not self.path.exists():
                raise GoogleAuthError("Connect Google Calendar first with mcs google-login, then Retry.")
            try:
                credentials = Credentials.from_authorized_user_file(self.path)
                if not credentials.valid:
                    credentials.refresh(Request())
                    self.save_json(credentials.to_json())
                return credentials.token
            except (ProviderError, ValueError, OSError):
                raise GoogleAuthError("Google authorization expired. Run mcs google-login again, then Retry.") from None

    def authorize(self, client_file: Path, expected_account: str):
        flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
        credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=False,
                                            timeout_seconds=900, login_hint=expected_account,
                                            prompt="consent", access_type="offline")
        # Check identity before saving or allowing the app to write anything.
        with httpx.Client(timeout=30) as client:
            response = client.get("https://www.googleapis.com/calendar/v3/users/me/calendarList/primary",
                                  headers={"Authorization": f"Bearer {credentials.token}"})
            if response.status_code != 200:
                raise GoogleAuthError("Google sign-in completed, but calendar access was not granted.")
            primary = response.json()
            if not primary.get("primary") or primary.get("id", "").casefold() != expected_account.casefold():
                raise GoogleAuthError(f"Sign in as {expected_account}; no credentials were saved for the other account.")
        with _lock:
            self.save_json(credentials.to_json())
