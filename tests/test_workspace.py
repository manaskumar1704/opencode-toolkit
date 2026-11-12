"""Workspace isolation: standalone copy, oracle exclusion, leak detection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from benchmarks.workspace import (
    bwrap_available,
    create_workspace,
    oracle_leaks,
    remove_workspace,
    tool_input_text,
    wrap_command,
)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (path / "benchmarks").mkdir()
    (path / "benchmarks" / "oracle.py").write_text("SECRET\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_workspace_is_standalone_and_excludes_harness(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    workspace = create_workspace(repo, "run-1", parent=tmp_path / "ws")
    try:
        assert (workspace / "mod.py").is_file()
        assert not (workspace / "benchmarks").exists()
        assert (workspace / ".git").is_dir()
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        assert Path(top.stdout.strip()).resolve() == workspace.resolve()
    finally:
        remove_workspace(workspace)
    assert not workspace.exists()


def test_workspace_does_not_share_history_with_the_host(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    workspace = create_workspace(repo, "run-2", parent=tmp_path / "ws")
    try:
        (workspace / "new.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "workspace-only"], cwd=workspace, check=True)
        host_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        assert "workspace-only" not in host_log
    finally:
        remove_workspace(workspace)


def test_oracle_leaks_ignores_names_the_agent_can_already_see() -> None:
    oracle = "def test_shared():\n    assert 1\ndef test_hidden():\n    assert 2\n"
    visible = "def test_shared():\n    assert 1\n"

    assert oracle_leaks("test_shared", oracle, visible_text=visible) == []
    assert oracle_leaks("test_hidden", oracle, visible_text=visible) == [
        "oracle test name: test_hidden"
    ]


def test_oracle_leaks_detects_oracle_path() -> None:
    path = "benchmarks/tasks/simple_bug/oracle/acceptance.py"
    leaks = oracle_leaks(f"cat {path}", "", path)
    assert f"oracle path: {path}" in leaks
    assert any("oracle/acceptance.py" in leak for leak in leaks)


def test_oracle_leaks_detects_cloning_the_public_repo() -> None:
    leaks = oracle_leaks("git clone https://github.com/manaskumar1704/opencode-toolkit.git", "")
    assert leaks == ["git clone of the benchmark repository"]


def test_wrap_command_masks_the_host_repo_when_bwrap_exists(tmp_path: Path) -> None:
    host = tmp_path / "host"
    (host / "benchmarks").mkdir(parents=True)
    (host / ".git").mkdir()
    workspace = tmp_path / "ws"
    command = wrap_command(["true"], workspace, host)

    if bwrap_available():
        assert command[0] == "bwrap"
        assert str(host / "benchmarks") in command
        assert str(host / ".git") in command
        assert command[-1] == "true"
        assert str(workspace) in command
        assert "--tmpfs" in command and "/tmp" in command
    else:
        assert command == ["true"]


def test_oracle_leaks_detects_pytest_artifacts() -> None:
    leaks = oracle_leaks(
        "cat /tmp/pytest-of-user/pytest-1/test/oracle/acceptance.py", ""
    )
    assert any("pytest-of-" in leak for leak in leaks)


def _wrap(events: list[dict]) -> str:
    inner = "\n".join(json.dumps(event) for event in events)
    return json.dumps({"event": "agent_stdout", "data": inner}) + "\n"


def test_tool_input_text_extracts_only_tool_inputs() -> None:
    stream = _wrap(
        [
            {"type": "text", "part": {"text": "/tmp/pytest-of-user/x"}},
            {
                "type": "tool_use",
                "part": {
                    "tool": "read",
                    "state": {"input": {"path": "docs/v2/NOTES.md"}},
                },
            },
        ]
    )

    evidence = tool_input_text(stream)

    assert "docs/v2/NOTES.md" in evidence
    # Text the model saw is not evidence that it went looking for the oracle.
    assert "pytest-of-" not in evidence


def test_tool_input_text_flags_a_read_of_the_oracle() -> None:
    stream = _wrap(
        [
            {
                "type": "tool_use",
                "part": {
                    "tool": "read",
                    "state": {
                        "input": {"path": "/tmp/pytest-of-u/pytest-1/oracle/acceptance.py"}
                    },
                },
            }
        ]
    )

    leaks = oracle_leaks(tool_input_text(stream), "")

    assert any("pytest-of-" in leak for leak in leaks)


def test_tool_input_text_reads_a_plain_stream() -> None:
    stream = json.dumps(
        {
            "type": "tool_use",
            "part": {"tool": "shell", "state": {"input": {"command": "ls"}}},
        }
    )

    assert '"ls"' in tool_input_text(stream)
