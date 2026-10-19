"""Real review/revision service with only the Microsoft network boundary simulated."""
import json
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from sqlmodel import Session

from mcs import service
from mcs.api.app import create_app
from mcs.calendar import get_sink
from mcs.calendar.graph import GRAPH_BASE
from mcs.config import REPO_ROOT


def test_verify_edit_revision_retry_and_cancel_use_same_demo_event_ids(settings):
    settings.calendar_sink = "outlook-demo"
    settings.graph_client_id = "demo-client"
    settings.graph_expected_account = "isaac@example.com"
    events, writes = {}, []
    calendar = {"id": "secondary", "name": "Meeting Calendar Sync Demo", "isDefaultCalendar": False}

    def graph(request):
        path = request.url.path
        if request.method == "GET":
            return httpx.Response(200, json={"value": [calendar]} if path.endswith("/calendars") else calendar)
        assert path.startswith("/v1.0/me/calendars/secondary/events")
        writes.append((request.method, path))
        if request.method == "POST":
            payload = json.loads(request.content)
            assert "attendees" not in payload
            event_id = "event-" + str(len(writes))
            events[event_id] = payload
            return httpx.Response(201, json={"id": event_id, **payload})
        event_id = path.rsplit("/", 1)[1]
        assert event_id in events
        if request.method == "PATCH":
            events[event_id].update(json.loads(request.content))
            return httpx.Response(200, json={"id": event_id, **events[event_id]})
        del events[event_id]
        return httpx.Response(204)

    http = httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(graph))
    auth = SimpleNamespace(configured=True, token=lambda: "test-token",
                           status=lambda: {"configured": True, "signed_in": True, "pending": False,
                                           "account": "isaac@example.com", "error": None})
    app = create_app(settings, graph_auth=auth, sink_factory=lambda: get_sink(settings, auth, http))
    with Session(app.state.engine) as session:
        service.seed_roster(session, REPO_ROOT / "samples" / "roster.sample.json")
    with TestClient(app) as client:
        pdf = REPO_ROOT / "samples" / "broker_a_grid.pdf"
        uploaded = client.post("/api/conferences", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
        assert uploaded.status_code == 201
        detail = uploaded.json()
        cobalt = next(m for m in detail["meetings"] if m["company"] == "Cobalt Freight Lines")
        verified = client.post(f"/api/meetings/{cobalt['id']}/confirm").json()
        assert verified["last_sync"]["failed"] == 0 and verified["last_sync"]["ok"] == 2
        event_ids = set(events)
        assert len(event_ids) == 2
        assert all(e["start"] == {"dateTime": "2026-11-10T15:00:00", "timeZone": "UTC"} for e in events.values())
        retried = client.post(f"/api/conferences/{detail['id']}/send?dry_run=false").json()
        assert retried["actions"] == []
        changed = client.patch(f"/api/meetings/{cobalt['id']}", json={"room": "Demo room"}).json()
        assert changed["last_sync"]["ok"] == 2
        assert set(events) == event_ids and all("Demo room" in e["location"]["displayName"] for e in events.values())
        v2 = REPO_ROOT / "samples" / "broker_a_grid_v2.pdf"
        revised = client.post("/api/conferences", files={"file": (v2.name, v2.read_bytes(), "application/pdf")}).json()
        revision = revised["pending_revision"]
        applied = client.post(f"/api/revisions/{revision['id']}/apply", json={"accepted": ["c1"]})
        assert applied.status_code == 200 and applied.json()["last_sync"]["failed"] == 0
        assert set(events) == event_ids
        assert all(e["start"] == {"dateTime": "2026-11-10T19:30:00", "timeZone": "UTC"} for e in events.values())
        cancelled = client.delete(f"/api/meetings/{cobalt['id']}").json()
        assert cancelled["last_sync"]["ok"] == 2
        assert events == {}
        assert [method for method, _ in writes] == ["POST", "POST", "PATCH", "PATCH", "PATCH", "PATCH", "DELETE", "DELETE"]
