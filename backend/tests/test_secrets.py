import sys

import pytest

from mcs import secrets
from mcs.secrets import keychain_lookup as real_keychain_lookup  # bound before the autouse patch


def test_env_var_wins_over_keychain(monkeypatch):
    calls = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    got = secrets.get_secret("ANTHROPIC_API_KEY", "svc", keychain=lambda s: calls.append(s) or "from-keychain")
    assert got == "from-env"
    assert calls == []


def test_falls_back_to_keychain():
    got = secrets.get_secret("ANTHROPIC_API_KEY", "svc", keychain=lambda s: f"kc:{s}")
    assert got == "kc:svc"


def test_blank_env_var_counts_as_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert secrets.get_secret("ANTHROPIC_API_KEY", "svc", keychain=lambda s: None) is None


def test_service_names():
    assert secrets.ANTHROPIC_KEYCHAIN_SERVICE == "meeting-calendar-sync.anthropic-api-key"
    assert secrets.FOUNDRY_KEYCHAIN_SERVICE == "meeting-calendar-sync.foundry-api-key"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain only")
def test_real_lookup_of_missing_item_returns_none():
    assert real_keychain_lookup("meeting-calendar-sync.does-not-exist-test") is None
