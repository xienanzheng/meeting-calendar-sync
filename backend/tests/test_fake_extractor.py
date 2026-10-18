import json

import pytest

from mcs.config import REPO_ROOT
from mcs.extraction import ExtractionError, get_extractor
from mcs.extraction.fake import FakeExtractor
from mcs.extraction.schema import parse_extraction

SAMPLES = REPO_ROOT / "samples"


@pytest.mark.parametrize("name", ["broker_a_grid", "broker_b_by_company", "broker_c_itinerary"])
def test_returns_expected_result_for_sample(name, tmp_path):
    copy = tmp_path / "upload.pdf"  # different file name, same bytes
    copy.write_bytes((SAMPLES / f"{name}.pdf").read_bytes())
    got = FakeExtractor(SAMPLES).extract(copy)
    assert got == parse_extraction(json.loads((SAMPLES / f"{name}.expected.json").read_text()))


def test_unknown_pdf_raises(tmp_path):
    other = tmp_path / "other.pdf"
    other.write_bytes(b"%PDF-1.4\n% not a sample\n")
    with pytest.raises(ExtractionError, match="sample PDFs"):
        FakeExtractor(SAMPLES).extract(other)


def test_factory_returns_fake(settings):
    extractor = get_extractor(settings)
    assert isinstance(extractor, FakeExtractor)
    assert extractor.name == "fake"
