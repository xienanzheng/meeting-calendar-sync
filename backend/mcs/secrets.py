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
