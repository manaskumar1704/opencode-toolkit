"""Prefix-cache and approval-gate health checks (`octk doctor`)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import ToolkitPaths, read_json
from .sentinel import SENTINEL_END, SENTINEL_START

DYNAMIC_RE = re.compile(
    r"(?m)(\b(?:19|20)\d{2}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b"
    r"|\*\*Current task:\*\*|generated\s+(?:at|on)\b)"
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
    from .adapters import permissions_gate

    status, detail = permissions_gate(root)
    return _check("permissions_gate", status, detail)


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
