import anthropic
import pytest

from mcs.config import REPO_ROOT, Settings
from mcs.extraction import ExtractionError, get_extractor
from mcs.extraction.anthropic_api import AnthropicExtractor
from mcs.extraction.claude_code import ClaudeCodeExtractor
from mcs.extraction.fake import FakeExtractor


def make(**kw):
    return Settings(_env_file=None, use_keychain=False, samples_dir=REPO_ROOT / "samples", **kw)


def test_fake():
    assert isinstance(get_extractor(make(extractor="fake")), FakeExtractor)


def test_auto_without_key_is_claude_code():
    e = get_extractor(make())
    assert isinstance(e, ClaudeCodeExtractor)
    assert e.model == "sonnet"


def test_claude_code_uses_settings():
    e = get_extractor(make(extractor="claude-code", claude_bin="/x/claude", extract_timeout=30, model="haiku"))
    assert (e.claude_bin, e.timeout, e.model) == ("/x/claude", 30, "haiku")


def test_anthropic_with_env_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    e = get_extractor(make())  # auto -> anthropic
    assert isinstance(e, AnthropicExtractor)
    assert e.name == "anthropic"
    assert e.model == "claude-sonnet-5-5"
    assert isinstance(e.client, anthropic.Anthropic)


def test_anthropic_without_key_raises():
    with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
        get_extractor(make(extractor="anthropic"))


def test_foundry_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "fk")
    e = get_extractor(make(extractor="foundry", foundry_resource="my-resource"))
    assert e.name == "foundry"
    assert isinstance(e.client, anthropic.AnthropicFoundry)


def test_foundry_without_resource_raises(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "fk")
    with pytest.raises(ExtractionError, match="ANTHROPIC_FOUNDRY_RESOURCE"):
        get_extractor(make(extractor="foundry"))


def test_secret_never_in_error_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "super-secret-value")
    with pytest.raises(ExtractionError) as info:
        get_extractor(make(extractor="foundry"))
    assert "super-secret-value" not in str(info.value)
