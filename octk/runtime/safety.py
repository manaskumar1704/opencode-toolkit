"""Safe subprocess execution with an allowlist. No shell, ever."""

from __future__ import annotations

import os
import shlex
import shutil
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


def _invoked_path(token: str) -> str | None:
    """Return the absolute path a token would execute, or None if it cannot.

    A bare name is looked up on PATH. A path is taken *literally*: symlinks
    are not followed, so a link called ``pytest`` sitting in an unexpected
    directory stays that link instead of becoming the allowlisted binary.
    """
    if os.sep in token or (os.altsep and os.altsep in token):
        candidate = Path(token)
        if not candidate.is_file():
            return None
        return os.path.normcase(os.path.abspath(str(candidate)))
    found = shutil.which(token)
    if not found:
        return None
    return os.path.normcase(os.path.abspath(found))


def _allowed(token: str, allowed: list[str]) -> bool:
    """True when ``token`` invokes exactly an allowlisted executable.

    Comparing the invoked path rather than its basename is the whole point:
    matching on names meant any path ending in an allowed name passed, so
    ``/tmp/anything/pytest`` ran while only ``pytest`` was approved.
    """
    target = _invoked_path(token)
    if target is None:
        return False
    for entry in allowed:
        candidate = _invoked_path(entry)
        if candidate is not None and candidate == target:
            return True
    return False


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
            check=False,
        )
        return CommandResult(stdout=proc.stdout or "", stderr=proc.stderr or "", returncode=proc.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(stdout=stdout, stderr=stderr, returncode=-1, timed_out=True)
