"""CLI tests: init, TTY gate, task round trip with --check, mcp-config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octk.cli import main
from octk.config import ToolkitPaths, read_json
from octk.metrics import MetricsStore

EXPECTED_PERMISSIONS = [
    {"action": "shell", "resource": "octk approve *", "effect": "deny"},
    {"action": "edit", "resource": ".toolkit/approvals.json", "effect": "deny"},
    {"action": "edit", "resource": ".toolkit/metrics.json", "effect": "deny"},
    {"action": "edit", "resource": ".toolkit/specs/roadmap.md", "effect": "ask"},
]


@pytest.fixture
def cli_root(tmp_root: Path, monkeypatch) -> Path:
    """Point the CLI at the fenced tmp_root via OCTK_ROOT."""
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    return tmp_root


def _store(root: Path) -> MetricsStore:
    return MetricsStore(ToolkitPaths(root).metrics)


def test_init_in_tmp_cwd(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    del monkeypatch  # chdir alone is the OCTK_ROOT-free injection path
    assert main(["init"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert any("AGENTS.md" in rel for rel in created["created"])
    assert (tmp_path / ".toolkit" / "index.md").exists()
    assert main(["init"]) == 0
    created2 = json.loads(capsys.readouterr().out)
    assert created2["created"] == []


def test_approve_requires_tty(cli_root: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code = main(["approve", "item"])
    assert code == 2
    assert "terminal" in capsys.readouterr().err


def test_approve_list_ok_without_tty(cli_root: Path, capsys) -> None:
    assert main(["approve", "--list"]) == 0
    assert capsys.readouterr().out == ""


def test_task_round_trip_with_check(cli_root: Path, capsys) -> None:
    assert main(["task", "start", "demo", "--mode", "with_octk", "--model", "test"]) == 0
    rc = main(["task", "end", "--check", "python -c pass"])
    assert rc == 0
    task = _store(cli_root).load()["tasks"][0]
    assert task["check_cmd"] == "python -c pass"
    assert task["check_passed"] is True
    assert task["mode"] == "with_octk"
    assert task["model"] == "test"


def test_task_end_check_failure_records_false(cli_root: Path) -> None:
    main(["task", "start", "demo"])
    main(["task", "end", "--check", 'python -c "import sys; sys.exit(3)"'])
    task = _store(cli_root).load()["tasks"][0]
    assert task["check_passed"] is False


def test_task_active_conflict_fails(cli_root: Path) -> None:
    main(["task", "start", "one"])
    with pytest.raises(RuntimeError):
        _store(cli_root).start_task("two")


def test_mcp_config_v2_syntax(tmp_root: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    assert main(["mcp-config"]) == 0
    printed = capsys.readouterr().out
    json_body = printed.split("\n# notes")[0]
    config = json.loads(json_body)
    entry = config["mcp"]["servers"]["octk"]
    assert entry["type"] == "local"
    assert entry["codemode"] is False
    assert isinstance(entry["command"], list) and entry["command"]
    assert "enabled" not in entry
    perms = config["permissions"]
    assert perms == EXPECTED_PERMISSIONS


def test_standing_add(cli_root: Path, capsys) -> None:
    assert main(["standing", "add", "skills", "--tokens-in", "1200"]) == 0
    data = read_json(ToolkitPaths(cli_root).metrics)
    assert data["standing_costs"] == [{"label": "skills", "tokens_in": 1200}]


def test_report_out_flag(cli_root: Path, tmp_path) -> None:
    main(["task", "start", "T1", "--mode", "without_octk"])
    main(["task", "end"])
    out = tmp_path / "sub" / "report.md"
    assert main(["report", "--out", str(out)]) == 0
    assert "Run summary" in out.read_text(encoding="utf-8")


def test_handoff_cli_writes_and_prints(cli_root: Path, capsys) -> None:
    assert main(["handoff"]) == 0
    captured = capsys.readouterr()
    assert "octk session handoff" in captured.out
    assert "handoff written:" in captured.err
    assert (ToolkitPaths(cli_root).handoff).exists()


def test_handoff_cli_custom_out(cli_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "snapshot.md"
    assert main(["handoff", "--out", str(out)]) == 0
    assert "octk session handoff" in out.read_text(encoding="utf-8")
