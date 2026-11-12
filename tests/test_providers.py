"""Provider detection tests: Graphify and Ponytail are detected, never executed."""

from __future__ import annotations

import os
from pathlib import Path

from octk.adapters.opencode import discover
from octk.providers import graphify, ponytail


def _config() -> dict:
    return {
        "graph_cmd": "graphify",
        "graph_report_paths": ["graphify-out/GRAPH_REPORT.md", "graphify-out/graph.json"],
    }


# -- Graphify --------------------------------------------------------------


def test_graphify_absent_is_cold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    status = graphify.detect(tmp_path, _config())

    assert status.available is False
    assert status.state == "cold"
    assert "not on PATH" in status.detail
    assert status.version is None


def test_graphify_warm_when_report_is_newer(tmp_path: Path) -> None:
    report = tmp_path / "graphify-out" / "GRAPH_REPORT.md"
    report.parent.mkdir(parents=True)
    report.write_text("# graph", encoding="utf-8")
    source = tmp_path / "module.py"
    source.write_text("x = 1\n", encoding="utf-8")
    os.utime(source, (1_000, 1_000))
    os.utime(report, (2_000, 2_000))

    status = graphify.detect(tmp_path, _config())

    assert status.state == "warm"


def test_graphify_stale_when_source_is_newer(tmp_path: Path) -> None:
    report = tmp_path / "graphify-out" / "GRAPH_REPORT.md"
    report.parent.mkdir(parents=True)
    report.write_text("# graph", encoding="utf-8")
    source = tmp_path / "module.py"
    source.write_text("x = 1\n", encoding="utf-8")
    os.utime(report, (1_000, 1_000))
    os.utime(source, (2_000, 2_000))

    status = graphify.detect(tmp_path, _config())

    assert status.state == "stale"
    assert "incremental" in status.detail


def test_graphify_record_marks_activation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    record = graphify.capability_record(tmp_path, _config(), "2026-11-09")

    assert record["id"] == "cli:graphify/graphify"
    assert record["type"] == "cli"
    assert record["activation"] == "disabled"
    assert record["provenance"] == "discovered"
    assert record["verified_at"] == "2026-11-09"
    assert record["invocation"]["state"] == "cold"


# -- Ponytail --------------------------------------------------------------


def test_ponytail_absent_has_no_records(tmp_path: Path) -> None:
    status = ponytail.detect(tmp_path)

    assert status.available is False
    assert status.state is None
    assert ponytail.capability_records(tmp_path) == []


def test_ponytail_skill_is_detected_with_version(tmp_path: Path) -> None:
    skill = tmp_path / ".opencode" / "skills" / "ponytail"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ponytail\nversion: 1.4.2\ndescription: Review\n---\n",
        encoding="utf-8",
    )

    status = ponytail.detect(tmp_path)

    assert status.available is True
    assert status.state == "skill"
    assert status.version == "1.4.2"
    # The skill adapter already lists it; do not duplicate the L0 entry.
    assert ponytail.capability_records(tmp_path) == []


def test_ponytail_plugin_produces_one_record(tmp_path: Path) -> None:
    plugins = tmp_path / ".opencode" / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "ponytail.js").write_text("export default {}", encoding="utf-8")

    status = ponytail.detect(tmp_path)
    records = ponytail.capability_records(tmp_path, today="2026-11-09")

    assert status.state == "plugin"
    assert len(records) == 1
    assert records[0]["id"] == "plugin:ponytail/ponytail"
    assert records[0]["verified_at"] == "2026-11-09"


def test_ponytail_detected_from_opencode_json(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text(
        '{"plugin": ["ponytail-plugin"]}', encoding="utf-8"
    )

    assert ponytail.detect(tmp_path).state == "plugin"


# -- integration -----------------------------------------------------------


def test_discovery_includes_graphify_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    (tmp_path / ".opencode").mkdir()
    (tmp_path / "opencode.json").write_text("{}", encoding="utf-8")

    ids = {record.id for record in discover(tmp_path)}

    assert "cli:graphify/graphify" in ids


def test_detection_creates_no_files(tmp_path: Path) -> None:
    before = {path for path in tmp_path.rglob("*")}

    graphify.detect(tmp_path, _config())
    ponytail.detect(tmp_path)

    assert {path for path in tmp_path.rglob("*")} == before
