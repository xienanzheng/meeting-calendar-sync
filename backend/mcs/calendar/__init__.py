from typing import Protocol, Sequence

from mcs.calendar.planner import SyncAction, SyncOutcome


class CalendarSink(Protocol):
    name: str

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]: ...


class SinkNotConfigured(Exception):
    """The configured sink cannot run yet; the message is shown to the coordinator."""


def get_sink(settings, graph_auth=None, client=None, google_auth=None) -> CalendarSink:
    if settings.calendar_sink == "ics":
        from mcs.calendar.ics import IcsSink

        return IcsSink()
    if settings.calendar_sink == "google-demo":
        import httpx
        from mcs.calendar.google_demo import GOOGLE_BASE, GoogleDemoSink
        if not settings.google_expected_account or google_auth is None:
            raise SinkNotConfigured("Choose a Google demo account and run mcs google-login first.")
        return GoogleDemoSink(google_auth, client or httpx.Client(base_url=GOOGLE_BASE, timeout=30),
                              settings.data_dir, settings.google_expected_account)
    if settings.calendar_sink in ("graph", "outlook-demo"):
        import httpx

        from mcs.calendar.graph import GRAPH_BASE, GraphSink

        if graph_auth is None or not graph_auth.configured:
            if settings.calendar_sink == "outlook-demo":
                raise SinkNotConfigured("Microsoft sign-in needs an app registration. Start the demo with --graph-client-id from your Microsoft app registration.")
            raise SinkNotConfigured(
                "Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID."
            )
        if settings.calendar_sink == "outlook-demo":
            from mcs.calendar.outlook_demo import OutlookDemoSink

            if not settings.graph_expected_account:
                raise SinkNotConfigured("Set MCS_GRAPH_EXPECTED_ACCOUNT to the personal account for this demo.")
            return OutlookDemoSink(graph_auth.token, client or httpx.Client(base_url=GRAPH_BASE, timeout=30),
                                   settings.data_dir, settings.graph_expected_account, settings.graph_client_id)
        return GraphSink(graph_auth.token, client or httpx.Client(base_url=GRAPH_BASE, timeout=30))
    raise ValueError(f"Unknown calendar sink {settings.calendar_sink!r}")
