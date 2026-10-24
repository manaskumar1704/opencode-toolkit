"""Config paths, defaults, deep-merge loader and atomic JSON io."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "always_on_skills": [],
    "approval_ttl_minutes": 120,
    "audit_mode": "instruct",
    "graph_cmd": "graphify",
    "audit_cmd": "ponytail-review",
    "graph_report_paths": ["graphify-out/GRAPH_REPORT.md", "graphify-out/graph.json"],
    "allowed_commands": ["pytest", "python", "python3", "uv"],
    "command_timeout_s": 120,
    "max_output_chars": 2500,
    "server_name": "octk",
}


@dataclass(frozen=True)
class ToolkitPaths:
    """All octk state lives under <root>/.toolkit."""

    root: Path

    @property
    def toolkit(self) -> Path:
        return self.root / ".toolkit"

    @property
    def specs(self) -> Path:
        return self.toolkit / "specs"

    @property
    def skills(self) -> Path:
        return self.toolkit / "skills"

    @property
    def index(self) -> Path:
        return self.toolkit / "index.md"

    @property
    def roadmap(self) -> Path:
        return self.toolkit / "specs" / "roadmap.md"

    @property
    def metrics(self) -> Path:
        return self.toolkit / "metrics.json"

    @property
    def approvals(self) -> Path:
        return self.toolkit / "approvals.json"

    @property
    def config(self) -> Path:
        return self.toolkit / "config.json"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override on top of base; dict values merge recursively."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(root: Path) -> dict[str, Any]:
    """Load .toolkit/config.json deep-merged over DEFAULT_CONFIG."""
    path = ToolkitPaths(root).config
    stored: dict[str, Any] = {}
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stored = {}
    return _deep_merge(DEFAULT_CONFIG, stored if isinstance(stored, dict) else {})


def read_json(path: Path, default: Any = None) -> Any:
    """Read JSON, returning default when the file is missing or invalid."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically: temp file in the same dir, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
