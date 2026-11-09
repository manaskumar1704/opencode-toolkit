"""Ponytail detection.

Ponytail is user-installed and user-owned. OCTK detects it and records where
it lives, and never duplicates its rules or review prompts.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from ..capabilities import MAX_DESCRIPTION
from . import ProviderStatus

ID = "ponytail"
_HEAD_CHARS = 4096


def _head(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(_HEAD_CHARS)
    except OSError:
        return ""


def _frontmatter(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+)$", text)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def _skill_dir(root: Path) -> Path | None:
    skills = root / ".opencode" / "skills"
    if not skills.is_dir():
        return None
    for entry in sorted(skills.iterdir()):
        if entry.is_dir() and ID in entry.name.casefold() and (entry / "SKILL.md").is_file():
            return entry
    return None


def _plugin_hit(root: Path) -> str | None:
    plugins = root / ".opencode" / "plugins"
    if plugins.is_dir():
        for entry in sorted(plugins.iterdir()):
            if ID in entry.name.casefold():
                return f".opencode/plugins/{entry.name}"

    config = root / "opencode.json"
    if config.is_file():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict):
            entries = data.get("plugin") or data.get("plugins") or []
            if isinstance(entries, list):
                for item in entries:
                    if isinstance(item, str) and ID in item.casefold():
                        return f"opencode.json plugin entry {item!r}"
    return None


def detect(root: Path, config: dict[str, Any] | None = None) -> ProviderStatus:
    """Report whether Ponytail is present, and in what form."""
    skill = _skill_dir(root)
    if skill is not None:
        version = _frontmatter(_head(skill / "SKILL.md"), "version") or None
        return ProviderStatus(
            id=ID,
            available=True,
            version=version,
            detail=f"detected as a skill at {skill.relative_to(root)}",
            state="skill",
        )

    plugin = _plugin_hit(root)
    if plugin is not None:
        return ProviderStatus(
            id=ID,
            available=True,
            version=None,
            detail=f"detected as a plugin via {plugin}",
            state="plugin",
        )

    return ProviderStatus(
        id=ID,
        available=False,
        version=None,
        detail="not detected as a skill, plugin, or opencode.json entry",
        state=None,
    )


def capability_records(
    root: Path, config: dict[str, Any] | None = None, today: str | None = None
) -> list[dict[str, Any]]:
    """Registry records for Ponytail.

    A Ponytail *skill* is already discovered by the skill adapter, so this
    returns nothing for that case - duplicating it would double the L0 entry.
    """
    status = detect(root, config)
    if status.state != "plugin":
        return []
    return [
        {
            "id": f"plugin:{ID}/{ID}",
            "type": "plugin",
            "name": ID,
            "description": (
                "Over-engineering and code-reuse review plugin, owned and "
                "installed by the user"
            )[:MAX_DESCRIPTION],
            "provider": ID,
            "version": status.version,
            "scope": "project",
            "harness": ["opencode"],
            "activation": "enabled",
            "invocation": {
                "method": "plugin",
                "command": None,
                "schema_ref": status.detail,
            },
            "permissions": {"side_effects": ["read_only"]},
            "cost": None,
            "provenance": "discovered",
            "verified_at": today or date.today().isoformat(),
            "source_path": None,
        }
    ]
