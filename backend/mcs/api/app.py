from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mcs import service
from mcs.api import routes_conferences, routes_meetings, routes_revisions, routes_roster, routes_system
from mcs.calendar import SinkNotConfigured, get_sink
from mcs.calendar.graph_auth import GraphAuth, GraphAuthError
from mcs.config import Settings, get_settings
from mcs.db import make_engine
from mcs.extraction import ExtractionError, get_extractor


def _error(status: int, detail: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, **extra})


def create_app(settings: Settings | None = None, *, extractor_factory: Callable | None = None,
               sink_factory: Callable | None = None, graph_auth: GraphAuth | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Meeting Calendar Sync")
    app.state.settings = settings
    app.state.engine = make_engine(settings)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    app.state.graph_auth = graph_auth or GraphAuth(settings.graph_client_id, settings.graph_tenant_id)
    app.state.extractor_factory = extractor_factory or (lambda: get_extractor(settings))
    app.state.sink_factory = sink_factory or (lambda: get_sink(settings, app.state.graph_auth))

    app.add_exception_handler(service.NotFound, lambda r, e: _error(404, str(e)))
    app.add_exception_handler(service.InvalidInput, lambda r, e: _error(400, str(e)))
    app.add_exception_handler(service.Conflict,
                              lambda r, e: _error(409, str(e), flags=[f.model_dump() for f in e.flags]))
    app.add_exception_handler(ExtractionError, lambda r, e: _error(502, str(e)))
    app.add_exception_handler(SinkNotConfigured, lambda r, e: _error(400, str(e)))
    app.add_exception_handler(GraphAuthError, lambda r, e: _error(401, str(e)))

    for router in (routes_system.router, routes_conferences.router, routes_meetings.router,
                  routes_revisions.router, routes_roster.router):
        app.include_router(router)

    dist = settings.frontend_dist
    if (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        root = dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request):
            if path.startswith("api/") or path == "api":
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
