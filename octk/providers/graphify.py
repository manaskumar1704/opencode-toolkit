"""Graphify detection: is it installed, and is the graph index warm?

Nothing here runs the binary. ``shutil.which`` only searches PATH.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from ..capabilities import MAX_DESCRIPTION
from . import ProviderStatus

ID = "graphify"
_SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "graphify-out",
    "dist",
    "build",
}


def _report_paths(root: Path, config: dict[str, Any]) -> list[Path]:
    raw = config.get("graph_report_paths") or []
    if not isinstance(raw, list):
        return []
    return [root / item for item in raw if isinstance(item, str)]


def _newest_python_mtime(root: Path) -> float | None:
    newest: float | None = None
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    return newest


def detect(root: Path, config: dict[str, Any]) -> ProviderStatus:
    """Report binary presence and index freshness without executing anything."""
    command = str(config.get("graph_cmd") or "graphify")
    binary = shutil.which(command)
    reports = [path for path in _report_paths(root, config) if path.is_file()]

    if not reports:
        state = "cold"
        detail = "no graph report found; indexing required before the first query"
    else:
        newest_report = max(path.stat().st_mtime for path in reports)
        newest_source = _newest_python_mtime(root)
        if newest_source is not None and newest_source > newest_report:
            state = "stale"
            detail = "graph report is older than the newest .py file; incremental update needed"
        else:
            state = "warm"
            detail = "graph report is newer than every .py file"

    if binary is None:
        detail = f"{detail}; binary {command!r} not on PATH"

    return ProviderStatus(
        id=ID,
        available=binary is not None,
        version=None,  # obtaining a version would require executing the binary
        detail=detail,
        state=state,
    )


def capability_record(
    root: Path, config: dict[str, Any], today: str | None = None
) -> dict[str, Any]:
    """Registry record for Graphify, available or not."""
    status = detect(root, config)
    command = str(config.get("graph_cmd") or "graphify")
    return {
        "id": f"cli:{ID}/{ID}",
        "type": "cli",
        "name": ID,
        "description": (
            "Optional repository graph provider for call paths, symbols, and "
            "affected components"
        )[:MAX_DESCRIPTION],
        "provider": ID,
        "version": None,
        "scope": "project",
        "harness": ["opencode"],
        "activation": "enabled" if status.available else "disabled",
        "invocation": {
            "method": "cli",
            "command": command,
            "schema_ref": None,
            "state": status.state,
        },
        "permissions": {"side_effects": ["read_only"]},
        "cost": None,
        "provenance": "discovered",
        "verified_at": today or date.today().isoformat(),
        "source_path": None,
    }
