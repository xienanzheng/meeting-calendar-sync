# Meeting Calendar Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web app where a calendar coordinator uploads a broker conference PDF, Claude extracts the meetings, the coordinator reviews/fixes/confirms them, and confirmed meetings go to each analyst's calendar (.ics now, Microsoft Graph when IT allows).

**Architecture:** FastAPI + SQLite (SQLModel) backend in `backend/` (package `mcs`, managed by uv), React + Vite + TypeScript + Tailwind frontend in `frontend/`. Two swappable seams: `Extractor` (claude-code | anthropic | foundry | fake) and `CalendarSink` (ics | graph). Pure logic (roster matching, normalization/flags, event content, sync planning) is separated from DB/service code and HTTP routes.

**Tech Stack:** Python ≥3.12, uv, FastAPI, SQLModel, pydantic-settings, icalendar, anthropic SDK (incl. `AnthropicFoundry`), httpx, msal, pytest, reportlab (dev, sample PDFs); Node 22, Vite, React 19, TypeScript, Tailwind v4, react-router, luxon, vitest.

**Spec:** `docs/superpowers/specs/2026-10-16-meeting-calendar-sync-design.md`

## Global Constraints

- Local mode binds to `127.0.0.1` by default (port `8765`); the hosted container binds `0.0.0.0:8080` behind the Cloudflare Worker password gate (spec §14).
- All sample/test data is synthetic: fictional companies, fictional analysts with `@example.com` emails, fictional brokers/hotels. Real broker PDFs live only in git-ignored `private/samples/`.
- The UI uses the Woodline Partners theme (spec §2, §9; `PRODUCT.md`; direction contract in `.impeccable/surfaces/frontend-src-pages-reviewpage-tsx.md`; chosen sketch `.impeccable/mocks/decision/assigned.html`). Internal local tool, never published. UI product name: "Meeting Calendar Sync". The UI says "Verify" for the confirm action.
- Secrets only from environment variables, a git-ignored `.env`, or the macOS Keychain (services `meeting-calendar-sync.anthropic-api-key`, `meeting-calendar-sync.foundry-api-key`); `.env.example` has names only. Never print, log or return a secret. Graph access tokens live in process memory only — never written to disk, logs, the DB, or API responses (including error messages).
- The app never sends email or Teams messages.
- Runtime files (`data/app.db`, `data/uploads/`) live under `data/` (git-ignored).
- Upload limit 20 MB; PDF only (`.pdf` extension and `%PDF` magic bytes).
- Default extractor `auto` (= `anthropic` if an Anthropic key is found in env or Keychain, else `claude-code`); default sink `ics`; default meeting length 45 minutes; extraction timeout 240 s.
- Model defaults: `sonnet` for `claude-code`, `claude-sonnet-5-5` for `anthropic`/`foundry`; `MCS_MODEL` overrides.
- Times on the wire to calendars are UTC. API dates are `"YYYY-MM-DD"`, API times are `"HH:MM"` (24h, hotel-local).
- Error responses are JSON `{"detail": ...}`.
- JSON list columns are always reassigned (new list), never mutated in place (SQLAlchemy does not track in-place mutation).
- Tests never call the network or the real `claude` CLI.
- All backend commands run from `backend/`: `uv run pytest`. All frontend commands run from `frontend/`.
- Commit after each task with a conventional message ending in the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Uploading a non-PDF, an empty file, or a file over 20 MB → 400 with a clear message and nothing stored (test in Task 9).
2. Clearing a conference's timezone after meetings were confirmed → those meetings drop back to draft and a send plans nothing for them (test in Task 8).
3. Names with accents or apostrophes ("José Núñez", "Liam O'Neil") → normalized and matched like ASCII names (test in Task 4).
4. "12:00pm" / "12:00am" / "12pm" → noon / midnight, not swapped (test in Task 5).
5. A send where the sink fails one item → successes are recorded; the next send retries only the failed item (test in Task 8).

## Rulings made while planning (deviations from the spec's letter)

- **SyncRecord gets `content_json`** (last successfully sent event content, JSON). Needed so cancellations and `.ics` files can be produced for events whose meeting has since changed. Spec §4 omits it.
- **`.ics` is rendered on demand at download time** from SyncRecords, instead of writing files under `data/ics/` at send time (spec §7). The ICS sink's `apply` only assigns UIDs. Same files, cannot go stale.
- **Env stripping for `claude -p`** removes `CLAUDECODE`, `CLAUDE_PID` and every `CLAUDE_CODE_*` variable (spec names the first and last).
- **Changing a conference's timezone** re-checks confirmed meetings and moves newly blocked ones back to draft (extends spec §6 status rules to conference edits).
- **Editing `start` of a meeting whose end was assumed** (and not sending `end`) recomputes `end = start + default minutes`.

---

### Task 1: Backend scaffold — config, secrets, database models

**Files:**
- Create: `backend/pyproject.toml`, `backend/.python-version`, `backend/mcs/__init__.py`, `backend/mcs/config.py`, `backend/mcs/secrets.py`, `backend/mcs/db.py`, `backend/mcs/models.py`
- Create: `backend/tests/conftest.py`, `backend/tests/test_config.py`, `backend/tests/test_secrets.py`, `backend/tests/test_models.py`
- Create: `.env.example` (repo root)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `mcs.config.REPO_ROOT: Path` (repo root = `Path(__file__).resolve().parents[2]`)
  - `mcs.config.Settings` (pydantic-settings, env prefix `MCS_`) with fields `extractor: Literal["auto","claude-code","anthropic","foundry","fake"] = "auto"`, `model: str | None = None`, `extract_timeout: int = 240`, `claude_bin: str = "claude"`, `calendar_sink: Literal["ics","graph"] = "ics"`, `default_meeting_minutes: int = 45`, `data_dir: Path`, `samples_dir: Path`, `frontend_dist: Path`, `host: str = "127.0.0.1"`, `port: int = 8765`, `graph_client_id: str | None`, `graph_tenant_id: str | None`, `max_upload_mb: int = 20`, `use_keychain: bool = True`, `ephemeral: bool = False`, `foundry_resource: str | None` (env `ANTHROPIC_FOUNDRY_RESOURCE`); properties `db_url: str`, `uploads_dir: Path`; methods `anthropic_api_key() -> str | None`, `foundry_api_key() -> str | None`, `resolved_extractor() -> str`, `resolved_model() -> str`
  - `mcs.config.get_settings() -> Settings`
  - `mcs.secrets.get_secret(env_name: str, keychain_service: str, *, keychain: Callable[[str], str | None]) -> str | None`, `mcs.secrets.keychain_lookup(service: str) -> str | None`, constants `ANTHROPIC_KEYCHAIN_SERVICE = "meeting-calendar-sync.anthropic-api-key"`, `FOUNDRY_KEYCHAIN_SERVICE = "meeting-calendar-sync.foundry-api-key"`
  - `mcs.db.make_engine(settings: Settings) -> sqlalchemy.Engine` (creates `data_dir`, enables SQLite foreign keys, creates tables)
  - `mcs.models`: `utcnow()`, tables `Analyst`, `Conference`, `Meeting`, `MeetingAttendee`, `SyncRecord` (exact fields below)
  - Test fixtures in `tests/conftest.py`: `settings` (tmp data dir, `extractor="fake"`, `use_keychain=False`), `engine`, `session`; an autouse fixture that removes `MCS_*`/`ANTHROPIC_*` env vars and patches `mcs.secrets.keychain_lookup` to return `None` (tests must never read the real Keychain).

- [ ] **Step 1: Create the uv project**

From the repo root:

```bash
mkdir -p backend && cd backend
uv init --package --name mcs --python 3.13 --no-readme .
rm -rf src  # we use a flat package layout
mkdir -p mcs tests
uv add fastapi "uvicorn[standard]" sqlmodel python-multipart icalendar anthropic httpx msal pydantic-settings
uv add --dev pytest reportlab
uv add --optional foundry-entra azure-identity
```

Then make `backend/pyproject.toml` contain (keep the version pins `uv add` wrote in `dependencies`):

```toml
[project]
name = "mcs"
version = "0.1.0"
description = "Meeting Calendar Sync - broker conference PDFs to calendars (prototype)"
requires-python = ">=3.12"
# dependencies = [...] as written by uv add

[project.scripts]
mcs = "mcs.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["mcs"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`backend/mcs/__init__.py`: `"""Meeting Calendar Sync backend."""`

- [ ] **Step 2: Write the failing tests**

`backend/tests/conftest.py`:

```python
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
```

`backend/tests/test_secrets.py`:

```python
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
```

`backend/tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from mcs.config import REPO_ROOT, Settings


def make(**kw):
    return Settings(_env_file=None, use_keychain=False, **kw)


def test_defaults():
    s = make()
    assert s.extractor == "auto"
    assert s.resolved_extractor() == "claude-code"
    assert s.resolved_model() == "sonnet"
    assert s.calendar_sink == "ics"
    assert (s.host, s.port) == ("127.0.0.1", 8765)
    assert s.default_meeting_minutes == 45
    assert s.extract_timeout == 240
    assert s.max_upload_mb == 20
    assert s.data_dir == REPO_ROOT / "data"
    assert s.frontend_dist == REPO_ROOT / "frontend" / "dist"


def test_auto_picks_anthropic_when_env_key_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = make()
    assert s.resolved_extractor() == "anthropic"
    assert s.resolved_model() == "claude-sonnet-5-5"
    assert s.anthropic_api_key() == "test-key"


def test_auto_picks_anthropic_when_keychain_has_key(monkeypatch):
    monkeypatch.setattr("mcs.secrets.keychain_lookup", lambda service: "kc-key" if "anthropic" in service else None)
    s = Settings(_env_file=None, use_keychain=True)
    assert s.anthropic_api_key() == "kc-key"
    assert s.resolved_extractor() == "anthropic"


def test_use_keychain_false_ignores_keychain(monkeypatch):
    monkeypatch.setattr("mcs.secrets.keychain_lookup", lambda service: "kc-key")
    assert make().anthropic_api_key() is None


def test_explicit_extractor_and_model(monkeypatch):
    monkeypatch.setenv("MCS_EXTRACTOR", "claude-code")
    monkeypatch.setenv("MCS_MODEL", "opus")
    monkeypatch.setenv("MCS_PORT", "9000")
    s = make()
    assert s.resolved_extractor() == "claude-code"
    assert s.resolved_model() == "opus"
    assert s.port == 9000


def test_foundry_resource_from_env_or_init(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "my-resource")
    assert make().foundry_resource == "my-resource"
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_RESOURCE")
    assert make(foundry_resource="other").foundry_resource == "other"


def test_foundry_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "fk")
    assert make().foundry_api_key() == "fk"


def test_invalid_extractor_rejected():
    with pytest.raises(ValidationError):
        make(extractor="gpt")


def test_paths(tmp_path):
    s = make(data_dir=tmp_path)
    assert s.db_url == f"sqlite:///{tmp_path / 'app.db'}"
    assert s.uploads_dir == tmp_path / "uploads"
```

`backend/tests/test_models.py`:

```python
import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from mcs.models import Analyst, Conference, Meeting, MeetingAttendee, SyncRecord


def _conference(session):
    c = Conference(name="Industrials Conference 2026", timezone="America/New_York")
    session.add(c)
    session.commit()
    return c


def test_roundtrip_all_tables(session):
    a = Analyst(name="Avery Kim", email="avery.kim@example.com", aliases=["A. Kim"])
    session.add(a)
    c = _conference(session)
    m = Meeting(
        conference_id=c.id, date=dt.date(2026, 11, 10), start_time=dt.time(8, 0), end_time=dt.time(8, 45),
        company="Northwind Robotics", company_attendees=["Dana Shore, CFO"], raw_attendee_names=["Avery Kim"],
    )
    session.add(m)
    session.commit()
    session.add(MeetingAttendee(meeting_id=m.id, analyst_id=a.id, match="exact"))
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="ics", external_id="uid-1",
                           content_hash="h", content_json="{}"))
    session.commit()
    session.expire_all()

    got = session.get(Meeting, m.id)
    assert got.company_attendees == ["Dana Shore, CFO"]
    assert got.raw_attendee_names == ["Avery Kim"]
    assert got.ignored_names == []
    assert (got.status, got.format, got.end_assumed, got.room) == ("draft", "one_on_one", False, "")
    assert session.get(Analyst, a.id).aliases == ["A. Kim"]
    assert session.get(Analyst, a.id).active is True
    rec = session.exec(select(SyncRecord)).one()
    assert (rec.sequence, rec.state, rec.last_error) == (0, "active", None)


def test_analyst_email_unique(session):
    session.add(Analyst(name="A", email="a@example.com"))
    session.commit()
    session.add(Analyst(name="B", email="a@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_sync_record_unique_per_meeting_analyst_sink(session):
    a = Analyst(name="A", email="a@example.com")
    session.add(a)
    c = _conference(session)
    m = Meeting(conference_id=c.id, company="X")
    session.add(m)
    session.commit()
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="ics"))
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="graph"))
    session.commit()
    session.add(SyncRecord(meeting_id=m.id, analyst_id=a.id, sink="ics"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_keys_enforced(session):
    session.add(Meeting(conference_id=999, company="X"))
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q`
Expected: collection errors — `ModuleNotFoundError: No module named 'mcs.config'`.

- [ ] **Step 4: Implement `mcs/secrets.py`**

```python
"""Secret lookup: environment variable first, then the macOS login Keychain.

Values are returned to the caller only — never printed or logged here.
"""
import os
import subprocess
import sys
from typing import Callable

ANTHROPIC_KEYCHAIN_SERVICE = "meeting-calendar-sync.anthropic-api-key"
FOUNDRY_KEYCHAIN_SERVICE = "meeting-calendar-sync.foundry-api-key"


def keychain_lookup(service: str) -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def get_secret(env_name: str, keychain_service: str, *, keychain: Callable[[str], str | None]) -> str | None:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    return keychain(keychain_service)
```

- [ ] **Step 5: Implement `mcs/config.py`**

```python
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcs import secrets

REPO_ROOT = Path(__file__).resolve().parents[2]


def _no_keychain(service: str) -> None:
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCS_", env_file=REPO_ROOT / ".env", extra="ignore")

    extractor: Literal["auto", "claude-code", "anthropic", "foundry", "fake"] = "auto"
    model: str | None = None
    extract_timeout: int = 240
    claude_bin: str = "claude"
    calendar_sink: Literal["ics", "graph"] = "ics"
    default_meeting_minutes: int = 45
    data_dir: Path = REPO_ROOT / "data"
    samples_dir: Path = REPO_ROOT / "samples"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    host: str = "127.0.0.1"
    port: int = 8765
    graph_client_id: str | None = None
    graph_tenant_id: str | None = None
    max_upload_mb: int = 20
    use_keychain: bool = True
    ephemeral: bool = False  # hosted demo: data resets when the container sleeps
    foundry_resource: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_FOUNDRY_RESOURCE", "foundry_resource")
    )

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'app.db'}"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    def _keychain(self):
        # Resolve the module attribute at call time so tests can patch it.
        return secrets.keychain_lookup if self.use_keychain else _no_keychain

    def anthropic_api_key(self) -> str | None:
        return secrets.get_secret("ANTHROPIC_API_KEY", secrets.ANTHROPIC_KEYCHAIN_SERVICE, keychain=self._keychain())

    def foundry_api_key(self) -> str | None:
        return secrets.get_secret("ANTHROPIC_FOUNDRY_API_KEY", secrets.FOUNDRY_KEYCHAIN_SERVICE, keychain=self._keychain())

    def resolved_extractor(self) -> str:
        if self.extractor != "auto":
            return self.extractor
        return "anthropic" if self.anthropic_api_key() else "claude-code"

    def resolved_model(self) -> str:
        if self.model:
            return self.model
        return "sonnet" if self.resolved_extractor() == "claude-code" else "claude-sonnet-5-5"


def get_settings() -> Settings:
    return Settings()
```

If `test_foundry_resource_from_env_or_init` fails because pydantic-settings ignores the alias for env lookup, add `populate_by_name=True` to `model_config` and re-run; do not change the test.

- [ ] **Step 6: Implement `mcs/models.py`**

```python
import datetime as dt

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Analyst(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    active: bool = True


class Conference(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    broker: str = ""
    hotel: str = ""
    city: str = ""
    timezone: str | None = None
    schedule_for: str = ""
    pdf_filename: str = ""
    pdf_path: str = ""
    extractor: str = ""
    created_at: dt.datetime = Field(default_factory=utcnow)


class Meeting(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conference_id: int = Field(foreign_key="conference.id", index=True)
    date: dt.date | None = None
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    end_assumed: bool = False
    room: str = ""
    company: str
    ticker: str | None = None
    format: str = "one_on_one"  # one_on_one | group | meal | other
    company_attendees: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    raw_attendee_names: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    ignored_names: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    notes: str = ""
    source_page: int | None = None
    status: str = "draft"  # draft | confirmed | cancelled
    created_at: dt.datetime = Field(default_factory=utcnow)
    updated_at: dt.datetime = Field(default_factory=utcnow)


class MeetingAttendee(SQLModel, table=True):
    meeting_id: int = Field(foreign_key="meeting.id", primary_key=True)
    analyst_id: int = Field(foreign_key="analyst.id", primary_key=True)
    match: str = "manual"  # exact | alias | initial | fuzzy | manual | default


class SyncRecord(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("meeting_id", "analyst_id", "sink"),)

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meeting.id", index=True)
    analyst_id: int = Field(foreign_key="analyst.id")
    sink: str  # ics | graph
    external_id: str | None = None  # ICS UID or Graph event id; None until a create succeeds
    content_hash: str = ""
    content_json: str = ""  # last successfully sent EventContent as JSON
    sequence: int = 0
    state: str = "active"  # active | cancelled | failed
    last_error: str | None = None
    updated_at: dt.datetime = Field(default_factory=utcnow)
```

- [ ] **Step 7: Implement `mcs/db.py`**

```python
from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from mcs import models  # noqa: F401  (registers tables on SQLModel.metadata)
from mcs.config import Settings


def make_engine(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)
    return engine
```

- [ ] **Step 8: Write `.env.example`** (repo root)

```bash
# Copy to .env (git-ignored). Names only - never commit values.
# MCS_EXTRACTOR=auto            # auto | claude-code | anthropic | foundry | fake
# MCS_MODEL=                    # default: sonnet (claude-code) / claude-sonnet-5-5 (anthropic, foundry)
# MCS_CALENDAR_SINK=ics         # ics | graph
# MCS_DEFAULT_MEETING_MINUTES=45
# MCS_PORT=8765
# ANTHROPIC_API_KEY=            # or macOS Keychain service: meeting-calendar-sync.anthropic-api-key
# ANTHROPIC_FOUNDRY_RESOURCE=
# ANTHROPIC_FOUNDRY_API_KEY=    # or macOS Keychain service: meeting-calendar-sync.foundry-api-key
# MCS_GRAPH_CLIENT_ID=
# MCS_GRAPH_TENANT_ID=
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all tests in `test_config.py`, `test_secrets.py`, `test_models.py` pass.

- [ ] **Step 10: Commit**

```bash
git add backend .env.example
git commit -m "feat: backend scaffold with settings, keychain secrets and SQLite models

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Extraction contract, synthetic sample PDFs, fake extractor

**Files:**
- Create: `backend/mcs/extraction/__init__.py`, `backend/mcs/extraction/schema.py`, `backend/mcs/extraction/fake.py`
- Create: `backend/scripts/make_sample_pdfs.py`
- Create (generated by the script, committed): `samples/broker_a_grid.pdf`, `samples/broker_b_by_company.pdf`, `samples/broker_c_itinerary.pdf`, `samples/broker_a_grid.expected.json`, `samples/broker_b_by_company.expected.json`, `samples/broker_c_itinerary.expected.json`, `samples/roster.sample.json`
- Test: `backend/tests/test_extraction_schema.py`, `backend/tests/test_samples.py`, `backend/tests/test_fake_extractor.py`

**Interfaces:**
- Consumes: `mcs.config.Settings` (`resolved_extractor()`, `samples_dir`) from Task 1.
- Produces:
  - `mcs.extraction.schema`: `ExtractionError(Exception)`; `ExtractedMeeting` (fields `date, start, end, room: str|None`, `company: str`, `ticker: str|None`, `format: Literal["one_on_one","group","meal","other"]`, `company_attendees: list[str]`, `firm_attendees: list[str]`, `notes: str|None`, `page: int|None`); `ExtractionResult` (fields `conference_name, broker, hotel, city, timezone, schedule_for: str|None`, `meetings: list[ExtractedMeeting]`, `skipped_items: int`); `parse_extraction(raw: Any) -> ExtractionResult`; `EXTRACTION_JSON_SCHEMA: dict`; `SYSTEM_PROMPT: str`; `EXTRACTION_PROMPT: str`
  - `mcs.extraction`: re-exports `ExtractionError`, `ExtractionResult`; `Extractor` Protocol (`name: str`, `extract(pdf_path: Path) -> ExtractionResult`); `get_extractor(settings) -> Extractor` (this task: `"fake"` only; Task 3 adds the rest)
  - `mcs.extraction.fake.FakeExtractor(samples_dir: Path)` with `name = "fake"`
  - `samples/roster.sample.json`: list of `{"name", "email", "aliases"}` (6 fictional analysts)
  - Sample facts later tasks rely on: broker A = 12 meetings, `America/New_York`, contains raw name "Chris Wong" (not on roster); broker B = 8 meetings, `America/Los_Angeles`, initials "A. Kim"/"Morgan D.", alias "Samir Patel"/"Tay Brooks", typo "Rilay Chen" (fuzzy → Riley Chen), Pixelmint 09:30–10:30 and Orbital 09:45–10:30 on 2026-12-02 both include "Rilay Chen" (double booking); broker C = 6 meetings, `Europe/London`, `schedule_for = "Sam Patel"`, no end times, empty `firm_attendees`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_extraction_schema.py`:

```python
import pytest

from mcs.extraction.schema import (
    EXTRACTION_JSON_SCHEMA, EXTRACTION_PROMPT, ExtractedMeeting, ExtractionError, ExtractionResult, parse_extraction,
)


def test_schema_properties_match_models():
    meeting_props = set(EXTRACTION_JSON_SCHEMA["properties"]["meetings"]["items"]["properties"])
    assert meeting_props == set(ExtractedMeeting.model_fields)
    top_props = set(EXTRACTION_JSON_SCHEMA["properties"])
    assert top_props == set(ExtractionResult.model_fields) - {"skipped_items"}
    assert EXTRACTION_JSON_SCHEMA["required"] == ["meetings"]
    assert EXTRACTION_JSON_SCHEMA["properties"]["meetings"]["items"]["required"] == ["company"]


def test_invalid_items_are_skipped_and_counted():
    raw = {"meetings": [{"company": "Northwind Robotics"}, {"company": "   "}, {"room": "Salon 4"}, "junk", {"company": "Cobalt"}]}
    result = parse_extraction(raw)
    assert [m.company for m in result.meetings] == ["Northwind Robotics", "Cobalt"]
    assert result.skipped_items == 3


@pytest.mark.parametrize("given,expected", [
    ("1x1", "one_on_one"), ("One-on-One", "one_on_one"), ("one_on_one", "one_on_one"),
    ("Lunch", "meal"), ("breakfast", "meal"), ("Small Group", "group"), ("group", "group"),
    ("presentation", "other"), (None, "one_on_one"),
])
def test_format_synonyms(given, expected):
    assert ExtractedMeeting(company="X", format=given).format == expected


def test_names_are_cleaned():
    m = ExtractedMeeting(company=" Cobalt ", firm_attendees=[" A. Kim ", "", None, "Jordan Lee"], company_attendees=None)
    assert m.company == "Cobalt"
    assert m.firm_attendees == ["A. Kim", "Jordan Lee"]
    assert m.company_attendees == []


def test_top_level_blanks_become_none_and_extras_are_ignored():
    result = parse_extraction({"hotel": "  ", "city": "London", "surprise": 1, "meetings": []})
    assert result.hotel is None
    assert result.city == "London"
    assert result.meetings == []
    assert result.skipped_items == 0


def test_missing_meetings_key_means_no_meetings():
    assert parse_extraction({"hotel": "X"}).meetings == []


def test_non_object_raises_extraction_error():
    with pytest.raises(ExtractionError):
        parse_extraction(["not", "an", "object"])


def test_prompt_covers_key_rules():
    for phrase in ("firm_attendees", "schedule_for", "IANA", "24-hour", "Never guess", "page"):
        assert phrase in EXTRACTION_PROMPT
```

`backend/tests/test_samples.py`:

```python
import hashlib
import importlib.util
import json
import re
from zoneinfo import ZoneInfo

import pytest

from mcs.config import REPO_ROOT
from mcs.extraction.schema import parse_extraction

SAMPLES = REPO_ROOT / "samples"
EXPECTED_COUNTS = {"broker_a_grid": 12, "broker_b_by_company": 8, "broker_c_itinerary": 6}


def _load_script():
    path = REPO_ROOT / "backend" / "scripts" / "make_sample_pdfs.py"
    spec = importlib.util.spec_from_file_location("make_sample_pdfs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _expected(name):
    return parse_extraction(json.loads((SAMPLES / f"{name}.expected.json").read_text()))


@pytest.mark.parametrize("name,count", EXPECTED_COUNTS.items())
def test_expected_json_is_valid(name, count):
    result = _expected(name)
    assert len(result.meetings) == count
    assert result.skipped_items == 0
    ZoneInfo(result.timezone)  # raises if invalid


@pytest.mark.parametrize("name", EXPECTED_COUNTS)
def test_pdf_page_count_matches_expected_pages(name):
    data = (SAMPLES / f"{name}.pdf").read_bytes()
    pages = len(re.findall(rb"/Type /Page[^s]", data))
    assert pages == max(m.page for m in _expected(name).meetings)


def test_regenerating_samples_is_byte_identical(tmp_path):
    _load_script().main(tmp_path)
    for path in sorted(SAMPLES.glob("*")):
        if path.suffix in (".pdf", ".json"):
            regenerated = tmp_path / path.name
            assert hashlib.sha256(regenerated.read_bytes()).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest(), path.name


def test_roster_sample():
    roster = json.loads((SAMPLES / "roster.sample.json").read_text())
    assert [a["name"] for a in roster] == ["Avery Kim", "Sam Patel", "Jordan Lee", "Riley Chen", "Morgan Diaz", "Taylor Brooks"]
    assert all(a["email"].endswith("@example.com") for a in roster)


def test_sample_b_contains_the_double_booking():
    b = _expected("broker_b_by_company")
    rows = {m.company: m for m in b.meetings}
    pix, orb = rows["Pixelmint Studios"], rows["Orbital Data Networks"]
    assert pix.date == orb.date == "2026-12-02"
    assert (pix.start, pix.end, orb.start, orb.end) == ("09:30", "10:30", "09:45", "10:30")
    assert "Rilay Chen" in pix.firm_attendees and "Rilay Chen" in orb.firm_attendees


def test_sample_c_is_an_itinerary_without_end_times():
    c = _expected("broker_c_itinerary")
    assert c.schedule_for == "Sam Patel"
    assert all(m.end is None and m.firm_attendees == [] for m in c.meetings)
```

`backend/tests/test_fake_extractor.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q tests/test_extraction_schema.py tests/test_samples.py tests/test_fake_extractor.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.extraction'`.

- [ ] **Step 3: Implement `mcs/extraction/schema.py`**

```python
"""Shared extraction contract: result models, the JSON schema given to Claude, and the prompt."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ExtractionError(Exception):
    """Extraction failed; the message is shown to the coordinator."""


MeetingFormat = Literal["one_on_one", "group", "meal", "other"]

_FORMAT_SYNONYMS = {
    "one_on_one": "one_on_one", "1x1": "one_on_one", "1:1": "one_on_one", "one-on-one": "one_on_one",
    "one on one": "one_on_one", "group": "group", "small group": "group", "meal": "meal", "lunch": "meal",
    "breakfast": "meal", "dinner": "meal", "other": "other",
}


class ExtractedMeeting(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str | None = None
    start: str | None = None
    end: str | None = None
    room: str | None = None
    company: str = Field(min_length=1)
    ticker: str | None = None
    format: MeetingFormat = "one_on_one"
    company_attendees: list[str] = Field(default_factory=list)
    firm_attendees: list[str] = Field(default_factory=list)
    notes: str | None = None
    page: int | None = None

    @field_validator("company", mode="before")
    @classmethod
    def _strip_company(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("format", mode="before")
    @classmethod
    def _normalise_format(cls, v):
        if v is None:
            return "one_on_one"
        return _FORMAT_SYNONYMS.get(str(v).strip().lower(), "other")

    @field_validator("company_attendees", "firm_attendees", mode="before")
    @classmethod
    def _clean_names(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        return [s.strip() for s in v if isinstance(s, str) and s.strip()]


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conference_name: str | None = None
    broker: str | None = None
    hotel: str | None = None
    city: str | None = None
    timezone: str | None = None
    schedule_for: str | None = None
    meetings: list[ExtractedMeeting] = Field(default_factory=list)
    skipped_items: int = 0


_TOP_LEVEL_TEXT_FIELDS = ("conference_name", "broker", "hotel", "city", "timezone", "schedule_for")


def parse_extraction(raw: Any) -> ExtractionResult:
    """Validate provider output leniently: invalid meeting items are skipped and counted."""
    if not isinstance(raw, dict):
        raise ExtractionError("Claude returned something other than a JSON object.")
    items = raw.get("meetings") or []
    if not isinstance(items, list):
        items = []
    meetings: list[ExtractedMeeting] = []
    skipped = 0
    for item in items:
        try:
            meetings.append(ExtractedMeeting.model_validate(item))
        except ValidationError:
            skipped += 1
    top = {}
    for key in _TOP_LEVEL_TEXT_FIELDS:
        value = raw.get(key)
        top[key] = value.strip() if isinstance(value, str) and value.strip() else None
    return ExtractionResult(**top, meetings=meetings, skipped_items=skipped)


_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "conference_name": {**_STR, "description": "Conference title as printed"},
        "broker": {**_STR, "description": "Hosting bank or broker"},
        "hotel": {**_STR, "description": "Venue or hotel name"},
        "city": _STR,
        "timezone": {**_STR, "description": "IANA timezone of the venue, e.g. America/New_York"},
        "schedule_for": {**_STR, "description": "Firm or person this schedule is addressed to, as printed"},
        "meetings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {**_STR, "description": "YYYY-MM-DD"},
                    "start": {**_STR, "description": "HH:MM 24-hour, venue local time"},
                    "end": {**_STR, "description": "HH:MM 24-hour, venue local time; omit if not printed"},
                    "room": _STR,
                    "company": _STR,
                    "ticker": _STR,
                    "format": {"type": "string", "enum": ["one_on_one", "group", "meal", "other"]},
                    "company_attendees": {**_STR_LIST, "description": "The company's executives as printed (name, title)"},
                    "firm_attendees": {**_STR_LIST, "description": "People from the schedule's firm printed on this row; empty if none"},
                    "notes": _STR,
                    "page": {"type": "integer", "description": "1-based PDF page number"},
                },
                "required": ["company"],
            },
        },
    },
    "required": ["meetings"],
}

SYSTEM_PROMPT = (
    "You extract meeting schedules from broker conference PDFs into structured data. "
    "Read the whole document, then return the structured result. Never invent values."
)

EXTRACTION_PROMPT = """Extract every scheduled meeting from this broker conference schedule.

Rules:
- One entry per meeting row. Include group meetings, meals and presentations the schedule lists.
- Copy names exactly as printed (do not expand initials or fix spelling).
- company: the company being met, without the ticker. ticker: its ticker symbol if printed.
- company_attendees: the company's executives as printed, e.g. "Dana Shore, CFO".
- firm_attendees: the people from the firm this schedule is for, printed on that row. Leave it empty if the row lists nobody.
- schedule_for: who the whole schedule is addressed to ("Schedule for: ...", "Itinerary for: ...").
- date: YYYY-MM-DD. Infer the year from the document header if a row omits it.
- start / end: 24-hour HH:MM in the venue's local time, exactly as printed. Omit end if only a start time is printed.
- format: one_on_one for 1x1 or one-on-one; group for group or small-group meetings; meal for breakfast, lunch or dinner; otherwise other.
- room: the room, suite or location as printed (e.g. "Suite 1201", "TBD").
- timezone: the IANA timezone of the venue's city (e.g. America/New_York, Europe/London).
- page: the 1-based PDF page number the meeting appears on.
- Omit any field you cannot find. Never guess."""
```

- [ ] **Step 4: Implement `mcs/extraction/__init__.py` and `mcs/extraction/fake.py`**

`backend/mcs/extraction/__init__.py`:

```python
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
```

`backend/mcs/extraction/fake.py`:

```python
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
```

- [ ] **Step 5: Write `backend/scripts/make_sample_pdfs.py`**

```python
"""Generate synthetic broker schedule PDFs and their expected extraction JSON into samples/.

Every company, person, broker and hotel here is fictional.
Run from backend/: uv run python scripts/make_sample_pdfs.py
"""
import datetime as dt
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
FOOTER = "Sample data — fictional companies and people"
STYLES = getSampleStyleSheet()
SMALL = ParagraphStyle("small", parent=STYLES["Normal"], fontSize=8, leading=10)
COMPACT = ParagraphStyle("compact", parent=STYLES["Normal"], fontSize=9, leading=11)

ROSTER = [
    {"name": "Avery Kim", "email": "avery.kim@example.com", "aliases": []},
    {"name": "Sam Patel", "email": "sam.patel@example.com", "aliases": ["Samir Patel"]},
    {"name": "Jordan Lee", "email": "jordan.lee@example.com", "aliases": []},
    {"name": "Riley Chen", "email": "riley.chen@example.com", "aliases": []},
    {"name": "Morgan Diaz", "email": "morgan.diaz@example.com", "aliases": []},
    {"name": "Taylor Brooks", "email": "taylor.brooks@example.com", "aliases": ["Tay Brooks"]},
]


def mt(date, start, end, fmt, room, company, ticker, execs, firm, page):
    return {"date": date, "start": start, "end": end, "room": room, "company": company, "ticker": ticker,
            "format": fmt, "company_attendees": execs, "firm_attendees": firm, "notes": None, "page": page}


BROKER_A = {
    "conference_name": "Industrials Conference 2026", "broker": "Example Securities",
    "hotel": "The Example Grand Hotel", "city": "New York, NY", "timezone": "America/New_York",
    "schedule_for": "Sample Capital",
    "meetings": [
        mt("2026-11-10", "08:00", "08:45", "one_on_one", "Salon 4", "Northwind Robotics", "NWRB", ["Dana Shore, CFO"], ["Avery Kim", "Jordan Lee"], 1),
        mt("2026-11-10", "09:00", "09:45", "one_on_one", "Suite 1201", "Borealis Grid Systems", "BRGS", ["Tom Rayner, CEO", "Ellen Ko, Investor Relations"], ["Jordan Lee"], 1),
        mt("2026-11-10", "10:00", "10:45", "one_on_one", "Salon 4", "Cobalt Freight Lines", "CBFL", ["Priya Nair, CFO"], ["Riley Chen", "Avery Kim"], 1),
        mt("2026-11-10", "11:00", "11:45", "group", "Suite 1410", "Halcyon Aerostructures", "HLAS", ["Marcus Webb, CEO"], ["Taylor Brooks"], 1),
        mt("2026-11-10", "12:00", "13:15", "meal", "Grand Ballroom B", "Keystone Valve Corp", "KSVC", ["Lena Ortiz, CFO"], ["Avery Kim", "Jordan Lee", "Riley Chen"], 1),
        mt("2026-11-10", "13:30", "14:15", "one_on_one", "TBD", "Meridian Rail Holdings", "MRHL", ["Owen Pratt, CFO"], ["Morgan Diaz"], 1),
        mt("2026-11-11", "08:00", "08:45", "one_on_one", "Salon 2", "Ironleaf Packaging", "IRLP", ["Grace Liu, CEO"], ["Sam Patel"], 2),
        mt("2026-11-11", "09:00", "09:45", "group", "Salon 2", "Quarry Point Materials", "QPMT", ["Victor Hale, CFO"], ["Sam Patel", "Taylor Brooks"], 2),
        mt("2026-11-11", "10:00", "10:45", "one_on_one", "Suite 1201", "Tidewater Pumps", "TWPM", ["Nina Brandt, Investor Relations"], ["Chris Wong"], 2),
        mt("2026-11-11", "11:00", "11:45", "one_on_one", "Suite 1201", "Summit Forge Industries", "SMFI", ["Ray Castillo, CEO"], ["Avery Kim"], 2),
        mt("2026-11-11", "14:00", "14:45", "one_on_one", "Salon 4", "Lumen Sensor Works", "LMSW", ["Hana Mori, CFO"], ["Jordan Lee"], 2),
        mt("2026-11-11", "15:00", "15:45", "group", "Salon 4", "Granite Bay Logistics", "GBLG", ["Eli Turner, CFO"], ["Morgan Diaz", "Riley Chen"], 2),
    ],
}

BROKER_B = {
    "conference_name": "Technology Summit 2026", "broker": "Demo Partners Securities",
    "hotel": "The Demo Resort", "city": "Las Vegas, NV", "timezone": "America/Los_Angeles",
    "schedule_for": "Sample Capital",
    "meetings": [
        mt("2026-12-02", "08:30", "09:15", "one_on_one", "Suite 3105", "Vantage Cloud Software", "VTCS", ["Ari Feld, CEO"], ["A. Kim"], 1),
        mt("2026-12-02", "09:30", "10:30", "group", "Ballroom C", "Pixelmint Studios", "PXMS", ["June Park, CFO"], ["A. Kim", "Rilay Chen"], 1),
        mt("2026-12-02", "09:45", "10:30", "one_on_one", "Suite 2210", "Orbital Data Networks", "ORDN", ["Sol Mendes, CFO"], ["Rilay Chen"], 1),
        mt("2026-12-02", "12:00", "13:30", "meal", "Sage Room", "Brightpath Payments", "BRPY", ["Kim Alvarez, CEO", "Rob Tan, CFO"], ["Morgan D.", "Tay Brooks"], 1),
        mt("2026-12-03", "08:00", "08:45", "one_on_one", "Suite 3105", "Kestrel Security", "KSTL", ["Ivan Petrov, CFO"], ["Jordan Lee"], 2),
        mt("2026-12-03", "09:00", "09:45", "one_on_one", "Suite 3105", "Nimbus Health Tech", "NBHT", ["Clara Voss, CEO"], ["Samir Patel"], 2),
        mt("2026-12-03", "10:00", "11:00", "group", "Ballroom A", "Driftwood Semiconductors", "DWSC", ["Ken Ito, CFO"], ["Jordan Lee", "Samir Patel", "A. Kim"], 2),
        mt("2026-12-03", "13:00", "13:45", "one_on_one", "Suite 2210", "Copperline Telecom", "CPLT", ["Maya Ross, Investor Relations"], ["Tay Brooks"], 2),
    ],
}

BROKER_C = {
    "conference_name": "Global Healthcare Conference 2026", "broker": "Demo Bank",
    "hotel": "The Sample Park Hotel", "city": "London", "timezone": "Europe/London",
    "schedule_for": "Sam Patel",
    "meetings": [
        mt("2026-11-17", "08:00", None, "meal", "Garden Room", "Asterion Biologics", "ASTB", ["Dr. Helen Marsh, CEO"], [], 1),
        mt("2026-11-17", "09:30", None, "one_on_one", "Suite 502", "Corvid Diagnostics", "CRVD", ["Paul Okafor, CFO"], [], 1),
        mt("2026-11-17", "11:00", None, "group", "Churchill Room", "Elmstone Pharma", "ELMP", ["Sofia Reyes, CFO", "Tim Hart, Investor Relations"], [], 1),
        mt("2026-11-17", "14:00", None, "one_on_one", "Suite 502", "Juniper MedDevices", "JNMD", ["Arun Mehta, CEO"], [], 1),
        mt("2026-11-18", "09:00", None, "one_on_one", "Suite 610", "Larkspur Genomics", "LKGN", ["Beth Collins, CFO"], [], 1),
        mt("2026-11-18", "10:30", None, "one_on_one", "Suite 610", "Mossgate Therapeutics", "MSGT", ["Omar Haddad, CEO"], [], 1),
    ],
}

A_TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Lunch"}
B_TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Lunch"}
C_TYPE = {"one_on_one": "1x1", "group": "Group", "meal": "Breakfast"}


def h12(hhmm: str, compact: bool = False) -> str:
    h, m = map(int, hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    text = f"{h % 12 or 12}:{m:02d}"
    return f"{text}{suffix.lower()}" if compact else f"{text} {suffix}"


def us_heading(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%A, %B} {d.day}, {d.year}"


def uk_heading(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%A} {d.day} {d:%B %Y}"


def _doc(path: Path) -> SimpleDocTemplate:
    return SimpleDocTemplate(str(path), pagesize=letter, invariant=1, title="Sample broker schedule",
                             leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)


def _table(rows, widths) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDDDDD")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    return table


def _header(lines: list[str]) -> list:
    story = [Paragraph(lines[0], STYLES["Title"])]
    story += [Paragraph(line, STYLES["Normal"]) for line in lines[1:]]
    return story + [Spacer(1, 10)]


def build_a(out: Path) -> None:
    d = BROKER_A
    story = _header([d["conference_name"], f"Hosted by {d['broker']}", f"{d['hotel']} · {d['city']}",
                     "November 10–11, 2026", f"Meeting schedule for: {d['schedule_for']}"])
    for i, day in enumerate(["2026-11-10", "2026-11-11"]):
        if i:
            story.append(PageBreak())
        story.append(Paragraph(us_heading(day), STYLES["Heading2"]))
        rows = [["Time", "Type", "Room", "Company (Ticker)", "Management", "Attendees"]]
        for m in (x for x in d["meetings"] if x["date"] == day):
            rows.append([f"{h12(m['start'])} - {h12(m['end'])}", A_TYPE[m["format"]], m["room"],
                         Paragraph(f"{m['company']} ({m['ticker']})", SMALL),
                         Paragraph("; ".join(m["company_attendees"]), SMALL),
                         Paragraph(", ".join(m["firm_attendees"]), SMALL)])
        story += [_table(rows, [85, 40, 70, 120, 120, 97]), Spacer(1, 12), Paragraph(FOOTER, SMALL)]
    _doc(out / "broker_a_grid.pdf").build(story)


def build_b(out: Path) -> None:
    d = BROKER_B
    story = _header([d["conference_name"], f"Hosted by {d['broker']}", f"{d['hotel']} · {d['city']}",
                     "December 2–3, 2026", f"Schedule for: {d['schedule_for']}"])
    for i, m in enumerate(d["meetings"]):
        if i == 4:
            story += [Paragraph(FOOTER, SMALL), PageBreak()]
        day = dt.date.fromisoformat(m["date"])
        story.append(Paragraph(f"<b>{m['company']} ({m['ticker']})</b>", STYLES["Heading4"]))
        for line in (f"Format: {B_TYPE[m['format']]}", f"Date: {day:%A, %B} {day.day}",
                     f"Time: {h12(m['start'], True)}-{h12(m['end'], True)}", f"Location: {m['room']}",
                     f"Company: {'; '.join(m['company_attendees'])}", f"Attendees: {', '.join(m['firm_attendees'])}"):
            story.append(Paragraph(line, COMPACT))
        story.append(Spacer(1, 6))
    story.append(Paragraph(FOOTER, SMALL))
    _doc(out / "broker_b_by_company.pdf").build(story)


def build_c(out: Path) -> None:
    d = BROKER_C
    story = _header([d["conference_name"], f"Hosted by {d['broker']}", f"{d['hotel']} · {d['city']}",
                     "17–18 November 2026", f"Itinerary for: {d['schedule_for']}"])
    for day in ["2026-11-17", "2026-11-18"]:
        story.append(Paragraph(uk_heading(day), STYLES["Heading2"]))
        rows = [["Time", "Meeting", "Company", "Location", "With"]]
        for m in (x for x in d["meetings"] if x["date"] == day):
            rows.append([m["start"], C_TYPE[m["format"]], Paragraph(f"{m['company']} ({m['ticker']})", SMALL),
                         m["room"], Paragraph("; ".join(m["company_attendees"]), SMALL)])
        story += [_table(rows, [50, 60, 150, 100, 172]), Spacer(1, 10)]
    story.append(Paragraph(FOOTER, SMALL))
    _doc(out / "broker_c_itinerary.pdf").build(story)


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main(out: Path = SAMPLES) -> None:
    out.mkdir(parents=True, exist_ok=True)
    build_a(out)
    build_b(out)
    build_c(out)
    for name, data in (("broker_a_grid", BROKER_A), ("broker_b_by_company", BROKER_B), ("broker_c_itinerary", BROKER_C)):
        _write_json(out / f"{name}.expected.json", data)
    _write_json(out / "roster.sample.json", ROSTER)


if __name__ == "__main__":
    main()
```

Generate the samples: `cd backend && uv run python scripts/make_sample_pdfs.py && ls ../samples`
Expected: 3 PDFs, 3 `.expected.json`, `roster.sample.json`.

If `test_pdf_page_count_matches_expected_pages` fails for broker B (page 1 overflowing), reduce the header `Spacer` and `COMPACT` leading until page 1 holds the first four companies; do not change the expected pages.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass (Task 1's plus the three new files).

- [ ] **Step 7: Commit**

```bash
git add backend/mcs/extraction backend/scripts backend/tests samples
git commit -m "feat: extraction contract, synthetic broker sample PDFs and fake extractor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: Claude extractors (Claude Code CLI, Anthropic API, Foundry) and the factory

**Files:**
- Create: `backend/mcs/extraction/claude_code.py`, `backend/mcs/extraction/anthropic_api.py`
- Modify: `backend/mcs/extraction/__init__.py` (complete `get_extractor`)
- Test: `backend/tests/test_claude_code_extractor.py`, `backend/tests/test_anthropic_extractor.py`, `backend/tests/test_extractor_factory.py`

**Interfaces:**
- Consumes: `Settings` (`resolved_extractor()`, `resolved_model()`, `claude_bin`, `extract_timeout`, `anthropic_api_key()`, `foundry_api_key()`, `foundry_resource`, `samples_dir`) from Task 1; `ExtractionError`, `ExtractionResult`, `parse_extraction`, `EXTRACTION_JSON_SCHEMA`, `EXTRACTION_PROMPT`, `SYSTEM_PROMPT`, `FakeExtractor` from Task 2.
- Produces:
  - `mcs.extraction.claude_code.ClaudeCodeExtractor(claude_bin: str = "claude", model: str = "sonnet", timeout: int = 240, runner: Runner | None = None)`, `name = "claude-code"`; `Runner = Callable[[list[str], Path, dict[str, str], int], subprocess.CompletedProcess]`; `clean_env(env: Mapping[str, str]) -> dict[str, str]`; `default_runner`
  - `mcs.extraction.anthropic_api.AnthropicExtractor(client, model: str, name: str = "anthropic", max_tokens: int = 16000)`; `make_anthropic_client(settings) -> anthropic.Anthropic`; `make_foundry_client(settings) -> anthropic.AnthropicFoundry`; `TOOL_NAME = "record_meetings"`
  - `mcs.extraction.get_extractor(settings)` returns one of the four providers per `settings.resolved_extractor()`; raises `ValueError` for an unknown name and `ExtractionError` when the chosen provider lacks credentials.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_claude_code_extractor.py`:

```python
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from mcs.extraction.claude_code import ClaudeCodeExtractor, clean_env
from mcs.extraction.schema import EXTRACTION_JSON_SCHEMA, ExtractionError

GOOD = {"type": "result", "is_error": False, "structured_output": {
    "hotel": "The Example Grand Hotel", "timezone": "America/New_York",
    "meetings": [{"company": "Northwind Robotics", "date": "2026-11-10", "start": "08:00"}, {"room": "no company"}]}}


def _pdf(tmp_path) -> Path:
    p = tmp_path / "in.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    return p


class FakeRunner:
    def __init__(self, stdout="", returncode=0, stderr="", exc=None):
        self.stdout, self.returncode, self.stderr, self.exc = stdout, returncode, stderr, exc
        self.calls = []

    def __call__(self, argv, cwd, env, timeout):
        self.calls.append({"argv": argv, "cwd": cwd, "env": env, "timeout": timeout,
                           "pdf_exists": (cwd / "schedule.pdf").exists()})
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def test_parses_structured_output_and_counts_skipped(tmp_path):
    runner = FakeRunner(stdout=json.dumps(GOOD))
    result = ClaudeCodeExtractor(runner=runner).extract(_pdf(tmp_path))
    assert [m.company for m in result.meetings] == ["Northwind Robotics"]
    assert result.skipped_items == 1
    assert result.timezone == "America/New_York"


def test_command_shape(tmp_path):
    runner = FakeRunner(stdout=json.dumps(GOOD))
    ClaudeCodeExtractor(claude_bin="/opt/claude", model="opus", timeout=99, runner=runner).extract(_pdf(tmp_path))
    call = runner.calls[0]
    argv = call["argv"]
    assert argv[0] == "/opt/claude"
    assert argv[1] == "-p"
    prompt = argv[2]
    assert str(call["cwd"] / "schedule.pdf") in prompt
    def flag(name):
        return argv[argv.index(name) + 1]
    assert flag("--tools") == "Read"
    assert flag("--allowedTools") == "Read"
    assert flag("--output-format") == "json"
    assert json.loads(flag("--json-schema")) == EXTRACTION_JSON_SCHEMA
    assert flag("--model") == "opus"
    assert "--no-session-persistence" in argv
    assert "--system-prompt" in argv
    assert call["timeout"] == 99
    assert call["pdf_exists"] is True


def test_temp_dir_is_removed_after_extract(tmp_path):
    runner = FakeRunner(stdout=json.dumps(GOOD))
    ClaudeCodeExtractor(runner=runner).extract(_pdf(tmp_path))
    assert not runner.calls[0]["cwd"].exists()


def test_clean_env_strips_claude_session_vars():
    env = {"PATH": "/bin", "HOME": "/h", "CLAUDECODE": "1", "CLAUDE_PID": "9", "CLAUDE_CODE_ENTRYPOINT": "cli",
           "CLAUDE_CODE_SESSION_ID": "x", "ANTHROPIC_API_KEY": "keep-me-for-cli"}
    assert clean_env(env) == {"PATH": "/bin", "HOME": "/h", "ANTHROPIC_API_KEY": "keep-me-for-cli"}


@pytest.mark.parametrize("runner,match", [
    (FakeRunner(exc=FileNotFoundError()), "claude` command was not found"),
    (FakeRunner(exc=subprocess.TimeoutExpired(cmd="claude", timeout=5)), "longer than"),
    (FakeRunner(stdout="not json"), "unreadable"),
    (FakeRunner(stdout="", returncode=1, stderr="Invalid API key"), "Invalid API key"),
    (FakeRunner(stdout=json.dumps({"is_error": True, "result": "Credit balance too low"})), "Credit balance too low"),
    (FakeRunner(stdout=json.dumps({"is_error": False, "result": "done"})), "structured"),
])
def test_failures_become_extraction_errors(tmp_path, runner, match):
    with pytest.raises(ExtractionError, match=match):
        ClaudeCodeExtractor(runner=runner).extract(_pdf(tmp_path))


def test_default_runner_wiring_with_fake_cli(tmp_path, monkeypatch):
    """Real subprocess path: a fake `claude` script echoes a result and records its env."""
    env_dump = tmp_path / "env.txt"
    script = tmp_path / "fake-claude"
    script.write_text(
        "#!/bin/sh\n"
        f"env > {env_dump}\n"
        f"echo '{json.dumps(GOOD)}'\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    result = ClaudeCodeExtractor(claude_bin=str(script)).extract(_pdf(tmp_path))
    assert result.meetings[0].company == "Northwind Robotics"
    dumped = env_dump.read_text()
    assert "CLAUDECODE=" not in dumped
    assert "CLAUDE_CODE_SESSION_ID=" not in dumped
```

`backend/tests/test_anthropic_extractor.py`:

```python
import base64
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from mcs.extraction.anthropic_api import TOOL_NAME, AnthropicExtractor
from mcs.extraction.schema import EXTRACTION_JSON_SCHEMA, EXTRACTION_PROMPT, SYSTEM_PROMPT, ExtractionError


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


def _tool_response(payload):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok"),
                                    SimpleNamespace(type="tool_use", name=TOOL_NAME, input=payload)])


def test_anthropic_sdk_has_foundry_client():
    assert hasattr(anthropic, "AnthropicFoundry")


def test_request_shape_and_parse(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4 hello")
    client = _client(_tool_response({"city": "London", "meetings": [{"company": "Corvid Diagnostics"}]}))
    result = AnthropicExtractor(client, model="claude-sonnet-5-5").extract(pdf)
    assert result.city == "London"
    assert result.meetings[0].company == "Corvid Diagnostics"
    kw = client.messages.kwargs
    assert kw["model"] == "claude-sonnet-5-5"
    assert kw["system"] == SYSTEM_PROMPT
    assert kw["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert kw["tools"][0]["name"] == TOOL_NAME
    assert kw["tools"][0]["input_schema"] == EXTRACTION_JSON_SCHEMA
    doc, text = kw["messages"][0]["content"]
    assert doc["type"] == "document"
    assert doc["source"] == {"type": "base64", "media_type": "application/pdf",
                             "data": base64.standard_b64encode(b"%PDF-1.4 hello").decode()}
    assert text == {"type": "text", "text": EXTRACTION_PROMPT}


def test_name_is_configurable():
    assert AnthropicExtractor(_client(), model="m", name="foundry").name == "foundry"


def test_missing_tool_use_raises(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    client = _client(SimpleNamespace(content=[SimpleNamespace(type="text", text="I can't")]))
    with pytest.raises(ExtractionError, match="did not return"):
        AnthropicExtractor(client, model="m").extract(pdf)


def test_api_error_becomes_extraction_error(tmp_path):
    pdf = tmp_path / "s.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    exc = anthropic.APIConnectionError(request=request)
    with pytest.raises(ExtractionError, match="Claude API error"):
        AnthropicExtractor(_client(exc=exc), model="m").extract(pdf)
```

`backend/tests/test_extractor_factory.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q tests/test_claude_code_extractor.py tests/test_anthropic_extractor.py tests/test_extractor_factory.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.extraction.claude_code'`.

- [ ] **Step 3: Implement `mcs/extraction/claude_code.py`**

```python
"""Extractor that runs the local Claude Code CLI headlessly (`claude -p`)."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Mapping

from mcs.extraction.schema import (
    EXTRACTION_JSON_SCHEMA, EXTRACTION_PROMPT, SYSTEM_PROMPT, ExtractionError, ExtractionResult, parse_extraction,
)

Runner = Callable[[list[str], Path, dict[str, str], int], subprocess.CompletedProcess]

_STRIP_EXACT = {"CLAUDECODE", "CLAUDE_PID"}


def clean_env(env: Mapping[str, str]) -> dict[str, str]:
    """Drop variables that make a nested `claude` think it runs inside another session."""
    return {k: v for k, v in env.items() if k not in _STRIP_EXACT and not k.startswith("CLAUDE_CODE_")}


def default_runner(argv: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout)


class ClaudeCodeExtractor:
    name = "claude-code"

    def __init__(self, claude_bin: str = "claude", model: str = "sonnet", timeout: int = 240,
                 runner: Runner | None = None):
        self.claude_bin = claude_bin
        self.model = model
        self.timeout = timeout
        self.runner = runner or default_runner

    def build_command(self, pdf_path: Path) -> list[str]:
        prompt = f"{EXTRACTION_PROMPT}\n\nThe PDF is at: {pdf_path}\nRead every page of it with the Read tool."
        return [
            self.claude_bin, "-p", prompt,
            "--system-prompt", SYSTEM_PROMPT,
            "--tools", "Read",
            "--allowedTools", "Read",
            "--output-format", "json",
            "--json-schema", json.dumps(EXTRACTION_JSON_SCHEMA),
            "--no-session-persistence",
            "--model", self.model,
        ]

    def extract(self, pdf_path: Path) -> ExtractionResult:
        with tempfile.TemporaryDirectory(prefix="mcs-extract-") as tmp:
            workdir = Path(tmp)
            target = workdir / "schedule.pdf"
            shutil.copyfile(pdf_path, target)
            argv = self.build_command(target)
            try:
                proc = self.runner(argv, workdir, clean_env(os.environ), self.timeout)
            except FileNotFoundError:
                raise ExtractionError(
                    "The `claude` command was not found. Install Claude Code or set MCS_CLAUDE_BIN."
                ) from None
            except subprocess.TimeoutExpired:
                raise ExtractionError(f"Claude Code took longer than {self.timeout}s to read the PDF.") from None
        return self._parse(proc)

    def _parse(self, proc: subprocess.CompletedProcess) -> ExtractionResult:
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            raise ExtractionError("Claude Code returned unreadable output.") from None
        if data is None:
            detail = (proc.stderr or "").strip()[-300:] or f"exit code {proc.returncode}"
            raise ExtractionError(f"Claude Code failed: {detail}")
        if data.get("is_error"):
            raise ExtractionError(f"Claude Code failed: {str(data.get('result', 'unknown error'))[:300]}")
        structured = data.get("structured_output")
        if structured is None:
            raise ExtractionError("Claude Code did not return structured meetings.")
        return parse_extraction(structured)
```

Note: the `returncode=1` + empty stdout case hits the `data is None` branch and surfaces stderr ("Invalid API key"), which the test expects.

- [ ] **Step 4: Implement `mcs/extraction/anthropic_api.py`**

```python
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
```

If `anthropic.AnthropicFoundry` does not accept `timeout`, drop that keyword for the Foundry client only and note it in the report.

- [ ] **Step 5: Complete the factory in `mcs/extraction/__init__.py`**

Replace `get_extractor` with:

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/mcs/extraction backend/tests
git commit -m "feat: Claude Code, Anthropic API and Foundry extractors behind one factory

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Roster name matching

**Files:**
- Create: `backend/mcs/roster.py`
- Test: `backend/tests/test_roster.py`

**Interfaces:**
- Consumes: `mcs.models.Analyst` (Task 1) only inside `roster_entries`.
- Produces: `RosterEntry(id: int, name: str, aliases: tuple[str, ...] = (), active: bool = True)` (frozen dataclass); `MatchResult(analyst_id: int | None, kind: str | None)` (frozen dataclass; kinds `"exact" | "alias" | "initial" | "fuzzy"`); `NO_MATCH`; `normalize_name(s: str) -> str`; `match_name(raw: str | None, roster: Sequence[RosterEntry]) -> MatchResult`; `roster_entries(analysts: Iterable[Analyst]) -> list[RosterEntry]`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_roster.py`:

```python
import pytest

from mcs.models import Analyst
from mcs.roster import MatchResult, RosterEntry, match_name, normalize_name, roster_entries

ROSTER = [
    RosterEntry(1, "Avery Kim"),
    RosterEntry(2, "Sam Patel", ("Samir Patel",)),
    RosterEntry(3, "Jordan Lee"),
    RosterEntry(4, "Riley Chen"),
    RosterEntry(5, "Morgan Diaz"),
    RosterEntry(6, "Taylor Brooks", ("Tay Brooks",)),
]


@pytest.mark.parametrize("raw,expected", [
    ("Avery Kim", (1, "exact")),
    ("  avery   KIM ", (1, "exact")),
    ("Samir Patel", (2, "alias")),
    ("Tay Brooks", (6, "alias")),
    ("A. Kim", (1, "initial")),
    ("A Kim", (1, "initial")),
    ("Morgan D.", (5, "initial")),
    ("Morgan D", (5, "initial")),
    ("Rilay Chen", (4, "fuzzy")),
    ("Chris Wong", (None, None)),
    ("", (None, None)),
    ("   ", (None, None)),
    (None, (None, None)),
])
def test_match_kinds(raw, expected):
    assert match_name(raw, ROSTER) == MatchResult(*expected)


def test_ambiguous_initial_is_no_match():
    roster = ROSTER + [RosterEntry(7, "Alex Kim")]
    assert match_name("A. Kim", roster) == MatchResult(None, None)


def test_ambiguous_exact_is_no_match():
    roster = [RosterEntry(1, "Jordan Lee"), RosterEntry(2, "Jordan Lee")]
    assert match_name("Jordan Lee", roster) == MatchResult(None, None)


def test_fuzzy_tie_is_no_match():
    roster = [RosterEntry(1, "Jon Lee"), RosterEntry(2, "Jan Lee")]
    assert match_name("Jen Lee", roster) == MatchResult(None, None)


def test_inactive_never_matched():
    roster = [RosterEntry(1, "Avery Kim", active=False)]
    assert match_name("Avery Kim", roster) == MatchResult(None, None)
    assert match_name("A. Kim", roster) == MatchResult(None, None)


def test_accents_and_apostrophes():
    assert normalize_name("José Núñez") == "josé núñez"
    assert normalize_name("Liam O'Neil") == "liam o neil"
    roster = [RosterEntry(1, "José Núñez"), RosterEntry(2, "Liam O'Neil")]
    assert match_name("JOSÉ NÚÑEZ", roster) == MatchResult(1, "exact")
    assert match_name("Liam O’Neil", roster) == MatchResult(2, "exact")
    assert match_name("J. Núñez", roster) == MatchResult(1, "initial")


def test_roster_entries_from_models():
    a = Analyst(id=3, name="Jordan Lee", email="jordan.lee@example.com", aliases=["J. Lee"], active=True)
    assert roster_entries([a]) == [RosterEntry(3, "Jordan Lee", ("J. Lee",), True)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_roster.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.roster'`.

- [ ] **Step 3: Implement `backend/mcs/roster.py`**

```python
"""Match names as printed in broker PDFs to roster colleagues."""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Sequence

FUZZY_THRESHOLD = 0.85
FUZZY_MARGIN = 0.05


@dataclass(frozen=True)
class RosterEntry:
    id: int
    name: str
    aliases: tuple[str, ...] = ()
    active: bool = True


@dataclass(frozen=True)
class MatchResult:
    analyst_id: int | None
    kind: str | None


NO_MATCH = MatchResult(None, None)


def normalize_name(s: str) -> str:
    """Casefold, turn punctuation into spaces, collapse whitespace. Accented letters are kept."""
    s = re.sub(r"[^\w\s]", " ", s.casefold()).replace("_", " ")
    return " ".join(s.split())


def roster_entries(analysts: Iterable) -> list[RosterEntry]:
    return [RosterEntry(a.id, a.name, tuple(a.aliases or ()), a.active) for a in analysts]


def _single(ids: set[int], kind: str) -> MatchResult:
    return MatchResult(next(iter(ids)), kind) if len(ids) == 1 else NO_MATCH


def match_name(raw: str | None, roster: Sequence[RosterEntry]) -> MatchResult:
    target = normalize_name(raw or "")
    if not target:
        return NO_MATCH
    active = [r for r in roster if r.active]

    ids = {r.id for r in active if normalize_name(r.name) == target}
    if ids:
        return _single(ids, "exact")

    ids = {r.id for r in active if any(normalize_name(a) == target for a in r.aliases)}
    if ids:
        return _single(ids, "alias")

    tokens = target.split()
    if len(tokens) == 2:
        first, last = tokens
        ids = set()
        for r in active:
            parts = normalize_name(r.name).split()
            if len(parts) < 2:
                continue
            r_first, r_last = parts[0], parts[-1]
            if len(first) == 1 and r_last == last and r_first.startswith(first):
                ids.add(r.id)
            elif len(last) == 1 and r_first == first and r_last.startswith(last):
                ids.add(r.id)
        if ids:
            return _single(ids, "initial")

    scores = sorted(
        ((max(SequenceMatcher(None, target, normalize_name(n)).ratio() for n in (r.name, *r.aliases)), r.id)
         for r in active),
        reverse=True,
    )
    if scores and scores[0][0] >= FUZZY_THRESHOLD:
        if len(scores) == 1 or scores[1][0] < scores[0][0] - FUZZY_MARGIN:
            return MatchResult(scores[0][1], "fuzzy")
    return NO_MATCH
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/mcs/roster.py backend/tests/test_roster.py
git commit -m "feat: roster name matching (exact, alias, initials, fuzzy)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: Normalization — extraction to draft meetings, and review flags

**Files:**
- Create: `backend/mcs/normalize.py`
- Test: `backend/tests/test_normalize.py`, `backend/tests/test_flags.py`

**Interfaces:**
- Consumes: `ExtractionResult` (Task 2); `RosterEntry`, `match_name`, `normalize_name`, `NO_MATCH` (Task 4).
- Produces:
  - `parse_time(value: str | None) -> dt.time | None`; `parse_date(value: str | None) -> dt.date | None`; `valid_timezone(tz: str | None) -> str | None`; `add_minutes(t: dt.time, minutes: int) -> dt.time`
  - `DraftMeeting` dataclass: `date, start_time, end_time, end_assumed, room: str, company: str, ticker: str | None, format: str, company_attendees: list[str], raw_attendee_names: list[str], notes: str, source_page: int | None, attendees: list[tuple[int, str]]` (analyst id, match kind)
  - `build_meetings(result: ExtractionResult, roster: Sequence[RosterEntry], default_attendee_ids: Sequence[int] = (), default_minutes: int = 45) -> list[DraftMeeting]`
  - `Flag(code: str, severity: str, message: str)` (frozen); `MeetingView(id, date, start_time, end_time, end_assumed, company, status, attendees: tuple[tuple[int, str], ...] = (), raw_attendee_names: tuple[str, ...] = (), ignored_names: tuple[str, ...] = ())` (frozen); `BLOCK_CODES: frozenset[str]`; `compute_flags(timezone: str | None, meetings: Sequence[MeetingView], roster: Sequence[RosterEntry]) -> dict[int, list[Flag]]`; `has_block(flags: Sequence[Flag]) -> bool`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_normalize.py`:

```python
import datetime as dt
import json

import pytest

from mcs.config import REPO_ROOT
from mcs.extraction.schema import ExtractedMeeting, ExtractionResult, parse_extraction
from mcs.normalize import add_minutes, build_meetings, parse_date, parse_time, valid_timezone
from mcs.roster import RosterEntry

ROSTER = [RosterEntry(1, "Avery Kim"), RosterEntry(2, "Sam Patel", ("Samir Patel",)), RosterEntry(3, "Jordan Lee"),
          RosterEntry(4, "Riley Chen"), RosterEntry(5, "Morgan Diaz"), RosterEntry(6, "Taylor Brooks", ("Tay Brooks",)),
          RosterEntry(7, "Former Analyst", active=False)]


def sample(name):
    return parse_extraction(json.loads((REPO_ROOT / "samples" / f"{name}.expected.json").read_text()))


@pytest.mark.parametrize("raw,expected", [
    ("08:00", dt.time(8, 0)), ("8:00", dt.time(8, 0)), ("08:00:00", dt.time(8, 0)), ("23:59", dt.time(23, 59)),
    ("8:00 AM", dt.time(8, 0)), ("8am", dt.time(8, 0)), ("8:00am", dt.time(8, 0)), ("8:00 a.m.", dt.time(8, 0)),
    ("1:30 PM", dt.time(13, 30)), ("12:00pm", dt.time(12, 0)), ("12pm", dt.time(12, 0)), ("12:00am", dt.time(0, 0)),
    ("12:30 AM", dt.time(0, 30)), ("TBD", None), ("", None), (None, None), ("25:00", None), ("13:00 PM", None),
    ("noon", None),
])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-11-10", dt.date(2026, 11, 10)), ("2026-11-10T00:00:00", dt.date(2026, 11, 10)),
    (" 2026-11-10 ", dt.date(2026, 11, 10)), ("Nov 10", None), ("", None), (None, None), ("2026-13-01", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_valid_timezone():
    assert valid_timezone("America/New_York") == "America/New_York"
    assert valid_timezone("Eastern") is None
    assert valid_timezone("") is None
    assert valid_timezone(None) is None
    assert valid_timezone("../etc/passwd") is None


def test_add_minutes():
    assert add_minutes(dt.time(8, 0), 45) == dt.time(8, 45)
    assert add_minutes(dt.time(23, 30), 45) == dt.time(0, 15)


def test_sample_a():
    drafts = build_meetings(sample("broker_a_grid"), ROSTER)
    assert len(drafts) == 12
    first = drafts[0]
    assert (first.date, first.start_time, first.end_time, first.end_assumed) == (
        dt.date(2026, 11, 10), dt.time(8, 0), dt.time(8, 45), False)
    assert first.attendees == [(1, "exact"), (3, "exact")]
    assert first.company_attendees == ["Dana Shore, CFO"]
    assert first.source_page == 1
    tidewater = next(d for d in drafts if d.company == "Tidewater Pumps")
    assert tidewater.attendees == []
    assert tidewater.raw_attendee_names == ["Chris Wong"]
    assert next(d for d in drafts if d.company == "Keystone Valve Corp").format == "meal"


def test_sample_b_match_kinds():
    drafts = {d.company: d for d in build_meetings(sample("broker_b_by_company"), ROSTER)}
    assert drafts["Vantage Cloud Software"].attendees == [(1, "initial")]
    assert drafts["Pixelmint Studios"].attendees == [(1, "initial"), (4, "fuzzy")]
    assert drafts["Brightpath Payments"].attendees == [(5, "initial"), (6, "alias")]
    assert drafts["Nimbus Health Tech"].attendees == [(2, "alias")]


def test_sample_c_uses_schedule_for_and_assumes_end():
    drafts = build_meetings(sample("broker_c_itinerary"), ROSTER, default_minutes=30)
    assert len(drafts) == 6
    assert all(d.attendees == [(2, "exact")] for d in drafts)
    assert all(d.end_assumed for d in drafts)
    assert drafts[1].start_time == dt.time(9, 30) and drafts[1].end_time == dt.time(10, 0)
    assert all(d.raw_attendee_names == [] for d in drafts)


def _one(**kw):
    return ExtractionResult(meetings=[ExtractedMeeting(company="Cobalt Freight Lines", **kw)])


def test_default_attendees_added_once_and_inactive_ignored():
    drafts = build_meetings(_one(firm_attendees=["Avery Kim"]), ROSTER, default_attendee_ids=[3, 1, 7])
    assert drafts[0].attendees == [(1, "exact"), (3, "default")]


def test_two_raw_names_for_same_colleague_give_one_attendee():
    drafts = build_meetings(_one(firm_attendees=["Avery Kim", "A. Kim"]), ROSTER)
    assert drafts[0].attendees == [(1, "exact")]
    assert drafts[0].raw_attendee_names == ["Avery Kim", "A. Kim"]


def test_blank_fields_are_cleaned():
    d = build_meetings(_one(room="  ", ticker=" ", notes=None, start="TBD"), ROSTER)[0]
    assert (d.room, d.ticker, d.notes) == ("", None, "")
    assert (d.start_time, d.end_time, d.end_assumed) == (None, None, False)
```

`backend/tests/test_flags.py`:

```python
import datetime as dt

from mcs.normalize import BLOCK_CODES, Flag, MeetingView, compute_flags, has_block
from mcs.roster import RosterEntry

ROSTER = [RosterEntry(1, "Avery Kim"), RosterEntry(4, "Riley Chen")]
TZ = "America/New_York"
D = dt.date(2026, 12, 2)


def mv(id, start=(9, 0), end=(9, 45), date=D, company="Co", status="draft", attendees=((1, "exact"),), **kw):
    return MeetingView(id=id, date=date, start_time=dt.time(*start) if start else None,
                       end_time=dt.time(*end) if end else None, end_assumed=kw.pop("end_assumed", False),
                       company=company, status=status, attendees=tuple(attendees), **kw)


def codes(flags):
    return sorted(f.code for f in flags)


def test_clean_meeting_has_no_flags():
    assert compute_flags(TZ, [mv(1)], ROSTER) == {1: []}


def test_block_flags():
    out = compute_flags(None, [mv(1, date=None), mv(2, start=None), mv(3, start=(10, 0), end=(10, 0)), mv(4, attendees=())], ROSTER)
    assert codes(out[1]) == ["missing_date", "no_timezone"]
    assert codes(out[2]) == ["missing_time", "no_timezone"]
    assert codes(out[3]) == ["end_before_start", "no_timezone"]
    assert codes(out[4]) == ["no_attendee", "no_timezone"]
    assert all(f.severity == "block" for fl in out.values() for f in fl)


def test_assumed_end_and_fuzzy_are_warnings():
    out = compute_flags(TZ, [mv(1, end_assumed=True, attendees=((4, "fuzzy"),))], ROSTER)
    assert codes(out[1]) == ["assumed_end", "fuzzy_match"]
    assert not has_block(out[1])
    assert "Riley Chen" in next(f.message for f in out[1] if f.code == "fuzzy_match")


def test_unmatched_name_rules():
    out = compute_flags(TZ, [
        mv(1, raw_attendee_names=("Chris Wong",), attendees=((1, "default"),)),
        mv(2, start=(11, 0), end=(11, 30), raw_attendee_names=("Chris Wong",), ignored_names=("chris  WONG",)),
        mv(3, start=(12, 0), end=(12, 30), raw_attendee_names=("A. Kim",)),
        mv(4, start=(13, 0), end=(13, 30), raw_attendee_names=("A. Kim",), attendees=((4, "manual"),)),
    ], ROSTER)
    assert codes(out[1]) == ["unmatched_name"]
    assert "Chris Wong" in out[1][0].message
    assert out[2] == [] and out[3] == []
    assert codes(out[4]) == ["unmatched_name"]


def test_double_booking_flags_both_meetings():
    pix = mv(1, start=(9, 30), end=(10, 30), company="Pixelmint Studios", attendees=((1, "initial"), (4, "fuzzy")))
    orb = mv(2, start=(9, 45), end=(10, 30), company="Orbital Data Networks", attendees=((4, "fuzzy"),))
    out = compute_flags(TZ, [pix, orb], ROSTER)
    assert "double_booked" in codes(out[1]) and "double_booked" in codes(out[2])
    msg = next(f.message for f in out[1] if f.code == "double_booked")
    assert "Riley Chen" in msg and "Orbital Data Networks" in msg


def test_adjacent_and_other_day_meetings_do_not_clash():
    out = compute_flags(TZ, [mv(1, start=(9, 0), end=(9, 45)), mv(2, start=(9, 45), end=(10, 30)),
                             mv(3, date=dt.date(2026, 12, 3))], ROSTER)
    assert out == {1: [], 2: [], 3: []}


def test_duplicate_rows_warn_without_double_booking():
    out = compute_flags(TZ, [mv(1, company="Kestrel Security"), mv(2, company="kestrel security ")], ROSTER)
    assert codes(out[1]) == ["duplicate"] and codes(out[2]) == ["duplicate"]


def test_cancelled_meetings_are_ignored():
    out = compute_flags(None, [mv(1, status="cancelled"), mv(2, start=(9, 0), end=(9, 45))], ROSTER)
    assert out[1] == []
    assert codes(out[2]) == ["no_timezone"]


def test_block_codes_and_has_block():
    assert BLOCK_CODES == {"no_timezone", "missing_date", "missing_time", "end_before_start", "no_attendee"}
    assert has_block([Flag("assumed_end", "warn", "x"), Flag("no_attendee", "block", "y")])
    assert not has_block([Flag("assumed_end", "warn", "x")])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q tests/test_normalize.py tests/test_flags.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.normalize'`.

- [ ] **Step 3: Implement `backend/mcs/normalize.py`**

```python
"""Turn an extraction into draft meetings, and compute review flags."""
import datetime as dt
import re
from dataclasses import dataclass
from typing import Sequence
from zoneinfo import ZoneInfo

from mcs.extraction.schema import ExtractionResult
from mcs.roster import NO_MATCH, RosterEntry, match_name, normalize_name

_H24 = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*$")
_H12 = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m?\.?\s*$", re.IGNORECASE)


def parse_time(value: str | None) -> dt.time | None:
    if not value:
        return None
    m = _H24.match(value)
    if m:
        hour, minute = int(m[1]), int(m[2])
        return dt.time(hour, minute) if hour < 24 and minute < 60 else None
    m = _H12.match(value)
    if m:
        hour, minute = int(m[1]), int(m[2] or 0)
        if not (1 <= hour <= 12 and minute < 60):
            return None
        return dt.time(hour % 12 + (12 if m[3].lower() == "p" else 0), minute)
    return None


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def valid_timezone(tz: str | None) -> str | None:
    if not tz:
        return None
    try:
        ZoneInfo(tz)
    except (ValueError, KeyError, OSError):  # ZoneInfoNotFoundError subclasses KeyError
        return None
    return tz


def add_minutes(t: dt.time, minutes: int) -> dt.time:
    return (dt.datetime.combine(dt.date(2000, 1, 1), t) + dt.timedelta(minutes=minutes)).time()


@dataclass
class DraftMeeting:
    date: dt.date | None
    start_time: dt.time | None
    end_time: dt.time | None
    end_assumed: bool
    room: str
    company: str
    ticker: str | None
    format: str
    company_attendees: list[str]
    raw_attendee_names: list[str]
    notes: str
    source_page: int | None
    attendees: list[tuple[int, str]]


def build_meetings(result: ExtractionResult, roster: Sequence[RosterEntry],
                   default_attendee_ids: Sequence[int] = (), default_minutes: int = 45) -> list[DraftMeeting]:
    active_ids = {r.id for r in roster if r.active}
    addressee = match_name(result.schedule_for, roster) if result.schedule_for else NO_MATCH
    drafts: list[DraftMeeting] = []
    for em in result.meetings:
        start, end = parse_time(em.start), parse_time(em.end)
        end_assumed = False
        if start is not None and end is None:
            end, end_assumed = add_minutes(start, default_minutes), True
        attendees: dict[int, str] = {}
        for raw in em.firm_attendees:
            match = match_name(raw, roster)
            if match.analyst_id is not None and match.analyst_id not in attendees:
                attendees[match.analyst_id] = match.kind
        if not em.firm_attendees and addressee.analyst_id is not None:
            attendees[addressee.analyst_id] = addressee.kind
        for analyst_id in default_attendee_ids:
            if analyst_id in active_ids and analyst_id not in attendees:
                attendees[analyst_id] = "default"
        drafts.append(DraftMeeting(
            date=parse_date(em.date), start_time=start, end_time=end, end_assumed=end_assumed,
            room=(em.room or "").strip(), company=em.company, ticker=(em.ticker or "").strip() or None,
            format=em.format, company_attendees=list(em.company_attendees),
            raw_attendee_names=list(em.firm_attendees), notes=(em.notes or "").strip(),
            source_page=em.page, attendees=list(attendees.items()),
        ))
    return drafts


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str  # "block" | "warn"
    message: str


@dataclass(frozen=True)
class MeetingView:
    id: int
    date: dt.date | None
    start_time: dt.time | None
    end_time: dt.time | None
    end_assumed: bool
    company: str
    status: str
    attendees: tuple[tuple[int, str], ...] = ()
    raw_attendee_names: tuple[str, ...] = ()
    ignored_names: tuple[str, ...] = ()


BLOCK_CODES = frozenset({"no_timezone", "missing_date", "missing_time", "end_before_start", "no_attendee"})


def has_block(flags: Sequence[Flag]) -> bool:
    return any(f.severity == "block" for f in flags)


def _times_ok(m: MeetingView) -> bool:
    return m.start_time is not None and m.end_time is not None and m.end_time > m.start_time


def compute_flags(timezone: str | None, meetings: Sequence[MeetingView],
                  roster: Sequence[RosterEntry]) -> dict[int, list[Flag]]:
    names = {r.id: r.name for r in roster}
    out: dict[int, list[Flag]] = {m.id: [] for m in meetings}
    live = [m for m in meetings if m.status != "cancelled"]

    for m in live:
        flags = out[m.id]
        if not timezone:
            flags.append(Flag("no_timezone", "block", "Set the conference timezone."))
        if m.date is None:
            flags.append(Flag("missing_date", "block", "The date is missing."))
        if m.start_time is None or m.end_time is None:
            flags.append(Flag("missing_time", "block", "The start or end time is missing."))
        elif m.end_time <= m.start_time:
            flags.append(Flag("end_before_start", "block", "The meeting ends before it starts."))
        if not m.attendees:
            flags.append(Flag("no_attendee", "block", "No colleague is assigned."))
        if m.end_assumed:
            flags.append(Flag("assumed_end", "warn", "The end time wasn't printed, so it was assumed."))
        attendee_ids = {aid for aid, _ in m.attendees}
        ignored = {normalize_name(n) for n in m.ignored_names}
        for raw in m.raw_attendee_names:
            if normalize_name(raw) in ignored:
                continue
            match = match_name(raw, roster)
            if match.analyst_id is None or match.analyst_id not in attendee_ids:
                flags.append(Flag("unmatched_name", "warn", f"“{raw}” isn't matched to a colleague."))
        for aid, kind in m.attendees:
            if kind == "fuzzy":
                flags.append(Flag("fuzzy_match", "warn",
                                  f"Matched to {names.get(aid, 'a colleague')} by similar spelling. Check it."))

    for i, a in enumerate(live):
        for b in live[i + 1:]:
            if a.date is None or a.date != b.date:
                continue
            if (a.start_time is not None and a.start_time == b.start_time
                    and a.company.casefold().strip() == b.company.casefold().strip()):
                out[a.id].append(Flag("duplicate", "warn", "Same company, date and time as another row."))
                out[b.id].append(Flag("duplicate", "warn", "Same company, date and time as another row."))
                continue
            if not (_times_ok(a) and _times_ok(b)):
                continue
            if a.start_time < b.end_time and b.start_time < a.end_time:
                shared = sorted({x for x, _ in a.attendees} & {x for x, _ in b.attendees})
                for aid in shared:
                    who = names.get(aid, "A colleague")
                    out[a.id].append(Flag("double_booked", "warn",
                                          f"{who} is also in {b.company} at {b.start_time:%H:%M}."))
                    out[b.id].append(Flag("double_booked", "warn",
                                          f"{who} is also in {a.company} at {a.start_time:%H:%M}."))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/mcs/normalize.py backend/tests/test_normalize.py backend/tests/test_flags.py
git commit -m "feat: build draft meetings from extractions and compute review flags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Calendar event content, sync planner, and the ICS sink

**Files:**
- Create: `backend/mcs/calendar/__init__.py`, `backend/mcs/calendar/content.py`, `backend/mcs/calendar/planner.py`, `backend/mcs/calendar/ics.py`
- Test: `backend/tests/test_calendar_content.py`, `backend/tests/test_planner.py`, `backend/tests/test_ics.py`

**Interfaces:**
- Consumes: `Conference`, `Meeting`, `Analyst`, `SyncRecord`, `utcnow` (Task 1).
- Produces:
  - `mcs.calendar.content`: `FORMAT_LABELS`; `EventContent(subject: str, location: str, body: str, start_utc: datetime, end_utc: datetime)` (frozen) with `content_hash() -> str`, `to_json() -> str`, `EventContent.from_json(s: str) -> EventContent`; `build_event(conference: Conference, meeting: Meeting, other_attendee_names: Sequence[str]) -> EventContent` (raises `ValueError` when timezone/date/start/end is missing)
  - `mcs.calendar.planner`: `SyncAction(kind: str, meeting_id: int, analyst_id: int, analyst_email: str, analyst_name: str, content: EventContent | None, sequence: int, external_id: str | None)` (frozen); `SyncOutcome(action: SyncAction, ok: bool, external_id: str | None = None, error: str | None = None)` (frozen); `plan_sync(conference: Conference, meetings: Sequence[Meeting], attendees: Mapping[int, Sequence[int]], analysts: Mapping[int, Analyst], records: Sequence[SyncRecord]) -> list[SyncAction]`
  - `mcs.calendar.ics`: `ics_uid(meeting_id: int, analyst_id: int) -> str`; `IcsSink` (`name = "ics"`, `apply(conference, actions) -> list[SyncOutcome]`); `render_ics(records: Sequence[SyncRecord], now: datetime | None = None) -> bytes`; `analyst_slug(name: str) -> str`; `zip_files(files: Mapping[str, bytes]) -> bytes`
  - `mcs.calendar.CalendarSink` Protocol (`name: str`; `apply(conference, actions) -> list[SyncOutcome]`). Task 7 adds `get_sink`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_calendar_content.py`:

```python
import datetime as dt

import pytest

from mcs.calendar.content import EventContent, build_event
from mcs.models import Conference, Meeting

UTC = dt.timezone.utc


def conf(**kw):
    base = dict(id=1, name="Industrials Conference 2026", hotel="The Example Grand Hotel",
                timezone="America/New_York", pdf_filename="broker_a_grid.pdf")
    return Conference(**{**base, **kw})


def meeting(**kw):
    base = dict(id=1, conference_id=1, date=dt.date(2026, 11, 10), start_time=dt.time(8, 0), end_time=dt.time(8, 45),
                room="Salon 4", company="Northwind Robotics", ticker="NWRB", format="one_on_one",
                company_attendees=["Dana Shore, CFO"], notes="", source_page=1)
    return Meeting(**{**base, **kw})


def test_subject_location_body():
    e = build_event(conf(), meeting(), ["Jordan Lee"])
    assert e.subject == "NWRB – Northwind Robotics (1x1)"
    assert e.location == "The Example Grand Hotel – Salon 4"
    assert e.body == ("Industrials Conference 2026\nCompany: Dana Shore, CFO\nAlso attending: Jordan Lee\n"
                      "Source: broker_a_grid.pdf, page 1")


@pytest.mark.parametrize("fmt,label", [("group", "Group"), ("meal", "Meal"), ("other", "Meeting")])
def test_labels_and_no_ticker(fmt, label):
    assert build_event(conf(), meeting(ticker=None, format=fmt), []).subject == f"Northwind Robotics ({label})"


def test_location_and_body_drop_empty_parts():
    e = build_event(conf(hotel="", pdf_filename=""), meeting(room="Suite 1201", company_attendees=[], notes="Bring model"), [])
    assert e.location == "Suite 1201"
    assert e.body == "Industrials Conference 2026\nBring model"
    assert build_event(conf(), meeting(room=""), []).location == "The Example Grand Hotel"
    assert build_event(conf(), meeting(source_page=None), []).body.endswith("Source: broker_a_grid.pdf")


@pytest.mark.parametrize("tz,date,time,expected", [
    ("America/New_York", dt.date(2026, 11, 10), dt.time(8, 0), dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC)),
    ("America/New_York", dt.date(2026, 7, 1), dt.time(8, 0), dt.datetime(2026, 7, 1, 12, 0, tzinfo=UTC)),
    ("Europe/London", dt.date(2026, 11, 17), dt.time(9, 30), dt.datetime(2026, 11, 17, 9, 30, tzinfo=UTC)),
    ("America/Los_Angeles", dt.date(2026, 12, 2), dt.time(8, 30), dt.datetime(2026, 12, 2, 16, 30, tzinfo=UTC)),
])
def test_utc_conversion(tz, date, time, expected):
    e = build_event(conf(timezone=tz), meeting(date=date, start_time=time, end_time=dt.time(23, 0)), [])
    assert e.start_utc == expected
    assert e.start_utc.tzinfo is not None


@pytest.mark.parametrize("bad", [dict(timezone=None)])
def test_missing_timezone_raises(bad):
    with pytest.raises(ValueError):
        build_event(conf(**bad), meeting(), [])


@pytest.mark.parametrize("field", ["date", "start_time", "end_time"])
def test_missing_meeting_time_raises(field):
    with pytest.raises(ValueError):
        build_event(conf(), meeting(**{field: None}), [])


def test_hash_and_json_roundtrip():
    a = build_event(conf(), meeting(), ["Jordan Lee"])
    b = build_event(conf(), meeting(), ["Jordan Lee"])
    assert a.content_hash() == b.content_hash()
    assert build_event(conf(), meeting(room="Salon 2"), ["Jordan Lee"]).content_hash() != a.content_hash()
    assert EventContent.from_json(a.to_json()) == a
```

`backend/tests/test_planner.py`:

```python
import datetime as dt

from mcs.calendar.content import build_event
from mcs.calendar.planner import plan_sync
from mcs.models import Analyst, Conference, Meeting, SyncRecord

CONF = Conference(id=1, name="Industrials Conference 2026", hotel="The Example Grand Hotel",
                  timezone="America/New_York", pdf_filename="a.pdf")
AVERY = Analyst(id=1, name="Avery Kim", email="avery.kim@example.com")
JORDAN = Analyst(id=3, name="Jordan Lee", email="jordan.lee@example.com")
ANALYSTS = {1: AVERY, 3: JORDAN}


def m(id=10, status="confirmed", room="Salon 4"):
    return Meeting(id=id, conference_id=1, date=dt.date(2026, 11, 10), start_time=dt.time(8, 0),
                   end_time=dt.time(8, 45), room=room, company="Northwind Robotics", ticker="NWRB", status=status)


def rec(meeting_id=10, analyst_id=1, state="active", external_id="ext-1", content=None, sequence=0):
    content = content or build_event(CONF, m(), ["Jordan Lee"])
    return SyncRecord(meeting_id=meeting_id, analyst_id=analyst_id, sink="ics", external_id=external_id,
                      content_hash=content.content_hash(), content_json=content.to_json(), sequence=sequence, state=state)


def kinds(actions):
    return [(a.kind, a.meeting_id, a.analyst_id, a.sequence, a.external_id) for a in actions]


def test_new_confirmed_meeting_creates_per_attendee():
    actions = plan_sync(CONF, [m()], {10: [1, 3]}, ANALYSTS, [])
    assert kinds(actions) == [("create", 10, 1, 0, None), ("create", 10, 3, 0, None)]
    assert actions[0].analyst_email == "avery.kim@example.com"
    assert "Also attending: Jordan Lee" in actions[0].content.body
    assert "Also attending: Avery Kim" in actions[1].content.body


def test_drafts_are_never_sent():
    assert plan_sync(CONF, [m(status="draft")], {10: [1]}, ANALYSTS, []) == []


def test_unchanged_active_record_is_skipped():
    assert plan_sync(CONF, [m()], {10: [1, 3]}, ANALYSTS,
                     [rec(), rec(analyst_id=3, content=build_event(CONF, m(), ["Avery Kim"]))]) == []


def test_changed_content_updates_with_next_sequence():
    actions = plan_sync(CONF, [m(room="Salon 2")], {10: [1]}, ANALYSTS, [rec(sequence=2)])
    assert kinds(actions) == [("update", 10, 1, 3, "ext-1")]
    assert "Salon 2" in actions[0].content.location


def test_failed_record_with_event_is_updated_even_if_unchanged():
    content = build_event(CONF, m(), [])
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS, [rec(state="failed", content=content)])
    assert kinds(actions) == [("update", 10, 1, 1, "ext-1")]


def test_failed_create_is_created_again():
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS, [rec(state="failed", external_id=None)])
    assert kinds(actions) == [("create", 10, 1, 0, None)]


def test_reconfirmed_after_cancel_recreates_with_same_id_and_higher_sequence():
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS, [rec(state="cancelled", sequence=4)])
    assert kinds(actions) == [("create", 10, 1, 5, "ext-1")]


def test_cancelled_meeting_cancels_active_records():
    actions = plan_sync(CONF, [m(status="cancelled")], {10: [1]}, ANALYSTS, [rec(sequence=1)])
    assert kinds(actions) == [("cancel", 10, 1, 2, "ext-1")]
    assert actions[0].content.subject.startswith("NWRB")


def test_removed_attendee_is_cancelled_only_for_them():
    content_j = build_event(CONF, m(), ["Avery Kim"])
    actions = plan_sync(CONF, [m()], {10: [1]}, ANALYSTS,
                        [rec(content=build_event(CONF, m(), [])), rec(analyst_id=3, external_id="ext-3", content=content_j)])
    assert kinds(actions) == [("cancel", 10, 3, 1, "ext-3")]


def test_draft_with_removed_attendee_leaves_record_alone():
    assert plan_sync(CONF, [m(status="draft")], {10: []}, ANALYSTS, [rec()]) == []


def test_already_cancelled_record_is_left_alone():
    assert plan_sync(CONF, [m(status="cancelled")], {10: [1]}, ANALYSTS, [rec(state="cancelled")]) == []
```

`backend/tests/test_ics.py`:

```python
import datetime as dt
import io
import zipfile

from icalendar import Calendar

from mcs.calendar.content import EventContent
from mcs.calendar.ics import IcsSink, analyst_slug, ics_uid, render_ics, zip_files
from mcs.calendar.planner import SyncAction
from mcs.models import Conference, SyncRecord

UTC = dt.timezone.utc


def content(subject="NWRB – Northwind Robotics (1x1)", location="The Example Grand Hotel – Salon 4", hour=13):
    return EventContent(subject, location, "Industrials Conference 2026\nSource: a.pdf, page 1",
                        dt.datetime(2026, 11, 10, hour, 0, tzinfo=UTC), dt.datetime(2026, 11, 10, hour, 45, tzinfo=UTC))


def test_uid_format():
    assert ics_uid(10, 3) == "mcs-10-3@meeting-calendar-sync"


def test_apply_assigns_uids_and_keeps_existing():
    actions = [SyncAction("create", 10, 1, "a@example.com", "A", content(), 0, None),
               SyncAction("update", 11, 1, "a@example.com", "A", content(), 1, "kept-uid")]
    outcomes = IcsSink().apply(Conference(id=1), actions)
    assert [(o.ok, o.external_id) for o in outcomes] == [(True, "mcs-10-1@meeting-calendar-sync"), (True, "kept-uid")]
    assert IcsSink.name == "ics"


def test_render_round_trip():
    records = [
        SyncRecord(meeting_id=11, analyst_id=1, sink="ics", external_id="uid-b", content_json=content(hour=15).to_json(),
                   sequence=2, state="cancelled"),
        SyncRecord(meeting_id=10, analyst_id=1, sink="ics", external_id="uid-a", content_json=content().to_json(),
                   sequence=0, state="active"),
        SyncRecord(meeting_id=12, analyst_id=1, sink="ics", external_id=None, content_json="", state="failed"),
    ]
    cal = Calendar.from_ical(render_ics(records, now=dt.datetime(2026, 10, 18, tzinfo=UTC)))
    assert str(cal["METHOD"]) == "PUBLISH"
    events = cal.walk("VEVENT")
    assert [str(e["UID"]) for e in events] == ["uid-a", "uid-b"]  # sorted by start
    first, second = events
    assert str(first["SUMMARY"]) == "NWRB – Northwind Robotics (1x1)"
    assert first["DTSTART"].dt == dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC)
    assert int(first["SEQUENCE"]) == 0 and str(first["STATUS"]) == "CONFIRMED"
    assert int(second["SEQUENCE"]) == 2 and str(second["STATUS"]) == "CANCELLED"
    assert "Source: a.pdf, page 1" in str(first["DESCRIPTION"])


def test_location_omitted_when_empty():
    rec = SyncRecord(meeting_id=1, analyst_id=1, sink="ics", external_id="u", content_json=content(location="").to_json())
    event = Calendar.from_ical(render_ics([rec])).walk("VEVENT")[0]
    assert "LOCATION" not in event


def test_slug_and_zip():
    assert analyst_slug("Avery Kim") == "avery-kim"
    assert analyst_slug("José Núñez") == "jose-nunez"
    assert analyst_slug("!!!") == "colleague"
    data = zip_files({"avery-kim.ics": b"A", "jordan-lee.ics": b"B"})
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sorted(z.namelist()) == ["avery-kim.ics", "jordan-lee.ics"]
        assert z.read("jordan-lee.ics") == b"B"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q tests/test_calendar_content.py tests/test_planner.py tests/test_ics.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.calendar'`.

- [ ] **Step 3: Implement `backend/mcs/calendar/content.py`**

```python
"""What a calendar event says: shared by every sink."""
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Sequence
from zoneinfo import ZoneInfo

from mcs.models import Conference, Meeting

FORMAT_LABELS = {"one_on_one": "1x1", "group": "Group", "meal": "Meal", "other": "Meeting"}


@dataclass(frozen=True)
class EventContent:
    subject: str
    location: str
    body: str
    start_utc: dt.datetime
    end_utc: dt.datetime

    def _as_dict(self) -> dict:
        return {"subject": self.subject, "location": self.location, "body": self.body,
                "start": self.start_utc.isoformat(), "end": self.end_utc.isoformat()}

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self._as_dict(), sort_keys=True).encode()).hexdigest()

    def to_json(self) -> str:
        return json.dumps(self._as_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "EventContent":
        d = json.loads(s)
        return cls(d["subject"], d["location"], d["body"],
                   dt.datetime.fromisoformat(d["start"]), dt.datetime.fromisoformat(d["end"]))


def build_event(conference: Conference, meeting: Meeting, other_attendee_names: Sequence[str]) -> EventContent:
    if not (conference.timezone and meeting.date and meeting.start_time and meeting.end_time):
        raise ValueError("The meeting needs a timezone, date, start and end before it can be sent.")
    tz = ZoneInfo(conference.timezone)
    start = dt.datetime.combine(meeting.date, meeting.start_time, tzinfo=tz).astimezone(dt.timezone.utc)
    end = dt.datetime.combine(meeting.date, meeting.end_time, tzinfo=tz).astimezone(dt.timezone.utc)
    label = FORMAT_LABELS.get(meeting.format, "Meeting")
    subject = f"{meeting.ticker} – {meeting.company} ({label})" if meeting.ticker else f"{meeting.company} ({label})"
    location = " – ".join(p for p in (conference.hotel, meeting.room) if p)
    lines = []
    if conference.name:
        lines.append(conference.name)
    if meeting.company_attendees:
        lines.append("Company: " + ", ".join(meeting.company_attendees))
    if other_attendee_names:
        lines.append("Also attending: " + ", ".join(other_attendee_names))
    if meeting.notes:
        lines.append(meeting.notes)
    if conference.pdf_filename:
        source = f"Source: {conference.pdf_filename}"
        lines.append(f"{source}, page {meeting.source_page}" if meeting.source_page else source)
    return EventContent(subject, location, "\n".join(lines), start, end)
```

- [ ] **Step 4: Implement `backend/mcs/calendar/planner.py`**

```python
"""Decide which calendar writes a send needs. Pure: no I/O."""
from dataclasses import dataclass
from typing import Mapping, Sequence

from mcs.calendar.content import EventContent, build_event
from mcs.models import Analyst, Conference, Meeting, SyncRecord


@dataclass(frozen=True)
class SyncAction:
    kind: str  # create | update | cancel
    meeting_id: int
    analyst_id: int
    analyst_email: str
    analyst_name: str
    content: EventContent | None
    sequence: int
    external_id: str | None


@dataclass(frozen=True)
class SyncOutcome:
    action: SyncAction
    ok: bool
    external_id: str | None = None
    error: str | None = None


def plan_sync(conference: Conference, meetings: Sequence[Meeting], attendees: Mapping[int, Sequence[int]],
              analysts: Mapping[int, Analyst], records: Sequence[SyncRecord]) -> list[SyncAction]:
    by_key = {(r.meeting_id, r.analyst_id): r for r in records}
    actions: list[SyncAction] = []
    current: set[tuple[int, int]] = set()

    for meeting in sorted(meetings, key=lambda x: x.id):
        if meeting.status != "confirmed":
            continue
        ids = list(attendees.get(meeting.id, []))
        for analyst_id in ids:
            current.add((meeting.id, analyst_id))
            analyst = analysts[analyst_id]
            others = [analysts[x].name for x in ids if x != analyst_id]
            content = build_event(conference, meeting, others)
            rec = by_key.get((meeting.id, analyst_id))
            if rec is None or rec.external_id is None or rec.state == "cancelled":
                sequence = 0 if rec is None or rec.external_id is None else rec.sequence + 1
                actions.append(SyncAction("create", meeting.id, analyst_id, analyst.email, analyst.name, content,
                                          sequence, rec.external_id if rec else None))
            elif rec.state == "failed" or rec.content_hash != content.content_hash():
                actions.append(SyncAction("update", meeting.id, analyst_id, analyst.email, analyst.name, content,
                                          rec.sequence + 1, rec.external_id))

    meetings_by_id = {x.id: x for x in meetings}
    for rec in sorted(records, key=lambda r: (r.meeting_id, r.analyst_id)):
        key = (rec.meeting_id, rec.analyst_id)
        if key in current or rec.external_id is None or rec.state == "cancelled":
            continue
        meeting = meetings_by_id.get(rec.meeting_id)
        if meeting is None:
            continue
        removed = meeting.status == "confirmed" and rec.analyst_id not in attendees.get(meeting.id, [])
        if meeting.status == "cancelled" or removed:
            analyst = analysts[rec.analyst_id]
            content = EventContent.from_json(rec.content_json) if rec.content_json else None
            actions.append(SyncAction("cancel", meeting.id, rec.analyst_id, analyst.email, analyst.name, content,
                                      rec.sequence + 1, rec.external_id))
    return actions
```

- [ ] **Step 5: Implement `backend/mcs/calendar/ics.py` and `backend/mcs/calendar/__init__.py`**

`backend/mcs/calendar/ics.py`:

```python
"""ICS sink: 'sending' assigns stable UIDs; files are rendered on demand from SyncRecords."""
import datetime as dt
import io
import re
import unicodedata
import zipfile
from typing import Mapping, Sequence

from icalendar import Calendar, Event

from mcs.calendar.content import EventContent
from mcs.calendar.planner import SyncAction, SyncOutcome
from mcs.models import SyncRecord, utcnow

PRODID = "-//Meeting Calendar Sync//EN"


def ics_uid(meeting_id: int, analyst_id: int) -> str:
    return f"mcs-{meeting_id}-{analyst_id}@meeting-calendar-sync"


class IcsSink:
    name = "ics"

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]:
        return [SyncOutcome(a, ok=True, external_id=a.external_id or ics_uid(a.meeting_id, a.analyst_id))
                for a in actions]


def render_ics(records: Sequence[SyncRecord], now: dt.datetime | None = None) -> bytes:
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    stamp = now or utcnow()
    usable = [(EventContent.from_json(r.content_json), r) for r in records if r.external_id and r.content_json]
    for content, rec in sorted(usable, key=lambda pair: (pair[0].start_utc, pair[1].external_id)):
        event = Event()
        event.add("uid", rec.external_id)
        event.add("summary", content.subject)
        if content.location:
            event.add("location", content.location)
        event.add("description", content.body)
        event.add("dtstart", content.start_utc)
        event.add("dtend", content.end_utc)
        event.add("dtstamp", stamp)
        event.add("sequence", rec.sequence)
        event.add("status", "CANCELLED" if rec.state == "cancelled" else "CONFIRMED")
        cal.add_component(event)
    return cal.to_ical()


def analyst_slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "colleague"


def zip_files(files: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()
```

`backend/mcs/calendar/__init__.py`:

```python
from typing import Protocol, Sequence

from mcs.calendar.planner import SyncAction, SyncOutcome


class CalendarSink(Protocol):
    name: str

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]: ...
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/mcs/calendar backend/tests
git commit -m "feat: event content, idempotent sync planner and ICS sink

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: Microsoft Graph sink, device-code sign-in, and the sink factory

**Files:**
- Create: `backend/mcs/calendar/graph.py`, `backend/mcs/calendar/graph_auth.py`
- Modify: `backend/mcs/calendar/__init__.py` (add `SinkNotConfigured`, `get_sink`)
- Test: `backend/tests/test_graph.py`, `backend/tests/test_graph_auth.py`, `backend/tests/test_sink_factory.py`

**Interfaces:**
- Consumes: `EventContent` (Task 6), `SyncAction`, `SyncOutcome` (Task 6), `IcsSink` (Task 6), `Settings.calendar_sink`, `graph_client_id`, `graph_tenant_id` (Task 1).
- Produces:
  - `mcs.calendar.graph`: `GRAPH_BASE = "https://graph.microsoft.com/v1.0"`; `event_payload(content: EventContent) -> dict`; `GraphSink(token_provider: Callable[[], str], client: httpx.Client, sleep: Callable[[float], None] = time.sleep)` with `name = "graph"` and `apply(conference, actions) -> list[SyncOutcome]`
  - `mcs.calendar.graph_auth`: `SCOPES = ["Calendars.ReadWrite.Shared"]`; `GraphAuthError(Exception)`; `GraphAuth(client_id: str | None, tenant_id: str | None, app_factory=msal.PublicClientApplication, run_in_background: Callable[[Callable[[], None]], None] | None = None)` with `configured: bool` (property), `start_device_flow() -> dict` (`user_code`, `verification_uri`, `message`, `expires_in`), `status() -> dict` (`configured`, `signed_in`, `pending`, `account`, `error`), `token() -> str`
  - `mcs.calendar.SinkNotConfigured(Exception)`; `mcs.calendar.get_sink(settings, graph_auth: GraphAuth | None = None, client: httpx.Client | None = None) -> CalendarSink`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_graph.py`:

```python
import datetime as dt
import json

import httpx
import pytest

from mcs.calendar.content import EventContent
from mcs.calendar.graph import GRAPH_BASE, GraphSink, event_payload
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.planner import SyncAction
from mcs.models import Conference

UTC = dt.timezone.utc
TOKEN = "tok-secret-value"
CONTENT = EventContent("NWRB – Northwind Robotics (1x1)", "The Example Grand Hotel – Salon 4",
                       "Industrials Conference 2026", dt.datetime(2026, 11, 10, 13, 0, tzinfo=UTC),
                       dt.datetime(2026, 11, 10, 13, 45, tzinfo=UTC))


def action(kind="create", external_id=None, sequence=0):
    return SyncAction(kind, 10, 1, "avery.kim@example.com", "Avery Kim", CONTENT, sequence, external_id)


def make_sink(handler, token_provider=lambda: TOKEN):
    calls, sleeps = [], []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    client = httpx.Client(base_url=GRAPH_BASE, transport=httpx.MockTransport(wrapped))
    return GraphSink(token_provider, client, sleep=sleeps.append), calls, sleeps


def test_event_payload():
    assert event_payload(CONTENT) == {
        "subject": "NWRB – Northwind Robotics (1x1)",
        "body": {"contentType": "text", "content": "Industrials Conference 2026"},
        "start": {"dateTime": "2026-11-10T13:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-10T13:45:00", "timeZone": "UTC"},
        "location": {"displayName": "The Example Grand Hotel – Salon 4"},
        "showAs": "busy",
    }


def test_create_posts_to_the_colleagues_calendar():
    sink, calls, _ = make_sink(lambda r: httpx.Response(201, json={"id": "AAMk-1"}))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert (outcome.ok, outcome.external_id, outcome.error) == (True, "AAMk-1", None)
    req = calls[0]
    assert req.method == "POST"
    assert req.url.path == "/v1.0/users/avery.kim@example.com/calendar/events"
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    body = json.loads(req.content)
    assert body["transactionId"] == "mcs-10-1-0"
    assert body["start"] == {"dateTime": "2026-11-10T13:00:00", "timeZone": "UTC"}


def test_update_patches_existing_event():
    sink, calls, _ = make_sink(lambda r: httpx.Response(200, json={"id": "AAMk-1"}))
    [outcome] = sink.apply(Conference(id=1), [action("update", "AAMk-1", 1)])
    assert (outcome.ok, outcome.external_id) == (True, "AAMk-1")
    assert calls[0].method == "PATCH"
    assert calls[0].url.path == "/v1.0/users/avery.kim@example.com/events/AAMk-1"


@pytest.mark.parametrize("status", [204, 404])
def test_cancel_deletes_and_404_counts_as_done(status):
    sink, calls, _ = make_sink(lambda r: httpx.Response(status))
    [outcome] = sink.apply(Conference(id=1), [action("cancel", "AAMk-1", 2)])
    assert outcome.ok and calls[0].method == "DELETE"


@pytest.mark.parametrize("status,body,expected", [
    (401, {}, "Sign in to Microsoft again."),
    (403, {}, "No delegate access to avery.kim@example.com's calendar."),
    (500, {"error": {"code": "x", "message": "Something broke"}}, "Graph error 500: Something broke"),
])
def test_errors_are_readable_and_never_leak_the_token(status, body, expected):
    sink, _, _ = make_sink(lambda r: httpx.Response(status, json=body))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok
    assert outcome.error == expected
    assert TOKEN not in outcome.error


def test_429_waits_retry_after_and_retries_once():
    responses = iter([httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(201, json={"id": "X"})])
    sink, calls, sleeps = make_sink(lambda r: next(responses))
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert outcome.ok and len(calls) == 2 and sleeps == [2.0]


def test_retry_after_is_capped():
    responses = iter([httpx.Response(429, headers={"Retry-After": "120"}), httpx.Response(201, json={"id": "X"})])
    sink, _, sleeps = make_sink(lambda r: next(responses))
    sink.apply(Conference(id=1), [action()])
    assert sleeps == [10.0]


def test_not_signed_in_fails_every_item_without_requests():
    def no_token():
        raise GraphAuthError("Sign in to Microsoft first.")
    sink, calls, _ = make_sink(lambda r: httpx.Response(201, json={"id": "X"}), token_provider=no_token)
    outcomes = sink.apply(Conference(id=1), [action(), action("cancel", "A", 1)])
    assert [o.error for o in outcomes] == ["Sign in to Microsoft first."] * 2
    assert calls == []


def test_network_error_is_reported_per_item():
    def boom(request):
        raise httpx.ConnectError("offline", request=request)
    sink, _, _ = make_sink(boom)
    [outcome] = sink.apply(Conference(id=1), [action()])
    assert not outcome.ok and outcome.error.startswith("Could not reach Microsoft Graph")
```

`backend/tests/test_graph_auth.py`:

```python
import pytest

from mcs.calendar.graph_auth import SCOPES, GraphAuth, GraphAuthError


class FakeApp:
    def __init__(self, client_id, authority):
        self.client_id, self.authority = client_id, authority
        self.accounts = []
        self.flow = {"user_code": "ABCD-1234", "verification_uri": "https://microsoft.com/devicelogin",
                     "message": "To sign in, use a web browser...", "expires_in": 900}
        self.device_result = {"access_token": "tok"}
        self.silent_result = {"access_token": "tok"}
        self.scopes = None

    def initiate_device_flow(self, scopes):
        self.scopes = scopes
        return self.flow

    def acquire_token_by_device_flow(self, flow):
        if "access_token" in self.device_result:
            self.accounts = [{"username": "coordinator@example.com"}]
        return self.device_result

    def get_accounts(self):
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return self.silent_result


def make(run=lambda fn: fn(), **app_overrides):
    apps = []

    def factory(client_id, authority):
        app = FakeApp(client_id, authority)
        for k, v in app_overrides.items():
            setattr(app, k, v)
        apps.append(app)
        return app

    return GraphAuth("client-id", "tenant-id", app_factory=factory, run_in_background=run), apps


def test_not_configured():
    auth = GraphAuth(None, None)
    assert auth.configured is False
    with pytest.raises(GraphAuthError, match="not configured"):
        auth.start_device_flow()
    assert auth.status() == {"configured": False, "signed_in": False, "pending": False, "account": None, "error": None}


def test_device_flow_signs_in():
    auth, apps = make()
    started = auth.start_device_flow()
    assert started["user_code"] == "ABCD-1234"
    assert started["verification_uri"] == "https://microsoft.com/devicelogin"
    assert apps[0].authority == "https://login.microsoftonline.com/tenant-id"
    assert apps[0].scopes == SCOPES == ["Calendars.ReadWrite.Shared"]
    status = auth.status()
    assert status["signed_in"] is True and status["account"] == "coordinator@example.com" and status["pending"] is False
    assert auth.token() == "tok"


def test_pending_until_background_finishes():
    jobs = []
    auth, _ = make(run=jobs.append)
    auth.start_device_flow()
    assert auth.status()["pending"] is True
    jobs[0]()
    assert auth.status()["pending"] is False


def test_declined_sign_in_reports_error():
    auth, _ = make(device_result={"error": "authorization_declined", "error_description": "User declined"})
    auth.start_device_flow()
    assert auth.status()["error"] == "User declined"
    with pytest.raises(GraphAuthError, match="first"):
        auth.token()


def test_silent_failure_asks_to_sign_in_again():
    auth, _ = make(silent_result=None)
    auth.start_device_flow()
    with pytest.raises(GraphAuthError, match="again"):
        auth.token()


def test_flow_start_error():
    auth, _ = make(flow={"error": "invalid_client", "error_description": "Public client flows are disabled"})
    with pytest.raises(GraphAuthError, match="Public client flows are disabled"):
        auth.start_device_flow()
```

`backend/tests/test_sink_factory.py`:

```python
import pytest

from mcs.calendar import SinkNotConfigured, get_sink
from mcs.calendar.graph import GraphSink
from mcs.calendar.graph_auth import GraphAuth
from mcs.calendar.ics import IcsSink
from mcs.config import Settings


def make(**kw):
    return Settings(_env_file=None, use_keychain=False, **kw)


def test_ics_is_default():
    assert isinstance(get_sink(make()), IcsSink)


def test_graph_without_configuration_raises():
    with pytest.raises(SinkNotConfigured, match="not configured"):
        get_sink(make(calendar_sink="graph"), GraphAuth(None, None))


def test_graph_with_configuration():
    auth = GraphAuth("cid", "tid", app_factory=lambda client_id, authority: object())
    assert isinstance(get_sink(make(calendar_sink="graph"), auth), GraphSink)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q tests/test_graph.py tests/test_graph_auth.py tests/test_sink_factory.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.calendar.graph'`.

- [ ] **Step 3: Implement `backend/mcs/calendar/graph_auth.py`**

```python
"""Delegated Microsoft Graph sign-in (device code). Tokens stay in MSAL's in-memory cache only."""
import threading
from typing import Callable

import msal

SCOPES = ["Calendars.ReadWrite.Shared"]


class GraphAuthError(Exception):
    """Sign-in problem; the message is shown to the coordinator."""


def _thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


class GraphAuth:
    def __init__(self, client_id: str | None, tenant_id: str | None,
                 app_factory=msal.PublicClientApplication,
                 run_in_background: Callable[[Callable[[], None]], None] | None = None):
        self.client_id = client_id
        self.tenant_id = tenant_id
        self._app_factory = app_factory
        self._run = run_in_background or _thread
        self._app = None
        self._lock = threading.Lock()
        self._pending = False
        self._error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.tenant_id)

    def _application(self):
        if not self.configured:
            raise GraphAuthError("Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID.")
        if self._app is None:
            self._app = self._app_factory(self.client_id,
                                          authority=f"https://login.microsoftonline.com/{self.tenant_id}")
        return self._app

    def start_device_flow(self) -> dict:
        app = self._application()
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise GraphAuthError(flow.get("error_description") or "Could not start Microsoft sign-in.")
        with self._lock:
            self._pending, self._error = True, None

        def finish() -> None:
            result = app.acquire_token_by_device_flow(flow)
            with self._lock:
                self._pending = False
                if "access_token" not in result:
                    self._error = result.get("error_description") or "Microsoft sign-in failed."

        self._run(finish)
        return {"user_code": flow["user_code"], "verification_uri": flow["verification_uri"],
                "message": flow.get("message", ""), "expires_in": flow.get("expires_in")}

    def status(self) -> dict:
        signed_in, account = False, None
        if self.configured and self._app is not None:
            accounts = self._app.get_accounts()
            if accounts:
                signed_in, account = True, accounts[0].get("username")
        with self._lock:
            return {"configured": self.configured, "signed_in": signed_in, "pending": self._pending,
                    "account": account, "error": self._error}

    def token(self) -> str:
        app = self._application()
        accounts = app.get_accounts()
        if not accounts:
            raise GraphAuthError("Sign in to Microsoft first.")
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result or "access_token" not in result:
            raise GraphAuthError("Sign in to Microsoft again.")
        return result["access_token"]
```

- [ ] **Step 4: Implement `backend/mcs/calendar/graph.py`**

```python
"""Graph sink: writes events straight into each colleague's calendar via delegate access."""
import datetime as dt
import time
from typing import Callable, Sequence
from urllib.parse import quote

import httpx

from mcs.calendar.content import EventContent
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.planner import SyncAction, SyncOutcome

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RETRY_AFTER = 10.0


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def event_payload(content: EventContent) -> dict:
    return {
        "subject": content.subject,
        "body": {"contentType": "text", "content": content.body},
        "start": {"dateTime": _utc(content.start_utc), "timeZone": "UTC"},
        "end": {"dateTime": _utc(content.end_utc), "timeZone": "UTC"},
        "location": {"displayName": content.location},
        "showAs": "busy",
    }


class GraphSink:
    name = "graph"

    def __init__(self, token_provider: Callable[[], str], client: httpx.Client,
                 sleep: Callable[[float], None] = time.sleep):
        self.token_provider = token_provider
        self.client = client
        self.sleep = sleep

    def apply(self, conference, actions: Sequence[SyncAction]) -> list[SyncOutcome]:
        try:
            token = self.token_provider()
        except GraphAuthError as exc:
            return [SyncOutcome(a, ok=False, external_id=a.external_id, error=str(exc)) for a in actions]
        headers = {"Authorization": f"Bearer {token}"}
        return [self._apply_one(a, headers) for a in actions]

    def _apply_one(self, action: SyncAction, headers: dict) -> SyncOutcome:
        user = quote(action.analyst_email, safe="@")
        try:
            if action.kind == "create":
                body = {**event_payload(action.content),
                        "transactionId": f"mcs-{action.meeting_id}-{action.analyst_id}-{action.sequence}"}
                resp = self._send("POST", f"/users/{user}/calendar/events", headers, body)
                if resp.status_code in (200, 201):
                    return SyncOutcome(action, ok=True, external_id=resp.json()["id"])
            elif action.kind == "update":
                resp = self._send("PATCH", f"/users/{user}/events/{quote(action.external_id, safe='')}",
                                  headers, event_payload(action.content))
                if resp.status_code == 200:
                    return SyncOutcome(action, ok=True, external_id=action.external_id)
            else:
                resp = self._send("DELETE", f"/users/{user}/events/{quote(action.external_id, safe='')}", headers)
                if resp.status_code in (200, 204, 404):
                    return SyncOutcome(action, ok=True, external_id=action.external_id)
        except httpx.HTTPError as exc:
            return SyncOutcome(action, ok=False, external_id=action.external_id,
                               error=f"Could not reach Microsoft Graph ({exc.__class__.__name__}).")
        return SyncOutcome(action, ok=False, external_id=action.external_id, error=self._error(resp, action))

    def _send(self, method: str, path: str, headers: dict, body: dict | None = None) -> httpx.Response:
        resp = self.client.request(method, path, headers=headers, json=body)
        if resp.status_code == 429:
            try:
                wait = float(resp.headers.get("Retry-After", "1"))
            except ValueError:
                wait = 1.0
            self.sleep(min(wait, MAX_RETRY_AFTER))
            resp = self.client.request(method, path, headers=headers, json=body)
        return resp

    @staticmethod
    def _error(resp: httpx.Response, action: SyncAction) -> str:
        if resp.status_code == 401:
            return "Sign in to Microsoft again."
        if resp.status_code == 403:
            return f"No delegate access to {action.analyst_email}'s calendar."
        try:
            message = resp.json().get("error", {}).get("message", "")
        except ValueError:
            message = ""
        return f"Graph error {resp.status_code}: {message}".strip().rstrip(":")
```

- [ ] **Step 5: Add the factory to `backend/mcs/calendar/__init__.py`**

Append:

```python
class SinkNotConfigured(Exception):
    """The configured sink cannot run yet; the message is shown to the coordinator."""


def get_sink(settings, graph_auth=None, client=None) -> CalendarSink:
    if settings.calendar_sink == "ics":
        from mcs.calendar.ics import IcsSink

        return IcsSink()
    if settings.calendar_sink == "graph":
        import httpx

        from mcs.calendar.graph import GRAPH_BASE, GraphSink

        if graph_auth is None or not graph_auth.configured:
            raise SinkNotConfigured(
                "Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID."
            )
        return GraphSink(graph_auth.token, client or httpx.Client(base_url=GRAPH_BASE, timeout=30))
    raise ValueError(f"Unknown calendar sink {settings.calendar_sink!r}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/mcs/calendar backend/tests
git commit -m "feat: Microsoft Graph sink with device-code sign-in (in-memory token)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: Service layer — conferences, meetings, verification rules, roster, send

**Files:**
- Create: `backend/mcs/schemas.py`, `backend/mcs/service.py`
- Test: `backend/tests/test_service.py`

**Interfaces:**
- Consumes: models (Task 1); `ExtractionResult`, `parse_extraction` (Task 2); `RosterEntry`, `roster_entries`, `match_name`, `normalize_name` (Task 4); `build_meetings`, `compute_flags`, `has_block`, `MeetingView`, `parse_time`, `parse_date`, `valid_timezone`, `add_minutes` (Task 5); `build_event`, `plan_sync`, `SyncAction`, `SyncOutcome`, `IcsSink` (Task 6); `CalendarSink` (Task 6/7).
- Produces:
  - `mcs.schemas` (Pydantic): `FlagOut`, `AttendeeOut`, `MeetingOut`, `Counts`, `ConferenceSummary`, `ConferenceDetail`, `AnalystIn`, `AnalystUpdate`, `AnalystOut`, `MeetingCreate`, `MeetingUpdate`, `ConferenceUpdate`, `ConfirmReadyIn`, `SyncActionOut`, `AnalystSendSummary`, `SendResult` — exact fields below.
  - `mcs.service`: exceptions `NotFound`, `Conflict(message, flags=())` (`.flags: list[FlagOut]`), `InvalidInput`; roster: `list_analysts`, `create_analyst`, `update_analyst`, `delete_analyst`, `seed_roster(session, path) -> int`; conferences: `create_conference(session, result, *, pdf_filename, pdf_path, extractor, default_attendee_ids=(), default_minutes=45) -> Conference`, `get_conference`, `list_conference_summaries(session, sink_name) -> list[ConferenceSummary]`, `conference_detail(session, conference_id, sink_name, skipped_items=0) -> ConferenceDetail`, `update_conference(session, conference_id, data) -> Conference`, `delete_conference(session, conference_id) -> str` (returns stored PDF path); meetings: `get_meeting`, `add_meeting(session, conference_id, data, default_minutes) -> Meeting`, `update_meeting(session, meeting_id, data, default_minutes) -> Meeting`, `confirm_meeting`, `unconfirm_meeting`, `confirm_ready(session, conference_id, meeting_ids=None) -> int`, `delete_meeting(session, meeting_id) -> str` (`"deleted"` | `"cancelled"`); sync: `plan_conference(session, conference_id, sink_name) -> list[SyncAction]`, `send_conference(session, conference_id, sink) -> list[SyncOutcome]`, `ics_records_for(session, conference_id, analyst_id) -> list[SyncRecord]`, `send_result(session, conference_id, sink_name, actions_or_outcomes, dry_run) -> SendResult`.
  - Meeting `review_state` values: `needs_attention` (draft with a block flag), `ready` (draft, no block flag), `verified` (confirmed, not fully sent), `sent` (confirmed, every attendee sent, nothing pending removal), `cancelled`.

- [ ] **Step 1: Write `backend/mcs/schemas.py`** (data shapes only; exercised by the service tests)

```python
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Format = Literal["one_on_one", "group", "meal", "other"]
SyncState = Literal["not_sent", "sent", "changed", "failed", "cancelled"]
ReviewState = Literal["needs_attention", "ready", "verified", "sent", "cancelled"]


class FlagOut(BaseModel):
    code: str
    severity: str
    message: str


class AttendeeOut(BaseModel):
    analyst_id: int
    name: str
    email: str
    match: str
    sync: SyncState
    sync_error: str | None = None


class MeetingOut(BaseModel):
    id: int
    conference_id: int
    date: str | None
    start: str | None
    end: str | None
    end_assumed: bool
    room: str
    company: str
    ticker: str | None
    format: str
    company_attendees: list[str]
    raw_attendee_names: list[str]
    ignored_names: list[str]
    unmatched_names: list[str]
    notes: str
    source_page: int | None
    status: str
    review_state: ReviewState
    attendees: list[AttendeeOut]
    removed: list[AttendeeOut]  # colleagues taken off a sent meeting; removed from their calendar on next send
    flags: list[FlagOut]


class Counts(BaseModel):
    total: int = 0
    needs_attention: int = 0
    ready: int = 0
    verified: int = 0
    sent: int = 0
    cancelled: int = 0
    warnings: int = 0
    changed: int = 0
    failed: int = 0
    pending_actions: int = 0


class ConferenceSummary(BaseModel):
    id: int
    name: str
    broker: str
    hotel: str
    city: str
    timezone: str | None
    created_at: dt.datetime
    first_date: str | None
    last_date: str | None
    counts: Counts


class ConferenceDetail(ConferenceSummary):
    schedule_for: str
    pdf_filename: str
    extractor: str
    meetings: list[MeetingOut]
    skipped_items: int = 0


class AnalystIn(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    aliases: list[str] = Field(default_factory=list)
    active: bool = True


class AnalystUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    aliases: list[str] | None = None
    active: bool | None = None


class AnalystOut(BaseModel):
    id: int
    name: str
    email: str
    aliases: list[str]
    active: bool


class MeetingCreate(BaseModel):
    company: str = Field(min_length=1)
    date: str | None = None
    start: str | None = None
    end: str | None = None
    room: str = ""
    ticker: str | None = None
    format: Format = "one_on_one"
    attendee_ids: list[int] = Field(default_factory=list)
    notes: str = ""


class MeetingUpdate(BaseModel):
    date: str | None = None
    start: str | None = None
    end: str | None = None
    room: str | None = None
    company: str | None = None
    ticker: str | None = None
    format: Format | None = None
    company_attendees: list[str] | None = None
    notes: str | None = None
    attendee_ids: list[int] | None = None
    ignored_names: list[str] | None = None


class ConferenceUpdate(BaseModel):
    name: str | None = None
    broker: str | None = None
    hotel: str | None = None
    city: str | None = None
    timezone: str | None = None


class ConfirmReadyIn(BaseModel):
    meeting_ids: list[int] | None = None


class SyncActionOut(BaseModel):
    kind: str
    meeting_id: int
    analyst_id: int
    analyst_name: str
    subject: str | None
    ok: bool | None = None
    error: str | None = None


class AnalystSendSummary(BaseModel):
    analyst_id: int
    name: str
    create: int = 0
    update: int = 0
    cancel: int = 0
    failed: int = 0
    download_url: str | None = None


class SendResult(BaseModel):
    sink: str
    dry_run: bool
    actions: list[SyncActionOut]
    by_analyst: list[AnalystSendSummary]
    ok_count: int = 0
    failed_count: int = 0
    zip_url: str | None = None
```

- [ ] **Step 2: Write the failing test** — `backend/tests/test_service.py`:

```python
import json

import pytest
from sqlmodel import select

from mcs import service
from mcs.calendar.ics import IcsSink
from mcs.calendar.planner import SyncOutcome
from mcs.config import REPO_ROOT
from mcs.extraction.schema import parse_extraction
from mcs.models import Meeting, MeetingAttendee, SyncRecord
from mcs.schemas import AnalystIn, AnalystUpdate, ConferenceUpdate, MeetingCreate, MeetingUpdate

SAMPLES = REPO_ROOT / "samples"


def sample(name):
    return parse_extraction(json.loads((SAMPLES / f"{name}.expected.json").read_text()))


@pytest.fixture
def seeded(session):
    service.seed_roster(session, SAMPLES / "roster.sample.json")
    return session


def ids(session):
    return {a.name: a.id for a in service.list_analysts(session)}


def make_conf(session, name="broker_a_grid"):
    return service.create_conference(session, sample(name), pdf_filename=f"{name}.pdf",
                                     pdf_path=f"/tmp/{name}.pdf", extractor="fake")


def detail(session, conf):
    return service.conference_detail(session, conf.id, "ics")


def by_company(d, company):
    return next(m for m in d.meetings if m.company == company)


def test_seed_roster_is_idempotent(session):
    assert service.seed_roster(session, SAMPLES / "roster.sample.json") == 6
    assert service.seed_roster(session, SAMPLES / "roster.sample.json") == 0
    assert [a.name for a in service.list_analysts(session)][:2] == ["Avery Kim", "Jordan Lee"]  # sorted by name


def test_create_conference_from_sample(seeded):
    conf = make_conf(seeded)
    assert (conf.name, conf.timezone, conf.hotel, conf.extractor) == (
        "Industrials Conference 2026", "America/New_York", "The Example Grand Hotel", "fake")
    d = detail(seeded, conf)
    assert len(d.meetings) == 12
    assert (d.first_date, d.last_date) == ("2026-11-10", "2026-11-11")
    first = d.meetings[0]
    assert (first.date, first.start, first.end, first.company) == ("2026-11-10", "08:00", "08:45", "Northwind Robotics")
    assert [(a.name, a.match, a.sync) for a in first.attendees] == [("Avery Kim", "exact", "not_sent"), ("Jordan Lee", "exact", "not_sent")]
    tide = by_company(d, "Tidewater Pumps")
    assert tide.review_state == "needs_attention"
    assert {f.code for f in tide.flags} == {"no_attendee", "unmatched_name"}
    assert tide.unmatched_names == ["Chris Wong"]
    assert d.counts.total == 12 and d.counts.needs_attention == 1 and d.counts.ready == 11
    assert d.counts.warnings == 1 and d.counts.pending_actions == 0


def test_itinerary_sample_assumes_ends_and_uses_addressee(seeded):
    d = detail(seeded, make_conf(seeded, "broker_c_itinerary"))
    assert d.timezone == "Europe/London"
    assert all(m.end_assumed and [a.name for a in m.attendees] == ["Sam Patel"] for m in d.meetings)
    assert all({f.code for f in m.flags} == {"assumed_end"} for m in d.meetings)


def test_verify_rules(seeded):
    conf = make_conf(seeded)
    d = detail(seeded, conf)
    tide = by_company(d, "Tidewater Pumps")
    with pytest.raises(service.Conflict) as info:
        service.confirm_meeting(seeded, tide.id)
    assert "no_attendee" in {f.code for f in info.value.flags}
    first = d.meetings[0]
    assert service.confirm_meeting(seeded, first.id).status == "confirmed"
    assert by_company(detail(seeded, conf), "Northwind Robotics").review_state == "verified"
    subset = [d.meetings[1].id, d.meetings[2].id, tide.id]
    assert service.confirm_ready(seeded, conf.id, subset) == 2
    assert service.confirm_ready(seeded, conf.id) == 8
    assert service.unconfirm_meeting(seeded, first.id).status == "draft"


def test_assign_and_dismiss_clear_flags(seeded):
    conf = make_conf(seeded)
    tide = by_company(detail(seeded, conf), "Tidewater Pumps")
    service.update_meeting(seeded, tide.id, MeetingUpdate(attendee_ids=[ids(seeded)["Jordan Lee"]]), 45)
    tide = by_company(detail(seeded, conf), "Tidewater Pumps")
    assert [(a.name, a.match) for a in tide.attendees] == [("Jordan Lee", "manual")]
    assert {f.code for f in tide.flags} == {"unmatched_name"}
    service.update_meeting(seeded, tide.id, MeetingUpdate(ignored_names=["Chris Wong"]), 45)
    assert by_company(detail(seeded, conf), "Tidewater Pumps").flags == []


def test_attendee_edit_keeps_existing_match_kinds(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    people = ids(seeded)
    service.update_meeting(seeded, first.id, MeetingUpdate(attendee_ids=[people["Avery Kim"], people["Sam Patel"]]), 45)
    got = [(a.name, a.match) for a in by_company(detail(seeded, conf), "Northwind Robotics").attendees]
    assert got == [("Avery Kim", "exact"), ("Sam Patel", "manual")]


def test_time_edits_and_status_rule(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    service.update_meeting(seeded, first.id, MeetingUpdate(start="9:15 AM", end="10:00"), 45)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert (m.start, m.end, m.end_assumed) == ("09:15", "10:00", False)
    with pytest.raises(service.InvalidInput):
        service.update_meeting(seeded, first.id, MeetingUpdate(start="nonsense"), 45)
    service.confirm_meeting(seeded, first.id)
    service.update_meeting(seeded, first.id, MeetingUpdate(end=None), 45)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert m.status == "draft" and "missing_time" in {f.code for f in m.flags}


def test_assumed_end_follows_start(seeded):
    conf = make_conf(seeded, "broker_c_itinerary")
    m = detail(seeded, conf).meetings[0]
    service.update_meeting(seeded, m.id, MeetingUpdate(start="08:30"), 45)
    m = detail(seeded, conf).meetings[0]
    assert (m.start, m.end, m.end_assumed) == ("08:30", "09:15", True)


def test_clearing_timezone_unverifies_and_blocks_sending(seeded):
    conf = make_conf(seeded)
    service.confirm_ready(seeded, conf.id)
    with pytest.raises(service.InvalidInput):
        service.update_conference(seeded, conf.id, ConferenceUpdate(timezone="Eastern"))
    service.update_conference(seeded, conf.id, ConferenceUpdate(timezone=None))
    d = detail(seeded, conf)
    assert all(m.status == "draft" for m in d.meetings)
    assert service.plan_conference(seeded, conf.id, "ics") == []


def test_send_update_remove_cancel_cycle(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]  # Northwind: Avery + Jordan
    service.confirm_meeting(seeded, first.id)
    assert [a.kind for a in service.plan_conference(seeded, conf.id, "ics")] == ["create", "create"]
    outcomes = service.send_conference(seeded, conf.id, IcsSink())
    assert all(o.ok for o in outcomes)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert m.review_state == "sent" and {a.sync for a in m.attendees} == {"sent"}
    recs = seeded.exec(select(SyncRecord)).all()
    assert {r.external_id for r in recs} == {f"mcs-{first.id}-{a.analyst_id}@meeting-calendar-sync" for a in m.attendees}

    service.update_meeting(seeded, first.id, MeetingUpdate(room="Salon 2"), 45)
    d = detail(seeded, conf)
    assert {a.sync for a in by_company(d, "Northwind Robotics").attendees} == {"changed"}
    assert d.counts.pending_actions == 2
    service.send_conference(seeded, conf.id, IcsSink())
    assert {r.sequence for r in seeded.exec(select(SyncRecord)).all()} == {1}

    service.update_meeting(seeded, first.id, MeetingUpdate(attendee_ids=[ids(seeded)["Avery Kim"]]), 45)
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    assert [r.name for r in m.removed] == ["Jordan Lee"]
    plan = service.plan_conference(seeded, conf.id, "ics")
    assert sorted(a.kind for a in plan) == ["cancel", "update"]  # Jordan cancelled; Avery's "Also attending" changed
    service.send_conference(seeded, conf.id, IcsSink())

    assert service.delete_meeting(seeded, first.id) == "cancelled"
    assert [a.kind for a in service.plan_conference(seeded, conf.id, "ics")] == ["cancel"]
    service.send_conference(seeded, conf.id, IcsSink())
    d = detail(seeded, conf)
    assert by_company(d, "Northwind Robotics").review_state == "cancelled"
    assert d.counts.cancelled == 1 and d.counts.total == 11
    avery_recs = service.ics_records_for(seeded, conf.id, ids(seeded)["Avery Kim"])
    assert [r.state for r in avery_recs] == ["cancelled"]


class FailFor:
    name = "ics"

    def __init__(self, email):
        self.email = email

    def apply(self, conference, actions):
        return [SyncOutcome(a, ok=a.analyst_email != self.email,
                            external_id=None if a.analyst_email == self.email else f"x-{a.analyst_id}",
                            error="Graph error 500: boom" if a.analyst_email == self.email else None)
                for a in actions]


def test_partial_failure_retries_only_failed_item(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    service.confirm_meeting(seeded, first.id)
    outcomes = service.send_conference(seeded, conf.id, FailFor("jordan.lee@example.com"))
    assert sorted(o.ok for o in outcomes) == [False, True]
    m = by_company(detail(seeded, conf), "Northwind Robotics")
    syncs = {a.name: (a.sync, a.sync_error) for a in m.attendees}
    assert syncs == {"Avery Kim": ("sent", None), "Jordan Lee": ("failed", "Graph error 500: boom")}
    retry = service.plan_conference(seeded, conf.id, "ics")
    assert [(a.kind, a.analyst_name) for a in retry] == [("create", "Jordan Lee")]
    assert detail(seeded, conf).counts.failed == 1


def test_delete_unsent_meeting_removes_it(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    assert service.delete_meeting(seeded, first.id) == "deleted"
    assert seeded.get(Meeting, first.id) is None
    assert seeded.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id == first.id)).all() == []


def test_add_meeting_manual(seeded):
    conf = make_conf(seeded)
    m = service.add_meeting(seeded, conf.id, MeetingCreate(company="Atlas Rail Systems", date="2026-11-10",
                                                           start="16:00", attendee_ids=[ids(seeded)["Riley Chen"]]), 45)
    out = by_company(detail(seeded, conf), "Atlas Rail Systems")
    assert (out.start, out.end, out.end_assumed, out.status) == ("16:00", "16:45", True, "draft")
    assert out.attendees[0].match == "manual"
    assert m.conference_id == conf.id


def test_cancelled_meeting_cannot_be_edited(seeded):
    conf = make_conf(seeded)
    first = detail(seeded, conf).meetings[0]
    service.confirm_meeting(seeded, first.id)
    service.send_conference(seeded, conf.id, IcsSink())
    service.delete_meeting(seeded, first.id)
    with pytest.raises(service.Conflict):
        service.update_meeting(seeded, first.id, MeetingUpdate(room="X"), 45)


def test_delete_conference_removes_everything(seeded):
    conf = make_conf(seeded)
    service.confirm_ready(seeded, conf.id)
    service.send_conference(seeded, conf.id, IcsSink())
    assert service.delete_conference(seeded, conf.id) == "/tmp/broker_a_grid.pdf"
    assert seeded.exec(select(Meeting)).all() == []
    assert seeded.exec(select(SyncRecord)).all() == []
    with pytest.raises(service.NotFound):
        service.get_conference(seeded, conf.id)


def test_roster_crud_rules(seeded):
    with pytest.raises(service.InvalidInput):
        service.create_analyst(seeded, AnalystIn(name="Dup", email="avery.kim@example.com"))
    new = service.create_analyst(seeded, AnalystIn(name="Casey Fox", email="casey.fox@example.com", aliases=["C. Fox"]))
    assert service.update_analyst(seeded, new.id, AnalystUpdate(active=False)).active is False
    service.delete_analyst(seeded, new.id)
    conf = make_conf(seeded)
    with pytest.raises(service.Conflict):
        service.delete_analyst(seeded, ids(seeded)["Avery Kim"])  # referenced by meetings


def test_summaries(seeded):
    make_conf(seeded)
    make_conf(seeded, "broker_b_by_company")
    summaries = service.list_conference_summaries(seeded, "ics")
    assert [s.name for s in summaries] == ["Technology Summit 2026", "Industrials Conference 2026"]  # newest first
    assert summaries[0].counts.total == 8


def test_send_result_shapes(seeded):
    conf = make_conf(seeded)
    service.confirm_meeting(seeded, detail(seeded, conf).meetings[0].id)
    plan = service.plan_conference(seeded, conf.id, "ics")
    preview = service.send_result(seeded, conf.id, "ics", plan, dry_run=True)
    assert preview.dry_run and [a.ok for a in preview.actions] == [None, None]
    assert {(s.name, s.create) for s in preview.by_analyst} == {("Avery Kim", 1), ("Jordan Lee", 1)}
    outcomes = service.send_conference(seeded, conf.id, IcsSink())
    done = service.send_result(seeded, conf.id, "ics", outcomes, dry_run=False)
    assert done.ok_count == 2 and done.failed_count == 0
    assert done.zip_url == f"/api/conferences/{conf.id}/ics.zip"
    assert all(s.download_url == f"/api/conferences/{conf.id}/ics/{s.analyst_id}" for s in done.by_analyst)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_service.py`
Expected: FAIL — `ImportError: cannot import name 'service' from 'mcs'`.

- [ ] **Step 4: Implement `backend/mcs/service.py`**

```python
"""Database-backed operations and the verification rules. Routes stay thin; this is the app's logic."""
import datetime as dt
import json
from pathlib import Path
from typing import Sequence

from sqlalchemy import delete
from sqlmodel import Session, select

from mcs.calendar.content import build_event
from mcs.calendar.planner import SyncAction, SyncOutcome, plan_sync
from mcs.extraction.schema import ExtractionResult
from mcs.models import Analyst, Conference, Meeting, MeetingAttendee, SyncRecord, utcnow
from mcs.normalize import (
    MeetingView, add_minutes, build_meetings, compute_flags, has_block, parse_date, parse_time, valid_timezone,
)
from mcs.roster import RosterEntry, match_name, normalize_name, roster_entries
from mcs.schemas import (
    AnalystIn, AnalystSendSummary, AnalystUpdate, AttendeeOut, ConferenceDetail, ConferenceSummary,
    ConferenceUpdate, Counts, FlagOut, MeetingCreate, MeetingOut, MeetingUpdate, SendResult, SyncActionOut,
)


class NotFound(Exception):
    pass


class InvalidInput(Exception):
    pass


class Conflict(Exception):
    def __init__(self, message: str, flags=()):
        super().__init__(message)
        self.flags = [FlagOut(code=f.code, severity=f.severity, message=f.message) for f in flags]


# ---------- helpers ----------

def _strict_time(value: str | None) -> dt.time | None:
    if value is None or not value.strip():
        return None
    parsed = parse_time(value)
    if parsed is None:
        raise InvalidInput(f"Couldn't read the time {value!r}. Use HH:MM, e.g. 08:30.")
    return parsed


def _strict_date(value: str | None) -> dt.date | None:
    if value is None or not value.strip():
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise InvalidInput(f"Couldn't read the date {value!r}. Use YYYY-MM-DD.")
    return parsed


def _hhmm(t: dt.time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def _analysts(session: Session) -> dict[int, Analyst]:
    return {a.id: a for a in session.exec(select(Analyst)).all()}


def _roster(session: Session) -> list[RosterEntry]:
    return roster_entries(session.exec(select(Analyst)).all())


def _meetings(session: Session, conference_id: int) -> list[Meeting]:
    return list(session.exec(select(Meeting).where(Meeting.conference_id == conference_id)).all())


def _attendee_map(session: Session, meeting_ids: Sequence[int]) -> dict[int, list[tuple[int, str]]]:
    out: dict[int, list[tuple[int, str]]] = {mid: [] for mid in meeting_ids}
    if meeting_ids:
        rows = session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meeting_ids))
                            .order_by(MeetingAttendee.analyst_id)).all()
        for row in rows:
            out[row.meeting_id].append((row.analyst_id, row.match))
    return out


def _records(session: Session, meeting_ids: Sequence[int], sink_name: str) -> list[SyncRecord]:
    if not meeting_ids:
        return []
    return list(session.exec(select(SyncRecord).where(SyncRecord.meeting_id.in_(meeting_ids),
                                                     SyncRecord.sink == sink_name)).all())


def _views(meetings: Sequence[Meeting], att: dict[int, list[tuple[int, str]]]) -> list[MeetingView]:
    return [MeetingView(id=m.id, date=m.date, start_time=m.start_time, end_time=m.end_time,
                        end_assumed=m.end_assumed, company=m.company, status=m.status,
                        attendees=tuple(att.get(m.id, [])), raw_attendee_names=tuple(m.raw_attendee_names),
                        ignored_names=tuple(m.ignored_names)) for m in meetings]


def _flags(session: Session, conference: Conference, meetings: Sequence[Meeting]):
    att = _attendee_map(session, [m.id for m in meetings])
    return compute_flags(conference.timezone, _views(meetings, att), _roster(session)), att


def _sort_key(m: Meeting):
    return (m.date is None, m.date or dt.date.max, m.start_time is None, m.start_time or dt.time.max,
            m.company.casefold(), m.id)


def _enforce_status(session: Session, conference: Conference) -> None:
    meetings = _meetings(session, conference.id)
    flags, _ = _flags(session, conference, meetings)
    changed = False
    for m in meetings:
        if m.status == "confirmed" and has_block(flags[m.id]):
            m.status = "draft"
            m.updated_at = utcnow()
            session.add(m)
            changed = True
    if changed:
        session.commit()


def _active_ids(session: Session, analyst_ids: Sequence[int]) -> list[int]:
    analysts = _analysts(session)
    for aid in analyst_ids:
        if aid not in analysts or not analysts[aid].active:
            raise InvalidInput(f"Unknown or inactive colleague id {aid}.")
    return list(dict.fromkeys(analyst_ids))


# ---------- roster ----------

def list_analysts(session: Session) -> list[Analyst]:
    return list(session.exec(select(Analyst).order_by(Analyst.name)).all())


def _email_taken(session: Session, email: str, exclude_id: int | None = None) -> bool:
    found = session.exec(select(Analyst).where(Analyst.email == email)).first()
    return found is not None and found.id != exclude_id


def create_analyst(session: Session, data: AnalystIn) -> Analyst:
    email = data.email.strip().lower()
    if _email_taken(session, email):
        raise InvalidInput(f"{email} is already on the roster.")
    analyst = Analyst(name=data.name.strip(), email=email, aliases=[a.strip() for a in data.aliases if a.strip()],
                      active=data.active)
    session.add(analyst)
    session.commit()
    session.refresh(analyst)
    return analyst


def update_analyst(session: Session, analyst_id: int, data: AnalystUpdate) -> Analyst:
    analyst = session.get(Analyst, analyst_id)
    if analyst is None:
        raise NotFound("Colleague not found.")
    fields = data.model_fields_set
    if "name" in fields and data.name:
        analyst.name = data.name.strip()
    if "email" in fields and data.email:
        email = data.email.strip().lower()
        if _email_taken(session, email, analyst_id):
            raise InvalidInput(f"{email} is already on the roster.")
        analyst.email = email
    if "aliases" in fields and data.aliases is not None:
        analyst.aliases = [a.strip() for a in data.aliases if a.strip()]
    if "active" in fields and data.active is not None:
        analyst.active = data.active
    session.add(analyst)
    session.commit()
    session.refresh(analyst)
    return analyst


def delete_analyst(session: Session, analyst_id: int) -> None:
    analyst = session.get(Analyst, analyst_id)
    if analyst is None:
        raise NotFound("Colleague not found.")
    used = session.exec(select(MeetingAttendee).where(MeetingAttendee.analyst_id == analyst_id)).first()
    synced = session.exec(select(SyncRecord).where(SyncRecord.analyst_id == analyst_id)).first()
    if used or synced:
        raise Conflict("This colleague is on meetings. Mark them inactive instead.")
    session.delete(analyst)
    session.commit()


def seed_roster(session: Session, path: Path) -> int:
    added = 0
    for item in json.loads(Path(path).read_text()):
        email = item["email"].strip().lower()
        if not _email_taken(session, email):
            session.add(Analyst(name=item["name"], email=email, aliases=list(item.get("aliases", []))))
            added += 1
    session.commit()
    return added


# ---------- conferences ----------

def get_conference(session: Session, conference_id: int) -> Conference:
    conference = session.get(Conference, conference_id)
    if conference is None:
        raise NotFound("Conference not found.")
    return conference


def create_conference(session: Session, result: ExtractionResult, *, pdf_filename: str, pdf_path: str,
                      extractor: str, default_attendee_ids: Sequence[int] = (), default_minutes: int = 45) -> Conference:
    defaults = _active_ids(session, default_attendee_ids)
    conference = Conference(
        name=result.conference_name or Path(pdf_filename).stem, broker=result.broker or "",
        hotel=result.hotel or "", city=result.city or "", timezone=valid_timezone(result.timezone),
        schedule_for=result.schedule_for or "", pdf_filename=pdf_filename, pdf_path=pdf_path, extractor=extractor,
    )
    session.add(conference)
    session.flush()
    for draft in build_meetings(result, _roster(session), defaults, default_minutes):
        meeting = Meeting(
            conference_id=conference.id, date=draft.date, start_time=draft.start_time, end_time=draft.end_time,
            end_assumed=draft.end_assumed, room=draft.room, company=draft.company, ticker=draft.ticker,
            format=draft.format, company_attendees=draft.company_attendees,
            raw_attendee_names=draft.raw_attendee_names, notes=draft.notes, source_page=draft.source_page,
        )
        session.add(meeting)
        session.flush()
        for analyst_id, kind in draft.attendees:
            session.add(MeetingAttendee(meeting_id=meeting.id, analyst_id=analyst_id, match=kind))
    session.commit()
    session.refresh(conference)
    return conference


def update_conference(session: Session, conference_id: int, data: ConferenceUpdate) -> Conference:
    conference = get_conference(session, conference_id)
    fields = data.model_fields_set
    for name in ("name", "broker", "hotel", "city"):
        if name in fields and getattr(data, name) is not None:
            setattr(conference, name, getattr(data, name).strip())
    if "timezone" in fields:
        if data.timezone is None or not data.timezone.strip():
            conference.timezone = None
        elif valid_timezone(data.timezone.strip()) is None:
            raise InvalidInput(f"Unknown timezone {data.timezone!r}. Use an IANA name like America/New_York.")
        else:
            conference.timezone = data.timezone.strip()
    session.add(conference)
    session.commit()
    _enforce_status(session, conference)
    session.refresh(conference)
    return conference


def delete_conference(session: Session, conference_id: int) -> str:
    conference = get_conference(session, conference_id)
    meeting_ids = [m.id for m in _meetings(session, conference_id)]
    if meeting_ids:
        session.execute(delete(SyncRecord).where(SyncRecord.meeting_id.in_(meeting_ids)))
        session.execute(delete(MeetingAttendee).where(MeetingAttendee.meeting_id.in_(meeting_ids)))
        session.execute(delete(Meeting).where(Meeting.id.in_(meeting_ids)))
    pdf_path = conference.pdf_path
    session.delete(conference)
    session.commit()
    return pdf_path


# ---------- meetings ----------

def get_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if meeting is None:
        raise NotFound("Meeting not found.")
    return meeting


def _set_attendees(session: Session, meeting: Meeting, analyst_ids: Sequence[int]) -> None:
    wanted = _active_ids(session, analyst_ids)
    existing = {row.analyst_id: row for row in
                session.exec(select(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting.id)).all()}
    for aid, row in existing.items():
        if aid not in wanted:
            session.delete(row)
    for aid in wanted:
        if aid not in existing:
            session.add(MeetingAttendee(meeting_id=meeting.id, analyst_id=aid, match="manual"))


def add_meeting(session: Session, conference_id: int, data: MeetingCreate, default_minutes: int) -> Meeting:
    get_conference(session, conference_id)
    start, end = _strict_time(data.start), _strict_time(data.end)
    end_assumed = False
    if start and not end:
        end, end_assumed = add_minutes(start, default_minutes), True
    meeting = Meeting(conference_id=conference_id, date=_strict_date(data.date), start_time=start, end_time=end,
                      end_assumed=end_assumed, room=data.room.strip(), company=data.company.strip(),
                      ticker=(data.ticker or "").strip() or None, format=data.format, notes=data.notes.strip())
    session.add(meeting)
    session.flush()
    _set_attendees(session, meeting, data.attendee_ids)
    session.commit()
    session.refresh(meeting)
    return meeting


def update_meeting(session: Session, meeting_id: int, data: MeetingUpdate, default_minutes: int) -> Meeting:
    meeting = get_meeting(session, meeting_id)
    if meeting.status == "cancelled":
        raise Conflict("This meeting was cancelled and can't be edited.")
    fields = data.model_fields_set
    if "date" in fields:
        meeting.date = _strict_date(data.date)
    if "start" in fields:
        meeting.start_time = _strict_time(data.start)
    if "end" in fields:
        meeting.end_time = _strict_time(data.end)
        meeting.end_assumed = False
    elif "start" in fields and meeting.end_assumed and meeting.start_time:
        meeting.end_time = add_minutes(meeting.start_time, default_minutes)
    if "company" in fields:
        if not (data.company or "").strip():
            raise InvalidInput("Company can't be empty.")
        meeting.company = data.company.strip()
    if "room" in fields:
        meeting.room = (data.room or "").strip()
    if "ticker" in fields:
        meeting.ticker = (data.ticker or "").strip() or None
    if "format" in fields and data.format:
        meeting.format = data.format
    if "notes" in fields:
        meeting.notes = (data.notes or "").strip()
    if "company_attendees" in fields:
        meeting.company_attendees = [s.strip() for s in (data.company_attendees or []) if s.strip()]
    if "ignored_names" in fields:
        meeting.ignored_names = [s.strip() for s in (data.ignored_names or []) if s.strip()]
    if "attendee_ids" in fields:
        _set_attendees(session, meeting, data.attendee_ids or [])
    meeting.updated_at = utcnow()
    session.add(meeting)
    session.commit()
    _enforce_status(session, get_conference(session, meeting.conference_id))
    session.refresh(meeting)
    return meeting


def confirm_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = get_meeting(session, meeting_id)
    if meeting.status == "cancelled":
        raise Conflict("This meeting was cancelled.")
    conference = get_conference(session, meeting.conference_id)
    flags, _ = _flags(session, conference, _meetings(session, conference.id))
    if has_block(flags[meeting.id]):
        raise Conflict("Fix the problems on this meeting before verifying it.",
                       [f for f in flags[meeting.id] if f.severity == "block"])
    meeting.status = "confirmed"
    meeting.updated_at = utcnow()
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def unconfirm_meeting(session: Session, meeting_id: int) -> Meeting:
    meeting = get_meeting(session, meeting_id)
    if meeting.status == "cancelled":
        raise Conflict("This meeting was cancelled.")
    meeting.status = "draft"
    meeting.updated_at = utcnow()
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def confirm_ready(session: Session, conference_id: int, meeting_ids: Sequence[int] | None = None) -> int:
    conference = get_conference(session, conference_id)
    meetings = _meetings(session, conference_id)
    flags, _ = _flags(session, conference, meetings)
    wanted = set(meeting_ids) if meeting_ids is not None else None
    count = 0
    for m in meetings:
        if m.status == "draft" and not has_block(flags[m.id]) and (wanted is None or m.id in wanted):
            m.status = "confirmed"
            m.updated_at = utcnow()
            session.add(m)
            count += 1
    session.commit()
    return count


def delete_meeting(session: Session, meeting_id: int) -> str:
    meeting = get_meeting(session, meeting_id)
    records = session.exec(select(SyncRecord).where(SyncRecord.meeting_id == meeting_id)).all()
    if any(r.external_id and r.state != "cancelled" for r in records):
        meeting.status = "cancelled"
        meeting.updated_at = utcnow()
        session.add(meeting)
        session.commit()
        return "cancelled"
    session.execute(delete(SyncRecord).where(SyncRecord.meeting_id == meeting_id))
    session.execute(delete(MeetingAttendee).where(MeetingAttendee.meeting_id == meeting_id))
    session.delete(meeting)
    session.commit()
    return "deleted"


# ---------- sync ----------

def plan_conference(session: Session, conference_id: int, sink_name: str) -> list[SyncAction]:
    conference = get_conference(session, conference_id)
    meetings = _meetings(session, conference_id)
    flags, att = _flags(session, conference, meetings)
    eligible = [m for m in meetings if not (m.status == "confirmed" and has_block(flags[m.id]))]
    attendee_ids = {mid: [aid for aid, _ in rows] for mid, rows in att.items()}
    records = _records(session, [m.id for m in meetings], sink_name)
    return plan_sync(conference, eligible, attendee_ids, _analysts(session), records)


def _record_outcome(session: Session, sink_name: str, outcome: SyncOutcome) -> None:
    a = outcome.action
    rec = session.exec(select(SyncRecord).where(SyncRecord.meeting_id == a.meeting_id,
                                                SyncRecord.analyst_id == a.analyst_id,
                                                SyncRecord.sink == sink_name)).first()
    if rec is None:
        rec = SyncRecord(meeting_id=a.meeting_id, analyst_id=a.analyst_id, sink=sink_name)
    if outcome.ok:
        rec.external_id = outcome.external_id or rec.external_id
        rec.sequence = a.sequence
        rec.last_error = None
        if a.kind == "cancel":
            rec.state = "cancelled"
        else:
            rec.state = "active"
            rec.content_hash = a.content.content_hash()
            rec.content_json = a.content.to_json()
    else:
        rec.state = "failed"
        rec.last_error = outcome.error or "Unknown error"
    rec.updated_at = utcnow()
    session.add(rec)


def send_conference(session: Session, conference_id: int, sink) -> list[SyncOutcome]:
    conference = get_conference(session, conference_id)
    actions = plan_conference(session, conference_id, sink.name)
    outcomes = sink.apply(conference, actions) if actions else []
    for outcome in outcomes:
        _record_outcome(session, sink.name, outcome)
    session.commit()
    return outcomes


def ics_records_for(session: Session, conference_id: int, analyst_id: int) -> list[SyncRecord]:
    meeting_ids = [m.id for m in _meetings(session, conference_id)]
    return [r for r in _records(session, meeting_ids, "ics") if r.analyst_id == analyst_id]


def send_result(session: Session, conference_id: int, sink_name: str, items, dry_run: bool) -> SendResult:
    analysts = _analysts(session)
    rows: list[SyncActionOut] = []
    summary: dict[int, AnalystSendSummary] = {}
    for item in items:
        action, ok, error = (item, None, None) if isinstance(item, SyncAction) else (item.action, item.ok, item.error)
        rows.append(SyncActionOut(kind=action.kind, meeting_id=action.meeting_id, analyst_id=action.analyst_id,
                                  analyst_name=action.analyst_name,
                                  subject=action.content.subject if action.content else None, ok=ok, error=error))
        s = summary.setdefault(action.analyst_id, AnalystSendSummary(analyst_id=action.analyst_id,
                                                                     name=analysts[action.analyst_id].name))
        setattr(s, action.kind, getattr(s, action.kind) + 1)
        if ok is False:
            s.failed += 1
    result = SendResult(sink=sink_name, dry_run=dry_run, actions=rows,
                        by_analyst=sorted(summary.values(), key=lambda s: s.name),
                        ok_count=sum(1 for r in rows if r.ok), failed_count=sum(1 for r in rows if r.ok is False))
    if sink_name == "ics" and not dry_run:
        for s in result.by_analyst:
            s.download_url = f"/api/conferences/{conference_id}/ics/{s.analyst_id}"
        result.zip_url = f"/api/conferences/{conference_id}/ics.zip"
    return result


# ---------- read models ----------

def _sync_state(conference, meeting, analyst_id, attendee_ids, analysts, rec) -> tuple[str, str | None]:
    if rec is None:
        return "not_sent", None
    if rec.state == "failed":
        return "failed", rec.last_error
    if rec.external_id is None:
        return "not_sent", None
    if rec.state == "cancelled":
        return ("not_sent", None) if meeting.status == "confirmed" else ("cancelled", None)
    if meeting.status == "confirmed":
        others = [analysts[x].name for x in attendee_ids if x != analyst_id]
        try:
            current = build_event(conference, meeting, others).content_hash()
        except ValueError:
            return "changed", None
        if current != rec.content_hash:
            return "changed", None
    return "sent", None


def _unmatched(meeting: Meeting, attendee_ids: set[int], roster: list[RosterEntry]) -> list[str]:
    ignored = {normalize_name(n) for n in meeting.ignored_names}
    out = []
    for raw in meeting.raw_attendee_names:
        if normalize_name(raw) in ignored:
            continue
        match = match_name(raw, roster)
        if match.analyst_id is None or match.analyst_id not in attendee_ids:
            out.append(raw)
    return out


def conference_detail(session: Session, conference_id: int, sink_name: str, skipped_items: int = 0) -> ConferenceDetail:
    conference = get_conference(session, conference_id)
    meetings = sorted(_meetings(session, conference_id), key=_sort_key)
    flags, att = _flags(session, conference, meetings)
    analysts = _analysts(session)
    roster = roster_entries(analysts.values())
    records = _records(session, [m.id for m in meetings], sink_name)
    rec_by = {(r.meeting_id, r.analyst_id): r for r in records}

    out: list[MeetingOut] = []
    for m in meetings:
        ids = [aid for aid, _ in att[m.id]]
        attendees = []
        for aid, kind in att[m.id]:
            sync, err = _sync_state(conference, m, aid, ids, analysts, rec_by.get((m.id, aid)))
            a = analysts[aid]
            attendees.append(AttendeeOut(analyst_id=aid, name=a.name, email=a.email, match=kind, sync=sync, sync_error=err))
        removed = [AttendeeOut(analyst_id=r.analyst_id, name=analysts[r.analyst_id].name,
                               email=analysts[r.analyst_id].email, match="removed",
                               sync="failed" if r.state == "failed" else "sent", sync_error=r.last_error)
                   for r in records if r.meeting_id == m.id and r.analyst_id not in ids
                   and r.external_id and r.state != "cancelled"]
        meeting_flags = flags[m.id]
        if m.status == "cancelled":
            state = "cancelled"
        elif m.status == "draft":
            state = "needs_attention" if has_block(meeting_flags) else "ready"
        else:
            all_sent = bool(attendees) and all(a.sync == "sent" for a in attendees) and not removed
            state = "sent" if all_sent else "verified"
        out.append(MeetingOut(
            id=m.id, conference_id=m.conference_id, date=m.date.isoformat() if m.date else None,
            start=_hhmm(m.start_time), end=_hhmm(m.end_time), end_assumed=m.end_assumed, room=m.room,
            company=m.company, ticker=m.ticker, format=m.format, company_attendees=list(m.company_attendees),
            raw_attendee_names=list(m.raw_attendee_names), ignored_names=list(m.ignored_names),
            unmatched_names=_unmatched(m, set(ids), roster), notes=m.notes, source_page=m.source_page,
            status=m.status, review_state=state, attendees=attendees, removed=removed,
            flags=[FlagOut(code=f.code, severity=f.severity, message=f.message) for f in meeting_flags],
        ))

    live = [o for o in out if o.review_state != "cancelled"]
    counts = Counts(
        total=len(live),
        needs_attention=sum(o.review_state == "needs_attention" for o in live),
        ready=sum(o.review_state == "ready" for o in live),
        verified=sum(o.review_state == "verified" for o in live),
        sent=sum(o.review_state == "sent" for o in live),
        cancelled=len(out) - len(live),
        warnings=sum(any(f.severity == "warn" for f in o.flags) for o in live),
        changed=sum(any(a.sync == "changed" for a in o.attendees) for o in live),
        failed=sum(any(a.sync == "failed" for a in o.attendees + o.removed) for o in out),
        pending_actions=len(plan_conference(session, conference_id, sink_name)),
    )
    dates = [m.date for m in meetings if m.date]
    return ConferenceDetail(
        id=conference.id, name=conference.name, broker=conference.broker, hotel=conference.hotel,
        city=conference.city, timezone=conference.timezone, created_at=conference.created_at,
        first_date=min(dates).isoformat() if dates else None, last_date=max(dates).isoformat() if dates else None,
        counts=counts, schedule_for=conference.schedule_for, pdf_filename=conference.pdf_filename,
        extractor=conference.extractor, meetings=out, skipped_items=skipped_items,
    )


def list_conference_summaries(session: Session, sink_name: str) -> list[ConferenceSummary]:
    conferences = session.exec(select(Conference).order_by(Conference.created_at.desc(), Conference.id.desc())).all()
    summaries = []
    for c in conferences:
        d = conference_detail(session, c.id, sink_name)
        summaries.append(ConferenceSummary(**d.model_dump(include=set(ConferenceSummary.model_fields))))
    return summaries
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass. If `test_summaries` ordering fails because both conferences got the same `created_at`, the `Conference.id.desc()` tiebreak already handles it; do not add sleeps.

- [ ] **Step 6: Commit**

```bash
git add backend/mcs/schemas.py backend/mcs/service.py backend/tests/test_service.py
git commit -m "feat: service layer with verification rules and idempotent send

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 9: HTTP API and static frontend serving

**Files:**
- Create: `backend/mcs/api/__init__.py` (empty), `backend/mcs/api/app.py`, `backend/mcs/api/deps.py`, `backend/mcs/api/routes_system.py`, `backend/mcs/api/routes_conferences.py`, `backend/mcs/api/routes_meetings.py`, `backend/mcs/api/routes_roster.py`
- Modify: `backend/mcs/service.py` (add public `check_attendee_ids`)
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything in `mcs.service` and `mcs.schemas` (Task 8); `get_extractor`, `ExtractionError` (Tasks 2–3); `get_sink`, `SinkNotConfigured`, `GraphAuth`, `GraphAuthError`, `render_ics`, `analyst_slug`, `zip_files` (Tasks 6–7); `Settings`, `get_settings`, `make_engine` (Task 1).
- Produces:
  - `mcs.api.app.create_app(settings: Settings | None = None, *, extractor_factory: Callable[[], Extractor] | None = None, sink_factory: Callable[[], CalendarSink] | None = None, graph_auth: GraphAuth | None = None) -> FastAPI`. `app.state` holds `settings`, `engine`, `extractor_factory`, `sink_factory`, `graph_auth`.
  - `mcs.service.check_attendee_ids(session, ids: Sequence[int]) -> list[int]` (raises `InvalidInput`)
  - The HTTP contract from spec §8, with these response shapes (the frontend relies on them):
    - `GET /api/health` → `{"ok": true}`
    - `GET /api/config` → `{"extractor": str, "model": str, "calendar_sink": "ics"|"graph", "ephemeral": bool, "graph": {configured, signed_in, pending, account, error}}`
    - `POST /api/conferences` (multipart: `file`, optional form `default_attendee_ids` = `"1,3"`) → 201 `ConferenceDetail`
    - `GET /api/conferences` → `ConferenceSummary[]`; `GET /api/conferences/{id}` → `ConferenceDetail`
    - `PATCH /api/conferences/{id}` (`ConferenceUpdate`) → `ConferenceDetail`; `DELETE /api/conferences/{id}` → 204
    - `GET /api/conferences/{id}/pdf` → the PDF, inline
    - `POST /api/conferences/{id}/meetings` (`MeetingCreate`) → 201 `ConferenceDetail`
    - `POST /api/conferences/{id}/confirm-ready` (optional `ConfirmReadyIn`) → `ConferenceDetail`
    - `POST /api/conferences/{id}/send?dry_run=true|false` → `SendResult`
    - `GET /api/conferences/{id}/ics/{analyst_id}` → `text/calendar` attachment; `GET /api/conferences/{id}/ics.zip` → `application/zip` attachment
    - `PATCH /api/meetings/{id}` (`MeetingUpdate`), `POST /api/meetings/{id}/confirm`, `POST /api/meetings/{id}/unconfirm`, `DELETE /api/meetings/{id}` → each returns the parent `ConferenceDetail`
    - `GET /api/roster` → `AnalystOut[]`; `POST /api/roster` (`AnalystIn`) → 201 `AnalystOut`; `PATCH /api/roster/{id}` (`AnalystUpdate`) → `AnalystOut`; `DELETE /api/roster/{id}` → 204
    - `POST /api/graph/login` → `{user_code, verification_uri, message, expires_in}`; `GET /api/graph/status` → status dict
    - Errors: `NotFound` → 404, `InvalidInput` → 400, `Conflict` → 409 `{"detail", "flags"}`, `ExtractionError` → 502, `SinkNotConfigured` → 400, `GraphAuthError` → 401. Every error body has `detail`.
    - Any non-`/api` GET serves `frontend_dist/index.html` (SPA fallback) or the matching file when the build exists.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_api.py`:

```python
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlmodel import Session

from mcs import service
from mcs.api.app import create_app
from mcs.config import REPO_ROOT

SAMPLES = REPO_ROOT / "samples"
PDF_A = (SAMPLES / "broker_a_grid.pdf").read_bytes()


@pytest.fixture
def app(settings, tmp_path):
    settings.frontend_dist = tmp_path / "no-dist"
    application = create_app(settings)
    with Session(application.state.engine) as s:
        service.seed_roster(s, SAMPLES / "roster.sample.json")
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def upload(client, data=PDF_A, name="broker_a_grid.pdf", **form):
    return client.post("/api/conferences", files={"file": (name, data, "application/pdf")}, data=form)


def people(client):
    return {a["name"]: a["id"] for a in client.get("/api/roster").json()}


def company(detail, name):
    return next(m for m in detail["meetings"] if m["company"] == name)


def test_health_and_config(client):
    assert client.get("/api/health").json() == {"ok": True}
    cfg = client.get("/api/config").json()
    assert (cfg["extractor"], cfg["calendar_sink"], cfg["ephemeral"]) == ("fake", "ics", False)
    assert cfg["graph"]["configured"] is False


def test_upload_review_and_pdf(client, settings):
    r = upload(client, default_attendee_ids="")
    assert r.status_code == 201, r.text
    d = r.json()
    assert len(d["meetings"]) == 12 and d["skipped_items"] == 0 and d["extractor"] == "fake"
    pdf = client.get(f"/api/conferences/{d['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(list(settings.uploads_dir.glob("*.pdf"))) == 1
    assert [c["name"] for c in client.get("/api/conferences").json()] == ["Industrials Conference 2026"]


@pytest.mark.parametrize("data,name,match", [
    (b"", "a.pdf", "empty"),
    (b"hello, not a pdf", "a.pdf", "PDF"),
    (PDF_A, "a.txt", "PDF"),
])
def test_bad_uploads_store_nothing(client, settings, data, name, match):
    r = upload(client, data=data, name=name)
    assert r.status_code == 400 and match in r.json()["detail"]
    assert list(settings.uploads_dir.glob("*")) == []
    assert client.get("/api/conferences").json() == []


def test_oversized_upload(client, settings):
    settings.max_upload_mb = 1
    r = upload(client, data=b"%PDF" + b"0" * (1024 * 1024))
    assert r.status_code == 400 and "larger than 1 MB" in r.json()["detail"]
    assert list(settings.uploads_dir.glob("*")) == []


def test_extraction_failure_is_502_and_stores_nothing(client, settings):
    r = upload(client, data=b"%PDF-1.4 unknown")
    assert r.status_code == 502 and "sample PDFs" in r.json()["detail"]
    assert list(settings.uploads_dir.glob("*")) == []


@pytest.mark.parametrize("ids", ["abc", "999"])
def test_bad_default_attendees(client, ids):
    assert upload(client, default_attendee_ids=ids).status_code == 400


def test_default_attendees_are_applied(client):
    d = upload(client, default_attendee_ids=str(people(client)["Morgan Diaz"])).json()
    assert all("Morgan Diaz" in [a["name"] for a in m["attendees"]] for m in d["meetings"])


def test_review_verify_send_and_download(client):
    d = upload(client).json()
    cid = d["id"]
    tide = company(d, "Tidewater Pumps")
    r = client.post(f"/api/meetings/{tide['id']}/confirm")
    assert r.status_code == 409 and {"no_attendee"} <= {f["code"] for f in r.json()["flags"]}
    d = client.patch(f"/api/meetings/{tide['id']}", json={"attendee_ids": [people(client)["Jordan Lee"]],
                                                          "ignored_names": ["Chris Wong"]}).json()
    assert company(d, "Tidewater Pumps")["flags"] == []
    d = client.post(f"/api/conferences/{cid}/confirm-ready", json={}).json()
    assert d["counts"]["verified"] == 12
    preview = client.post(f"/api/conferences/{cid}/send?dry_run=true").json()
    assert preview["dry_run"] is True and {a["kind"] for a in preview["actions"]} == {"create"}
    done = client.post(f"/api/conferences/{cid}/send?dry_run=false").json()
    assert done["failed_count"] == 0 and done["ok_count"] == len(preview["actions"])
    avery = people(client)["Avery Kim"]
    ics = client.get(f"/api/conferences/{cid}/ics/{avery}")
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "attachment" in ics.headers["content-disposition"] and "avery-kim" in ics.headers["content-disposition"]
    assert len(Calendar.from_ical(ics.content).walk("VEVENT")) == 4  # Avery: NWRB, CBFL, KSVC, SMFI
    z = client.get(f"/api/conferences/{cid}/ics.zip")
    assert z.headers["content-type"] == "application/zip"
    assert "avery-kim.ics" in zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert client.get(f"/api/conferences/{cid}/send?dry_run=true").status_code == 405
    assert client.post(f"/api/conferences/{cid}/send?dry_run=true").json()["actions"] == []


def test_ics_for_unsent_colleague_is_404(client):
    cid = upload(client).json()["id"]
    assert client.get(f"/api/conferences/{cid}/ics/{people(client)['Avery Kim']}").status_code == 404
    assert client.get(f"/api/conferences/{cid}/ics.zip").status_code == 404


def test_conference_edit_add_delete_meeting(client, settings):
    cid = upload(client).json()["id"]
    assert client.patch(f"/api/conferences/{cid}", json={"timezone": "Eastern"}).status_code == 400
    d = client.patch(f"/api/conferences/{cid}", json={"timezone": "America/Chicago", "name": "Renamed"}).json()
    assert (d["timezone"], d["name"]) == ("America/Chicago", "Renamed")
    r = client.post(f"/api/conferences/{cid}/meetings", json={"company": "Atlas Rail Systems", "date": "2026-11-10",
                                                              "start": "16:00"})
    assert r.status_code == 201 and company(r.json(), "Atlas Rail Systems")["end"] == "16:45"
    mid = company(r.json(), "Atlas Rail Systems")["id"]
    assert client.patch(f"/api/meetings/{mid}", json={"start": "nonsense"}).status_code == 400
    d = client.delete(f"/api/meetings/{mid}").json()
    assert all(m["company"] != "Atlas Rail Systems" for m in d["meetings"])
    assert client.delete(f"/api/conferences/{cid}").status_code == 204
    assert client.get(f"/api/conferences/{cid}").status_code == 404
    assert list(settings.uploads_dir.glob("*")) == []


def test_unconfirm(client):
    d = upload(client).json()
    mid = d["meetings"][0]["id"]
    client.post(f"/api/meetings/{mid}/confirm")
    d = client.post(f"/api/meetings/{mid}/unconfirm").json()
    assert d["meetings"][0]["status"] == "draft"


def test_roster_api(client):
    assert client.post("/api/roster", json={"name": "Dup", "email": "avery.kim@example.com"}).status_code == 400
    r = client.post("/api/roster", json={"name": "Casey Fox", "email": "Casey.Fox@example.com", "aliases": ["C. Fox"]})
    assert r.status_code == 201 and r.json()["email"] == "casey.fox@example.com"
    cid = r.json()["id"]
    assert client.patch(f"/api/roster/{cid}", json={"active": False}).json()["active"] is False
    assert client.delete(f"/api/roster/{cid}").status_code == 204
    upload(client)
    assert client.delete(f"/api/roster/{people(client)['Avery Kim']}").status_code == 409


def test_not_found_and_graph_errors(client):
    assert client.get("/api/conferences/999").status_code == 404
    assert client.patch("/api/meetings/999", json={"room": "x"}).status_code == 404
    r = client.post("/api/graph/login")
    assert r.status_code == 400 and "not configured" in r.json()["detail"]
    assert client.get("/api/graph/status").json()["configured"] is False


def test_send_with_unconfigured_graph(settings, tmp_path):
    settings.calendar_sink = "graph"
    settings.frontend_dist = tmp_path / "no-dist"
    with TestClient(create_app(settings)) as c:
        cid = upload(c).json()["id"]
        r = c.post(f"/api/conferences/{cid}/send?dry_run=false")
        assert r.status_code == 400 and "not configured" in r.json()["detail"]


def test_spa_fallback(settings, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    settings.frontend_dist = dist
    with TestClient(create_app(settings)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/conferences/1").text == "<html>app</html>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        r = c.get("/api/nope")
        assert r.status_code == 404 and "detail" in r.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest -q tests/test_api.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.api'`.

- [ ] **Step 3: Add `check_attendee_ids` to `backend/mcs/service.py`** (after `_active_ids`)

```python
def check_attendee_ids(session: Session, ids: Sequence[int]) -> list[int]:
    return _active_ids(session, ids)
```

- [ ] **Step 4: Implement `backend/mcs/api/deps.py`**

```python
from typing import Iterator

from fastapi import Request
from sqlmodel import Session

from mcs.config import Settings


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
```

- [ ] **Step 5: Implement the routers**

`backend/mcs/api/routes_system.py`:

```python
from fastapi import APIRouter, Request

from mcs.calendar import SinkNotConfigured

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/config")
def config(request: Request):
    s = request.app.state.settings
    return {"extractor": s.resolved_extractor(), "model": s.resolved_model(), "calendar_sink": s.calendar_sink,
            "ephemeral": s.ephemeral, "graph": request.app.state.graph_auth.status()}


@router.post("/graph/login")
def graph_login(request: Request):
    auth = request.app.state.graph_auth
    if not auth.configured:
        raise SinkNotConfigured("Microsoft Graph is not configured. Set MCS_GRAPH_CLIENT_ID and MCS_GRAPH_TENANT_ID.")
    return auth.start_device_flow()


@router.get("/graph/status")
def graph_status(request: Request):
    return request.app.state.graph_auth.status()
```

`backend/mcs/api/routes_conferences.py`:

```python
import re
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from mcs import service
from mcs.api.deps import get_app_settings, get_session
from mcs.calendar.graph_auth import GraphAuthError
from mcs.calendar.ics import analyst_slug, render_ics, zip_files
from mcs.config import Settings
from mcs.models import Analyst
from mcs.schemas import (
    ConferenceDetail, ConferenceSummary, ConferenceUpdate, ConfirmReadyIn, MeetingCreate, SendResult,
)

router = APIRouter(prefix="/api/conferences")


def _parse_ids(raw: str) -> list[int]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise service.InvalidInput("default_attendee_ids must be a comma-separated list of ids.") from None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "conference"


@router.post("", response_model=ConferenceDetail, status_code=201)
def upload(request: Request, file: UploadFile = File(...), default_attendee_ids: str = Form(""),
           session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if not data:
        raise service.InvalidInput("The file is empty.")
    if len(data) > limit:
        raise service.InvalidInput(f"The file is larger than {settings.max_upload_mb} MB.")
    name = Path(file.filename or "schedule.pdf").name
    if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
        raise service.InvalidInput("Upload a PDF file.")
    ids = service.check_attendee_ids(session, _parse_ids(default_attendee_ids))
    extractor = request.app.state.extractor_factory()
    with tempfile.TemporaryDirectory(prefix="mcs-upload-") as tmp:
        tmp_pdf = Path(tmp) / "upload.pdf"
        tmp_pdf.write_bytes(data)
        result = extractor.extract(tmp_pdf)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    stored = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
    stored.write_bytes(data)
    conference = service.create_conference(
        session, result, pdf_filename=name, pdf_path=str(stored), extractor=extractor.name,
        default_attendee_ids=ids, default_minutes=settings.default_meeting_minutes,
    )
    return service.conference_detail(session, conference.id, settings.calendar_sink, skipped_items=result.skipped_items)


@router.get("", response_model=list[ConferenceSummary])
def list_conferences(session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    return service.list_conference_summaries(session, settings.calendar_sink)


@router.get("/{conference_id}", response_model=ConferenceDetail)
def get_conference(conference_id: int, session: Session = Depends(get_session),
                   settings: Settings = Depends(get_app_settings)):
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.patch("/{conference_id}", response_model=ConferenceDetail)
def patch_conference(conference_id: int, body: ConferenceUpdate, session: Session = Depends(get_session),
                     settings: Settings = Depends(get_app_settings)):
    service.update_conference(session, conference_id, body)
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.delete("/{conference_id}", status_code=204)
def delete_conference(conference_id: int, session: Session = Depends(get_session),
                      settings: Settings = Depends(get_app_settings)):
    pdf_path = Path(service.delete_conference(session, conference_id)) if True else None
    uploads = settings.uploads_dir.resolve()
    if pdf_path and pdf_path.exists() and uploads in pdf_path.resolve().parents:
        pdf_path.unlink()
    return Response(status_code=204)


@router.get("/{conference_id}/pdf")
def get_pdf(conference_id: int, session: Session = Depends(get_session)):
    conference = service.get_conference(session, conference_id)
    path = Path(conference.pdf_path)
    if not path.is_file():
        raise service.NotFound("The uploaded PDF is no longer on disk.")
    return FileResponse(path, media_type="application/pdf", filename=conference.pdf_filename,
                        content_disposition_type="inline")


@router.post("/{conference_id}/meetings", response_model=ConferenceDetail, status_code=201)
def add_meeting(conference_id: int, body: MeetingCreate, session: Session = Depends(get_session),
                settings: Settings = Depends(get_app_settings)):
    service.add_meeting(session, conference_id, body, settings.default_meeting_minutes)
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.post("/{conference_id}/confirm-ready", response_model=ConferenceDetail)
def confirm_ready(conference_id: int, body: ConfirmReadyIn | None = None, session: Session = Depends(get_session),
                  settings: Settings = Depends(get_app_settings)):
    service.confirm_ready(session, conference_id, body.meeting_ids if body else None)
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.post("/{conference_id}/send", response_model=SendResult)
def send(conference_id: int, request: Request, dry_run: bool = True, session: Session = Depends(get_session),
         settings: Settings = Depends(get_app_settings)):
    if dry_run:
        plan = service.plan_conference(session, conference_id, settings.calendar_sink)
        return service.send_result(session, conference_id, settings.calendar_sink, plan, dry_run=True)
    sink = request.app.state.sink_factory()
    if sink.name == "graph" and not request.app.state.graph_auth.status()["signed_in"]:
        raise GraphAuthError("Sign in to Microsoft first.")
    outcomes = service.send_conference(session, conference_id, sink)
    return service.send_result(session, conference_id, sink.name, outcomes, dry_run=False)


@router.get("/{conference_id}/ics.zip")
def ics_zip(conference_id: int, session: Session = Depends(get_session)):
    conference = service.get_conference(session, conference_id)
    files = {}
    for analyst in service.list_analysts(session):
        records = service.ics_records_for(session, conference_id, analyst.id)
        if records:
            files[f"{analyst_slug(analyst.name)}.ics"] = render_ics(records)
    if not files:
        raise service.NotFound("Nothing has been sent yet.")
    return Response(zip_files(files), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{_slug(conference.name)}-calendars.zip"'})


@router.get("/{conference_id}/ics/{analyst_id}")
def ics_one(conference_id: int, analyst_id: int, session: Session = Depends(get_session)):
    conference = service.get_conference(session, conference_id)
    analyst = session.get(Analyst, analyst_id)
    if analyst is None:
        raise service.NotFound("Colleague not found.")
    records = service.ics_records_for(session, conference_id, analyst_id)
    if not records:
        raise service.NotFound("Nothing has been sent to this colleague yet.")
    filename = f"{analyst_slug(analyst.name)}-{_slug(conference.name)}.ics"
    return Response(render_ics(records), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

Clean-up note for the implementer: in `delete_conference`, write `pdf_path = Path(service.delete_conference(session, conference_id))` (drop the leftover `if True else None`).

`backend/mcs/api/routes_meetings.py`:

```python
from fastapi import APIRouter, Depends
from sqlmodel import Session

from mcs import service
from mcs.api.deps import get_app_settings, get_session
from mcs.config import Settings
from mcs.schemas import ConferenceDetail, MeetingUpdate

router = APIRouter(prefix="/api/meetings")


def _detail(session: Session, conference_id: int, settings: Settings) -> ConferenceDetail:
    return service.conference_detail(session, conference_id, settings.calendar_sink)


@router.patch("/{meeting_id}", response_model=ConferenceDetail)
def patch_meeting(meeting_id: int, body: MeetingUpdate, session: Session = Depends(get_session),
                  settings: Settings = Depends(get_app_settings)):
    meeting = service.update_meeting(session, meeting_id, body, settings.default_meeting_minutes)
    return _detail(session, meeting.conference_id, settings)


@router.post("/{meeting_id}/confirm", response_model=ConferenceDetail)
def confirm(meeting_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    meeting = service.confirm_meeting(session, meeting_id)
    return _detail(session, meeting.conference_id, settings)


@router.post("/{meeting_id}/unconfirm", response_model=ConferenceDetail)
def unconfirm(meeting_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    meeting = service.unconfirm_meeting(session, meeting_id)
    return _detail(session, meeting.conference_id, settings)


@router.delete("/{meeting_id}", response_model=ConferenceDetail)
def delete(meeting_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_app_settings)):
    conference_id = service.get_meeting(session, meeting_id).conference_id
    service.delete_meeting(session, meeting_id)
    return _detail(session, conference_id, settings)
```

`backend/mcs/api/routes_roster.py`:

```python
from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from mcs import service
from mcs.api.deps import get_session
from mcs.schemas import AnalystIn, AnalystOut, AnalystUpdate

router = APIRouter(prefix="/api/roster")


@router.get("", response_model=list[AnalystOut])
def list_roster(session: Session = Depends(get_session)):
    return service.list_analysts(session)


@router.post("", response_model=AnalystOut, status_code=201)
def create(body: AnalystIn, session: Session = Depends(get_session)):
    return service.create_analyst(session, body)


@router.patch("/{analyst_id}", response_model=AnalystOut)
def update(analyst_id: int, body: AnalystUpdate, session: Session = Depends(get_session)):
    return service.update_analyst(session, analyst_id, body)


@router.delete("/{analyst_id}", status_code=204)
def remove(analyst_id: int, session: Session = Depends(get_session)):
    service.delete_analyst(session, analyst_id)
    return Response(status_code=204)
```

- [ ] **Step 6: Implement `backend/mcs/api/app.py`**

```python
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mcs import service
from mcs.api import routes_conferences, routes_meetings, routes_roster, routes_system
from mcs.calendar import SinkNotConfigured, get_sink
from mcs.calendar.graph_auth import GraphAuth, GraphAuthError
from mcs.config import Settings, get_settings
from mcs.db import make_engine
from mcs.extraction import ExtractionError, get_extractor


def _error(status: int, detail: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, **extra})


def create_app(settings: Settings | None = None, *, extractor_factory: Callable | None = None,
               sink_factory: Callable | None = None, graph_auth: GraphAuth | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Meeting Calendar Sync")
    app.state.settings = settings
    app.state.engine = make_engine(settings)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    app.state.graph_auth = graph_auth or GraphAuth(settings.graph_client_id, settings.graph_tenant_id)
    app.state.extractor_factory = extractor_factory or (lambda: get_extractor(settings))
    app.state.sink_factory = sink_factory or (lambda: get_sink(settings, app.state.graph_auth))

    app.add_exception_handler(service.NotFound, lambda r, e: _error(404, str(e)))
    app.add_exception_handler(service.InvalidInput, lambda r, e: _error(400, str(e)))
    app.add_exception_handler(service.Conflict,
                              lambda r, e: _error(409, str(e), flags=[f.model_dump() for f in e.flags]))
    app.add_exception_handler(ExtractionError, lambda r, e: _error(502, str(e)))
    app.add_exception_handler(SinkNotConfigured, lambda r, e: _error(400, str(e)))
    app.add_exception_handler(GraphAuthError, lambda r, e: _error(401, str(e)))

    for router in (routes_system.router, routes_conferences.router, routes_meetings.router, routes_roster.router):
        app.include_router(router)

    dist = settings.frontend_dist
    if (dist / "index.html").is_file():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        root = dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request):
            if path.startswith("api/") or path == "api":
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass. (FastAPI's default handler renders `HTTPException` as `{"detail": ...}`, which `test_spa_fallback` relies on.)

- [ ] **Step 8: Commit**

```bash
git add backend/mcs/api backend/mcs/service.py backend/tests/test_api.py
git commit -m "feat: HTTP API with upload validation, ICS downloads and SPA serving

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: Frontend foundation — Woodline theme, shell, API client, helpers, Conferences and Roster pages

**Before writing any UI code, read:** `PRODUCT.md`; spec §9; the direction contract `.impeccable/surfaces/frontend-src-pages-reviewpage-tsx.md`; the chosen sketch `.impeccable/mocks/decision/assigned.html` (open it in a browser); and the craft floor `/Users/xienanzheng/.claude/skills/impeccable/reference/craft-floor.md`. The sketch fixes the arrangement, palette, type and density. The craft floor overrides two details in the sketch:
- the selected row gets a tinted background, not a coloured left border;
- status icons are drawn SVG (lucide), not Unicode glyphs.

**Files:**
- Create: `frontend/` (Vite React-TS scaffold), `frontend/vite.config.ts`, `frontend/src/styles.css`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/lib/format.ts`, `frontend/src/lib/review.ts`, `frontend/src/components/Shell.tsx`, `frontend/src/components/WoodlineMark.tsx`, `frontend/src/components/Stamp.tsx`, `frontend/src/components/Button.tsx`, `frontend/src/pages/ConferencesPage.tsx`, `frontend/src/pages/RosterPage.tsx`, `frontend/src/pages/ReviewPage.tsx` (placeholder that Task 11 replaces)
- Test: `frontend/src/lib/format.test.ts`, `frontend/src/lib/review.test.ts`

**Interfaces:**
- Consumes: the HTTP contract and response shapes from Task 9 (`ConferenceDetail`, `MeetingOut`, `Counts`, `SendResult`, `AnalystOut`, `/api/config` with `ephemeral`).
- Produces (Task 11 relies on these exact names):
  - `src/api.ts`: types `Flag`, `Attendee`, `Meeting`, `Counts`, `ConferenceSummary`, `ConferenceDetail`, `Analyst`, `SendAction`, `AnalystSendSummary`, `SendResult`, `GraphStatus`, `AppConfig`, `ReviewState`, `SyncState`; `class ApiError extends Error { status: number; detail: string; flags: Flag[] }`; functions `getConfig`, `listConferences`, `getConference(id)`, `uploadConference(file, defaultIds: number[])`, `patchConference(id, body)`, `deleteConference(id)`, `addMeeting(cid, body)`, `patchMeeting(id, body)`, `confirmMeeting(id)`, `unconfirmMeeting(id)`, `deleteMeeting(id)`, `confirmReady(cid, meetingIds?: number[])`, `sendPreview(cid)`, `sendNow(cid)`, `listRoster`, `createAnalyst(body)`, `updateAnalyst(id, body)`, `deleteAnalyst(id)`, `graphLogin()`, `graphStatus()`, `pdfUrl(cid, page?)`. All return parsed JSON (typed); non-2xx throws `ApiError`.
  - `src/lib/format.ts`: `formatTime12(hhmm: string | null): string`; `localHint(date: string | null, hhmm: string | null, hotelTz: string | null, viewerTz: string): string | null`; `dayHeading(isoDate: string | null): string`; `tzLabel(tz: string | null): string`; `dateRange(first: string | null, last: string | null): string`
  - `src/lib/review.ts`: `type Selection = { kind: "all" } | { kind: "colleague"; id: number } | { kind: "unmatched"; name: string }`; `type StatusFilter = "all" | "needs_attention" | "ready" | "verified" | "sent"`; `groupByDate(meetings)`; `colleaguesIn(detail)`; `unmatchedNames(detail)`; `filterMeetings(meetings, selection, status)`; `statusCounts(meetings)`; `stampFor(meeting)`; `sharedWith(meeting, selection)`; `sendLabel(counts)`
  - `src/components/Shell.tsx`: `<Shell context?: ReactNode actions?: ReactNode>` renders the navy top bar (mark + WOODLINE wordmark + "Meeting Calendar Sync" + context + nav + extractor/sink badges + actions) and the ephemeral banner; `src/components/Stamp.tsx`: `<Stamp meeting={Meeting} />`; `src/components/Button.tsx`: `<Button variant="primary" | "beige" | "quiet" | "danger" …>`
  - Routes: `/` Conferences, `/conferences/:id` Review, `/roster` Roster.

- [ ] **Step 1: Scaffold and install**

```bash
cd "<repo root>"
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router luxon lucide-react @fontsource-variable/figtree @fontsource-variable/manrope @fontsource/libre-baskerville
npm install -D tailwindcss @tailwindcss/vite vitest @types/luxon
rm -f src/App.css src/assets/react.svg public/vite.svg
```

`frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { environment: "node" },
});
```

Add the `"test": "vitest run"` script to `package.json`. Add `/// <reference types="vitest/config" />` at the top of `vite.config.ts` if TypeScript complains about `test`. Set `<title>Meeting Calendar Sync</title>` in `index.html`, and add the favicon: the Woodline mark as an inline SVG data URI (navy on transparent).

- [ ] **Step 2: Write the failing helper tests**

`frontend/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { dateRange, dayHeading, formatTime12, localHint, tzLabel } from "./format";

describe("formatTime12", () => {
  it.each([
    ["08:00", "8:00 AM"], ["13:30", "1:30 PM"], ["12:00", "12:00 PM"], ["00:15", "12:15 AM"], [null, "—"],
  ])("%s -> %s", (input, out) => expect(formatTime12(input)).toBe(out));
});

describe("localHint", () => {
  it("shows the viewer's time when zones differ", () => {
    expect(localHint("2026-11-10", "08:00", "America/New_York", "America/Los_Angeles")).toBe("5:00 AM PT");
  });
  it("marks a day shift", () => {
    expect(localHint("2026-11-17", "08:00", "Europe/London", "America/Los_Angeles")).toBe("12:00 AM PT");
    expect(localHint("2026-11-17", "02:00", "Europe/London", "America/Los_Angeles")).toBe("6:00 PM PT, day before");
  });
  it("is null when the offset is the same or data is missing", () => {
    expect(localHint("2026-11-10", "08:00", "America/New_York", "America/New_York")).toBeNull();
    expect(localHint("2026-11-10", "08:00", "America/New_York", "America/Toronto")).toBeNull();
    expect(localHint(null, "08:00", "America/New_York", "America/Los_Angeles")).toBeNull();
    expect(localHint("2026-11-10", "08:00", null, "America/Los_Angeles")).toBeNull();
  });
});

describe("dates", () => {
  it("formats headings and ranges", () => {
    expect(dayHeading("2026-11-10")).toBe("Tuesday, November 10");
    expect(dayHeading(null)).toBe("Date missing");
    expect(dateRange("2026-11-10", "2026-11-11")).toBe("Nov 10–11, 2026");
    expect(dateRange("2026-11-30", "2026-12-02")).toBe("Nov 30 – Dec 2, 2026");
    expect(dateRange("2026-11-10", "2026-11-10")).toBe("Nov 10, 2026");
    expect(dateRange(null, null)).toBe("Dates unknown");
  });
  it("labels timezones", () => {
    expect(tzLabel("America/New_York")).toBe("Eastern time");
    expect(tzLabel(null)).toBe("Timezone not set");
  });
});
```

The `PT` abbreviation comes from a fixed map: `America/Los_Angeles → PT`, `America/Denver → MT`, `America/Chicago → CT`, `America/New_York → ET`, `Europe/London → UK`, `Asia/Hong_Kong → HKT`, `Asia/Tokyo → JT`, `Asia/Singapore → SGT`. Any other zone falls back to luxon `toFormat("ZZZZ")`. `tzLabel` uses `Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "longGeneric" })`, lower-cases the trailing " Time", and falls back to the raw zone name.

`frontend/src/lib/review.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ConferenceDetail, Meeting } from "../api";
import { colleaguesIn, filterMeetings, groupByDate, sendLabel, sharedWith, stampFor, statusCounts, unmatchedNames } from "./review";

const att = (id: number, name: string, sync = "not_sent") =>
  ({ analyst_id: id, name, email: `${name.split(" ")[0].toLowerCase()}@example.com`, match: "exact", sync, sync_error: null });

function m(id: number, over: Partial<Meeting> = {}): Meeting {
  return {
    id, conference_id: 1, date: "2026-11-10", start: "09:00", end: "09:45", end_assumed: false, room: "Salon 4",
    company: `Co ${id}`, ticker: null, format: "one_on_one", company_attendees: [], raw_attendee_names: [],
    ignored_names: [], unmatched_names: [], notes: "", source_page: 1, status: "draft", review_state: "ready",
    attendees: [att(1, "Avery Kim")], removed: [], flags: [], ...over,
  } as Meeting;
}

const meetings = [
  m(1, { start: "10:00" }),
  m(2, { start: "08:00", attendees: [att(1, "Avery Kim"), att(3, "Jordan Lee")], review_state: "verified", status: "confirmed" }),
  m(3, { date: "2026-11-11", attendees: [], review_state: "needs_attention",
         flags: [{ code: "no_attendee", severity: "block", message: "x" }, { code: "unmatched_name", severity: "warn", message: "y" }],
         unmatched_names: ["Chris Wong"] }),
  m(4, { date: null, start: null, review_state: "needs_attention", flags: [{ code: "missing_date", severity: "block", message: "x" }] }),
  m(5, { review_state: "cancelled", status: "cancelled", start: "11:00" }),
  m(6, { start: "12:00", attendees: [att(3, "Jordan Lee", "sent")], review_state: "sent", status: "confirmed",
         flags: [{ code: "double_booked", severity: "warn", message: "z" }] }),
];
const detail = { meetings } as unknown as ConferenceDetail;

describe("groupByDate", () => {
  it("groups by date, missing date last, sorted by start", () => {
    const groups = groupByDate(meetings);
    expect(groups.map((g) => g.date)).toEqual(["2026-11-10", "2026-11-11", null]);
    expect(groups[0].meetings.map((x) => x.id)).toEqual([2, 1, 5, 6]);
  });
});

describe("colleagues and unmatched", () => {
  it("lists colleagues with counts and worst flag, ignoring cancelled meetings", () => {
    expect(colleaguesIn(detail)).toEqual([
      { id: 1, name: "Avery Kim", email: "avery@example.com", count: 3, worst: "block" },
      { id: 3, name: "Jordan Lee", email: "jordan@example.com", count: 2, worst: "warn" },
    ]);
  });
  it("aggregates unmatched names", () => {
    expect(unmatchedNames(detail)).toEqual([{ name: "Chris Wong", count: 1 }]);
  });
});

describe("filterMeetings and counts", () => {
  it("filters by colleague, unmatched name and status", () => {
    expect(filterMeetings(meetings, { kind: "colleague", id: 3 }, "all").map((x) => x.id)).toEqual([2, 6]);
    expect(filterMeetings(meetings, { kind: "unmatched", name: "Chris Wong" }, "all").map((x) => x.id)).toEqual([3]);
    expect(filterMeetings(meetings, { kind: "all" }, "needs_attention").map((x) => x.id)).toEqual([3, 4]);
    expect(filterMeetings(meetings, { kind: "all" }, "all").map((x) => x.id)).toContain(5);
  });
  it("counts statuses without cancelled", () => {
    expect(statusCounts(meetings)).toEqual({ all: 5, needs_attention: 2, ready: 1, verified: 1, sent: 1 });
  });
});

describe("stamps and labels", () => {
  it.each([
    [m(1), "DRAFT", "muted"],
    [m(4, { review_state: "needs_attention", flags: [{ code: "missing_date", severity: "block", message: "" }] }), "NEEDS DATE", "red"],
    [m(7, { review_state: "needs_attention", flags: [{ code: "missing_time", severity: "block", message: "" }] }), "NEEDS TIME", "red"],
    [m(8, { review_state: "needs_attention", flags: [{ code: "no_attendee", severity: "block", message: "" }] }), "NEEDS COLLEAGUE", "red"],
    [m(9, { review_state: "needs_attention", flags: [{ code: "no_timezone", severity: "block", message: "" }] }), "NEEDS TIMEZONE", "red"],
    [m(10, { review_state: "needs_attention", flags: [{ code: "end_before_start", severity: "block", message: "" }] }), "CHECK TIME", "red"],
    [m(11, { review_state: "verified" }), "VERIFIED", "navy"],
    [m(12, { review_state: "verified", attendees: [att(1, "Avery Kim", "changed")] }), "CHANGED — RESEND", "amber"],
    [m(13, { review_state: "verified", attendees: [att(1, "Avery Kim", "failed")] }), "FAILED", "red"],
    [m(14, { review_state: "sent" }), "SENT", "green"],
    [m(15, { review_state: "cancelled" }), "CANCELLED", "struck"],
  ])("stamp %#", (meeting, label, tone) => expect(stampFor(meeting as Meeting)).toEqual({ label, tone }));

  it("shared-with excludes the selected colleague", () => {
    expect(sharedWith(meetings[1], { kind: "colleague", id: 1 })).toEqual(["Jordan Lee"]);
    expect(sharedWith(meetings[1], { kind: "all" })).toEqual(["Avery Kim", "Jordan Lee"]);
  });

  it("send label", () => {
    expect(sendLabel({ pending_actions: 29 } as never)).toBe("Send 29 to calendars");
    expect(sendLabel({ pending_actions: 1 } as never)).toBe("Send 1 to calendars");
    expect(sendLabel({ pending_actions: 0 } as never)).toBe("Nothing to send");
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run`
Expected: FAIL — cannot resolve `./format` / `./review`.

- [ ] **Step 4: Implement `src/api.ts`, `src/lib/format.ts`, `src/lib/review.ts`**

`src/api.ts`: the types mirror `backend/mcs/schemas.py` field for field (snake_case kept). Core of the client:

```ts
export class ApiError extends Error {
  constructor(public status: number, public detail: string, public flags: Flag[] = []) { super(detail); }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.detail ?? `Request failed (${res.status})`, body.flags ?? []);
  return body as T;
}

export const uploadConference = (file: File, defaultIds: number[]) => {
  const form = new FormData();
  form.append("file", file);
  form.append("default_attendee_ids", defaultIds.join(","));
  return request<ConferenceDetail>("/api/conferences", { method: "POST", body: form });
};
export const pdfUrl = (cid: number, page?: number | null) => `/api/conferences/${cid}/pdf${page ? `#page=${page}` : ""}`;
export const sendPreview = (cid: number) => request<SendResult>(`/api/conferences/${cid}/send?dry_run=true`, { method: "POST" });
export const sendNow = (cid: number) => request<SendResult>(`/api/conferences/${cid}/send?dry_run=false`, { method: "POST" });
// …the remaining functions follow the same pattern, one line each, matching Task 9's routes.
```

`src/lib/format.ts` uses luxon `DateTime.fromISO(\`${date}T${hhmm}\`, { zone: hotelTz })`. It returns `null` when `viewer.offset === hotel.offset` at that instant. The day suffix is `", day before"` or `", next day"` when the calendar date differs.

`src/lib/review.ts` rules:
- `groupByDate`: dates ascending with `null` last; inside a group, sort by start (null last), then company.
- `colleaguesIn`: only non-cancelled meetings. `worst` is `"block"` if any of that colleague's meetings has a block flag, else `"warn"` if any warn flag, else `null`. Sorted by name.
- `unmatchedNames`: counts `unmatched_names` across non-cancelled meetings, sorted by name.
- `filterMeetings`:
  - Selection: `all` keeps everything (cancelled included, rendered struck); `colleague` keeps meetings whose `attendees` or `removed` contain the id; `unmatched` keeps meetings whose `unmatched_names` contains the name.
  - Status `all` keeps every review state; any other status keeps only that state.
- `statusCounts`: counts the non-cancelled meetings in its input. `all` = non-cancelled.
- `stampFor`: as in the test table. The first block flag picks the NEEDS label. `verified` with a failed attendee or removal → FAILED; with a changed attendee → CHANGED — RESEND.
- `sharedWith`: attendee names, excluding the selected colleague.
- `sendLabel`: as tested.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run`
Expected: PASS (both files).

- [ ] **Step 6: Theme, shell and shared components**

`src/styles.css`:

```css
@import "tailwindcss";
@import "@fontsource-variable/figtree";
@import "@fontsource-variable/manrope";
@import "@fontsource/libre-baskerville/400.css";

@theme {
  --color-navy: #182958;
  --color-navy-2: #283968;
  --color-blue: #475b90;
  --color-cream: #f9f7ed;
  --color-cream-2: #f2efdb;
  --color-beige: #e3deb0;
  --color-line: #e6e1c7;
  --color-ink: #1c2340;
  --color-muted: #5f6585;
  --color-red: #c42b3b;
  --color-red-bg: #fdf1f2;
  --color-green: #2f7d32;
  --color-amber: #8a5a12;
  --color-amber-bg: #fbf3e4;
  --font-sans: "Manrope Variable", ui-sans-serif, system-ui, sans-serif;
  --font-heading: "Figtree Variable", "Manrope Variable", ui-sans-serif, sans-serif;
  --font-wordmark: "Libre Baskerville", Georgia, serif;
}

html { background: var(--color-cream); color: var(--color-ink); font-family: var(--font-sans); }
::selection { background: var(--color-beige); color: var(--color-navy); }
:focus-visible { outline: 2px solid var(--color-navy); outline-offset: 2px; }
input, textarea, select { caret-color: var(--color-navy); }
* { scrollbar-color: #c9c4a8 transparent; }
.tabular { font-variant-numeric: tabular-nums; }
```

The text colours were chosen to pass the craft floor's contrast checks on cream and white: muted `#5f6585`, green `#2f7d32`, red `#c42b3b`.

`WoodlineMark.tsx`: the mark drawn as two paths, from the public site's logo, `fill="currentColor"`:

```tsx
export function WoodlineMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 78 29" className={className} aria-hidden="true">
      <path d="M38.64 4.04L0 28.65h77.2z" fill="currentColor" />
      <path d="M0 0v22.6l38.64-18.56 38.58 18.56V0z" fill="currentColor" />
    </svg>
  );
}
```

`Shell.tsx`:
- The 64px navy top bar matches the sketch:
  - the mark (40×15) and "WOODLINE" in `font-wordmark`, tracking 0.25em, 15px, white;
  - a 1px divider, then "Meeting Calendar Sync" in Figtree 600;
  - then the `context` slot (the Review page puts the conference name, hotel, dates and timezone there);
  - nav links "Conferences" and "Roster" (active link underlined beige);
  - small badges for the extractor and sink from `/api/config` (e.g. "Claude · anthropic", "Calendar · .ics"), white on navy-2;
  - then the `actions` slot.
- When `config.ephemeral`, a thin cream-2 strip sits under the bar: "Hosted demo — data resets when the server sleeps. Use sample schedules." The Stamp components are left to Task 11.
- No photos, no hero.

`Stamp.tsx`:
- A small Figtree 700, 11px, letter-spaced (0.1em) label with a 1.5px border in its tone colour, rotated −3deg.
- `muted` is flat: no rotation, muted border.
- `struck` is muted with a line-through.
- `green` shows a lucide `Check` icon (12px) before the label.

`Button.tsx`: four variants with every state (hover, active, focus-visible, disabled, loading spinner via lucide `Loader2` with `animate-spin`):
- `primary`: navy fill, white text;
- `beige`: beige fill, navy text (used on navy);
- `quiet`: white with a line border;
- `danger`: red text, line border.

- [ ] **Step 7: Conferences page**

`ConferencesPage.tsx` sits under the Shell with a max-width of 1100px:
- **Upload card:**
  - a dashed beige drop zone that also opens a file picker, `accept="application/pdf"`;
  - the selected file's name and size;
  - an optional "Default colleagues" multi-select of active roster colleagues (checkbox chips), with the hint "Added to every meeting — use for itineraries addressed to one person";
  - the **Extract meetings** primary button.
- **While extracting:** a progress state, "Reading the PDF with Claude — usually 30–60 seconds", with the button disabled.
- **On error:** an inline red note with `ApiError.detail` and a "Try again" button.
- **On success:** navigate to `/conferences/{id}`.
- **Conference list:** a table with name, hotel · city, `dateRange`, meeting count, needs attention (red when > 0), verified, sent, and a "Delete" quiet button. Delete uses a confirm step: the button changes to "Delete for good?" for 4 seconds; no modal.
- **Empty state:** "No conferences yet. Upload a broker schedule PDF to start."

- [ ] **Step 8: Roster page**

`RosterPage.tsx`:
- A table of colleagues (name, email, aliases as comma-separated text, active toggle) with inline edit: click a cell, edit, save on blur or Enter, Esc cancels.
- An "Add colleague" row at the bottom.
- Delete shows the API's 409 message inline ("This colleague is on meetings. Mark them inactive instead.").
- Empty state: "Add the colleagues whose calendars you manage."

- [ ] **Step 9: App routes, placeholder Review page, build**

`App.tsx`: `BrowserRouter` with routes `/` → `ConferencesPage`, `/conferences/:id` → `ReviewPage`, `/roster` → `RosterPage`. `main.tsx` imports `./styles.css`. `ReviewPage.tsx` placeholder: Shell plus "Review coming in the next task."

Run: `cd frontend && npx vitest run && npm run build`
Expected: tests pass; `tsc -b && vite build` succeeds; `frontend/dist/index.html` exists.

Manual check: `cd backend && uv run python -c "from mcs.api.app import create_app; import uvicorn; uvicorn.run(create_app(), port=8765)"`. Open http://127.0.0.1:8765, upload `samples/broker_a_grid.pdf` with `MCS_EXTRACTOR=fake`, and confirm it lands on the placeholder route.

- [ ] **Step 10: Commit**

```bash
git add frontend
git commit -m "feat: Woodline-themed shell, API client, helpers, conferences and roster pages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 11: Review page — "By colleague" verification surface

**Before writing UI code, read the same four design sources as Task 10.** This page is the surface the direction contract describes; the chosen sketch is its first viewport. Build the real, responsive page with every state the sketch skipped.

**Files:**
- Replace: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/components/review/ConferenceContext.tsx`, `ColleagueRail.tsx`, `StatusChips.tsx`, `Timetable.tsx`, `SourcePanel.tsx`, `AttendeePicker.tsx`, `AddMeetingRow.tsx`, `SendDialog.tsx`, `frontend/src/lib/useConference.ts`
- Test: `frontend/src/lib/useConference.test.ts`

**Interfaces:**
- Consumes: everything Task 10 produces (api functions and types, `format.ts`, `review.ts`, `Shell`, `Stamp`, `Button`, `WoodlineMark`).
- Produces: the finished `/conferences/:id` route. `useConference(id)` returns `{ detail, error, loading, apply(promise: Promise<ConferenceDetail>) }`. `apply` swaps in the server's fresh detail after every mutation; on `ApiError` it keeps the old detail and exposes `error`.

- [ ] **Step 1: Write the failing test for the state helper**

`useConference.ts` exports a pure reducer the hook wraps, so it can be tested without a DOM:

```ts
// frontend/src/lib/useConference.test.ts
import { describe, expect, it } from "vitest";
import { ApiError, type ConferenceDetail } from "../api";
import { reduce, type State } from "./useConference";

const d1 = { id: 1, name: "A" } as ConferenceDetail;
const d2 = { id: 1, name: "B" } as ConferenceDetail;

describe("conference state", () => {
  it("loads, applies fresh detail, keeps old detail on error", () => {
    let s: State = { detail: null, error: null, loading: true };
    s = reduce(s, { type: "loaded", detail: d1 });
    expect(s).toEqual({ detail: d1, error: null, loading: false });
    s = reduce(s, { type: "failed", error: new ApiError(409, "Fix the problems", []) });
    expect(s.detail).toBe(d1);
    expect(s.error?.detail).toBe("Fix the problems");
    s = reduce(s, { type: "loaded", detail: d2 });
    expect(s).toEqual({ detail: d2, error: null, loading: false });
  });
});
```

Run: `cd frontend && npx vitest run src/lib/useConference.test.ts` → FAIL (module missing). Implement `reduce` plus the `useConference` hook (`useReducer`, plus a fetch on mount and on id change), then run again → PASS.

- [ ] **Step 2: Build the page**

Layout (desktop ≥1281px), matching the sketch:
- `Shell` with `context = <ConferenceContext/>`, which shows:
  - the conference name, editable inline (click, input, Enter/blur saves via `patchConference`);
  - below it, small: hotel · city · `dateRange` · `tzLabel`. The timezone is a button that opens a searchable `<select>` of `Intl.supportedValuesOf("timeZone")`; saving calls `patchConference({timezone})`.
  - When the timezone is null, it reads "Set timezone" in red.
- `actions` = totals ("63 meetings · 7 need attention · 41 verified · 12 sent", numbers in Figtree with tabular numerals; "need attention" in light red when > 0) and the beige **Send N to calendars** button (`sendLabel(counts)`, disabled at 0).
- Below the bar, a three-column grid `250px | 1fr | 400px` with full height:
  - **ColleagueRail** (cream-2, right border):
    - the heading "Colleagues";
    - an "All colleagues" row with the total;
    - one row per `colleaguesIn(detail)` entry: an initials avatar (beige circle, navy initials), the name, a dot (red for block, amber for warn), and the count in Figtree;
    - then a "Not on roster" heading and the `unmatchedNames` rows (avatar tinted red-bg).
    - The selected row is a navy fill with white text and beige count.
    - The rows are buttons; Up/Down arrows move between rows when the rail has focus.
  - **Main column**:
    - an `h1` in Figtree 700 28px navy with the selected colleague's name (or "All colleagues", or the unmatched name);
    - a muted line, e.g. "14 meetings · 2 days · what lands in avery.kim@example.com" (for "All": "63 meetings across 6 colleagues");
    - `StatusChips` (All, Needs attention, Ready, Verified, Sent with counts from `statusCounts` of the colleague-filtered list; selected chip navy-2 fill);
    - the **Timetable**, then `AddMeetingRow`.
    - With selection "all" or a colleague, a quiet "Verify all ready (N)" button sits beside the chips. It calls `confirmReady(cid, ids of ready meetings in the current filter)`.
  - **Timetable**: one white table per `groupByDate` group, each under a day heading (Figtree 700, 13px, uppercase, letter-spacing 0.08em, blue).
    - Columns: Time | Company | Room | Shared with | Status, always in this order (columns never move). Rows are sorted by start time.
    - Time cell: `formatTime12(start)` bold Figtree tabular, then a small muted line "to {end}" + `localHint`, plus "(assumed)" when `end_assumed`.
    - Company cell: the company bold with the ticker in blue Figtree 700 11px, then a muted line with executives · format label (1x1 / Group / Meal / Meeting).
    - Room cell: the room, or a muted "—".
    - Shared-with cell: `sharedWith(...)` joined, or "—". When `removed` is non-empty, an amber note "Removing from {names} on next send".
    - Status cell: `<Stamp>`, plus amber warn-flag icons (lucide `TriangleAlert` 14px) with a tooltip of the messages.
    - The row is a button-like `<tr>` (`tabIndex=0`, Enter/Space selects). The selected row gets a `#eef0f8` background, never a coloured left border. Hover gets a cream tint. Cancelled rows are muted with the company struck through.
  - **SourcePanel** (white, left border) for the selected meeting (default: the first meeting needing attention, else the first row):
    - a heading line: "Source · {pdf_filename} · page {n}";
    - an `<iframe title="Source PDF page" src={pdfUrl(cid, source_page)}>` 330px tall, in a cream-2 frame;
    - the editable fields in a 2-column grid: Date (`<input type=date>`), Start / End (`<input type=time>`), Room, Format (`<select>`), Company, Ticker, Executives (one per line in a textarea), Notes. Each saves on blur via `patchMeeting` and re-renders from the returned detail.
    - `AttendeePicker`: the current colleagues as removable chips plus an "Add colleague" select of active roster colleagues; it saves `attendee_ids`.
    - Flag notes: block flags in a red note box (`red-bg`, red text); warn flags in an amber note box. Each `unmatched_name` row has a **Dismiss** link that adds the name to `ignored_names`.
    - When the meeting has other colleagues: an amber note, "Shared with N colleagues — verifying updates every calendar."
    - The action row: primary **Verify meeting** (or **Unverify** for confirmed). A 409 shows the returned flags' messages inline. A quiet **Delete** (or **Cancel meeting** when it was sent) with the same "click again to confirm" pattern as Task 10.
    - Per-attendee sync line: "Sent to Avery Kim · Changed — resend · Failed: {error}".
  - **AddMeetingRow**: a collapsed "+ Add meeting" quiet button. It expands into an inline form (company, date, start, end, room, colleagues) that calls `addMeeting`, then selects the new meeting.
  - **SendDialog**: a native `<dialog>` (protected focus is justified: it writes to colleagues' calendars).
    - On open it calls `sendPreview`.
    - It shows one row per colleague with counts: "3 new · 1 update · 1 removal". With nothing to send: "Everything is already on your colleagues' calendars."
    - Buttons: **Send to calendars** (primary) and Close.
    - After `sendNow`, results per colleague with failures listed by subject and error.
    - For `sink = ics`: a download link per colleague ("avery-kim.ics") and **Download all (.zip)**, plus a one-line how-to: "Open each file in Outlook (or email it to the colleague) to add the meetings."
    - For `sink = graph` when `config.graph.signed_in` is false: a "Sign in to Microsoft" step that calls `graphLogin()`, shows the code and the verification link, and polls `graphStatus()` every 3 seconds until signed in.
- **Empty and edge states:**
  - a conference with 0 meetings: "No meetings were found in this PDF. Add them by hand, or check the PDF." plus the add row;
  - `skipped_items > 0` (from the upload response, kept in router state): a quiet note "Claude skipped N unreadable rows — check the PDF.";
  - loading: skeleton rows (cream-2 bars), not a spinner;
  - not found: "This conference doesn't exist." with a link back.
- **Responsive:**
  - ≤1280px: the SourcePanel becomes a right-side drawer (fixed, 420px, shadow `0 8px 24px rgba(24,41,88,.18)`) that opens when a row is selected and has a Close button.
  - ≤900px: the rail becomes a `<select>` above the chips, and table columns collapse into a stacked cell (time on top, company, room · shared with, then the stamp).
- **Motion:** 150–200ms ease-out on row selection tint, drawer slide and chip changes, and nothing else. Respect `prefers-reduced-motion`.

- [ ] **Step 3: Verify**

Run: `cd frontend && npx vitest run && npm run build`
Expected: all tests pass and the build succeeds.

Manual check against the backend with `MCS_EXTRACTOR=fake` and the seeded sample roster:
1. Upload `samples/broker_b_by_company.pdf`.
2. Riley Chen's rail dot is amber (double booking and fuzzy match).
3. Fix a flag, verify a meeting, then send.
4. Download Avery's `.ics`.
5. Resize to 1200px (drawer) and 800px (select).

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat: By-colleague review page with source panel, verification and send

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 12: CLI, extraction scoring, README

**Files:**
- Create: `backend/mcs/cli.py`, `backend/mcs/evaluate.py`, `backend/scripts/eval_extraction.py`, `README.md` (repo root)
- Test: `backend/tests/test_cli.py`, `backend/tests/test_evaluate.py`

**Interfaces:**
- Consumes: `create_app` (Task 9), `service.seed_roster`, `service.list_analysts` (Task 8), `get_settings`, `make_engine` (Task 1), `get_extractor` (Task 3), `ExtractionResult`, `parse_extraction` (Task 2), `normalize_name` (Task 4).
- Produces: console script `mcs` with `mcs serve [--host H] [--port P] [--seed-sample-roster]` and `mcs seed-roster [PATH]`; `mcs.cli.main(argv: list[str] | None = None) -> int`; `mcs.evaluate.Score` and `mcs.evaluate.score(expected: ExtractionResult, actual: ExtractionResult) -> Score`, `format_score(name: str, s: Score) -> str`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_cli.py`:

```python
from sqlmodel import Session

from mcs import cli, service
from mcs.db import make_engine


def test_seed_roster_command(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["seed-roster"]) == 0
    assert "Added 6 colleague(s)" in capsys.readouterr().out
    assert cli.main(["seed-roster"]) == 0
    assert "Added 0 colleague(s)" in capsys.readouterr().out


def test_serve_uses_flags_and_seeds(settings, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(app=app, host=host, port=port))
    assert cli.main(["serve", "--host", "0.0.0.0", "--port", "9999", "--seed-sample-roster"]) == 0
    assert (calls["host"], calls["port"]) == ("0.0.0.0", 9999)
    with Session(make_engine(settings)) as s:
        assert len(service.list_analysts(s)) == 6


def test_serve_defaults_to_localhost(settings, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: calls.update(host=host, port=port))
    cli.main(["serve"])
    assert calls == {"host": "127.0.0.1", "port": 8765}
```

`backend/tests/test_evaluate.py`:

```python
import json

from mcs.config import REPO_ROOT
from mcs.evaluate import format_score, score
from mcs.extraction.schema import parse_extraction

A = parse_extraction(json.loads((REPO_ROOT / "samples" / "broker_a_grid.expected.json").read_text()))


def test_perfect_score():
    s = score(A, A)
    assert (s.expected, s.found, s.matched) == (12, 12, 12)
    assert s.missed == [] and s.extra == []
    assert all(v == 1.0 for v in s.field_accuracy.values())
    assert all(s.header_accuracy.values())


def test_missed_extra_and_wrong_field():
    raw = json.loads((REPO_ROOT / "samples" / "broker_a_grid.expected.json").read_text())
    raw["meetings"] = raw["meetings"][1:]                                  # miss Northwind
    raw["meetings"][0]["room"] = "Wrong Room"                              # Borealis room wrong
    raw["meetings"].append({"company": "Ghost Corp", "date": "2026-11-10", "start": "17:00"})
    raw["hotel"] = "Another Hotel"
    s = score(A, parse_extraction(raw))
    assert (s.expected, s.found, s.matched) == (12, 12, 11)
    assert s.missed == ["2026-11-10 08:00 Northwind Robotics"]
    assert s.extra == ["2026-11-10 17:00 Ghost Corp"]
    assert s.field_accuracy["room"] == 10 / 11
    assert s.header_accuracy["hotel"] is False
    text = format_score("broker_a_grid", s)
    assert "11/12 meetings matched" in text and "room" in text


def test_names_compare_as_normalized_sets():
    raw = json.loads((REPO_ROOT / "samples" / "broker_a_grid.expected.json").read_text())
    raw["meetings"][0]["firm_attendees"] = ["jordan lee", "AVERY KIM"]
    assert score(A, parse_extraction(raw)).field_accuracy["firm_attendees"] == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest -q tests/test_cli.py tests/test_evaluate.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcs.cli'`.

- [ ] **Step 3: Implement `backend/mcs/cli.py`**

```python
"""Command line: `mcs serve` and `mcs seed-roster`."""
import argparse
from pathlib import Path

from sqlmodel import Session

from mcs import service
from mcs.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcs", description="Meeting Calendar Sync")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the web app")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--seed-sample-roster", action="store_true",
                       help="Load samples/roster.sample.json when the roster is empty (hosted demo)")
    seed = sub.add_parser("seed-roster", help="Add colleagues from a JSON file (default: the sample roster)")
    seed.add_argument("path", nargs="?")
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "seed-roster":
        from mcs.db import make_engine

        path = Path(args.path) if args.path else settings.samples_dir / "roster.sample.json"
        with Session(make_engine(settings)) as session:
            added = service.seed_roster(session, path)
        print(f"Added {added} colleague(s) from {path}")
        return 0

    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    import uvicorn

    from mcs.api.app import create_app

    app = create_app(settings)
    if args.seed_sample_roster:
        with Session(app.state.engine) as session:
            if not service.list_analysts(session):
                service.seed_roster(session, settings.samples_dir / "roster.sample.json")
    print(f"Meeting Calendar Sync on http://{settings.host}:{settings.port} "
          f"(extractor: {settings.resolved_extractor()}, calendar: {settings.calendar_sink})")
    uvicorn.run(app, host=settings.host, port=settings.port)
    return 0
```

- [ ] **Step 4: Implement `backend/mcs/evaluate.py` and `backend/scripts/eval_extraction.py`**

```python
"""Score an extraction against the expected result (field-level)."""
from dataclasses import dataclass, field

from mcs.extraction.schema import ExtractedMeeting, ExtractionResult
from mcs.roster import normalize_name

MEETING_FIELDS = ("end", "room", "ticker", "format", "firm_attendees", "company_attendees", "page")
HEADER_FIELDS = ("conference_name", "broker", "hotel", "city", "timezone", "schedule_for")


@dataclass
class Score:
    expected: int
    found: int
    matched: int
    missed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    field_accuracy: dict[str, float] = field(default_factory=dict)
    header_accuracy: dict[str, bool] = field(default_factory=dict)


def _key(m: ExtractedMeeting) -> tuple:
    return (m.date, m.start, normalize_name(m.company))


def _label(m: ExtractedMeeting) -> str:
    return f"{m.date} {m.start} {m.company}"


def _same(a, b) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return {normalize_name(x) for x in a or []} == {normalize_name(x) for x in b or []}
    if isinstance(a, str) or isinstance(b, str):
        return normalize_name(a or "") == normalize_name(b or "")
    return a == b


def score(expected: ExtractionResult, actual: ExtractionResult) -> Score:
    exp = {_key(m): m for m in expected.meetings}
    act = {_key(m): m for m in actual.meetings}
    matched = [k for k in exp if k in act]
    s = Score(expected=len(exp), found=len(act), matched=len(matched),
              missed=[_label(exp[k]) for k in exp if k not in act],
              extra=[_label(act[k]) for k in act if k not in exp])
    for name in MEETING_FIELDS:
        good = sum(_same(getattr(exp[k], name), getattr(act[k], name)) for k in matched)
        s.field_accuracy[name] = good / len(matched) if matched else 0.0
    for name in HEADER_FIELDS:
        s.header_accuracy[name] = _same(getattr(expected, name), getattr(actual, name))
    return s


def format_score(name: str, s: Score) -> str:
    lines = [f"{name}: {s.matched}/{s.expected} meetings matched ({s.found} found)"]
    lines += [f"  {f:<18} {acc:6.1%}" for f, acc in s.field_accuracy.items()]
    wrong = [f for f, ok in s.header_accuracy.items() if not ok]
    lines.append(f"  header mismatches: {', '.join(wrong) or 'none'}")
    lines += [f"  missed: {x}" for x in s.missed] + [f"  extra:  {x}" for x in s.extra]
    return "\n".join(lines)
```

`backend/scripts/eval_extraction.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Write `README.md`** (repo root)

Required sections, in this order, in plain language:
1. **Title and one-paragraph summary**, plus this note, verbatim:
   > Unofficial prototype built by Nanzheng Xie for a calendar coordinator's workflow. Not an official Woodline Partners product; the Woodline look is used for an internal demo. All sample schedules, companies and people in `samples/` are fictional.
2. **How it works:** upload → Claude extracts → review by colleague → verify → send (`.ics` or Microsoft Graph). Embed one screenshot later in Task 14 (`docs/screenshots/review.png`).
3. **Quick start (local):** `cd backend && uv sync`, `cd frontend && npm ci && npm run build`, `cd backend && uv run mcs seed-roster`, `uv run mcs serve`, then open http://127.0.0.1:8765.
4. **Claude access:** a table of `MCS_EXTRACTOR` values (auto, claude-code, anthropic, foundry, fake) and what each needs. Storing the key in the Keychain:
   `security add-generic-password -a "$USER" -s meeting-calendar-sync.anthropic-api-key -w` (prompts for the key; never put keys in files). Switching to Microsoft Foundry: `MCS_EXTRACTOR=foundry`, `ANTHROPIC_FOUNDRY_RESOURCE`, and a key or Entra sign-in (`uv sync --extra foundry-entra`).
5. **Calendars:**
   - **`.ics`:** download per colleague and open in Outlook.
   - **Microsoft Graph:** in Entra, register an app, enable "Allow public client flows", and add the delegated permission `Calendars.ReadWrite.Shared` (admin consent may be required). Then set `MCS_GRAPH_CLIENT_ID` and `MCS_GRAPH_TENANT_ID`, and `MCS_CALENDAR_SINK=graph`.
   - State plainly: the Graph path is tested against a mock only, not a real tenant.
6. **Hosted demo (Cloudflare Containers):** what it is; that data resets when the container sleeps; the password gate. Deploy steps, mirroring Task 16: `cd deploy/cloudflare && npm ci`, `npx wrangler login`, `npx wrangler deploy`, then `npx wrangler secret put APP_PASSWORD` and `npx wrangler secret put ANTHROPIC_API_KEY`. Don't upload real broker schedules there unless your firm's data rules allow it.
7. **Development:** `uv run pytest`, `npx vitest run`, `uv run python scripts/eval_extraction.py`, `uv run python scripts/make_sample_pdfs.py`; the folder layout in one short tree; the link to the spec and plan.
8. **Limitations:**
   - a revised broker PDF is uploaded as a new conference (no merge yet);
   - single user;
   - hosted data is ephemeral;
   - Graph is untested against a real tenant.

- [ ] **Step 7: Commit**

```bash
git add backend/mcs/cli.py backend/mcs/evaluate.py backend/scripts/eval_extraction.py backend/tests README.md
git commit -m "feat: mcs CLI, extraction scoring script and README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 13: Container image and the password-gated Cloudflare Worker

**Files:**
- Create: `Dockerfile`, `.dockerignore` (repo root)
- Create: `deploy/cloudflare/package.json`, `deploy/cloudflare/tsconfig.json`, `deploy/cloudflare/wrangler.jsonc`, `deploy/cloudflare/src/index.ts`, `deploy/cloudflare/src/auth.ts`, `deploy/cloudflare/test/auth.test.ts`
- Modify: `.gitignore` (add `deploy/cloudflare/node_modules/`, `deploy/cloudflare/.wrangler/`)

**Interfaces:**
- Consumes: `mcs serve --seed-sample-roster` (Task 12); `MCS_*` settings (Task 1); `/api/health` and `/api/config` (Task 9); `frontend/dist` (Tasks 10–11).
- Produces: a Docker image that serves the whole app on `0.0.0.0:8080`; a Worker `meeting-calendar-sync` with Durable Object binding `MCS` → class `McsContainer`; `checkBasicAuth(request: Request, password: string | undefined): Response | null` and `constantTimeEqual(a: string, b: string): boolean` in `src/auth.ts`.

- [ ] **Step 1: Write the failing Worker auth test**

`deploy/cloudflare/test/auth.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { checkBasicAuth, constantTimeEqual } from "../src/auth";

const req = (auth?: string) => new Request("https://x.test/api/health", { headers: auth ? { Authorization: auth } : {} });
const basic = (user: string, pass: string) => `Basic ${btoa(`${user}:${pass}`)}`;

describe("checkBasicAuth", () => {
  it("fails closed when no password is configured", async () => {
    const res = checkBasicAuth(req(basic("a", "b")), undefined)!;
    expect(res.status).toBe(503);
  });
  it("asks for credentials when missing or wrong", () => {
    for (const r of [req(), req("Bearer abc"), req(basic("coordinator", "wrong")), req("Basic !!!notbase64")]) {
      const res = checkBasicAuth(r, "s3cret-pass")!;
      expect(res.status).toBe(401);
      expect(res.headers.get("WWW-Authenticate")).toContain('Basic realm="Meeting Calendar Sync"');
    }
  });
  it("lets the right password through with any user name", () => {
    expect(checkBasicAuth(req(basic("coordinator", "s3cret-pass")), "s3cret-pass")).toBeNull();
    expect(checkBasicAuth(req(basic("", "s3cret-pass")), "s3cret-pass")).toBeNull();
  });
  it("handles passwords containing colons", () => {
    expect(checkBasicAuth(req(basic("u", "a:b:c")), "a:b:c")).toBeNull();
  });
});

describe("constantTimeEqual", () => {
  it("compares exactly", () => {
    expect(constantTimeEqual("abc", "abc")).toBe(true);
    expect(constantTimeEqual("abc", "abd")).toBe(false);
    expect(constantTimeEqual("abc", "abcd")).toBe(false);
    expect(constantTimeEqual("", "")).toBe(true);
  });
});
```

`deploy/cloudflare/package.json`:

```json
{
  "name": "meeting-calendar-sync-worker",
  "private": true,
  "type": "module",
  "scripts": { "test": "vitest run", "deploy": "wrangler deploy", "types": "wrangler types" },
  "dependencies": { "@cloudflare/containers": "latest" },
  "devDependencies": { "wrangler": "latest", "typescript": "latest", "vitest": "latest", "@cloudflare/workers-types": "latest" }
}
```

Run `cd deploy/cloudflare && npm install` (pins versions in the lockfile), then `npx vitest run` → FAIL (`../src/auth` missing).

- [ ] **Step 2: Implement the Worker**

`deploy/cloudflare/src/auth.ts`:

```ts
const REALM = 'Basic realm="Meeting Calendar Sync", charset="UTF-8"';

export function constantTimeEqual(a: string, b: string): boolean {
  const x = new TextEncoder().encode(a);
  const y = new TextEncoder().encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

export function checkBasicAuth(request: Request, password: string | undefined): Response | null {
  if (!password) {
    return new Response("APP_PASSWORD is not set, so every request is refused.", { status: 503 });
  }
  const [scheme, encoded] = (request.headers.get("Authorization") ?? "").split(" ");
  if (scheme === "Basic" && encoded) {
    let decoded = "";
    try {
      decoded = atob(encoded);
    } catch {
      decoded = "";
    }
    const colon = decoded.indexOf(":");
    if (colon >= 0 && constantTimeEqual(decoded.slice(colon + 1), password)) return null;
  }
  return new Response("Sign in to Meeting Calendar Sync.", { status: 401, headers: { "WWW-Authenticate": REALM } });
}
```

`deploy/cloudflare/src/index.ts`:

```ts
import { Container, getContainer } from "@cloudflare/containers";
import { checkBasicAuth } from "./auth";

export interface Env {
  MCS: DurableObjectNamespace<McsContainer>;
  APP_PASSWORD?: string;
  ANTHROPIC_API_KEY?: string;
}

export class McsContainer extends Container<Env> {
  defaultPort = 8080;
  sleepAfter = "2h";
  enableInternet = true;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.envVars = { ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY ?? "" };
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const denied = checkBasicAuth(request, env.APP_PASSWORD);
    if (denied) return denied;
    return getContainer(env.MCS, "main").fetch(request);
  },
} satisfies ExportedHandler<Env>;
```

If the installed `@cloudflare/containers` types differ (e.g. the constructor's `ctx` type), run `npx wrangler types` and adjust the types only; keep the behaviour.

`deploy/cloudflare/wrangler.jsonc`:

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "meeting-calendar-sync",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  "observability": { "enabled": true },
  "containers": [
    {
      "class_name": "McsContainer",
      "image": "../../Dockerfile",
      "image_build_context": "../..",
      "instance_type": "basic",
      "max_instances": 1
    }
  ],
  "durable_objects": { "bindings": [{ "class_name": "McsContainer", "name": "MCS" }] },
  "migrations": [{ "tag": "v1", "new_sqlite_classes": ["McsContainer"] }]
}
```

`deploy/cloudflare/tsconfig.json`: `{"compilerOptions": {"target": "ES2022", "module": "ES2022", "moduleResolution": "Bundler", "strict": true, "lib": ["ES2022"], "types": ["@cloudflare/workers-types"], "skipLibCheck": true}, "include": ["src", "test"]}`

Run: `cd deploy/cloudflare && npx vitest run && npx tsc --noEmit`
Expected: tests pass; no type errors.

- [ ] **Step 3: Write the Dockerfile and `.dockerignore`**

`Dockerfile`:

```dockerfile
# --- build the frontend ---
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- run the backend ---
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend/ backend/
COPY samples/ samples/
COPY --from=web /app/frontend/dist frontend/dist
RUN cd backend && uv sync --frozen --no-dev
ENV MCS_HOST=0.0.0.0 \
    MCS_PORT=8080 \
    MCS_DATA_DIR=/data \
    MCS_USE_KEYCHAIN=false \
    MCS_EPHEMERAL=true \
    MCS_EXTRACTOR=anthropic
EXPOSE 8080
CMD ["/app/backend/.venv/bin/mcs", "serve", "--seed-sample-roster"]
```

`.dockerignore`:

```
**/node_modules
**/.venv
**/__pycache__
.git
data
private
.env
.impeccable
.superpowers
docs
frontend/dist
deploy
```

- [ ] **Step 4: Verify the image locally**

```bash
docker build -t meeting-calendar-sync:local .
docker run -d --rm --name mcs-local -p 18080:8080 -e MCS_EXTRACTOR=fake meeting-calendar-sync:local
sleep 5   # (in a script; do not use a bare foreground sleep in the harness — poll /api/health instead)
curl -s localhost:18080/api/health
curl -s localhost:18080/api/config
curl -s localhost:18080/api/roster | head -c 200
curl -s localhost:18080/ | head -c 200
curl -s -F "file=@samples/broker_a_grid.pdf;type=application/pdf" localhost:18080/api/conferences | head -c 200
docker stop mcs-local
```

Expected:
- `{"ok":true}`;
- the config shows `"ephemeral":true`;
- the roster has 6 sample colleagues;
- `/` returns the built `index.html`;
- the upload returns a conference with 12 meetings (fake extractor).

No `ANTHROPIC_API_KEY` is baked into the image: `docker run --rm meeting-calendar-sync:local env | grep -c ANTHROPIC` prints `0`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore .gitignore deploy/cloudflare/package.json deploy/cloudflare/package-lock.json \
  deploy/cloudflare/tsconfig.json deploy/cloudflare/wrangler.jsonc deploy/cloudflare/src deploy/cloudflare/test
git commit -m "feat: container image and password-gated Cloudflare Worker

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 14: Real-extraction check and the design finish (controller-run)

Run by the controller, not an implementer subagent. It needs the user's Keychain key, the browser and the impeccable finish agents.

- [ ] **Step 1: Real extraction against the samples.** `cd backend && uv run python scripts/eval_extraction.py`. With no `MCS_EXTRACTOR` set, this uses the Anthropic API key from the Keychain. Record each sample's score in the ledger.
  - Bar: ≥ 95% of meetings matched, and ≥ 90% on `room`, `format`, `firm_attendees` and `end`.
  - Below the bar, refine `EXTRACTION_PROMPT`, keeping the tests green, and re-run once.
  - Run the same with `MCS_EXTRACTOR=claude-code` and record it.
- [ ] **Step 2: Run the app with the real extractor.**
  1. Add `.impeccable/review/` and `.impeccable/build/` to `.gitignore`.
  2. Start `uv run mcs serve` (port 8765) and upload `samples/broker_b_by_company.pdf`.
  3. Select Riley Chen, and select the Pixelmint meeting in the source panel.
  4. Capture `.impeccable/review/desktop.png` (1440 wide, full page) and `.impeccable/review/mobile.png` (390 wide) with headless Chrome.
  5. Open both files and check them.
- [ ] **Step 3: Detector.** Run `/Users/xienanzheng/.claude/skills/impeccable/scripts/impeccable detect --json frontend/src` once. Fix mechanical findings and keep the rest for the reviewer.
- [ ] **Step 4: Finish review.** Spawn `impeccable-finish-reviewer`, fresh with no forked history, with:
  - the original request;
  - the confirmed answers (Woodline theme from the public site; 60+ meetings; laptop and monitor; must not look like a marketing site);
  - the artifact paths (`frontend/src`, built `frontend/dist`) and the screenshot paths;
  - the direction contract path;
  - the detector findings;
  - the chosen sketch `.impeccable/mocks/decision/assigned.html` as the critique reference (code-led build: no approved comp);
  - the craft-floor path.

  Act on its disposition word (ship / fix / rebuild / recapture). Two rounds at most.
- [ ] **Step 5: Document.** Spawn `impeccable-documenter` with the project root, `frontend/src`, the direction contract, `PRODUCT.md`, `/Users/xienanzheng/.claude/skills/impeccable/reference/document.md`, and the write boundary (`DESIGN.md`, `.impeccable/design.json`). Verify both files exist and carry tokens.
- [ ] **Step 6:** Copy the desktop screenshot to `docs/screenshots/review.png` and reference it in the README. Commit `DESIGN.md`, `.impeccable/design.json`, `.impeccable/surfaces/`, `.impeccable/mocks/decision/`, `.gitignore`, `docs/screenshots/review.png`, `README.md` and any fixes. Message: `docs: design system record, screenshots and finish-review fixes` plus the trailer.

### Task 15: Publish to the user's GitHub (public)

The user asked for this in chat ("upload to my personal github account"; public chosen on 2026-10-18).

- [ ] **Step 1: Secret and privacy scan over all history** (from the repo root, on `main` after the branch is merged):

```bash
git grep -nIE 'sk-ant-[A-Za-z0-9_-]{10,}|gh[opsu]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----' $(git rev-list --all) || echo "CLEAN"
git ls-files | grep -E '^(private/|data/|\.env$)' || echo "NO PRIVATE FILES TRACKED"
```

Expected: `CLEAN` and `NO PRIVATE FILES TRACKED`. Anything else stops the task: fix it before pushing (rewrite history only with the user's go-ahead).
- [ ] **Step 2: Create the repo and push.**

```bash
gh repo create xienanzheng/meeting-calendar-sync --public --source . --remote origin \
  --description "Broker conference PDFs -> verified meetings -> colleagues' calendars (prototype)" --push
gh repo view xienanzheng/meeting-calendar-sync --json url,visibility,defaultBranchRef
```

Expected: visibility `PUBLIC`, default branch `main`, README rendered. Report the URL.

### Task 16: Deploy to Cloudflare Containers

The user asked for this in chat ("deploy it for me on cloudflare"; Containers chosen on 2026-10-18). Docker must be running.

- [ ] **Step 1: The user signs in.** Ask the user to run `! cd "deploy/cloudflare" && npx wrangler login` (it opens their browser) and to enable the Workers Paid plan (Containers need it). Then confirm with `npx wrangler whoami`.
- [ ] **Step 2: Deploy.** `cd deploy/cloudflare && npm ci && npx wrangler deploy`. Wrangler builds the image for linux/amd64, pushes it to Cloudflare's registry and deploys the Worker. Note the `*.workers.dev` URL. Until `APP_PASSWORD` exists, the Worker answers every request with 503 (fail closed).
- [ ] **Step 3: Secrets, never printed.**

```bash
# app password: generated, kept in the Keychain, sent to Cloudflare
P="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
security add-generic-password -U -a "$USER" -s meeting-calendar-sync.app-password -l "Meeting Calendar Sync - hosted password" -w "$P"
printf '%s' "$P" | npx wrangler secret put APP_PASSWORD; unset P
# Anthropic key: piped from the Keychain
security find-generic-password -s meeting-calendar-sync.anthropic-api-key -w | tr -d '\n' | npx wrangler secret put ANTHROPIC_API_KEY
```

- [ ] **Step 4: Verify.**
  - Without credentials, `/api/health` returns **401**.
  - With `-u "coordinator:$(security find-generic-password -s meeting-calendar-sync.app-password -w)"`:
    - `/api/health` returns `{"ok":true}`. Poll up to ~3 minutes for the container's cold start.
    - `/api/config` shows `"extractor":"anthropic"` and `"ephemeral":true`.
    - Uploading `samples/broker_c_itinerary.pdf` returns 201 with 6 meetings.
- [ ] **Step 5: Report.** Give the user:
  - the URL;
  - how to read the password themselves (`security find-generic-password -s meeting-calendar-sync.app-password -w`; any user name works);
  - that hosted data resets when the container sleeps (2h idle) or redeploys;
  - that real broker schedules shouldn't be uploaded there unless the firm's data rules allow it;
  - an optional next step: put Cloudflare Access (email login) in front from the Zero Trust dashboard.
- [ ] **Step 6:** Commit any deploy-config fixes and push to `origin/main`.
