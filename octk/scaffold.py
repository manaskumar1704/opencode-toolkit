"""Idempotent project scaffold for octk-managed state."""

from __future__ import annotations

import json
from pathlib import Path

from .config import DEFAULT_CONFIG, load_config
from .templates import (
    ACCEPTANCE_MD_TEMPLATE,
    ARCH_MD_TEMPLATE,
    FLOW_MD_TEMPLATE,
    IDEATE_COMMAND_TEMPLATE,
    INDEX_MD_TEMPLATE,
    ROADMAP_MD_TEMPLATE,
    render_agents_md,
)

_MANAGED_FILES = {
    ".opencode/commands/ideate.md": IDEATE_COMMAND_TEMPLATE,
    "AGENTS.md": None,  # rendered
    ".toolkit/index.md": INDEX_MD_TEMPLATE,
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
    wanted = (".toolkit/metrics.json", ".toolkit/approvals.json")
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

    agents_rel = "AGENTS.md"
    agents_path = root / agents_rel
    if agents_path.exists() and not force:
        skipped.append(agents_rel)
    else:
        _write_text(agents_path, _render_agents(root))
        created.append(agents_rel)

    for rel, template in _MANAGED_FILES.items():
        if rel == "AGENTS.md":
            continue
        path = root / rel
        if path.exists() and not force:
            skipped.append(rel)
            continue
        _write_text(path, template or "")
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
