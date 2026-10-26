"""Out-of-band approvals stored in .toolkit/approvals.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ToolkitPaths, atomic_write_json, load_config, read_json

def _fresh_store() -> dict[str, Any]:
    return {"version": 1, "approvals": []}


def _load(root: Path) -> dict[str, Any]:
    data = read_json(ToolkitPaths(root).approvals, None)
    if not isinstance(data, dict) or not isinstance(data.get("approvals"), list):
        return _fresh_store()
    return {**data, "approvals": list(data["approvals"])}


def create_approval(
    root: Path, task_substring: str, now: float | None = None
) -> dict[str, Any]:
    """Create an unconsumed approval for a task substring."""
    import time

    now = time.time() if now is None else now
    path = ToolkitPaths(root).approvals
    data = _load(root)
    approval = {
        "id": f"apr-{int(now * 1000)}",
        "task_substring": task_substring,
        "created_at": now,
        "consumed_at": None,
    }
    data["approvals"].append(approval)
    atomic_write_json(path, data)
    return approval


def list_approvals(root: Path) -> list[dict[str, Any]]:
    """Return all approval records."""
    return _load(root)["approvals"]


def open_approvals(root: Path, now: float | None = None) -> list[dict[str, Any]]:
    """Unconsumed, unexpired approvals (same TTL rule as the completion gate)."""
    import time

    now = time.time() if now is None else now
    ttl_seconds = float(load_config(root).get("approval_ttl_minutes", 120)) * 60.0
    return [a for a in _load(root)["approvals"] if _valid(a, now, ttl_seconds)]


def _valid(approval: dict[str, Any], now: float, ttl_seconds: float) -> bool:
    return approval.get("consumed_at") is None and (
        now - float(approval.get("created_at", 0)) <= ttl_seconds
    )


def find_valid_approval(
    root: Path, roadmap_line: str, now: float
) -> dict[str, Any] | None:
    """Newest unconsumed, unexpired approval whose substring matches the line."""
    ttl_seconds = float(load_config(root).get("approval_ttl_minutes", 120)) * 60.0
    needle = roadmap_line.casefold()
    matches = [
        a
        for a in _load(root)["approvals"]
        if a.get("task_substring", "").casefold() in needle
    ]
    valid = [a for a in matches if _valid(a, now, ttl_seconds)]
    if not valid:
        return None
    return sorted(valid, key=lambda a: float(a.get("created_at", 0)))[-1]


def consume_approval(root: Path, approval: dict[str, Any], now: float) -> None:
    """Mark an approval as consumed (atomic write)."""
    path = ToolkitPaths(root).approvals
    data = _load(root)
    for record in data["approvals"]:
        if record.get("id") == approval.get("id"):
            record["consumed_at"] = now
            break
    atomic_write_json(path, data)
