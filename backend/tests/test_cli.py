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
