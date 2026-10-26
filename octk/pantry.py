"""Lazy-loaded pantry: glance + equip."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import ToolkitPaths, load_config

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class NameError(ValueError):  # noqa: A001 - literal stdlib-shadowing is intentional
    """Raised when a spec/skill name is invalid or traversal-like."""


@dataclass
class PantryResult:
    text: str
    raw_chars: int
    pruned_chars: int


def _desc_from_md(text: str) -> str:
    """Frontmatter description, else first heading, else first line; 80 chars."""
    fm_desc = re.search(
        r"(?m)^description:\s*(.+)$", text
    )
    if fm_desc:
        raw = fm_desc.group(1).strip('"')
    else:
        heading = re.search(r"(?m)^#\s+(.+)$", text)
        raw = heading.group(1) if heading else (text.strip().splitlines() or [""])[0]
    return raw[:80]


def _dir_listing(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".md")


def glance(root: Path) -> PantryResult:
    """Index summary plus skills/specs inventories and honest size delta."""
    paths = ToolkitPaths(root)
    parts: list[str] = []
    if paths.index.exists():
        parts.append(paths.index.read_text(encoding="utf-8").rstrip())
    skills: list[str] = []
    for path in _dir_listing(paths.skills):
        if path.name == ".gitkeep":
            continue
        skills.append(f"{path.stem} ({_desc_from_md(path.read_text(encoding='utf-8'))})")
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    parts.append(
        "Specs: "
        + ", ".join(p.stem for p in _dir_listing(paths.specs))
        + " (names only; use equip_spec to load)"
    )
    external = load_config(root).get("external_mcps", {})
    if isinstance(external, dict) and external:
        items: list[str] = []
        for name in sorted(external):
            spec = external[name] if isinstance(external[name], dict) else {}
            description = str(spec.get("description", "no description")).splitlines()[0][:80]
            items.append(f"{name} ({description})")
        parts.append(
            "External MCPs (lazy; use equip_external_mcp): " + ", ".join(items)
        )
    if paths.handoff.exists():
        parts.append('Handoff: .toolkit/handoff.md (use equip_spec("handoff"))')
    text = "\n".join(parts)
    raw_chars = 0
    for path in [paths.index, *paths.specs.rglob("*"), *paths.skills.rglob("*")]:
        if path.is_file():
            raw_chars += path.stat().st_size
    if paths.handoff.exists():
        raw_chars += paths.handoff.stat().st_size
    return PantryResult(text=text, raw_chars=raw_chars, pruned_chars=len(text))


def _resolve(directory: Path, name: str, kind: str) -> Path:
    if not NAME_RE.match(name):
        raise NameError(f"invalid {kind} name {name!r}: must match ^[A-Za-z0-9_-]+$")
    return directory / f"{name}.md"


def equip(root: Path, name: str, kind: str) -> str:
    """Load one spec/skill file by validated name."""
    paths = ToolkitPaths(root)
    directory = paths.specs if kind == "spec" else paths.skills
    if kind == "spec" and name == "handoff":
        if not NAME_RE.match(name):
            raise NameError(f"invalid {kind} name {name!r}")
        if not paths.handoff.exists():
            raise NameError(
                'handoff not found; run `octk handoff` first or use equip_spec("architecture")'
            )
        return paths.handoff.read_text(encoding="utf-8")
    path = _resolve(directory, name, kind)
    if not path.exists():
        available = ", ".join(p.stem for p in _dir_listing(directory)) or "(none)"
        raise NameError(f"unknown {kind} {name!r}. Available: {available}")
    return path.read_text(encoding="utf-8")


def equip_spec(root: Path, name: str) -> str:
    """Load .toolkit/specs/<name>.md."""
    return equip(root, name, "spec")


def equip_skill(root: Path, name: str) -> str:
    """Load .toolkit/skills/<name>.md (extras only, not native skills)."""
    return equip(root, name, "skill")
