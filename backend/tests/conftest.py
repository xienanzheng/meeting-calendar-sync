import os

import pytest
from sqlmodel import Session

from mcs.config import REPO_ROOT, Settings
from mcs.db import make_engine


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Tests never see the developer's real config or secrets."""
    for key in list(os.environ):
        if key.startswith("MCS_") or key.startswith("ANTHROPIC_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("mcs.secrets.keychain_lookup", lambda service: None)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        use_keychain=False,
        extractor="fake",
        data_dir=tmp_path / "data",
        samples_dir=REPO_ROOT / "samples",
    )


@pytest.fixture
def engine(settings):
    return make_engine(settings)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
