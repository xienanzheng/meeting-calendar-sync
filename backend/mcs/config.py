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
    auto_sync: bool = True  # approval sends: sync calendars after every approval-type change
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
