import io

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlmodel import Session

from mcs import service
from mcs.api.app import create_app
from mcs.calendar.graph_auth import GraphAuth
from mcs.calendar.planner import SyncOutcome
from mcs.config import REPO_ROOT

SAMPLES = REPO_ROOT / "samples"
PDF_A = (SAMPLES / "broker_a_grid.pdf").read_bytes()


def make_client(settings, tmp_path, **app_kw):
    settings.frontend_dist = tmp_path / "no-dist"
    app = create_app(settings, **app_kw)
    with Session(app.state.engine) as s:
        service.seed_roster(s, SAMPLES / "roster.sample.json")
    return TestClient(app)


def upload(client):
    r = client.post("/api/conferences", files={"file": ("broker_a_grid.pdf", PDF_A, "application/pdf")})
    assert r.status_code == 201, r.text
    return r.json()


def company(detail, name):
    return next(m for m in detail["meetings"] if m["company"] == name)


def people(client):
    return {a["name"]: a["id"] for a in client.get("/api/roster").json()}


def ics_events(client, cid, analyst_id):
    return Calendar.from_ical(client.get(f"/api/conferences/{cid}/ics/{analyst_id}").content).walk("VEVENT")


def test_verify_sends_immediately(settings, tmp_path):
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        d = c.post(f"/api/meetings/{north['id']}/confirm").json()
        m = company(d, "Northwind Robotics")
        assert {a["sync"] for a in m["attendees"]} == {"sent"}
        assert m["review_state"] == "sent"
        assert d["last_sync"] == {"ok": 2, "failed": 0, "message": "Updated 2 calendar entries."}
        assert d["counts"]["pending_actions"] == 0


def test_editing_a_verified_meeting_updates_calendars(settings, tmp_path):
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        c.post(f"/api/meetings/{north['id']}/confirm")
        d = c.patch(f"/api/meetings/{north['id']}", json={"room": "Salon 2"}).json()
        assert {a["sync"] for a in company(d, "Northwind Robotics")["attendees"]} == {"sent"}
        [event] = ics_events(c, d["id"], people(c)["Avery Kim"])
        assert int(event["SEQUENCE"]) == 1 and "Salon 2" in str(event["LOCATION"])


def test_deleting_a_sent_meeting_cancels_it(settings, tmp_path):
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        c.post(f"/api/meetings/{north['id']}/confirm")
        d = c.delete(f"/api/meetings/{north['id']}").json()
        assert company(d, "Northwind Robotics")["review_state"] == "cancelled"
        [event] = ics_events(c, d["id"], people(c)["Avery Kim"])
        assert str(event["STATUS"]) == "CANCELLED"


def test_verify_all_ready_sends_everything(settings, tmp_path):
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        d = c.post(f"/api/conferences/{d['id']}/confirm-ready", json={}).json()
        assert d["counts"]["sent"] == 11 and d["counts"]["pending_actions"] == 0
        assert d["last_sync"]["failed"] == 0 and d["last_sync"]["ok"] > 11


def test_nothing_to_do_says_up_to_date(settings, tmp_path):
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        d = c.patch(f"/api/meetings/{north['id']}", json={"notes": "bring model"}).json()
        assert d["last_sync"] == {"ok": 0, "failed": 0, "message": "Calendars are up to date."}


def test_auto_sync_off_keeps_manual_send(settings, tmp_path):
    settings.auto_sync = False
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        d = c.post(f"/api/meetings/{north['id']}/confirm").json()
        assert d["last_sync"] is None
        assert {a["sync"] for a in company(d, "Northwind Robotics")["attendees"]} == {"not_sent"}


def test_unconfigured_graph_never_fails_the_approval(settings, tmp_path):
    settings.calendar_sink = "graph"
    with make_client(settings, tmp_path) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        r = c.post(f"/api/meetings/{north['id']}/confirm")
        assert r.status_code == 200
        d = r.json()
        assert company(d, "Northwind Robotics")["status"] == "confirmed"
        assert "not configured" in d["last_sync"]["message"]
        assert d["last_sync"]["ok"] == 0


class NoAccountsApp:
    def __init__(self, *args, **kwargs):
        pass

    def get_accounts(self):
        return []


def test_graph_not_signed_in_asks_to_sign_in(settings, tmp_path):
    settings.calendar_sink = "graph"
    auth = GraphAuth("cid", "tid", app_factory=NoAccountsApp)
    with make_client(settings, tmp_path, graph_auth=auth) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        d = c.post(f"/api/meetings/{north['id']}/confirm").json()
        assert d["last_sync"]["message"] == "Sign in to Microsoft to update calendars."


class FailingSink:
    name = "ics"

    def apply(self, conference, actions):
        return [SyncOutcome(a, ok=False, error="boom") for a in actions]


def test_sync_failures_are_reported_not_raised(settings, tmp_path):
    with make_client(settings, tmp_path, sink_factory=FailingSink) as c:
        d = upload(c)
        north = company(d, "Northwind Robotics")
        r = c.post(f"/api/meetings/{north['id']}/confirm")
        assert r.status_code == 200
        d = r.json()
        assert d["last_sync"] == {"ok": 0, "failed": 2, "message": "2 calendar updates failed — use Retry."}
        assert {a["sync"] for a in company(d, "Northwind Robotics")["attendees"]} == {"failed"}
