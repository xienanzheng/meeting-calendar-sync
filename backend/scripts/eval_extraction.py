"""Run the configured extractor on every sample PDF and score it. Uses Claude: run by hand, not in pytest.

Also scores private/samples/*.pdf when a matching *.expected.json exists (git-ignored folder).
"""
import json
import sys
import time

from mcs.config import REPO_ROOT, get_settings
from mcs.evaluate import format_score, score
from mcs.extraction import get_extractor
from mcs.extraction.schema import parse_extraction


def main() -> int:
    settings = get_settings()
    extractor = get_extractor(settings)
    print(f"extractor={extractor.name} model={settings.resolved_model()}")
    pdfs = sorted(settings.samples_dir.glob("*.pdf")) + sorted((REPO_ROOT / "private" / "samples").glob("*.pdf"))
    for pdf in pdfs:
        expected_path = pdf.with_suffix(".expected.json")
        if not expected_path.exists():
            print(f"{pdf.name}: no expected JSON, skipped")
            continue
        started = time.monotonic()
        actual = extractor.extract(pdf)
        elapsed = time.monotonic() - started
        print(format_score(pdf.name, score(parse_extraction(json.loads(expected_path.read_text())), actual)))
        print(f"  time: {elapsed:.1f}s, skipped items: {actual.skipped_items}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
