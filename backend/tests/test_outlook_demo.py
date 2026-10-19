"""Personal demo writes must stay in one secondary calendar, across retries and edits."""
import datetime as dt
import json
from types import SimpleNamespace

import httpx
import pytest

from mcs.calendar import SinkNotConfigured, get_sink
from mcs.calendar.graph import GRAPH_BASE
from mcs.calendar.content import EventContent
from mcs.calendar.planner import SyncAction
from mcs.models import Conference

ACCOUNT = "isaac@example.com"
CALENDAR = {"id": "demo-calendar", "name": "Meeting Calendar Sync Demo", "isDefaultCalendar": False}


def action(kind="create", external_id=None, sequence=0):
    content = EventContent("Northwind Robotics", "Salon 4", "Test conference",
                           dt.datetime(2026, 11, 10, 13, 0, tzinfo=dt.timezone.utc),
                           dt.datetime(2026, 11, 10, 13, 45, tzinfo=dt.timezone.utc))
    return SyncAction(kind, 10, 1, "avery.kim@example.com", "Avery Kim", content, sequence, external_id)


def settings(tmp_path, **overrides):
    return SimpleNamespace(calendar_sink="outlook-demo", graph_expected_account=ACCOUNT,
                           graph_client_id="demo-client", data_dir=tmp_path, **overrides)


def make(tmp_path, handler, account=ACCOUNT):
    calls = []

    def transport(request):
        calls.append(request)
        return handler(request)

    client = httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(transport))
    auth = SimpleNamespace(configured=True, token=lambda: "demo-token")
    config = settings(tmp_path)
    config.graph_expected_account = account
    return get_sink(config, auth, client), calls


def test_create_uses_only_named_secondary_calendar_and_no_invitations(tmp_path):
    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"value": []})
        if req.url.path == "/v1.0/me/calendars":
            assert json.loads(req.content) == {"name": "Meeting Calendar Sync Demo"}
            return httpx.Response(201, json=CALENDAR)
        assert req.url.path == "/v1.0/me/calendars/demo-calendar/events"
        return httpx.Response(201, json={"id": "event-1"})

    sink, calls = make(tmp_path, handler)
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert outcome.ok and outcome.external_id == "event-1"
    event = json.loads(calls[-1].content)
    assert event["subject"].startswith("[Demo · Avery Kim]")
    assert "attendees" not in event
    assert "avery.kim@example.com" not in str(calls[-1].url)
    assert "demo-token" not in (tmp_path / "outlook-demo-target.json").read_text()


def test_restarts_reuse_calendar_and_scope_update_and_cancel_to_it(tmp_path):
    calls = []

    def handler(req):
        calls.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"value": [CALENDAR]} if req.url.path.endswith("/calendars") else CALENDAR)
        if req.method == "POST":
            return httpx.Response(201, json={"id": "event-1"})
        if req.method == "PATCH":
            return httpx.Response(200, json={"id": "event-1"})
        return httpx.Response(204)

    conf = Conference(id=1)
    first, _ = make(tmp_path, handler)
    assert first.apply(conf, [action()])[0].ok
    second, _ = make(tmp_path, handler)
    results = second.apply(conf, [action("update", "event-1", 1), action("cancel", "event-1", 2)])
    assert all(o.ok for o in results)
    writes = [(r.method, r.url.path) for r in calls if r.method != "GET"]
    assert writes == [("POST", "/v1.0/me/calendars/demo-calendar/events"),
                      ("PATCH", "/v1.0/me/calendars/demo-calendar/events/event-1"),
                      ("DELETE", "/v1.0/me/calendars/demo-calendar/events/event-1")]


@pytest.mark.parametrize("calendars", [
    [{**CALENDAR, "isDefaultCalendar": True}],
    [CALENDAR, {**CALENDAR, "id": "duplicate"}],
])
def test_ambiguous_or_default_calendar_never_receives_writes(tmp_path, calendars):
    sink, calls = make(tmp_path, lambda r: httpx.Response(200, json={"value": calendars}))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok
    assert all(r.method == "GET" for r in calls)


def test_binding_cannot_be_reused_for_another_account(tmp_path):
    sink, _ = make(tmp_path, lambda r: httpx.Response(200, json={"value": [CALENDAR]} if r.url.path.endswith("/calendars") else CALENDAR))
    sink.apply(Conference(id=1), [action()])
    other, calls = make(tmp_path, lambda r: pytest.fail("must not contact Graph"), account="other@example.com")
    [outcome] = other.apply(Conference(id=1), [action()])
    assert not outcome.ok and "account" in outcome.error.lower()
    assert calls == []


def test_missing_bound_calendar_does_not_create_replacement(tmp_path):
    sink, _ = make(tmp_path, lambda r: httpx.Response(200, json={"value": [CALENDAR]}))
    sink.apply(Conference(id=1), [action()])
    retry, calls = make(tmp_path, lambda r: httpx.Response(404))
    [outcome] = retry.apply(Conference(id=1), [action("update", "old-id", 1)])
    assert not outcome.ok
    assert [(r.method, r.url.path) for r in calls] == [("GET", "/v1.0/me/calendars/demo-calendar")]


def test_requires_explicit_account_before_any_graph_write(tmp_path):
    with pytest.raises(SinkNotConfigured, match="account"):
        make(tmp_path, lambda r: pytest.fail("must not contact Graph"), account=None)


def test_personal_graph_failure_is_retryable_without_leaking_token(tmp_path):
    sink, _ = make(tmp_path, lambda r: httpx.Response(403, json={"error": {"message": "Access denied"}}))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok and "403" in outcome.error
    assert "demo-token" not in outcome.error


def test_calendar_discovery_follows_graph_pagination(tmp_path):
    def handler(req):
        if req.url.params.get("$skiptoken"):
            return httpx.Response(200, json={"value": [CALENDAR]})
        if req.method == "GET":
            return httpx.Response(200, json={"value": [], "@odata.nextLink": GRAPH_BASE + "/me/calendars?$skiptoken=next"})
        return httpx.Response(201, json={"id": "event-1"})

    sink, calls = make(tmp_path, handler)
    assert sink.apply(Conference(id=1), [action()])[0].ok
    assert not any(r.method == "POST" and r.url.path.endswith("/calendars") for r in calls)


def test_calendar_discovery_never_sends_bearer_to_external_next_link(tmp_path):
    sink, calls = make(tmp_path, lambda r: httpx.Response(200, json={"value": [], "@odata.nextLink": "https://untrusted.example/calendars"}))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok
    assert len(calls) == 1


def test_short_create_response_is_verified_before_event_write(tmp_path):
    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"value": []} if req.url.path.endswith("/calendars") else CALENDAR)
        if req.url.path.endswith("/calendars"):
            return httpx.Response(201, json={"id": "demo-calendar", "name": "Meeting Calendar Sync Demo"})
        return httpx.Response(201, json={"id": "event-1"})

    sink, calls = make(tmp_path, handler)
    assert sink.apply(Conference(id=1), [action()])[0].ok
    assert (calls[-2].method, calls[-2].url.path) == ("GET", "/v1.0/me/calendars/demo-calendar")


def test_lost_create_response_retries_same_transaction_without_duplicate_event(tmp_path):
    events, attempts = {}, []

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json={"value": [CALENDAR]} if req.url.path.endswith("/calendars") else CALENDAR)
        payload = json.loads(req.content)
        transaction = payload["transactionId"]
        attempts.append(transaction)
        events.setdefault(transaction, "created-before-response")
        if len(attempts) == 1:
            raise httpx.ReadError("response lost", request=req)
        return httpx.Response(201, json={"id": events[transaction]})

    conf = Conference(id=1)
    first, _ = make(tmp_path, handler)
    assert not first.apply(conf, [action()])[0].ok
    retry, _ = make(tmp_path, handler)
    [outcome] = retry.apply(conf, [action()])
    assert outcome.ok and outcome.external_id == "created-before-response"
    assert len(events) == 1 and len(attempts) == 2 and attempts[0] == attempts[1]
