import pytest
from pydantic import ValidationError

from mcs.config import REPO_ROOT, Settings


def make(**kw):
    return Settings(_env_file=None, use_keychain=False, **kw)


def test_defaults():
    s = make()
    assert s.extractor == "auto"
    assert s.resolved_extractor() == "claude-code"
    assert s.resolved_model() == "sonnet"
    assert s.calendar_sink == "ics"
    assert (s.host, s.port) == ("127.0.0.1", 8765)
    assert s.default_meeting_minutes == 45
    assert s.extract_timeout == 240
    assert s.max_upload_mb == 20
    assert s.data_dir == REPO_ROOT / "data"
    assert s.frontend_dist == REPO_ROOT / "frontend" / "dist"


def test_auto_picks_anthropic_when_env_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = make()
    assert s.resolved_extractor() == "anthropic"
    assert s.resolved_model() == "claude-sonnet-5-5"
    assert s.anthropic_api_key() == "test-key"


def test_auto_picks_anthropic_when_keychain_has_key(monkeypatch):
    monkeypatch.setattr("mcs.secrets.keychain_lookup", lambda service: "kc-key" if "anthropic" in service else None)
    s = Settings(_env_file=None, use_keychain=True)
    assert s.anthropic_api_key() == "kc-key"
    assert s.resolved_extractor() == "anthropic"


def test_use_keychain_false_ignores_keychain(monkeypatch):
    monkeypatch.setattr("mcs.secrets.keychain_lookup", lambda service: "kc-key")
    assert make().anthropic_api_key() is None


def test_explicit_extractor_and_model(monkeypatch):
    monkeypatch.setenv("MCS_EXTRACTOR", "claude-code")
    monkeypatch.setenv("MCS_MODEL", "opus")
    monkeypatch.setenv("MCS_PORT", "9000")
    s = make()
    assert s.resolved_extractor() == "claude-code"
    assert s.resolved_model() == "opus"
    assert s.port == 9000


def test_foundry_resource_from_env_or_init(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "my-resource")
    assert make().foundry_resource == "my-resource"
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_RESOURCE")
    assert make(foundry_resource="other").foundry_resource == "other"


def test_foundry_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "fk")
    assert make().foundry_api_key() == "fk"


def test_invalid_extractor_rejected():
    with pytest.raises(ValidationError):
        make(extractor="gpt")


def test_paths(tmp_path):
    s = make(data_dir=tmp_path)
    assert s.db_url == f"sqlite:///{tmp_path / 'app.db'}"
    assert s.uploads_dir == tmp_path / "uploads"
