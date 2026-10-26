"""Cache-hit telemetry and `octk doctor` prefix-cache/gate checks."""

from __future__ import annotations

import json
from pathlib import Path

from octk.cli import main
from octk.config import ToolkitPaths, read_json
from octk.doctor import run_doctor
from octk.metrics import MetricsStore
from octk.report import build_report, build_report_data


def _end_with_cache(root: Path, tokens_in: int, tokens_cached: int) -> None:
    store = MetricsStore(ToolkitPaths(root).metrics)
    store.start_task("cached-task", mode="with_octk", model="test")
    store.log_tool_call("debug_inspect", 100, 50, kind="measured")
    store.end_task(tokens_in=tokens_in, tokens_cached=tokens_cached, tokens_out=0)


def test_cache_hit_rate_math_and_report(tmp_root) -> None:
    _end_with_cache(tmp_root, tokens_in=100, tokens_cached=900)
    task = read_json(ToolkitPaths(tmp_root).metrics)["tasks"][0]
    assert task["tokens_cached"] == 900
    assert task["cache_hit_rate"] == 0.9

    path = ToolkitPaths(tmp_root).metrics
    data = build_report_data([path])
    assert data["summary"]["with_octk"]["median_cache_hit_rate"] == 0.9
    assert data["summary"]["with_octk"]["median_cache_hit_rate_pct"] == "90.0%"
    assert data["cache"][0]["cache_hit_rate"] == 0.9
    assert data["cache"][0]["cache_hit_rate_pct"] == "90.0%"
    report = build_report([path])
    assert "Prefix-cache hit rate" in report
    assert "90.0%" in report


def test_task_end_tokens_cached_flags(tmp_root, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    assert main(["task", "start", "demo"]) == 0
    assert main(["task", "end", "--tokens-in", "100", "--tokens-cached", "900"]) == 0
    task = read_json(ToolkitPaths(tmp_root).metrics)["tasks"][0]
    assert task["cache_hit_rate"] == 0.9

    assert main(["task", "start", "demo2"]) == 0
    assert main(["task", "end", "--tokens-in", "50", "--cache-read", "50"]) == 0
    tasks = read_json(ToolkitPaths(tmp_root).metrics)["tasks"]
    assert tasks[1]["tokens_cached"] == 50
    assert tasks[1]["cache_hit_rate"] == 0.5


def test_doctor_passes_clean_scaffold(tmp_root, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "octk doctor: PASS" in output
    assert "[pass] agents_static" in output
    assert "[pass] permissions_gate" in output


def test_doctor_flags_dynamic_agents_text(tmp_root, monkeypatch, capsys) -> None:
    agents = tmp_root / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n2026-10-27\n", encoding="utf-8")
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    assert main(["doctor"]) == 1
    assert "dynamic/volatile text" in capsys.readouterr().out


def test_doctor_flags_missing_deny_rules(tmp_root) -> None:
    path = tmp_root / "opencode.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["permissions"] = []
    path.write_text(json.dumps(config), encoding="utf-8")
    result = run_doctor(tmp_root)
    gate = next(c for c in result["checks"] if c["name"] == "permissions_gate")
    assert gate["status"] == "warn"
    assert "octk approve *" in gate["detail"]


def test_doctor_json_output_shape(tmp_root, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert {c["name"] for c in payload["checks"]} == {
        "agents_static",
        "config_valid",
        "permissions_gate",
    }
