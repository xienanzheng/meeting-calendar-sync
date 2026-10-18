from fastapi import APIRouter, Request

from mcs.calendar import SinkNotConfigured

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/config")
def config(request: Request):
    s = request.app.state.settings
    return {"extractor": s.resolved_extractor(), "model": s.resolved_model(), "calendar_sink": s.calendar_sink,
            "ephemeral": s.ephemeral, "graph": request.app.state.graph_auth.status()}


@router.post("/graph/login")
def graph_login(request: Request):
    auth = request.app.state.graph_auth
    if not auth.configured:
        raise SinkNotConfigured("Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID.")
    return auth.start_device_flow()


@router.get("/graph/status")
def graph_status(request: Request):
    return request.app.state.graph_auth.status()
