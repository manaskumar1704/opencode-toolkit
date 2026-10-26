"""Metrics store: tasks, tool calls, and standing context costs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .config import ToolkitPaths, atomic_write_json, read_json

_SCHEMA: dict[str, Any] = {
    "version": 1,
    "active_task": None,
    "tasks": [],
    "unattributed": [],
    "standing_costs": [],
    "debug_state": {"active_task": None, "signature": None, "strikes": 0, "detail": ""},
}

MODES = ("with_octk", "without_octk")

def approx_tokens(chars: int) -> int:
    """Approximate token count: ceil(chars / 4)."""
    return (int(chars) + 3) // 4


def cache_hit_rate(tokens_in: int | None, tokens_cached: int | None) -> float | None:
    """Share of total input tokens served from cache, or None without token data."""
    total = int(tokens_in or 0) + int(tokens_cached or 0)
    if total <= 0:
        return None
    return int(tokens_cached or 0) / total


def _fresh_debug_state(active_task: str | None = None) -> dict[str, Any]:
    return {"active_task": active_task, "signature": None, "strikes": 0, "detail": ""}


class MetricsStore:
    """JSON-backed store for task runs, tool calls and standing costs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        stored = read_json(path, None)
        if not isinstance(stored, dict):
            stored = {}
        debug_state = stored.get("debug_state")
        if not isinstance(debug_state, dict):
            debug_state = _fresh_debug_state(stored.get("active_task"))
        self._data = {
            **_SCHEMA,
            "active_task": stored.get("active_task"),
            "tasks": [dict(t) for t in stored.get("tasks", [])],
            "unattributed": list(stored.get("unattributed", [])),
            "standing_costs": list(stored.get("standing_costs", [])),
            "debug_state": {
                "active_task": debug_state.get("active_task"),
                "signature": debug_state.get("signature"),
                "strikes": int(debug_state.get("strikes", 0) or 0),
                "detail": str(debug_state.get("detail", "")),
            },
        }

    def load(self) -> dict[str, Any]:
        """Return the store's full data dict."""
        return self._data

    def _save(self) -> None:
        atomic_write_json(self.path, self._data)

    def start_task(
        self,
        name: str,
        mode: str = "with_octk",
        model: str | None = None,
        started_at: float | None = None,
    ) -> dict[str, Any]:
        """Begin a task run; error if one is already active."""
        if self._data.get("active_task"):
            raise RuntimeError("a task is already active; end it first")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        task = {
            "name": name,
            "mode": mode,
            "model": model,
            "started_at": started_at if started_at is not None else time.time(),
            "ended_at": None,
            "duration_s": None,
            "status": "active",
            "notes": "",
            "tool_calls": [],
            "tokens_in": None,
            "tokens_out": None,
            "tokens_cached": 0,
            "cache_hit_rate": None,
            "cost_usd": None,
            "turns": None,
            "check_cmd": None,
            "check_passed": None,
        }
        self._data["tasks"].append(task)
        self._data["active_task"] = name
        self._data["debug_state"] = _fresh_debug_state(name)
        self._save()
        return task

    def _append_tool_call(self, record: dict[str, Any]) -> None:
        if self._data.get("active_task"):
            for task in self._data["tasks"]:
                if task["name"] == self._data["active_task"] and task["status"] == "active":
                    task["tool_calls"].append(record)
                    break
            else:
                self._data["unattributed"].append(record)
        else:
            self._data["unattributed"].append(record)

    def log_tool_call(
        self,
        tool: str,
        raw_chars: int,
        pruned_chars: int,
        kind: str = "measured",
        ts: float | None = None,
    ) -> None:
        """Record a tool call on the active task, else unattributed."""
        record = {
            "tool": tool,
            "kind": kind,
            "raw_chars": int(raw_chars),
            "pruned_chars": int(pruned_chars),
            "ts": ts if ts is not None else time.time(),
        }
        self._append_tool_call(record)
        self._save()

    def record_debug_call(
        self,
        signature: str | None,
        detail: str,
        raw_chars: int,
        pruned_chars: int,
        ts: float | None = None,
    ) -> int:
        """Log debug_inspect and update its consecutive-failure strike count.

        A signature of None means the command succeeded and clears the streak.
        Stale state from another active task also resets the streak.
        """
        active = self._data.get("active_task")
        state = self._data.get("debug_state")
        if not isinstance(state, dict) or state.get("active_task") != active:
            state = _fresh_debug_state(active)
        if signature is None:
            state = _fresh_debug_state(active)
        elif state.get("signature") == signature:
            state["strikes"] = int(state.get("strikes", 0)) + 1
            state["detail"] = str(detail)[:500]
        else:
            state = {
                "active_task": active,
                "signature": signature,
                "strikes": 1,
                "detail": str(detail)[:500],
            }
        self._data["debug_state"] = state
        self._append_tool_call(
            {
                "tool": "debug_inspect",
                "kind": "measured",
                "raw_chars": int(raw_chars),
                "pruned_chars": int(pruned_chars),
                "ts": ts if ts is not None else time.time(),
            }
        )
        self._save()
        return int(state.get("strikes", 0))

    def add_standing(self, label: str, tokens_in: int) -> dict[str, Any]:
        """Record a measured turn-1 input-token standing cost."""
        entry = {"label": label, "tokens_in": int(tokens_in)}
        self._data.setdefault("standing_costs", []).append(entry)
        self._save()
        return entry

    def end_task(
        self,
        status: str = "completed",
        notes: str = "",
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        tokens_cached: int = 0,
        cost_usd: float | None = None,
        turns: int | None = None,
        check_cmd: str | None = None,
        check_passed: bool | None = None,
        ended_at: float | None = None,
    ) -> dict[str, Any]:
        """Close the active task with optional acceptance-check results."""
        name = self._data.get("active_task")
        if not name:
            raise RuntimeError("no active task")
        for task in reversed(self._data["tasks"]):
            if task["name"] == name and task["status"] == "active":
                ended = ended_at if ended_at is not None else time.time()
                task.update(
                    {
                        "ended_at": ended,
                        "duration_s": ended - task["started_at"],
                        "status": status,
                        "notes": notes,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "tokens_cached": int(tokens_cached or 0),
                        "cache_hit_rate": cache_hit_rate(tokens_in, tokens_cached),
                        "cost_usd": cost_usd,
                        "turns": turns,
                        "check_cmd": check_cmd,
                        "check_passed": check_passed,
                    }
                )
                break
        self._data["active_task"] = None
        self._data["debug_state"] = _fresh_debug_state(None)
        self._save()
        return task
