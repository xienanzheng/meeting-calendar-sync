import base64
import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from mcs.extraction.anthropic_api import AnthropicExtractor
from mcs.extraction.schema import EXTRACTION_OUTPUT_SCHEMA, EXTRACTION_PROMPT, SYSTEM_PROMPT, ExtractionError


class FakeMessages:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.kwargs = response, exc, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.exc:
            raise self.exc
        return self.response


def _client(response=None, exc=None):
    return SimpleNamespace(messages=FakeMessages(response, exc))


def _text_response(payload, stop_reason="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))], stop_reason=stop_reason)


def test_anthropic_sdk_has_foundry_client():
    assert hasattr(anthropic, "AnthropicFoundry")


def test_request_shape_and_parse(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4 hello")
    client = _client(_text_response({"city": "London", "meetings": [{"company": "Corvid Diagnostics"}]}))
    result = AnthropicExtractor(client, model="claude-sonnet-5-5").extract(pdf)
    assert result.city == "London"
    assert result.meetings[0].company == "Corvid Diagnostics"
    kw = client.messages.kwargs
    assert kw["model"] == "claude-sonnet-5-5"
    assert kw["system"] == SYSTEM_PROMPT
    assert kw["output_config"] == {"format": {"type": "json_schema", "schema": EXTRACTION_OUTPUT_SCHEMA}}
    assert "tools" not in kw and "tool_choice" not in kw
    doc, text = kw["messages"][0]["content"]
    assert doc["type"] == "document"
    assert doc["source"] == {"type": "base64", "media_type": "application/pdf",
                             "data": base64.standard_b64encode(b"%PDF-1.4 hello").decode()}
    assert text == {"type": "text", "text": EXTRACTION_PROMPT}


def test_name_is_configurable():
    assert AnthropicExtractor(_client(), model="m", name="foundry").name == "foundry"


def test_no_text_raises(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    client = _client(SimpleNamespace(content=[], stop_reason="end_turn"))
    with pytest.raises(ExtractionError, match="did not return"):
        AnthropicExtractor(client, model="m").extract(pdf)


def test_invalid_json_raises(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    client = _client(SimpleNamespace(content=[SimpleNamespace(type="text", text="not json")], stop_reason="end_turn"))
    with pytest.raises(ExtractionError, match="unreadable"):
        AnthropicExtractor(client, model="m").extract(pdf)


def test_max_tokens_stop_reason_raises(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    client = _client(_text_response({"meetings": []}, stop_reason="max_tokens"))
    with pytest.raises(ExtractionError, match="ran out of room"):
        AnthropicExtractor(client, model="m").extract(pdf)


def test_api_error_becomes_extraction_error(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIConnectionError(request=request)
    with pytest.raises(ExtractionError, match="Claude API error"):
        AnthropicExtractor(_client(exc=exc), model="m").extract(pdf)
