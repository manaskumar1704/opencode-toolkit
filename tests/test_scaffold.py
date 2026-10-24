"""Scaffold tests: creation, idempotence, rendering, gitignore."""

from __future__ import annotations

import json
from pathlib import Path

from octk.scaffold import init_repo


EXPECTED = [
    ".opencode/commands/ideate.md",
    "AGENTS.md",
    ".toolkit/index.md",
    ".toolkit/config.json",
    ".toolkit/specs/architecture.md",
    ".toolkit/specs/user_flow.md",
    ".toolkit/specs/acceptance.md",
    ".toolkit/specs/roadmap.md",
    ".toolkit/skills/.gitkeep",
]


def test_all_files_created(tmp_path: Path) -> None:
    result = init_repo(tmp_path)
    for rel in EXPECTED:
        assert (tmp_path / rel).exists(), rel
        assert rel in result["created"]


def test_idempotent(tmp_path: Path) -> None:
    init_repo(tmp_path)
    result = init_repo(tmp_path)
    assert result["created"] == []
    assert set(EXPECTED) <= set(result["skipped"])


def test_force_recreates(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "AGENTS.md").write_text("stale", encoding="utf-8")
    init_repo(tmp_path, force=True)
    assert "stale" not in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")


def test_gitignore_appended_once(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("x.txt\n", encoding="utf-8")
    init_repo(tmp_path)
    body = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".toolkit/metrics.json" in body and ".toolkit/approvals.json" in body
    init_repo(tmp_path, force=True)
    body2 = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert body2.count(".toolkit/metrics.json") == 1


def test_agents_md_rules(tmp_path: Path) -> None:
    init_repo(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 25
    assert "taste" not in text
    assert "{{ALWAYS_ON}}" not in text
    assert "none" in text.splitlines()[7] or "none" in text


def test_always_on_rendering(tmp_path: Path) -> None:
    config = {"always_on_skills": ["budget-owl"]}
    (tmp_path / ".toolkit").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".toolkit" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    init_repo(tmp_path)
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "budget-owl" in text


def test_config_json_written_from_defaults(tmp_path: Path) -> None:
    init_repo(tmp_path)
    cfg = json.loads((tmp_path / ".toolkit" / "config.json").read_text(encoding="utf-8"))
    assert cfg["always_on_skills"] == []
    assert cfg["server_name"] == "octk"
    assert cfg["audit_mode"] == "instruct"
    assert "graphify-out/GRAPH_REPORT.md" in cfg["graph_report_paths"]
