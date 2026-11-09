"""OpenCode discovery adapter.

Reads the on-disk layout OpenCode already uses. It does not connect to MCP
servers, execute skills, or write configuration - discovery is not execution.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from ..capabilities import MAX_DESCRIPTION, RegistryError, record_from_dict
from ..config import load_config
from ..providers import graphify, ponytail
from .base import DiscoveryResult

HEAD_CHARS = 4096
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _slug(value: str) -> str:
    """Make a value safe for the ``type:provider/name`` id shape."""
    return _SLUG_RE.sub("-", value).strip("-.") or "unnamed"


def _head(path: Path) -> str:
    """Read at most HEAD_CHARS so discovery stays cheap on large files."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(HEAD_CHARS)
    except OSError:
        return ""


def _frontmatter(text: str, key: str) -> str:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+)$", text)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def _description(text: str, fallback: str) -> str:
    raw = _frontmatter(text, "description")
    if not raw:
        heading = re.search(r"(?m)^#\s+(.+)$", text)
        raw = heading.group(1).strip() if heading else fallback
    return raw[:MAX_DESCRIPTION]


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


class OpenCodeAdapter:
    """Discovers skills, commands, MCP servers, and octk-native docs."""

    id = "opencode"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # -- contract ---------------------------------------------------------

    def detect(self) -> dict[str, Any] | None:
        opencode_dir = self.root / ".opencode"
        config = self.root / "opencode.json"
        if not opencode_dir.is_dir() and not config.is_file():
            return None
        return {
            "harness": self.id,
            "root": str(self.root),
            "opencode_json": config.is_file(),
            "skills_dir": (opencode_dir / "skills").is_dir(),
            "commands_dir": (opencode_dir / "commands").is_dir(),
        }

    def discover_capabilities(self) -> DiscoveryResult:
        if self.detect() is None:
            return DiscoveryResult(
                (), "no supported harness detected (no .opencode/ or opencode.json)"
            )
        today = date.today().isoformat()
        raw: list[dict[str, Any]] = []
        raw.extend(self._skills(today))
        raw.extend(self._commands(today))
        raw.extend(self._mcp_servers(today))
        raw.extend(self._octk_native(today))
        raw.extend(self._providers(today))

        records: list[Any] = []
        skipped: list[str] = []
        for item in raw:
            try:
                records.append(record_from_dict(item, scope="project"))
            except RegistryError as exc:
                skipped.append(str(exc))
        reason = f"{len(skipped)} invalid record(s) skipped: {skipped[0]}" if skipped else None
        return DiscoveryResult(tuple(records), reason)

    def install_hints(self) -> list[str]:
        hints: list[str] = []
        if not (self.root / "opencode.json").is_file():
            hints.append(
                "Add opencode.json with an `mcp` block so OCTK can discover MCP servers."
            )
        if not (self.root / ".opencode" / "skills").is_dir():
            hints.append(
                "Add .opencode/skills/<name>/SKILL.md to make skills discoverable."
            )
        return hints

    # -- discovery --------------------------------------------------------

    def _skills(self, today: str) -> list[dict[str, Any]]:
        directory = self.root / ".opencode" / "skills"
        if not directory.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for entry in sorted(directory.iterdir()):
            skill_md = entry / "SKILL.md"
            if not entry.is_dir() or not skill_md.is_file():
                continue
            text = _head(skill_md)
            name = _slug(entry.name)
            provider = _slug(_frontmatter(text, "name") or entry.name)
            records.append(
                {
                    "id": f"skill:{provider}/{name}",
                    "type": "skill",
                    "name": entry.name,
                    "description": _description(text, entry.name),
                    "provider": provider,
                    "version": None,
                    "scope": "project",
                    "harness": ["opencode"],
                    "activation": "enabled",
                    "invocation": {
                        "method": "skill",
                        "command": None,
                        "schema_ref": _rel(self.root, skill_md),
                    },
                    "permissions": {"side_effects": ["read_only"], "requires_approval": False},
                    "cost": None,
                    "provenance": "discovered",
                    "verified_at": today,
                    "source_path": _rel(self.root, entry),
                }
            )
        return records

    def _commands(self, today: str) -> list[dict[str, Any]]:
        directory = self.root / ".opencode" / "commands"
        if not directory.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.md")):
            text = _head(path)
            name = _slug(path.stem)
            records.append(
                {
                    "id": f"command:opencode/{name}",
                    "type": "command",
                    "name": path.stem,
                    "description": _description(text, f"Command {path.stem}"),
                    "provider": "opencode",
                    "version": None,
                    "scope": "project",
                    "harness": ["opencode"],
                    "activation": "enabled",
                    "invocation": {
                        "method": "command",
                        "command": f"/{path.stem}",
                        "schema_ref": _rel(self.root, path),
                    },
                    "permissions": {"side_effects": ["read_only"], "requires_approval": False},
                    "cost": None,
                    "provenance": "discovered",
                    "verified_at": today,
                    "source_path": _rel(self.root, path),
                }
            )
        return records

    def _mcp_servers(self, today: str) -> list[dict[str, Any]]:
        config = self.root / "opencode.json"
        if not config.is_file():
            return []
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, dict):
            return []

        servers = data.get("mcp") or data.get("mcpServers") or {}
        if not isinstance(servers, dict):
            return []

        records: list[dict[str, Any]] = []
        for key in sorted(servers):
            spec = servers[key] if isinstance(servers[key], dict) else {}
            # Only the executable name is kept; arguments may carry secrets.
            raw_command = spec.get("command")
            if isinstance(raw_command, list) and raw_command:
                command = str(raw_command[0])
            elif isinstance(raw_command, str):
                command = raw_command
            else:
                command = None
            name = _slug(key)
            records.append(
                {
                    "id": f"mcp_server:{name}/{name}",
                    "type": "mcp_server",
                    "name": key,
                    "description": str(
                        spec.get("description") or f"MCP server {key} (lazy)"
                    )[:MAX_DESCRIPTION],
                    "provider": name,
                    "version": None,
                    "scope": "project",
                    "harness": ["opencode"],
                    "activation": "disabled" if spec.get("enabled") is False else "enabled",
                    "invocation": {
                        "method": "mcp",
                        "command": command,
                        "schema_ref": f"opencode.json#mcp.{key}",
                    },
                    "permissions": {"side_effects": ["unknown"], "requires_approval": False},
                    "cost": None,
                    "provenance": "discovered",
                    "verified_at": today,
                    "source_path": "opencode.json",
                }
            )
        return records

    def _octk_native(self, today: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        specs = self.root / ".toolkit" / "specs"
        if specs.is_dir():
            for path in sorted(specs.glob("*.md")):
                text = _head(path)
                records.append(
                    {
                        "id": f"octk_native:octk/spec-{_slug(path.stem)}",
                        "type": "octk_native",
                        "name": path.stem,
                        "description": _description(text, f"Spec {path.stem}"),
                        "provider": "octk",
                        "version": None,
                        "scope": "project",
                        "harness": ["opencode"],
                        "activation": "enabled",
                        "invocation": {
                            "method": "equip_spec",
                            "command": path.stem,
                            "schema_ref": _rel(self.root, path),
                        },
                        "permissions": {"side_effects": ["read_only"], "requires_approval": False},
                        "cost": None,
                        "provenance": "octk_provided",
                        "verified_at": today,
                        "source_path": _rel(self.root, path),
                    }
                )
        extras = self.root / ".toolkit" / "skills"
        if extras.is_dir():
            for path in sorted(extras.glob("*.md")):
                text = _head(path)
                records.append(
                    {
                        "id": f"octk_native:octk/skill-{_slug(path.stem)}",
                        "type": "octk_native",
                        "name": path.stem,
                        "description": _description(text, f"Skill {path.stem}"),
                        "provider": "octk",
                        "version": None,
                        "scope": "project",
                        "harness": ["opencode"],
                        "activation": "enabled",
                        "invocation": {
                            "method": "equip_skill",
                            "command": path.stem,
                            "schema_ref": _rel(self.root, path),
                        },
                        "permissions": {"side_effects": ["read_only"], "requires_approval": False},
                        "cost": None,
                        "provenance": "octk_provided",
                        "verified_at": today,
                        "source_path": _rel(self.root, path),
                    }
                )
        return records


    def _providers(self, today: str) -> list[dict[str, Any]]:
        """External providers: detection only, never execution."""
        config = load_config(self.root)
        records = [graphify.capability_record(self.root, config, today)]
        records.extend(ponytail.capability_records(self.root, config, today))
        return records


def discover(root: Path) -> DiscoveryResult:
    """Discover capabilities for a root using every available adapter."""
    return OpenCodeAdapter(root).discover_capabilities()
