"""Deterministic handoff snapshot: roadmap, git diff, runtime signal, approvals."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from octk.approvals import create_approval
from octk.config import ToolkitPaths
from octk.handoff import generate_handoff
from octk.metrics import MetricsStore
from octk.pantry import equip_spec, glance


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_handoff_writes_roadmap_git_signal_and_approvals(tmp_root) -> None:
    roadmap = ToolkitPaths(tmp_root).roadmap
    roadmap.write_text(
        "# Roadmap\n\n- [~] fix circuit breaker\n- [ ] publish handoff\n- [x] old task\n",
        encoding="utf-8",
    )
    _git(tmp_root, "init")
    _git(tmp_root, "config", "user.email", "octk@example.invalid")
    _git(tmp_root, "config", "user.name", "octk test")
    tracked = tmp_root / "tracked.py"
    tracked.write_text("value = 1\n", encoding="utf-8")
    _git(tmp_root, "add", "tracked.py")
    _git(tmp_root, "commit", "-m", "initial")
    tracked.write_text("value = 2\n", encoding="utf-8")

    store = MetricsStore(ToolkitPaths(tmp_root).metrics)
    store.log_tool_call("debug_inspect", 100, 50, kind="measured")
    create_approval(tmp_root, "publish handoff")

    text = generate_handoff(tmp_root)

    assert (ToolkitPaths(tmp_root).handoff).read_text(encoding="utf-8") == text
    assert "In progress `[~]`: fix circuit breaker" in text
    assert "Next pending `[ ]`: publish handoff" in text
    assert "tracked.py" in text
    assert "1 file changed" in text
    assert "debug_inspect" in text
    assert "publish handoff" in text
    assert "Read `.toolkit/handoff.md`" in text
    assert "/clear" in text


def test_handoff_round_trips_through_equip_spec(tmp_root) -> None:
    generate_handoff(tmp_root)
    assert "octk session handoff" in equip_spec(tmp_root, "handoff")
    assert 'Handoff: .toolkit/handoff.md' in glance(tmp_root).text


def test_handoff_includes_debug_strike_state(tmp_root) -> None:
    store = MetricsStore(ToolkitPaths(tmp_root).metrics)
    store.record_debug_call("sig", "pytest x | rc=1 | ValueError: boom", 10, 10)
    store.record_debug_call("sig", "pytest x | rc=1 | ValueError: boom", 10, 10)
    text = generate_handoff(tmp_root)
    assert "debug_inspect strikes=2" in text
    assert "ValueError: boom" in text


def test_handoff_custom_output_path(tmp_root) -> None:
    target = tmp_root / "artifacts" / "handoff.md"
    text = generate_handoff(tmp_root, target)
    assert target.read_text(encoding="utf-8") == text
    assert "octk session handoff" in text
