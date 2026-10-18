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
    raise ValueError(f"Unknown extractor {kind!r}")
