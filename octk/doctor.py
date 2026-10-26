"""Prefix-cache and approval-gate health checks (`octk doctor`)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import ToolkitPaths, read_json
from .sentinel import SENTINEL_END, SENTINEL_START

DYNAMIC_RE = re.compile(
    r"(?m)(\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b"
    r"|\*\*Current task:\*\*|generated\s+(?:at|on)\b)"
)
REQUIRED_PERMISSIONS = (
    ("shell", "octk approve *"),
    ("edit", ".toolkit/approvals.json"),
)


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _check_agents(root: Path) -> dict[str, str]:
    path = root / "AGENTS.md"
    if not path.exists():
        return _check("agents_static", "warn", "AGENTS.md missing; run `octk init`")
    text = path.read_text(encoding="utf-8")
    if (SENTINEL_START in text) != (SENTINEL_END in text):
        return _check("agents_static", "warn", "AGENTS.md has only one OCTK sentinel marker")
    dynamic = DYNAMIC_RE.search(text)
    if dynamic:
        return _check(
            "agents_static",
            "warn",
            f"dynamic/volatile text found: {dynamic.group(0)!r} (breaks prefix caching)",
        )
    block = text
    start, end = text.find(SENTINEL_START), text.find(SENTINEL_END)
    if start != -1 and end > start:
        block = text[start + len(SENTINEL_START) : end]
    if len(block.splitlines()) >= 30:
        return _check(
            "agents_static",
            "warn",
            f"managed AGENTS.md block is {len(block.splitlines())} lines (target < 30)",
        )
    return _check("agents_static", "pass", "AGENTS.md is static and cache-safe")


def _check_config(root: Path) -> dict[str, str]:
    path = ToolkitPaths(root).config
    if not path.exists():
        return _check("config_valid", "warn", ".toolkit/config.json missing; run `octk init`")
    data = read_json(path, None)
    if not isinstance(data, dict):
        return _check("config_valid", "warn", ".toolkit/config.json is not valid JSON")
    external = data.get("external_mcps", {})
    if not isinstance(external, dict):
        return _check("config_valid", "warn", "external_mcps must be an object")
    for name, spec in external.items():
        if not isinstance(spec, dict):
            return _check("config_valid", "warn", f"external_mcps[{name!r}] must be an object")
        command = spec.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) and part for part in command)
        ):
            return _check(
                "config_valid",
                "warn",
                f"external_mcps[{name!r}].command must be a non-empty string list",
            )
    return _check("config_valid", "pass", ".toolkit/config.json is valid")


def _check_permissions(root: Path) -> dict[str, str]:
    path = root / "opencode.json"
    if not path.exists():
        return _check("permissions_gate", "warn", "opencode.json missing; run `octk init`")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _check("permissions_gate", "warn", "opencode.json is not valid JSON")
    rules = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        return _check("permissions_gate", "warn", "opencode.json has no permissions rule list")
    missing = []
    for action, resource in REQUIRED_PERMISSIONS:
        if not any(
            isinstance(rule, dict)
            and rule.get("action") == action
            and rule.get("resource") == resource
            and rule.get("effect") == "deny"
            for rule in rules
        ):
            missing.append(f"{action}:{resource}")
    if missing:
        return _check(
            "permissions_gate",
            "warn",
            "missing deny rule(s): " + ", ".join(missing),
        )
    return _check("permissions_gate", "pass", "approval gate deny rules are present")


def run_doctor(root: Path) -> dict[str, Any]:
    """Return deterministic prefix-cache and gate integrity checks."""
    checks = [
        _check_agents(root),
        _check_config(root),
        _check_permissions(root),
    ]
    warnings = sum(1 for check in checks if check["status"] != "pass")
    return {
        "status": "pass" if warnings == 0 else "warn",
        "warnings": warnings,
        "checks": checks,
    }


def format_doctor(data: dict[str, Any]) -> str:
    """Human-readable pass/warn summary."""
    lines = [f"octk doctor: {str(data.get('status', 'warn')).upper()}"]
    for check in data.get("checks", []):
        lines.append(f"- [{check['status']}] {check['name']}: {check['detail']}")
    return "\n".join(lines) + "\n"
