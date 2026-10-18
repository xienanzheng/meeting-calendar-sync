"""Offline extractor for tests and demos: knows only the committed sample PDFs."""
import hashlib
import json
from pathlib import Path

from mcs.extraction.schema import ExtractionError, ExtractionResult, parse_extraction


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeExtractor:
    name = "fake"

    def __init__(self, samples_dir: Path):
        self.samples_dir = samples_dir

    def extract(self, pdf_path: Path) -> ExtractionResult:
        digest = _sha256(pdf_path)
        for sample in sorted(self.samples_dir.glob("*.pdf")):
            if _sha256(sample) == digest:
                expected = sample.with_suffix(".expected.json")
                return parse_extraction(json.loads(expected.read_text()))
        raise ExtractionError(
            "The fake extractor only knows the sample PDFs in samples/. Set MCS_EXTRACTOR to use Claude."
        )
