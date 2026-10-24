"""Metrics + report tests: medians, deltas, unattributed, standing costs."""

from __future__ import annotations

import json
from pathlib import Path

from octk.metrics import MetricsStore, approx_tokens
from octk.report import build_report, build_report_data

NOW = 1_000_000.0


def _store(path: Path) -> MetricsStore:
    return MetricsStore(path)


def test_approx_tokens() -> None:
    assert approx_tokens(0) == 0
    assert approx_tokens(1) == 1
    assert approx_tokens(4) == 1
    assert approx_tokens(5) == 2


def _fill(path: Path, mode: str, name: str, duration: float, raw: int, pruned: int,
          tokens: tuple[int, int] | None, turns: int | None, passed: bool | None) -> None:
    store = _store(path)
    store.start_task(name, mode=mode, model="test-model", started_at=NOW)
    store.log_tool_call("debug_inspect", raw, pruned, kind="measured", ts=NOW)
    store.end_task(
        status="completed",
        check_cmd="pytest -q",
        check_passed=passed,
        tokens_in=tokens[0] if tokens else None,
        tokens_out=tokens[1] if tokens else None,
        turns=turns,
        ended_at=NOW + duration,
    )


def test_unattributed_when_no_active_task(tmp_path: Path) -> None:
    store = _store(tmp_path / "metrics.json")
    store.log_tool_call("glance_pantry", 100, 80, kind="counterfactual")
    data = store.load()
    assert len(data["unattributed"]) == 1
    assert data["unattributed"][0]["tool"] == "glance_pantry"


def _synthetic_pair_file(path: Path) -> None:
    """3 paired tasks, known numbers (with = half of without)."""
    for name, duration, raw, pruned in (("T1", 10.0, 1000, 300), ("T2", 20.0, 2000, 700), ("T3", 30.0, 3000, 1100)):
        _fill(path, "with_octk", name, duration, raw, pruned, (100, 100), 4, True)
        _fill(path, "without_octk", name, duration * 2, raw, raw, (400, 400), 8, True)


def test_medians_and_deltas_exact(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    _synthetic_pair_file(path)
    data = build_report_data([path])
    s = data["summary"]
    assert s["with_octk"]["n"] == 3
    assert s["without_octk"]["n"] == 3
    assert s["with_octk"]["median_duration_s"] == 20.0
    assert s["without_octk"]["median_duration_s"] == 40.0
    assert s["with_octk"]["median_tokens"] == 200  # tokens_in+tokens_out = 100+100
    assert s["without_octk"]["median_tokens"] == 800  # 400+400
    assert s["with_octk"]["median_turns"] == 4
    assert s["without_octk"]["median_turns"] == 8
    assert s["with_octk"]["pass_rate"] == 1.0
    assert s["with_octk"]["median_tool_calls"] == 1

    paired = data["paired"]
    assert len(paired) == 3
    assert paired[0]["duration_delta_pct"] == pytest_approx(50.0)
    assert paired[0]["tokens_delta_pct"] == pytest_approx(75.0)
    assert paired[0]["turns_delta_pct"] == pytest_approx(50.0)


def pytest_approx(value: float) -> float:
    """Formatter helper so tests express intent exactly."""
    return round(value, 6)


def test_counterfactual_not_in_measured(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    store = _store(path)
    store.start_task("T1", mode="with_octk", model="m", started_at=NOW)
    store.log_tool_call("package_loader", 5000, 900, kind="measured", ts=NOW)
    store.log_tool_call("glance_pantry", 9000, 400, kind="counterfactual", ts=NOW)
    store.end_task(status="completed", ended_at=NOW + 5)
    data = build_report_data([path])
    measured_tools = [r["tool"] for r in data["measured_tools"]]
    counterfactual = [r["tool"] for r in data["counterfactual"]]
    assert "package_loader" in measured_tools
    assert "glance_pantry" not in measured_tools
    assert "glance_pantry" in counterfactual


def test_report_resume_line_absent_below_five_pairs(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    _synthetic_pair_file(path)  # 3 pairs only
    report = build_report([path])
    assert "Not enough paired tasks (3/5)" in report


def test_report_merges_two_files(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _fill(a, "with_octk", "T1", 10.0, 1000, 300, None, 4, True)
    _fill(b, "without_octk", "T1", 30.0, 1000, 1000, None, 9, False)
    report = build_report([a, b])
    assert "Not enough paired tasks (1/5)" in report
    data = build_report_data([a, b])
    paired = data["paired"][0]
    assert paired["duration_s"]["with"] == 10.0
    assert paired["duration_s"]["without"] == 30.0
    # tokens not recorded: approx chars/4 of each task's logged raw_chars (1000 both sides)
    assert paired["tokens"]["with"] == approx_tokens(1000)
    assert paired["tokens"]["without"] == approx_tokens(1000)
    assert paired["tokens_delta_pct"] == 0.0


def test_report_resume_line_present_at_five_pairs_and_honest_when_worse(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    for i in range(5):
        _fill(path, "with_octk", f"T{i}", 40.0, 1000, 300, None, 5, True)
        _fill(path, "without_octk", f"T{i}", 20.0, 1000, 1000, None, 3, True)
    report = build_report([path])
    assert "Not enough paired tasks" not in report
    assert "worse" in report


def test_standing_costs_recorded_and_reported(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    store = _store(path)
    store.add_standing("bare", 1000)
    store.add_standing("skills", 1200)
    store.add_standing("mcps", 1500)
    data = json.loads(store.load() and json.dumps(store.load()))
    assert [r["tokens_in"] for r in data["standing_costs"]] == [1000, 1200, 1500]
    report = build_report([path])
    assert "Standing context cost (turn-1 input tokens)" in report
    assert "| bare | 1000 |" in report
    assert "| skills | 1200 | +200 |" in report
    assert "| mcps | 1500 | +500 |" in report
    d = build_report_data([path])
    standing = {row["label"]: row for row in d["standing"]}
    assert standing["skills"]["delta_vs_bare"] == 200
    assert standing["mcps"]["delta_vs_bare"] == 500
