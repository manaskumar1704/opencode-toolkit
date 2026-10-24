"""Roadmap gate tests: approvals, TTL, ambiguity, current-task bookkeeping."""

from __future__ import annotations

from pathlib import Path

import pytest

from octk.approvals import create_approval
from octk.roadmap import GateError, RoadmapError, parse_roadmap, set_status

NOW = 1_000_000.0


def test_done_without_approval_gates(tmp_root) -> None:
    with pytest.raises(GateError):
        set_status(tmp_root, "item", "done", now=NOW)
    entries = parse_roadmap(tmp_root)
    assert entries[0]["status"] == " "


def test_done_with_approval_succeeds_and_consumes(tmp_root) -> None:
    approval = create_approval(tmp_root, "item", now=NOW)
    line = set_status(tmp_root, "item", "done", now=NOW + 10)
    assert line.startswith("- [x] ")
    assert set_status.__module__  # sanity
    records = [
        r
        for r in __import__("octk.approvals", fromlist=["list_approvals"]).list_approvals(
            tmp_root
        )
        if r["id"] == approval["id"]
    ]
    assert records[0]["consumed_at"] is not None
    with pytest.raises(GateError):
        set_status(tmp_root, "item", "done", now=NOW + 20)  # no unconsumed left


def test_expired_approval_rejected(tmp_root) -> None:
    create_approval(tmp_root, "item", now=NOW)
    ttl = 120 * 60
    with pytest.raises(GateError):
        set_status(tmp_root, "item", "done", now=NOW + ttl + 60)


def test_ambiguous_substring_raises(tmp_root) -> None:
    roadmap = tmp_root / ".toolkit" / "specs" / "roadmap.md"
    roadmap.write_text(
        "# Roadmap\n- [ ] ship login\n- [ ] ship logout\n", encoding="utf-8"
    )
    with pytest.raises(RoadmapError):
        set_status(tmp_root, "ship", "done", now=NOW)


def test_second_current_refused(tmp_root) -> None:
    set_status(tmp_root, "item", "current", now=NOW)
    with pytest.raises(RoadmapError):
        set_status(tmp_root, "something totally different", "current", now=NOW)


def test_index_current_task_updated(tmp_root) -> None:
    index = tmp_root / ".toolkit" / "index.md"
    set_status(tmp_root, "item", "current", now=NOW)
    assert "**Current task:** item" in index.read_text(encoding="utf-8")
    with pytest.raises(GateError):
        set_status(tmp_root, "item", "done", now=NOW + 5)
    assert "**Current task:** item" in index.read_text(encoding="utf-8")


def test_done_updates_task_and_current_line(tmp_root) -> None:
    index = tmp_root / ".toolkit" / "index.md"
    set_status(tmp_root, "item", "current", now=NOW)
    create_approval(tmp_root, "item", now=NOW)
    set_status(tmp_root, "item", "done", now=NOW + 10)
    body = index.read_text(encoding="utf-8")
    assert "**Current task:** none" in body


def test_line_endings_preserved(tmp_root) -> None:
    roadmap = tmp_root / ".toolkit" / "specs" / "roadmap.md"
    roadmap.write_bytes(("# Roadmap\r\n- [ ] item\r\n").encode("utf-8"))
    create_approval(tmp_root, "item", now=NOW)
    set_status(tmp_root, "item", "current", now=NOW)
    raw = roadmap.read_bytes().decode("utf-8")
    assert "\r\n" in raw and "\n\n" not in raw
