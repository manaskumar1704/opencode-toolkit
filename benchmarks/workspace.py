"""Per-run workspace isolation for the benchmark.

A linked git worktree is **not** isolation. Worktrees share ``.git``, so
OpenCode resolves the project to the host repository, loads the host config
(including MCP servers the arm was supposed to disable), and the agent can walk
to the host path. Measured: an arm-A run called ``glance_pantry`` and read
``benchmarks/tasks/simple_bug/oracle/acceptance.py``.

This module builds a standalone copy instead:

- no ``.git`` link to the host, so the project identity is the copy;
- ``benchmarks/`` is excluded, so the hidden oracles are not in the workspace;
- the copy gets its own git history, so ``git apply`` and ``git diff`` work;
- when bubblewrap is available, the host repository is masked inside the
  sandbox, so a shell cannot walk back to it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from benchmarks.runner import safe_id

WORKSPACE_PARENT = Path.home() / ".cache" / "octk-bench"

# Never copy these into a workspace: VCS metadata (would link to the host),
# the benchmark harness itself (contains the oracles), and local caches.
IGNORE = shutil.ignore_patterns(
    ".git",
    "benchmarks",
    ".venv",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
)

CLONE_RE = re.compile(r"git\s+clone\s+\S*opencode-toolkit", re.IGNORECASE)
ORACLE_DEF_RE = re.compile(r"\bdef (test_\w+)")

# Fragments that only appear if the agent reached a leftover pytest fixture
# directory. Documentation mentions oracle paths, so those are not markers.
LEAK_FRAGMENTS = ("pytest-of-",)


def create_workspace(
    repo: Path, run_id: str, parent: Path | None = None
) -> Path:
    """Copy ``repo`` into a standalone workspace and commit the baseline."""
    root = parent or WORKSPACE_PARENT
    root.mkdir(parents=True, exist_ok=True)
    target = root / safe_id(run_id)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(repo, target, ignore=IGNORE, symlinks=True)

    _git(target, "init", "-q")
    _git(target, "config", "user.email", "bench@octk.local")
    _git(target, "config", "user.name", "octk bench")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "bench baseline")
    return target


def remove_workspace(path: Path) -> None:
    """Remove a workspace. Safe to call on a missing path."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def wrap_command(
    argv: list[str],
    workspace: Path,
    host_repo: Path,
    home: Path | None = None,
) -> list[str]:
    """Wrap ``argv`` in bubblewrap with the host repository masked.

    Falls back to the bare command when bwrap is unavailable; callers record
    which mode ran so the manifest can say so.
    """
    if not bwrap_available():
        return list(argv)

    home = home or Path.home()
    command = [
        "bwrap",
        "--die-with-parent",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
    ]
    # Hide the oracle fixtures and the git history that contains them. The rest
    # of the host tree stays visible read-only so the project venv still works.
    for masked in (host_repo / "benchmarks", host_repo / ".git"):
        if masked.exists():
            command += ["--tmpfs", str(masked)]
    # The workspace lives outside /tmp on purpose: host temp dirs contain
    # pytest artifacts (including oracle copies), so /tmp is replaced with an
    # empty private tmpfs. The workspace itself is the only writable mount.
    command += [
        "--bind",
        str(workspace),
        str(workspace),
        "--tmpfs",
        "/tmp",
    ]
    for relative in (".local/share/opencode", ".cache", ".config/opencode"):
        path = home / relative
        if path.exists():
            command += ["--bind", str(path), str(path)]
    command += ["--chdir", str(workspace), "--", *argv]
    return command


def oracle_leaks(
    transcript_text: str,
    oracle_text: str,
    oracle_path: str | None = None,
    visible_text: str = "",
) -> list[str]:
    """Return evidence that the agent saw the hidden acceptance oracle.

    Only test names that are *not* already present in the visible task files
    count as evidence; shared names would otherwise fire on a normal run.
    """
    visible_names = set(ORACLE_DEF_RE.findall(visible_text))
    leaks: list[str] = []
    for name in sorted(set(ORACLE_DEF_RE.findall(oracle_text)) - visible_names):
        if name in transcript_text:
            leaks.append(f"oracle test name: {name}")
    if oracle_path and oracle_path in transcript_text:
        leaks.append(f"oracle path: {oracle_path}")
    for fragment in LEAK_FRAGMENTS:
        if fragment in transcript_text:
            leaks.append(f"oracle path fragment: {fragment}")
    if CLONE_RE.search(transcript_text):
        leaks.append("git clone of the benchmark repository")
    return sorted(set(leaks))
