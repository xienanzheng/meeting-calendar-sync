from typing import Protocol, Sequence

from mcs.calendar.planner import SyncAction, SyncOutcome


class CalendarSink(Protocol):
    name: str

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]: ...


class SinkNotConfigured(Exception):
    """The configured sink cannot run yet; the message is shown to the coordinator."""


def get_sink(settings, graph_auth=None, client=None) -> CalendarSink:
    if settings.calendar_sink == "ics":
        from mcs.calendar.ics import IcsSink

        return IcsSink()
    if settings.calendar_sink == "graph":
        import httpx

        from mcs.calendar.graph import GRAPH_BASE, GraphSink

        if graph_auth is None or not graph_auth.configured:
            raise SinkNotConfigured(
                "Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID."
            )
        return GraphSink(graph_auth.token, client or httpx.Client(base_url=GRAPH_BASE, timeout=30))
    raise ValueError(f"Unknown calendar sink {settings.calendar_sink!r}")
