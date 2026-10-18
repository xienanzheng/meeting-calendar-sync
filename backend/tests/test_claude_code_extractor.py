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
