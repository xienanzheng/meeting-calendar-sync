from fastapi import APIRouter, Request

from mcs.calendar import SinkNotConfigured
from mcs.calendar.outlook_demo import DEMO_CALENDAR_NAME

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/config")
def config(request: Request):
    s = request.app.state.settings
    return {"extractor": s.resolved_extractor(), "model": s.resolved_model(), "calendar_sink": s.calendar_sink,
            "ephemeral": s.ephemeral, "graph": request.app.state.graph_auth.status(),
            "calendar_target": {"account": s.google_expected_account if s.calendar_sink == "google-demo" else s.graph_expected_account,
                                "name": DEMO_CALENDAR_NAME}
            if s.calendar_sink in ("outlook-demo", "google-demo") else None}


@router.post("/graph/login")
def graph_login(request: Request):
    auth = request.app.state.graph_auth
    if not auth.configured:
        if request.app.state.settings.calendar_sink == "outlook-demo":
            raise SinkNotConfigured("Microsoft sign-in needs an app registration. Start the demo with --graph-client-id from your Microsoft app registration.")
        raise SinkNotConfigured("Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID.")
    return auth.start_device_flow()


@router.get("/graph/status")
def graph_status(request: Request):
    return request.app.state.graph_auth.status()
