"""Idempotent project scaffold for octk-managed state."""

from __future__ import annotations

import json
from pathlib import Path

from .adapters import scaffold_managed_files
from .config import DEFAULT_CONFIG, load_config
from .sentinel import upsert_sentinel_block
from .templates import (
    ACCEPTANCE_MD_TEMPLATE,
    ARCH_MD_TEMPLATE,
    FLOW_MD_TEMPLATE,
    INDEX_MD_TEMPLATE,
    ROADMAP_MD_TEMPLATE,
    render_agents_md,
)

_MANAGED_FILES = {
    ".toolkit/specs/architecture.md": ARCH_MD_TEMPLATE,
    ".toolkit/specs/user_flow.md": FLOW_MD_TEMPLATE,
    ".toolkit/specs/acceptance.md": ACCEPTANCE_MD_TEMPLATE,
    ".toolkit/specs/roadmap.md": ROADMAP_MD_TEMPLATE,
}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _render_agents(root: Path) -> str:
    cfg = load_config(root)
    always_on = list(cfg.get("always_on_skills", []))
    server = str(cfg.get("server_name", "octk"))
    return render_agents_md(server, always_on)


def _append_gitignore_once(root: Path) -> bool:
    """Append octk runtime files to .gitignore once; True when changed."""
    gitignore = root / ".gitignore"
    wanted = (".toolkit/metrics.json", ".toolkit/approvals.json", ".toolkit/handoff.md")
    if gitignore.exists():
        body = gitignore.read_text(encoding="utf-8")
    else:
        body = ""
    lines = body.splitlines()
    missing = [w for w in wanted if w not in lines]
    if not missing:
        return False
    body = body.rstrip("\r\n") + ("\n" if body else "") + "\n".join(missing) + "\n"
    _write_text(gitignore, body)
    return True


def _upsert_managed(root: Path, rel: str, content: str, force: bool) -> str | None:
    """Sentinel-preserving write for AGENTS.md / index.md / agent files.

    Returns "created" when written/changed, "skipped" when already present.
    """
    path = root / rel
    if path.exists() and not force:
        return "skipped"
    if upsert_sentinel_block(path, content):
        return "created"
    return "skipped"


def init_repo(root: Path, force: bool = False) -> dict[str, list[str]]:
    """Create octk files under root; skip existing unless force."""
    created: list[str] = []
    skipped: list[str] = []

    config_rel = ".toolkit/config.json"
    config_path = root / config_rel
    if config_path.exists() and not force:
        skipped.append(config_rel)
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        created.append(config_rel)

    # Sentinel-preserved: AGENTS.md and .toolkit/index.md
    for rel, content in (
        ("AGENTS.md", _render_agents(root)),
        (".toolkit/index.md", INDEX_MD_TEMPLATE),
    ):
        outcome = _upsert_managed(root, rel, content, force)
        if outcome == "created":
            created.append(rel)
        elif outcome == "skipped":
            skipped.append(rel)

    # Plain managed files: skip existing unless force.
    for rel, template in _MANAGED_FILES.items():
        path = root / rel
        if path.exists() and not force:
            skipped.append(rel)
            continue
        _write_text(path, template or "")
        created.append(rel)

    # Harness-specific files (config, agents, commands) come from the adapter.
    for rel, content, mode in scaffold_managed_files():
        if mode == "sentinel":
            outcome = _upsert_managed(root, rel, content, force)
            if outcome == "created":
                created.append(rel)
            elif outcome == "skipped":
                skipped.append(rel)
            continue
        path = root / rel
        if path.exists() and not force:
            skipped.append(rel)
            continue
        _write_text(path, content)
        created.append(rel)

    skills_keep = ".toolkit/skills/.gitkeep"
    skills_dir = root / ".toolkit" / "skills"
    if skills_dir.exists() and not force:
        skipped.append(skills_keep)
    else:
        skills_dir.mkdir(parents=True, exist_ok=True)
        (root / skills_keep).touch()
        created.append(skills_keep)

    if _append_gitignore_once(root):
        created.append(".gitignore(updated)")

    return {"created": sorted(created), "skipped": sorted(skipped)}
