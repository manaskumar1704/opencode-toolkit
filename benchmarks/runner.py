"""Benchmark runner: worktree isolation and cohort orchestration.

Legacy helper: the driver now uses ``benchmarks.workspace`` instead, because a
linked worktree shares ``.git`` and OpenCode resolves the project to the host.
Kept for compatibility with existing tests. See handoff D3 and D5.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from benchmarks.manifest import RunManifest, hash_text, now_iso
from benchmarks.preflight import run_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"

ARMS = ("A", "B", "C", "D", "E", "F", "G", "H")


def safe_id(value: str) -> str:
    """Reduce a task/arm name to one filesystem-safe path segment."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return cleaned or "run"


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=check
    )


def create_worktree(repo: Path, run_id: str, base_ref: str = "HEAD") -> Path:
    """Create an isolated worktree for one run. Raises on failure."""
    parent = Path(tempfile.gettempdir()) / "octk-bench"
    parent.mkdir(parents=True, exist_ok=True)
    # Defence in depth: never let a caller-supplied id escape the parent dir.
    target = parent / safe_id(run_id)
    if target.exists():
        remove_worktree(repo, target)
    proc = _git(repo, "worktree", "add", "--detach", str(target), base_ref)
    if proc.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {proc.stderr.strip()}")
    return target


def remove_worktree(repo: Path, path: Path) -> None:
    """Remove a worktree. Safe to call on a missing path."""
    if path.exists():
        _git(repo, "worktree", "remove", "--force", str(path))
    _git(repo, "worktree", "prune")


def list_worktrees(repo: Path) -> list[Path]:
    proc = _git(repo, "worktree", "list", "--porcelain")
    paths = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]))
    return paths


def isolate_run(repo: Path, arm: str, task: str, seed: int, run_order: int) -> tuple[Path, str]:
    """Create a worktree and return (path, run_id)."""
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    run_id = f"bench-{arm}-{task}-s{seed}-r{run_order}"
    path = create_worktree(repo, run_id, base)
    return path, run_id


def list_tasks(root: Path | None = None) -> list[dict[str, Any]]:
    """Return every task fixture's metadata, sorted by name."""
    directory = root or TASKS_DIR
    tasks: list[dict[str, Any]] = []
    for task_json in sorted(directory.glob("*/task.json")):
        try:
            data = json.loads(task_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data["path"] = str(task_json.parent)
        tasks.append(data)
    return tasks


def read_task_prompt(task_dir: Path) -> str:
    task_json = task_dir / "task.json"
    if not task_json.exists():
        raise FileNotFoundError(f"task.json missing in {task_dir}")
    data = json.loads(task_json.read_text(encoding="utf-8"))
    return str(data.get("prompt", ""))


def read_task_category(task_dir: Path) -> str:
    task_json = task_dir / "task.json"
    if not task_json.exists():
        return "unknown"
    data = json.loads(task_json.read_text(encoding="utf-8"))
    return str(data.get("category", "unknown"))


def arm_has(arm: str, component: str) -> bool:
    """Whether an arm enables OCTK / Ponytail / Graphify."""
    octk_on = arm in ("E", "F", "G", "H")
    ponytail_on = arm in ("B", "D", "F", "H")
    graphify_on = arm in ("C", "D", "G", "H")
    if component == "octk":
        return octk_on
    if component == "ponytail":
        return ponytail_on
    if component == "graphify":
        return graphify_on
    raise ValueError(f"unknown component: {component}")


def build_manifest_skeleton(
    arm: str,
    task: str,
    task_category: str,
    base_commit: str,
    opencode_version: str,
    model_id: str,
    effort: str,
    task_prompt: str,
    acceptance_test: str,
    seed: int,
    run_order: int,
    worktree: Path,
    ponytail_version: str | None,
    graphify_version: str | None,
    graphify_state: str | None,
    ponytail_available: bool,
    graphify_available: bool,
) -> RunManifest:
    """Build a manifest with all D7 fields populated except results."""
    from benchmarks.manifest import RunManifest

    transcript = RESULTS_DIR / f"{task}_{arm}_seed{seed}_run{run_order}.jsonl"
    manifest = RunManifest(
        arm=arm,
        task=task,
        task_category=task_category,
        base_commit=base_commit,
        opencode_version=opencode_version,
        model_id=model_id,
        effort=effort,
        task_prompt_hash=hash_text(task_prompt),
        acceptance_test_hash=hash_text(acceptance_test),
        randomization_seed=seed,
        run_order=run_order,
        isolation_verified=True,
        transcript_path=str(transcript),
        ponytail_version=ponytail_version,
        graphify_version=graphify_version,
        graphify_state=graphify_state,
        ponytail_available=ponytail_available,
        graphify_available=graphify_available,
        started_at=now_iso(),
        environment_manifest={"worktree": str(worktree)},
    )
    return manifest


def run_preflight_or_raise(repo: Path) -> dict[str, Any]:
    """Run pre-flight and raise if it fails. Returns the preflight dict."""
    result = run_preflight(repo)
    if not result.ok:
        raise RuntimeError(
            "pre-flight failed:\n" + "\n".join(f"  - {e}" for e in result.errors)
        )
    return result.to_dict()
