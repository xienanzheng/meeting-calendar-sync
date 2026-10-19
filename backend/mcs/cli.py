"""Command line: `mcs serve` and `mcs seed-roster`."""
import argparse
import hashlib
from pathlib import Path

from sqlmodel import Session

from mcs import service
from mcs.config import get_settings


def _demo_dir(root: Path, provider: str, account: str) -> Path:
    return root / provider / hashlib.sha256(account.casefold().encode()).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcs", description="Meeting Calendar Sync")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the web app")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--outlook-demo", metavar="EMAIL", help="Sync sample colleagues into your own secondary Outlook calendar")
    serve.add_argument("--google-demo", metavar="EMAIL", help="Sync sample colleagues into your own secondary Google calendar")
    serve.add_argument("--graph-client-id", help="Application (client) ID of your Microsoft public-client app registration")
    serve.add_argument("--seed-sample-roster", action="store_true",
                       help="Load samples/roster.sample.json when the roster is empty (hosted demo)")
    seed = sub.add_parser("seed-roster", help="Add colleagues from a JSON file (default: the sample roster)")
    seed.add_argument("path", nargs="?")
    google_login = sub.add_parser("google-login", help="Authorize the personal Google calendar demo")
    google_login.add_argument("--account", required=True)
    google_login.add_argument("--client-file", required=True, type=Path)
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "google-login":
        from mcs.calendar.google_auth import GoogleAuth, GoogleAuthError
        account = args.account.strip().casefold()
        path = _demo_dir(settings.data_dir, "google-demo", account) / "google-oauth.json"
        try:
            GoogleAuth(path).authorize(args.client_file, account)
        except GoogleAuthError as exc:
            print(str(exc))
            return 1
        print(f"Google Calendar connected as {account}. Start the Google demo launcher.")
        return 0

    if args.command == "seed-roster":
        from mcs.db import make_engine

        path = Path(args.path) if args.path else settings.samples_dir / "roster.sample.json"
        with Session(make_engine(settings)) as session:
            added = service.seed_roster(session, path)
        print(f"Added {added} colleague(s) from {path}")
        return 0

    if args.host:
        settings.host = args.host
    if args.graph_client_id:
        settings.graph_client_id = args.graph_client_id
    if args.outlook_demo and args.google_demo:
        parser.error("Choose one demo calendar provider")
    demo_account = args.outlook_demo or args.google_demo
    if demo_account:
        account = demo_account.strip().casefold()
        if "@" not in account or any(c.isspace() for c in account):
            parser.error("--outlook-demo needs the email address of your Microsoft account")
        provider = "google-demo" if args.google_demo else "outlook-demo"
        settings.calendar_sink = provider
        if args.google_demo:
            settings.google_expected_account = account
        else:
            settings.graph_expected_account = account
            settings.graph_tenant_id = "consumers"
        settings.data_dir = _demo_dir(settings.data_dir, provider, account)
        settings.host, settings.port = "127.0.0.1", 8767 if args.google_demo else 8766
        args.seed_sample_roster = True
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
    if demo_account:
        print(f"Demo target: {account} / Meeting Calendar Sync Demo")
        if args.outlook_demo and not settings.graph_client_id:
            print("Microsoft setup pending: see docs/outlook-demo.md for app registration, then use --graph-client-id.")
    uvicorn.run(app, host=settings.host, port=settings.port)
    return 0
