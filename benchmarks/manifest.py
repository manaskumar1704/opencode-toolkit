"""Run manifest: the D7 pre-registration checklist, made enforceable.

A run is not evidence unless every required field is populated. The runner
records the manifest; the report marks any incomplete run ``INVALID`` and
excludes it from aggregates. See handoff D7.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Required fields per handoff D7. A manifest missing any of these is INVALID.
REQUIRED_FIELDS = (
    "arm",
    "task",
    "task_category",
    "base_commit",
    "opencode_version",
    "model_id",
    "effort",
    "task_prompt_hash",
    "acceptance_test_hash",
    "randomization_seed",
    "run_order",
    "isolation_verified",
    "transcript_path",
    "ponytail_version",
    "graphify_version",
    "graphify_state",
    "ponytail_available",
    "graphify_available",
    "correctness",
    "rate_limit_log",
    "provider_errors",
)


@dataclass
class RunManifest:
    """One paired run. ``validate()`` returns the list of missing fields."""

    arm: str = ""
    task: str = ""
    task_category: str = ""
    base_commit: str = ""
    opencode_version: str = ""
    model_id: str = ""
    effort: str = ""
    task_prompt_hash: str = ""
    acceptance_test_hash: str = ""
    randomization_seed: int = 0
    run_order: int = 0
    isolation_verified: bool = False
    transcript_path: str = ""
    ponytail_version: str | None = None
    graphify_version: str | None = None
    graphify_state: str | None = None
    ponytail_available: bool = False
    graphify_available: bool = False
    correctness: dict[str, Any] = field(default_factory=dict)
    rate_limit_log: list[dict[str, Any]] = field(default_factory=list)
    provider_errors: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    duration_s: float | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    tokens_cached: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    files_read: int = 0
    search_ops: int = 0
    wall_clock_s: float | None = None
    patch: str = ""
    test_output: str = ""
    environment_manifest: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Return the list of required fields that are missing or falsy."""
        missing = []
        for name in REQUIRED_FIELDS:
            value = getattr(self, name)
            if name in ("rate_limit_log", "provider_errors"):
                if value is None:
                    missing.append(name)
                continue
            if name in ("ponytail_version", "graphify_version", "graphify_state"):
                # Optional scalars: None is allowed when the tool is absent.
                # graphify_state must be present when graphify is available.
                if name == "graphify_state" and self.graphify_available and value is None:
                    missing.append(name)
                continue
            if name in ("ponytail_available", "graphify_available"):
                # Boolean flags: False is a valid value (tool absent).
                if value is None:
                    missing.append(name)
                continue
            if value is None or value == "" or value is False:
                missing.append(name)
        if not isinstance(self.correctness, dict) or not self.correctness:
            missing.append("correctness")
        if not self.isolation_verified:
            if "isolation_verified" not in missing:
                missing.append("isolation_verified")
        if self.transcript_path and not Path(self.transcript_path).exists():
            missing.append("transcript_path (file missing)")
        return sorted(set(missing))

    @property
    def valid(self) -> bool:
        return not self.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunManifest":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def hash_text(text: str) -> str:
    """Stable SHA-256 hash of a text block (prompt, acceptance test)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_manifest(path: Path, manifest: RunManifest) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    return path


def load_manifest(path: Path) -> RunManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunManifest.from_dict(data)
