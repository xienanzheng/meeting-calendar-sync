import json
import stat
from types import SimpleNamespace

import httpx

import pytest


def test_missing_google_authorization_never_starts_interactive_login(tmp_path):
    from mcs.calendar.google_auth import GoogleAuth, GoogleAuthError
    with pytest.raises(GoogleAuthError, match="google-login"):
        GoogleAuth(tmp_path / "oauth.json").token()


def test_google_token_file_is_private_and_existing_valid_token_is_reused(tmp_path):
    from mcs.calendar.google_auth import GoogleAuth
    path = tmp_path / "oauth.json"
    auth = GoogleAuth(path)
    auth.save_json(json.dumps({"token": "test-token", "refresh_token": "test-refresh", "client_id": "test-client",
                              "client_secret": "test-secret", "expiry": "2099-01-01T00:00:00Z"}))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert auth.token() == "test-token"


@pytest.mark.parametrize("account", ["isaac@example.com", "other@example.com"])
def test_authorization_checks_primary_identity_directly_before_saving(tmp_path, monkeypatch, account):
    from google.oauth2.credentials import Credentials
    from mcs.calendar.google_auth import GoogleAuth, GoogleAuthError
    credentials = Credentials.from_authorized_user_info({"token": "test-token", "refresh_token": "test-refresh",
        "client_id": "test-client", "client_secret": "test-secret", "expiry": "2099-01-01T00:00:00Z"})
    flow = SimpleNamespace(run_local_server=lambda **kw: credentials)
    monkeypatch.setattr("mcs.calendar.google_auth.InstalledAppFlow.from_client_secrets_file", lambda *a, **kw: flow)
    def handler(req):
        assert req.url.path == "/calendar/v3/users/me/calendarList/primary"
        return httpx.Response(200, json={"id": account, "primary": True})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("mcs.calendar.google_auth.httpx.Client", lambda **kw: client)
    path = tmp_path / "oauth.json"
    auth = GoogleAuth(path)
    if account == "isaac@example.com":
        auth.authorize(tmp_path / "client.json", "isaac@example.com")
        assert auth.token() == "test-token"
    else:
        with pytest.raises(GoogleAuthError, match="isaac@example.com"):
            auth.authorize(tmp_path / "client.json", "isaac@example.com")
        assert not path.exists()
