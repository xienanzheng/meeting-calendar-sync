"""Extractor using the Anthropic Messages API — direct, or through Microsoft Foundry."""
import base64
from pathlib import Path

import anthropic

from mcs.config import Settings
from mcs.extraction.schema import (
    EXTRACTION_JSON_SCHEMA, EXTRACTION_PROMPT, SYSTEM_PROMPT, ExtractionError, ExtractionResult, parse_extraction,
)

TOOL_NAME = "record_meetings"


class AnthropicExtractor:
    def __init__(self, client, model: str, name: str = "anthropic", max_tokens: int = 16000):
        self.client = client
        self.model = model
        self.name = name
        self.max_tokens = max_tokens

    def extract(self, pdf_path: Path) -> ExtractionResult:
        data = base64.standard_b64encode(pdf_path.read_bytes()).decode()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=[{"name": TOOL_NAME, "description": "Record every meeting found in the schedule.",
                        "input_schema": EXTRACTION_JSON_SCHEMA}],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user", "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}},
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ]}],
            )
        except anthropic.APIError as exc:
            raise ExtractionError(f"Claude API error: {exc.__class__.__name__}: {getattr(exc, 'message', exc)}") from None
        block = next((b for b in response.content
                      if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == TOOL_NAME), None)
        if block is None:
            raise ExtractionError("Claude did not return the meetings in the expected format.")
        return parse_extraction(block.input)


def make_anthropic_client(settings: Settings) -> anthropic.Anthropic:
    key = settings.anthropic_api_key()
    if not key:
        raise ExtractionError(
            "No Anthropic API key: set ANTHROPIC_API_KEY or store it in the Keychain "
            "(service meeting-calendar-sync.anthropic-api-key)."
        )
    return anthropic.Anthropic(api_key=key, timeout=settings.extract_timeout)


def make_foundry_client(settings: Settings) -> anthropic.AnthropicFoundry:
    if not settings.foundry_resource:
        raise ExtractionError("Set ANTHROPIC_FOUNDRY_RESOURCE to your Foundry resource name.")
    key = settings.foundry_api_key()
    if key:
        return anthropic.AnthropicFoundry(api_key=key, resource=settings.foundry_resource,
                                          timeout=settings.extract_timeout)
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError:
        raise ExtractionError(
            "Set ANTHROPIC_FOUNDRY_API_KEY, or install the foundry-entra extra (azure-identity) for Entra sign-in."
        ) from None
    provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")
    return anthropic.AnthropicFoundry(azure_ad_token_provider=provider, resource=settings.foundry_resource,
                                      timeout=settings.extract_timeout)
