"""Audit workflow: freshness, instruct (no exec), subprocess (fake runner)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from octk.audit import AuditResult, graph_is_fresh, run_audit_workflow
from octk.runtime.safety import CommandResult

NOW = 1_000_000.0


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "graphify-out").mkdir()
    return tmp_path


def _graph(root: Path) -> Path:
    return root / "graphify-out" / "GRAPH_REPORT.md"


def _write_graph(project: Path) -> Path:
    graph = _graph(project)
    graph.write_text("graph", encoding="utf-8")
    return graph


def test_missing_graph_is_stale(project) -> None:
    fresh, why = graph_is_fresh(project, {"graph_report_paths": ["graphify-out/GRAPH_REPORT.md"]})
    assert fresh is False and why == "missing"


def test_fresh_graph(project) -> None:
    graph = _write_graph(project)
    os.utime(graph, (NOW + 10, NOW + 10))
    os.utime(project / "app.py", (NOW, NOW))
    fresh, _ = graph_is_fresh(project, {"graph_report_paths": ["graphify-out/GRAPH_REPORT.md"]})
    assert fresh is True


def test_stale_graph(project) -> None:
    graph = _write_graph(project)
    os.utime(graph, (NOW, NOW))
    os.utime(project / "app.py", (NOW + 10, NOW + 10))
    fresh, _ = graph_is_fresh(project, {"graph_report_paths": ["graphify-out/GRAPH_REPORT.md"]})
    assert fresh is False


CONFIG = {
    "audit_mode": "instruct",
    "graph_cmd": "graphify",
    "audit_cmd": "ponytail-review",
    "graph_report_paths": ["graphify-out/GRAPH_REPORT.md"],
}


def test_instruct_mode_never_executes(project) -> None:
    calls = []
    fake = lambda argv, root, allowed, timeout_s: calls.append(argv) or CommandResult("", "", 0)  # noqa: E731
    os.utime(_write_graph(project), (NOW, NOW))
    os.utime(project / "app.py", (NOW + 1, NOW + 1))
    result = run_audit_workflow(project, CONFIG, runner=fake)
    assert calls == []
    assert "/graphify ." in result.text and "/ponytail-review" in result.text
    assert "stale" in result.text


def test_instruct_fresh_text(project) -> None:
    graph = _write_graph(project)
    os.utime(graph, (NOW + 5, NOW + 5))
    os.utime(project / "app.py", (NOW, NOW))
    result = run_audit_workflow(project, CONFIG, runner=lambda *a: None)
    assert "Graph is fresh" in result.text


def test_subprocess_stale_runs_graph_first(project) -> None:
    calls: list[list[str]] = []
    fake = lambda argv, root, allowed, timeout_s: calls.append(list(argv)) or CommandResult("ok", "", 0)  # noqa: E731
    which = lambda name: f"/usr/bin/{name}"  # noqa: E731
    sub = {**CONFIG, "audit_mode": "subprocess"}
    graph = _write_graph(project)
    os.utime(graph, (NOW, NOW))
    os.utime(project / "app.py", (NOW + 1, NOW + 1))
    result = run_audit_workflow(project, sub, runner=fake, which_fn=which)
    assert [c[0] for c in calls] == ["graphify", "ponytail-review"]
    assert result.raw_chars >= 0


def test_subprocess_fresh_skips_graph(project) -> None:
    calls: list[list[str]] = []
    fake = lambda argv, root, allowed, timeout_s: calls.append(list(argv)) or CommandResult("ok", "", 0)  # noqa: E731
    which = lambda name: f"/usr/bin/{name}"  # noqa: E731
    sub = {**CONFIG, "audit_mode": "subprocess"}
    graph = _write_graph(project)
    os.utime(graph, (NOW + 10, NOW + 10))
    os.utime(project / "app.py", (NOW, NOW))
    run_audit_workflow(project, sub, runner=fake, which_fn=which)
    assert [c[0] for c in calls] == ["ponytail-review"]


def test_subprocess_refuses_foreign_cmd(project) -> None:
    sub = {**CONFIG, "audit_mode": "subprocess"}
    result = run_audit_workflow(project, sub, audit_cmd="evil-cmd", runner=lambda *a: None)
    assert isinstance(result, AuditResult)
    assert "refused" in result.text
