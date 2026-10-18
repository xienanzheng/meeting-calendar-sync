"""Command line: `mcs serve` and `mcs seed-roster`."""
import argparse
from pathlib import Path

from sqlmodel import Session

from mcs import service
from mcs.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcs", description="Meeting Calendar Sync")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the web app")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--seed-sample-roster", action="store_true",
                       help="Load samples/roster.sample.json when the roster is empty (hosted demo)")
    seed = sub.add_parser("seed-roster", help="Add colleagues from a JSON file (default: the sample roster)")
    seed.add_argument("path", nargs="?")
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "seed-roster":
        from mcs.db import make_engine

        path = Path(args.path) if args.path else settings.samples_dir / "roster.sample.json"
        with Session(make_engine(settings)) as session:
            added = service.seed_roster(session, path)
        print(f"Added {added} colleague(s) from {path}")
        return 0

    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    import uvicorn

    from mcs.api.app import create_app

    app = create_app(settings)
    if args.seed_sample_roster:
        with Session(app.state.engine) as session:
            if not service.list_analysts(session):
                service.seed_roster(session, settings.samples_dir / "roster.sample.json")
    print(f"Meeting Calendar Sync on http://{settings.host}:{settings.port} "
          f"(extractor: {settings.resolved_extractor()}, calendar: {settings.calendar_sink})")
    uvicorn.run(app, host=settings.host, port=settings.port)
    return 0
