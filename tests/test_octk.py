"""Tests for the EGM integration: sentinel upsert, AST drift, agents, set-effort."""

from __future__ import annotations

import re
from pathlib import Path

from octk import drift, sentinel
from octk.cli import main as cli_main
from octk.scaffold import init_repo
from octk.templates import AGENT_DEFAULTS, AGENT_NAMES


def test_sentinel_upsert_preserves_user_text(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(
        "<!-- OCTK:START -->\nold managed\n<!-- OCTK:END -->\n\n# My notes\nkeep me\n",
        encoding="utf-8",
    )
    changed = sentinel.upsert_sentinel_block(
        path, "<!-- OCTK:START -->\nnew managed\n<!-- OCTK:END -->\n"
    )
    assert changed is True
    text = path.read_text(encoding="utf-8")
    assert "new managed" in text
    assert "old managed" not in text
    assert "# My notes" in text
    assert "keep me" in text


def test_sentinel_upsert_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    content = "<!-- OCTK:START -->\nmanaged\n<!-- OCTK:END -->\n"
    assert sentinel.upsert_sentinel_block(path, content) is True
    assert sentinel.upsert_sentinel_block(path, content) is False


def test_init_force_preserves_user_notes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n\n# Handwritten notes\n", encoding="utf-8"
    )
    init_repo(tmp_path, force=True)
    assert "# Handwritten notes" in agents.read_text(encoding="utf-8")


def test_check_spec_drift_detects_undocumented(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "class Widget:\n    pass\n\n"
        "@app.get('/widgets')\n"
        "def list_widgets():\n    return []\n",
        encoding="utf-8",
    )
    result = drift.check_drift(tmp_path)
    assert "class Widget" in result.report
    assert "route app.get /widgets" in result.report
    assert result.raw_chars > 0


def test_agent_roster_is_four_roles() -> None:
    assert AGENT_NAMES == ["plan", "build", "explore", "verifier"]
    assert set(AGENT_DEFAULTS) == set(AGENT_NAMES)
    assert AGENT_DEFAULTS["plan"]["mode"] == "primary"
    assert AGENT_DEFAULTS["plan"]["model"] == "opencode-go/mimo-v2.6-pro"
    assert AGENT_DEFAULTS["build"]["mode"] == "primary"
    assert AGENT_DEFAULTS["build"]["model"] == "opencode-go/deepseek-v4-pro"
    assert AGENT_DEFAULTS["explore"]["mode"] == "subagent"
    assert AGENT_DEFAULTS["explore"]["effort"] == "medium"
    assert AGENT_DEFAULTS["verifier"]["mode"] == "subagent"
    assert AGENT_DEFAULTS["verifier"]["model"] == "opencode-go/deepseek-v4.1-flash"


def test_init_creates_all_agents(tmp_path: Path) -> None:
    init_repo(tmp_path)
    for name in AGENT_NAMES:
        path = tmp_path / ".opencode" / "agents" / f"{name}.md"
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert f"mode: {AGENT_DEFAULTS[name]['mode']}" in text, name
        assert f"effort: {AGENT_DEFAULTS[name]['effort']}" in text, name
        assert f"#{AGENT_DEFAULTS[name]['effort']}" in text, name


def test_set_effort_changes_and_preserves_file(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    monkeypatch.setenv("OCTK_ROOT", str(tmp_path))
    agent = tmp_path / ".opencode" / "agents" / "build.md"
    before = agent.read_text(encoding="utf-8")
    assert "effort: high" in before
    assert "opencode-go/deepseek-v4-pro#high" in before

    assert cli_main(["set-effort", "build", "max"]) == 0

    after = agent.read_text(encoding="utf-8")
    assert "effort: max" in after
    assert "opencode-go/deepseek-v4-pro#max" in after
    assert "effort: high" not in after
    # frontmatter + body otherwise intact
    assert "mode: primary" in after
    assert "glance_pantry" in after
    assert "coding workhorse" in after


def test_set_effort_inserts_when_missing(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path)
    monkeypatch.setenv("OCTK_ROOT", str(tmp_path))
    agent = tmp_path / ".opencode" / "agents" / "build.md"
    text = agent.read_text(encoding="utf-8")
    agent.write_text(re.sub(r"(?m)^effort:.*\n", "", text), encoding="utf-8")
    assert "effort:" not in agent.read_text(encoding="utf-8")

    assert cli_main(["set-effort", "build", "xhigh"]) == 0

    after = agent.read_text(encoding="utf-8")
    assert "effort: xhigh" in after
    assert "opencode-go/deepseek-v4-pro#xhigh" in after


def test_set_effort_rejects_unknown_agent(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path)
    monkeypatch.setenv("OCTK_ROOT", str(tmp_path))
    assert cli_main(["set-effort", "nope", "max"]) == 1


def test_set_model_updates_frontmatter(tmp_path: Path, monkeypatch) -> None:
    init_repo(tmp_path)
    monkeypatch.setenv("OCTK_ROOT", str(tmp_path))
    agent = tmp_path / ".opencode" / "agents" / "build.md"
    assert cli_main(["set-model", "build", "opencode-go/gpt-6-luna"]) == 0
    after = agent.read_text(encoding="utf-8")
    assert "model: opencode-go/gpt-6-luna" in after
    assert "effort: high" in after
