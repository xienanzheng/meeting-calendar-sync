from sqlmodel import Session

from mcs import cli, service
from mcs.db import make_engine


def test_seed_roster_command(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["seed-roster"]) == 0
    assert "Added 6 colleague(s)" in capsys.readouterr().out
    assert cli.main(["seed-roster"]) == 0
    assert "Added 0 colleague(s)" in capsys.readouterr().out


def test_serve_uses_flags_and_seeds(settings, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(app=app, host=host, port=port))
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "9999", "--seed-sample-roster"]) == 0
    assert (calls["host"], calls["port"]) == ("0.0.0.0", 9999)
    with Session(make_engine(settings)) as s:
        assert len(service.list_analysts(s)) == 6


def test_serve_defaults_to_localhost(settings, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(host=host, port=port))
    cli.main(["serve"])
    assert calls == {"host": "127.0.0.1", "port": 8765}


def test_outlook_demo_is_local_account_pinned_and_separate_from_existing_data(settings, monkeypatch):
    calls = {}
    original_data = settings.data_dir
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(app=app, host=host, port=port))
    assert cli.main(["serve", "--outlook-demo", "Isaac@Example.com", "--graph-client-id", "demo-client"]) == 0
    app = calls["app"]
    config = app.state.settings
    assert (config.calendar_sink, config.graph_expected_account) == ("outlook-demo", "isaac@example.com")
    assert (calls["host"], calls["port"]) == ("127.0.0.1", 8766)
    assert original_data in config.data_dir.parents and config.data_dir != original_data
    assert app.state.graph_auth.configured
    assert app.state.graph_auth.scopes == ["Calendars.ReadWrite"]
    with Session(app.state.engine) as s:
        assert len(service.list_analysts(s)) == 6


def test_google_demo_uses_its_own_account_data_and_google_sink(settings, monkeypatch):
    calls = {}
    original_data = settings.data_dir
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(app=app, host=host, port=port))
    assert cli.main(["serve", "--google-demo", "Isaac@Example.com"]) == 0
    config = calls["app"].state.settings
    assert (config.calendar_sink, config.google_expected_account) == ("google-demo", "isaac@example.com")
    assert (calls["host"], calls["port"]) == ("127.0.0.1", 8767)
    assert original_data in config.data_dir.parents
    assert calls["app"].state.sink_factory().name == "google-demo"
