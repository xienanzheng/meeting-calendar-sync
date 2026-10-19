"""Exercise approval and revision through the real API, with Google's HTTP boundary simulated."""
import json
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

from mcs import service
from mcs.api.app import create_app
from mcs.calendar import get_sink
from mcs.calendar.google_demo import GOOGLE_BASE
from mcs.config import REPO_ROOT


def test_google_verify_revision_and_cancel_keep_same_remote_ids(settings):
    settings.calendar_sink = "google-demo"
    settings.google_expected_account = "isaac@example.com"
    calendar = {"id": "secondary", "summary": "Meeting Calendar Sync Demo", "accessRole": "owner", "dataOwner": "isaac@example.com"}
    events, methods = {}, []
    def google(req):
        if req.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "isaac@example.com", "primary": True}, calendar]}
                                  if req.url.path.endswith("/calendarList") else calendar)
        assert req.url.path.startswith("/calendar/v3/calendars/secondary/events")
        methods.append(req.method)
        if req.method == "POST":
            body = json.loads(req.content)
            assert "attendees" not in body
            events[body["id"]] = body
            return httpx.Response(200, json=body)
        event_id = req.url.path.rsplit("/", 1)[1]
        assert event_id in events
        if req.method == "PATCH":
            events[event_id].update(json.loads(req.content))
            return httpx.Response(200, json=events[event_id])
        del events[event_id]
        return httpx.Response(204)
    http = httpx.Client(base_url=GOOGLE_BASE, transport=httpx.MockTransport(google))
    auth = SimpleNamespace(token=lambda: "test-token")
    app = create_app(settings, sink_factory=lambda: get_sink(settings, client=http, google_auth=auth))
    with Session(app.state.engine) as session:
        service.seed_roster(session, REPO_ROOT / "samples" / "roster.sample.json")
    with TestClient(app) as client:
        pdf = REPO_ROOT / "samples" / "broker_a_grid.pdf"
        detail = client.post("/api/conferences", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")}).json()
        meeting = next(m for m in detail["meetings"] if m["company"] == "Cobalt Freight Lines")
        result = client.post(f"/api/meetings/{meeting['id']}/confirm").json()
        assert result["last_sync"] == {"ok": 2, "failed": 0, "message": "Updated 2 calendar entries."}
        ids = set(events)
        assert len(ids) == 2
        assert client.post(f"/api/conferences/{detail['id']}/send?dry_run=false").json()["actions"] == []
        revised = REPO_ROOT / "samples" / "broker_a_grid_v2.pdf"
        revision = client.post("/api/conferences", files={"file": (revised.name, revised.read_bytes(), "application/pdf")}).json()["pending_revision"]
        result = client.post(f"/api/revisions/{revision['id']}/apply", json={"accepted": ["c1"]}).json()
        assert result["last_sync"]["ok"] == 2 and result["last_sync"]["failed"] == 0
        assert set(events) == ids
        assert all(e["start"]["dateTime"] == "2026-11-10T19:30:00+00:00" for e in events.values())
        assert client.delete(f"/api/meetings/{meeting['id']}").json()["last_sync"]["ok"] == 2
        assert events == {}
        assert methods == ["POST", "POST", "PATCH", "PATCH", "DELETE", "DELETE"]
