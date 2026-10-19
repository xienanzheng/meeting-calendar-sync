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
                 run_in_background: Callable[[Callable[[], None]], None] | None = None,
                 *, scopes: list[str] | None = None, expected_account: str | None = None):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self._app_factory = app_factory
        self._run = run_in_background or _thread
        self._app = None
        self._lock = threading.Lock()
        self._pending = False
        self._error: str | None = None
        self.scopes = list(scopes) if scopes is not None else SCOPES
        self.expected_account = expected_account

    def _account(self, app):
        accounts = app.get_accounts() if app else []
        if self.expected_account:
            return next((a for a in accounts if a.get("username", "").casefold() ==
                         self.expected_account.casefold()), None)
        return accounts[0] if accounts else None

    def _account_error(self) -> str:
        return f"Sign in as {self.expected_account} to use this demo calendar."

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
        flow = app.initiate_device_flow(scopes=self.scopes)
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
            selected = self._account(app)
            if selected:
                signed_in, account = True, selected.get("username")
        with self._lock:
            error = self._error
            if self.expected_account and app is not None and app.get_accounts():
                error = None if signed_in else self._account_error()
            return {"configured": self.configured, "signed_in": signed_in, "pending": self._pending,
                    "account": account, "error": error}

    def token(self) -> str:
        app = self._application()
        account = self._account(app)
        if account is None:
            raise GraphAuthError(self._account_error() if self.expected_account else "Sign in to Microsoft first.")
        result = app.acquire_token_silent(self.scopes, account=account)
        if not result or "access_token" not in result:
            raise GraphAuthError("Sign in to Microsoft again.")
        return result["access_token"]
