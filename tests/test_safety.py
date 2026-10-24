"""safety.run_command: allowlist, timeouts, no shell interpretation."""

from __future__ import annotations

from pathlib import Path

import pytest

from octk.runtime.safety import CommandNotAllowed, run_command

ALLOWED = ["pytest", "python", "python3", "uv"]


def test_allowlisted_command_runs(tmp_path: Path) -> None:
    result = run_command("python -c print(6*7)", tmp_path, ALLOWED)
    assert result.returncode == 0
    assert "42" in result.stdout


def test_non_allowlisted_raises(tmp_path: Path) -> None:
    with pytest.raises(CommandNotAllowed):
        run_command("curl https://example.com", tmp_path, ALLOWED)


def test_no_shell_metachar_interpretation(tmp_path: Path) -> None:
    # "pytest;" with an echo is a single weird token, NOT a shell chain
    with pytest.raises(CommandNotAllowed):
        run_command("pytest; echo hi", tmp_path, ALLOWED)
    # even allowlisted first word does not shell out the semicolon chain
    result = run_command('python -c "print(1)"', tmp_path, ALLOWED)
    assert result.returncode == 0


def test_timeout_returns_partial(tmp_path: Path) -> None:
    result = run_command('python -c "import time; time.sleep(5)"', tmp_path, ALLOWED, timeout_s=1)
    assert result.timed_out is True
    assert result.returncode != 0


def test_cwd_is_root(tmp_path: Path) -> None:
    script = tmp_path / "wd.py"
    script.write_text("import os; print(os.getcwd())", encoding="utf-8")
    result = run_command(["python", str(script)], tmp_path, ALLOWED)
    assert result.stdout.strip() == str(tmp_path)
