"""Bench tests: fixtures, retention honesty, formatting, CLI behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octk import bench
from octk.cli import main as cli_main


def _fake_case(name: str, retention: float | None, skipped: str | None = None) -> dict:
    return {
        "name": name,
        "kind": "measured",
        "raw_chars": 1000,
        "pruned_chars": 100,
        "saved_chars": 900,
        "pct_reduction": 90.0,
        "approx_tokens_saved": 225,
        "signals": {"found": [], "missed": [], "total": 3, "retention": retention},
        "skipped": skipped,
    }


def _fake_results(cases: list[dict]) -> dict:
    return {
        "timestamp": "2026-10-25T00:00:00+00:00",
        "cases": cases,
        "schema_overhead": {
            "tools": 7,
            "name_bytes": 60,
            "description_bytes": 300,
            "schema_bytes": 900,
            "total_bytes": 1260,
        },
        "agents_md_bytes": None,
    }


def test_signal_check_finds_and_misses() -> None:
    signals = bench._signal_check("has alpha and gamma", ["alpha", "beta", "gamma"])
    assert signals["found"] == ["alpha", "gamma"]
    assert signals["missed"] == ["beta"]
    assert signals["retention"] == pytest.approx(2 / 3)


def test_signal_check_no_expected_is_full_retention() -> None:
    assert bench._signal_check("<anything>", [])["retention"] == 1.0


def test_pantry_case_saves_and_retains() -> None:
    case = bench._case_pantry()
    assert case["kind"] == "counterfactual"
    assert case["signals"]["retention"] == 1.0
    assert case["raw_chars"] > case["pruned_chars"] > 0
    assert 0 < case["pct_reduction"] < 100
    assert "extra_notes" in case["signals"]["found"]


def test_debug_case_saves_and_retains() -> None:
    case = bench._case_debug()
    assert case["kind"] == "measured"
    assert case["signals"]["retention"] == 1.0, case["signals"]["missed"]
    assert case["raw_chars"] > case["pruned_chars"] > 0
    assert case["skipped"] is None
    assert bench.DEBUG_SENTINEL in case["signals"]["found"]


def test_debug_fixture_runs_failing_test(tmp_path: Path) -> None:
    bench._make_debug_fixture(tmp_path)
    test_file = tmp_path / "tests" / "test_broken.py"
    assert test_file.exists()
    assert bench.DEBUG_SENTINEL in test_file.read_text(encoding="utf-8")


def test_pantry_fixture_inflates_files(tmp_path: Path) -> None:
    bench._make_pantry_fixture(tmp_path)
    arch = tmp_path / ".toolkit" / "specs" / "architecture.md"
    assert arch.stat().st_size > 5000
    assert (tmp_path / ".toolkit" / "skills" / "extra_notes.md").exists()


def test_run_tool_bench_pantry_only(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# bench root\n", encoding="utf-8")
    results = bench.run_tool_bench(tmp_path, cases=["pantry_glance"])
    names = [c["name"] for c in results["cases"]]
    assert names == ["pantry_glance"]
    assert results["schema_overhead"]["tools"] == 8
    assert isinstance(results["agents_md_bytes"], int)
    json.dumps(results)  # must be JSON-serializable


def test_run_tool_bench_unknown_case(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown case"):
        bench.run_tool_bench(tmp_path, cases=["nope"])


def test_schema_overhead_seven_tools() -> None:
    head = bench._schema_overhead()
    assert head["tools"] == 8
    assert head["total_bytes"] > 0
    assert head["schema_bytes"] > 0


def test_format_bench_honest_markers(tmp_path: Path) -> None:
    results = bench.run_tool_bench(tmp_path, cases=["pantry_glance"])
    text = bench.format_bench(results)
    assert text.startswith("# octk tool bench report")
    assert "| pantry_glance | counterfactual |" in text
    assert "Schema overhead" in text
    assert "retention" in text
    assert "estimate" in text
    assert "AGENTS.md root injection: not present" in text


@pytest.mark.browser
def test_browser_case_saves_and_retains() -> None:
    case = bench._case_browser()
    if case["skipped"]:
        pytest.skip(case["skipped"])
    assert case["signals"]["retention"] == 1.0, case["signals"]["missed"]
    assert case["raw_chars"] > case["pruned_chars"] > 100


def test_cli_bench_exit_one_on_lost_signals(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        bench,
        "run_tool_bench",
        lambda root: _fake_results([_fake_case("debug_pruning", 0.5)]),
    )
    out_path = tmp_path / "b.md"
    code = cli_main(["bench", "tools", "--out", str(out_path)])
    assert code == 1
    assert out_path.exists()
    assert "debug_pruning" in out_path.read_text(encoding="utf-8")


def test_cli_bench_skipped_case_never_fails(monkeypatch, tmp_path: Path) -> None:
    case = _fake_case("browser_pruning", None, skipped="chromium not installed")
    monkeypatch.setattr(bench, "run_tool_bench", lambda root: _fake_results([case]))
    assert cli_main(["bench", "tools", "--out", str(tmp_path / "b.md")]) == 0


def test_cli_bench_exit_zero_and_json(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        bench,
        "run_tool_bench",
        lambda root: _fake_results([_fake_case("debug_pruning", 1.0)]),
    )
    code = cli_main(["bench", "tools", "--json", "--out", str(tmp_path / "b.md")])
    assert code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)  # stdout is pure JSON
    assert payload["cases"][0]["name"] == "debug_pruning"
    assert "bench report written" in captured.err
