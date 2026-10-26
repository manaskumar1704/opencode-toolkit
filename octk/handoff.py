"""Deterministic session handoff snapshot (no LLM calls, no network)."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .approvals import open_approvals
from .config import ToolkitPaths, read_json
from .roadmap import RoadmapError, parse_roadmap

GIT_TIMEOUT_S = 10


def _roadmap_state(root: Path) -> tuple[str, str]:
    """Return (current '~' task, next pending ' ' task), with fallbacks."""
    try:
        entries = parse_roadmap(root)
    except (RoadmapError, OSError):
        return "(roadmap unavailable)", "(roadmap unavailable)"
    current = next(
        (str(e["text"]) for e in entries if e.get("status") == "~"),
        "(none in progress)",
    )
    current_line = next((int(e["line_no"]) for e in entries if e.get("status") == "~"), 0)
    pending = next(
        (
            str(e["text"])
            for e in entries
            if e.get("status") == " " and int(e["line_no"]) > current_line
        ),
        None,
    )
    if pending is None:
        pending = next((str(e["text"]) for e in entries if e.get("status") == " "), "(none pending)")
    return current, pending


def _git_output(root: Path, args: list[str]) -> str:
    git = shutil.which("git")
    if not git:
        return "(git not installed)"
    try:
        proc = subprocess.run(
            [git, *args],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"(git failed: {type(exc).__name__})"
    text = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        return text or f"(git {args[0]} exited {proc.returncode})"
    return text or "(clean)"


def _latest_signal(root: Path) -> str:
    data = read_json(ToolkitPaths(root).metrics, None)
    if not isinstance(data, dict):
        return "none recorded"
    calls: list[dict[str, Any]] = []
    for task in data.get("tasks", []) or []:
        calls.extend(task.get("tool_calls", []) or [])
    calls.extend(data.get("unattributed", []) or [])
    if not calls:
        return "none recorded"
    last = max(
        calls,
        key=lambda call: float(call.get("ts", 0) or 0),
    )
    ts = last.get("ts")
    stamp = (
        datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        if isinstance(ts, (int, float))
        else "unknown time"
    )
    signal = (
        f"{last.get('tool')} ({last.get('kind')}) at {stamp}: "
        f"{last.get('raw_chars')} raw / {last.get('pruned_chars')} pruned chars"
    )
    state = data.get("debug_state")
    if isinstance(state, dict) and int(state.get("strikes", 0) or 0) > 0:
        signal += (
            f"; debug_inspect strikes={state.get('strikes')} "
            f"detail={state.get('detail') or '(none)'}"
        )
    return signal


def _approval_lines(root: Path) -> list[str]:
    try:
        approvals = open_approvals(root)
    except OSError:
        return ["- (approvals unreadable)"]
    if not approvals:
        return ["- (none open)"]
    return [
        f"- `{a.get('id')}` for `{a.get('task_substring')}`"
        for a in sorted(approvals, key=lambda a: float(a.get("created_at", 0)))
    ]


def generate_handoff(root: Path, out_path: Path | None = None) -> str:
    """Write and return .toolkit/handoff.md with resume-critical state."""
    paths = ToolkitPaths(root)
    target = out_path or paths.handoff
    current, pending = _roadmap_state(root)
    git_status = _git_output(root, ["status", "--short"])
    git_stat = _git_output(root, ["diff", "--stat"])
    approvals = _approval_lines(root)

    lines = [
        "# octk session handoff",
        "",
        "## Active roadmap state",
        "",
        f"- In progress `[~]`: {current}",
        f"- Next pending `[ ]`: {pending}",
        "",
        "## Git working tree",
        "",
        "```text",
        "$ git status --short",
        git_status,
        "$ git diff --stat",
        git_stat,
        "```",
        "",
        "## Latest runtime signal",
        "",
        f"- {_latest_signal(root)}",
        "",
        "## Open approvals",
        "",
        *approvals,
        "",
        "## Resume after /clear",
        "",
        "Read `.toolkit/handoff.md`, `.toolkit/index.md`, and `.toolkit/specs/roadmap.md`.",
        f"Resume the `[~]` task above and preserve the latest runtime signal; do not redo completed work.",
        'Run the acceptance command before asking the user for `octk approve "<task>"`.',
        "",
    ]
    text = "\n".join(lines)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return text
