"""Delegated Microsoft Graph sign-in (device code). Tokens stay in MSAL's in-memory cache only."""
import threading
from typing import Callable

import msal

SCOPES = ["Calendars.ReadWrite.Shared"]


class GraphAuthError(Exception):
    """Sign-in problem; the message is shown to the coordinator."""


def _thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class GraphAuth:
    def __init__(self, client_id: str | None, tenant_id: str | None,
                 app_factory=msal.PublicClientApplication,
                 run_in_background: Callable[[Callable[[], None]], None] | None = None):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self._app_factory = app_factory
        self._run = run_in_background or _thread
        self._app = None
        self._lock = threading.Lock()
        self._pending = False
        self._error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.tenant_id)

    def _application(self):
        if not self.configured:
            raise GraphAuthError("Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID.")
        with self._lock:
            if self._app is None:
                self._app = self._app_factory(self.client_id,
                                              authority=f"https://login.microsoftonline.com/{self.tenant_id}")
            return self._app

    def start_device_flow(self) -> dict:
        app = self._application()
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise GraphAuthError(flow.get("error_description") or "Could not start Microsoft sign-in.")
        with self._lock:
            self._pending, self._error = True, None

        def finish() -> None:
            result = app.acquire_token_by_device_flow(flow)
            with self._lock:
                self._pending = False
                if "access_token" not in result:
                    self._error = result.get("error_description") or "Microsoft sign-in failed."

        self._run(finish)
        return {"user_code": flow["user_code"], "verification_uri": flow["verification_uri"],
                "message": flow.get("message", ""), "expires_in": flow.get("expires_in")}

    def status(self) -> dict:
        signed_in, account = False, None
        with self._lock:
            app = self._app
        if self.configured and app is not None:
            accounts = app.get_accounts()
            if accounts:
                signed_in, account = True, accounts[0].get("username")
        with self._lock:
            return {"configured": self.configured, "signed_in": signed_in, "pending": self._pending,
                    "account": account, "error": self._error}

    def token(self) -> str:
        app = self._application()
        accounts = app.get_accounts()
        if not accounts:
            raise GraphAuthError("Sign in to Microsoft first.")
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            raise GraphAuthError("Sign in to Microsoft again.")
        return result["access_token"]
