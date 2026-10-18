from pathlib import Path
from typing import Protocol

from mcs.config import Settings
from mcs.extraction.schema import ExtractionError, ExtractionResult

__all__ = ["ExtractionError", "ExtractionResult", "Extractor", "get_extractor"]


class Extractor(Protocol):
    name: str

    def extract(self, pdf_path: Path) -> ExtractionResult: ...


def get_extractor(settings: Settings) -> Extractor:
    kind = settings.resolved_extractor()
    if kind == "fake":
        from mcs.extraction.fake import FakeExtractor

        return FakeExtractor(settings.samples_dir)
    if kind == "claude-code":
        from mcs.extraction.claude_code import ClaudeCodeExtractor

        return ClaudeCodeExtractor(settings.claude_bin, settings.resolved_model(), settings.extract_timeout)
    if kind in ("anthropic", "foundry"):
        from mcs.extraction.anthropic_api import AnthropicExtractor, make_anthropic_client, make_foundry_client

        client = make_anthropic_client(settings) if kind == "anthropic" else make_foundry_client(settings)
        return AnthropicExtractor(client, settings.resolved_model(), name=kind)
    raise ValueError(f"Unknown extractor {kind!r}; use auto, claude-code, anthropic, foundry or fake")
