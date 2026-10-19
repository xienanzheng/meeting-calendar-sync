import threading

import pytest

from mcs.calendar.graph_auth import SCOPES, GraphAuth, GraphAuthError


class FakeApp:
    def __init__(self, client_id, authority):
        self.client_id, self.authority = client_id, authority
        self.accounts = []
        self.flow = {"user_code": "ABCD-1234", "verification_uri": "https://microsoft.com/devicelogin",
                     "message": "To sign in, use a web browser...", "expires_in": 900}
        self.device_result = {"access_token": "tok"}
        self.silent_result = {"access_token": "tok"}
        self.scopes = None

    def initiate_device_flow(self, scopes):
        self.scopes = scopes
        return self.flow

    def acquire_token_by_device_flow(self, flow):
        if "access_token" in self.device_result:
            self.accounts = [{"username": "coordinator@example.com"}]
        return self.device_result

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return self.silent_result


def make(run=lambda fn: fn(), **app_overrides):
    apps = []

    def factory(client_id, authority):
        app = FakeApp(client_id, authority)
        for k, v in app_overrides.items():
            setattr(app, k, v)
        apps.append(app)
        return app

    return GraphAuth("client-id", "tenant-id", app_factory=factory, run_in_background=run), apps


def test_not_configured():
    auth = GraphAuth(None, None)
    assert auth.configured is False
    with pytest.raises(GraphAuthError, match="not configured"):
        auth.start_device_flow()
    assert auth.status() == {"configured": False, "signed_in": False, "pending": False, "account": None, "error": None}


def test_device_flow_signs_in():
    auth, apps = make()
    started = auth.start_device_flow()
    assert started["user_code"] == "ABCD-1234"
    assert started["verification_uri"] == "https://microsoft.com/devicelogin"
    assert apps[0].authority == "https://login.microsoftonline.com/tenant-id"
    assert apps[0].scopes == SCOPES == ["Calendars.ReadWrite.Shared"]
    status = auth.status()
    assert status["signed_in"] is True and status["account"] == "coordinator@example.com" and status["pending"] is False
    assert auth.token() == "tok"


def test_pending_until_background_finishes():
    jobs = []
    auth, _ = make(run=jobs.append)
    auth.start_device_flow()
    assert auth.status()["pending"] is True
    jobs[0]()
    assert auth.status()["pending"] is False


def test_declined_sign_in_reports_error():
    auth, _ = make(device_result={"error": "authorization_declined", "error_description": "User declined"})
    auth.start_device_flow()
    assert auth.status()["error"] == "User declined"
    with pytest.raises(GraphAuthError, match="first"):
        auth.token()


def test_silent_failure_asks_to_sign_in_again():
    auth, _ = make(silent_result=None)
    auth.start_device_flow()
    with pytest.raises(GraphAuthError, match="again"):
        auth.token()


def test_flow_start_error():
    auth, _ = make(flow={"error": "invalid_client", "error_description": "Public client flows are disabled"})
    with pytest.raises(GraphAuthError, match="Public client flows are disabled"):
        auth.start_device_flow()


def test_application_creation_is_thread_safe():
    call_count = [0]
    apps_created = []

    def counting_factory(client_id, authority):
        call_count[0] += 1
        app = FakeApp(client_id, authority)
        apps_created.append(app)
        return app

    auth = GraphAuth("client-id", "tenant-id", app_factory=counting_factory, run_in_background=lambda fn: fn())

    barrier = threading.Barrier(8)
    results = []

    def worker():
        barrier.wait()  # Synchronize all threads at the same point
        app = auth._application()
        results.append(app)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count[0] == 1, f"Factory should be called exactly once, but was called {call_count[0]} times"
    assert len(set(id(app) for app in results)) == 1, "All threads should get the same app instance"


def test_personal_mode_requests_own_calendar_permission_and_selects_pinned_account():
    app = FakeApp("client", "consumers")
    auth = GraphAuth("client", "consumers", app_factory=lambda *a, **k: app,
                     scopes=["Calendars.ReadWrite"], expected_account="Isaac@Example.com",
                     run_in_background=lambda fn: fn())
    auth.start_device_flow()
    assert app.scopes == ["Calendars.ReadWrite"]
    assert auth.status()["signed_in"] is False
    assert "Isaac@Example.com" in auth.status()["error"]
    with pytest.raises(GraphAuthError, match="Isaac@Example.com"):
        auth.token()
    app.accounts = [{"username": "other@example.com"}, {"username": "isaac@example.com"}]
    assert auth.status()["signed_in"] is True
    assert auth.status()["account"] == "isaac@example.com"
    assert auth.status()["error"] is None
    assert auth.token() == "tok"
