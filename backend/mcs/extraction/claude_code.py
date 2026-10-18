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
