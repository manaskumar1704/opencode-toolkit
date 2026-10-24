"""Safe subprocess execution with an allowlist. No shell, ever."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


class CommandNotAllowed(Exception):
    """Raised when a command's executable is not on the allowlist."""


def _allowed(token: str, allowed: list[str]) -> bool:
    if token in allowed:
        return True
    name = os.path.basename(token)
    stem = os.path.splitext(name)[0]
    return name in allowed or stem in allowed


def run_command(
    argv_or_str: str | list[str],
    root: Path,
    allowed: list[str],
    timeout_s: int = 120,
) -> CommandResult:
    """Run a command (allowlisted, no shell, cwd=root, timeout enforced)."""
    argv = shlex.split(argv_or_str) if isinstance(argv_or_str, str) else [str(a) for a in argv_or_str]
    if not argv:
        raise CommandNotAllowed("empty command")
    if not _allowed(argv[0], allowed):
        raise CommandNotAllowed(
            f"command {argv[0]!r} not in allowed_commands: {sorted(allowed)}"
        )
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            timeout=timeout_s,
            capture_output=True,
            text=True,
            errors="replace",
        )
        return CommandResult(stdout=proc.stdout or "", stderr=proc.stderr or "", returncode=proc.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(stdout=stdout, stderr=stderr, returncode=-1, timed_out=True)
