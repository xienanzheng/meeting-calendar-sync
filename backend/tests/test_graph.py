import datetime as dt
import json

import httpx
import pytest

from mcs.calendar.content import EventContent
from mcs.calendar.graph import GRAPH_BASE, GraphSink, event_payload
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.planner import SyncAction
from mcs.models import Conference

UTC = dt.timezone.utc
TOKEN = "tok-secret-value"
CONTENT = EventContent("NWRB – Northwind Robotics (1x1)", "The Example Grand Hotel – Salon 4",
                       "Industrials Conference 2026", dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC),
                       dt.datetime(2026, 11, 10, 13, 45, tzinfo=UTC))


def action(kind="create", external_id=None, sequence=0):
    return SyncAction(kind, 10, 1, "avery.kim@example.com", "Avery Kim", CONTENT, sequence, external_id)


def make_sink(handler, token_provider=lambda: TOKEN):
    calls, sleeps = [], []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    client = httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(wrapped))
    return GraphSink(token_provider, client, sleep=sleeps.append), calls, sleeps


def test_event_payload():
    assert event_payload(CONTENT) == {
        "subject": "NWRB – Northwind Robotics (1x1)",
        "body": {"contentType": "text", "content": "Industrials Conference 2026"},
        "start": {"dateTime": "2026-11-10T13:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-10T13:45:00", "timeZone": "UTC"},
        "location": {"displayName": "The Example Grand Hotel – Salon 4"},
        "showAs": "busy",
    }


def test_create_posts_to_the_colleagues_calendar():
    sink, calls, _ = make_sink(lambda r: httpx.Response(201, json={"id": "AAMk-1"}))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert (outcome.ok, outcome.external_id, outcome.error) == (True, "AAMk-1", None)
    req = calls[0]
    assert req.method == "POST"
    assert req.url.path == "/v1.0/users/avery.kim@example.com/calendar/events"
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    body = json.loads(req.content)
    assert body["transactionId"] == "mcs-10-1-0"
    assert body["start"] == {"dateTime": "2026-11-10T13:00:00", "timeZone": "UTC"}


def test_update_patches_existing_event():
    sink, calls, _ = make_sink(lambda r: httpx.Response(200, json={"id": "AAMk-1"}))
    [outcome] = sink.apply(Conference(id=1), [action("update", "AAMk-1", 1)])
    assert (outcome.ok, outcome.external_id) == (True, "AAMk-1")
    assert calls[0].method == "PATCH"
    assert calls[0].url.path == "/v1.0/users/avery.kim@example.com/events/AAMk-1"


@pytest.mark.parametrize("status", [204, 404])
def test_cancel_deletes_and_404_counts_as_done(status):
    sink, calls, _ = make_sink(lambda r: httpx.Response(status))
    [outcome] = sink.apply(Conference(id=1), [action("cancel", "AAMk-1", 2)])
    assert outcome.ok and calls[0].method == "DELETE"


@pytest.mark.parametrize("status,body,expected", [
    (401, {}, "Sign in to Microsoft again."),
    (403, {}, "No delegate access to avery.kim@example.com's calendar."),
    (500, {"error": {"code": "x", "message": "Something broke"}}, "Graph error 500: Something broke"),
])
def test_errors_are_readable_and_never_leak_the_token(status, body, expected):
    sink, _, _ = make_sink(lambda r: httpx.Response(status, json=body))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok
    assert outcome.error == expected
    assert TOKEN not in outcome.error


def test_429_waits_retry_after_and_retries_once():
    responses = iter([httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(201, json={"id": "X"})])
    sink, calls, sleeps = make_sink(lambda r: next(responses))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert outcome.ok and len(calls) == 2 and sleeps == [2.0]


def test_retry_after_is_capped():
    responses = iter([httpx.Response(429, headers={"Retry-After": "120"}), httpx.Response(201, json={"id": "X"})])
    sink, _, sleeps = make_sink(lambda r: next(responses))
    sink.apply(Conference(id=1), [action()])
    assert sleeps == [10.0]


def test_not_signed_in_fails_every_item_without_requests():
    def no_token():
        raise GraphAuthError("Sign in to Microsoft first.")
    sink, calls, _ = make_sink(lambda r: httpx.Response(201, json={"id": "X"}), token_provider=no_token)
    outcomes = sink.apply(Conference(id=1), [action(), action("cancel", "A", 1)])
    assert [o.error for o in outcomes] == ["Sign in to Microsoft first."] * 2
    assert calls == []


def test_network_error_is_reported_per_item():
    def boom(request):
        raise httpx.ConnectError("offline", request=request)
    sink, _, _ = make_sink(boom)
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok and outcome.error.startswith("Could not reach Microsoft Graph")
