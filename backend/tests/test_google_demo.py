import datetime as dt
import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from mcs.calendar import get_sink
from mcs.calendar.content import EventContent
from mcs.calendar.planner import SyncAction
from mcs.models import Conference

ACCOUNT = "isaac@example.com"
CALENDAR = {"id": "secondary", "summary": "Meeting Calendar Sync Demo", "accessRole": "owner", "primary": False, "dataOwner": ACCOUNT}
PRIMARY = {"id": ACCOUNT, "primary": True, "accessRole": "owner"}


def action(kind="create", external_id=None):
    content = EventContent("Cobalt Freight Lines", "Salon 4", "Demo conference",
                           dt.datetime(2026, 11, 10, 15, tzinfo=dt.timezone.utc),
                           dt.datetime(2026, 11, 10, 15, 45, tzinfo=dt.timezone.utc), categories=("Conference",))
    return SyncAction(kind, 10, 1, "avery@example.com", "Avery Kim", content, 0, external_id)


def make(tmp_path, handler):
    calls = []
    def transport(req):
        calls.append(req)
        return handler(req)
    client = httpx.Client(base_url="https://www.googleapis.com/calendar/v3", transport=httpx.MockTransport(transport))
    settings = SimpleNamespace(calendar_sink="google-demo", google_expected_account=ACCOUNT, data_dir=tmp_path)
    auth = SimpleNamespace(token=lambda: "private-token")
    return get_sink(settings, client=client, google_auth=auth), calls


def test_google_demo_creates_secondary_calendar_and_never_invites_colleagues(tmp_path):
    def handler(req):
        if req.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": [PRIMARY]})
        if req.url.path.endswith("/calendars"):
            return httpx.Response(201, json={"id": "secondary", "summary": "Meeting Calendar Sync Demo"})
        if "/calendarList/" in req.url.path:
            return httpx.Response(200, json=CALENDAR)
        body = json.loads(req.content)
        assert req.url.path == "/calendar/v3/calendars/secondary/events"
        assert req.url.params["sendUpdates"] == "none"
        assert "attendees" not in body
        assert body["summary"] == "[Demo · Avery Kim] Cobalt Freight Lines"
        assert body["start"] == {"dateTime": "2026-11-10T15:00:00+00:00"}
        assert body["colorId"] == "10"  # Google's green ("Basil") stands in for the Outlook category
        return httpx.Response(200, json={"id": body["id"]})
    sink, calls = make(tmp_path, handler)
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert outcome.ok and outcome.external_id
    assert all("private-token" not in p.read_text() for p in tmp_path.glob("*.json"))


def test_wrong_google_account_stops_before_writes(tmp_path):
    sink, calls = make(tmp_path, lambda r: httpx.Response(200, json={"items": [{**PRIMARY, "id": "other@example.com"}]}))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok and ACCOUNT in outcome.error
    assert [r.method for r in calls] == ["GET"]


def test_retry_after_lost_response_uses_same_client_event_id_and_updates_existing(tmp_path):
    events, ids = {}, []
    def handler(req):
        if req.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": [PRIMARY, CALENDAR]})
        if "/calendarList/" in req.url.path:
            return httpx.Response(200, json=CALENDAR)
        body = json.loads(req.content)
        if req.method == "POST":
            ids.append(body["id"])
            if body["id"] in events:
                return httpx.Response(409)
            events[body["id"]] = body
            raise httpx.ReadError("lost", request=req)
        event_id = req.url.path.rsplit("/", 1)[1]
        events[event_id].update(body)
        return httpx.Response(200, json={"id": event_id})
    conf = Conference(id=1)
    sink, _ = make(tmp_path, handler)
    assert not sink.apply(conf, [action()])[0].ok
    retry, _ = make(tmp_path, handler)
    [outcome] = retry.apply(conf, [action()])
    assert outcome.ok and len(events) == 1 and ids[0] == ids[1]


@pytest.mark.parametrize("calendar", [{**CALENDAR, "primary": True}, {**CALENDAR, "accessRole": "writer"},
                                       {**CALENDAR, "dataOwner": "other@example.com"}, {**CALENDAR, "dataOwner": None}])
def test_google_demo_rejects_primary_or_shared_calendar(tmp_path, calendar):
    sink, calls = make(tmp_path, lambda r: httpx.Response(200, json={"items": [PRIMARY, calendar]}))
    assert not sink.apply(Conference(id=1), [action()])[0].ok
    assert all(r.method == "GET" for r in calls)


def test_google_update_and_cancel_are_scoped_to_bound_calendar(tmp_path):
    def handler(req):
        if req.url.path.endswith("/calendarList"):
            return httpx.Response(200, json={"items": [PRIMARY, CALENDAR]})
        if "/calendarList/" in req.url.path:
            return httpx.Response(200, json=CALENDAR)
        return httpx.Response(200, json={"id": "existing"}) if req.method == "PATCH" else httpx.Response(204)
    sink, calls = make(tmp_path, handler)
    outcomes = sink.apply(Conference(id=1), [action("update", "existing"), replace(action("cancel", "existing"), content=None)])
    assert all(o.ok for o in outcomes)
    assert [(r.method, r.url.path) for r in calls if r.method != "GET"] == [
        ("PATCH", "/calendar/v3/calendars/secondary/events/existing"),
        ("DELETE", "/calendar/v3/calendars/secondary/events/existing")]
