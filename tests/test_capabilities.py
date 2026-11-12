"""Capability Registry tests: validation, scope merge, disclosure, invariants.

The five invariants from the handoff (B3) each have a dedicated test below.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octk.capabilities import (
    L0_QUERY_DESC,
    MAX_L0_LINE,
    RegistryError,
    load_registry,
    merge_scopes,
    record_from_dict,
    register,
    render,
    render_l0,
    render_l2,
    sync_discovered,
)


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "skill:demo/demo",
        "type": "skill",
        "name": "demo",
        "description": "A demo skill",
        "provider": "demo",
        "scope": "project",
        "harness": ["opencode"],
        "activation": "enabled",
        "invocation": {"method": "skill", "command": None, "schema_ref": "x"},
        "permissions": {"side_effects": ["read_only"]},
        "provenance": "discovered",
        "verified_at": "2026-11-09",
        "source_path": "x",
    }
    base.update(overrides)
    return base


def _write(path: Path, records: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "capabilities": records}), encoding="utf-8"
    )
    return path


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "user_index": tmp_path / "user.json",
        "project_index": tmp_path / "project.json",
        "local_index": tmp_path / "local.json",
    }


# -- invariant 1: loading never executes a capability ----------------------


def test_load_never_executes(tmp_path: Path) -> None:
    sentinel = tmp_path / "ran"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
    script.chmod(0o755)

    paths = _paths(tmp_path)
    _write(paths["project_index"], [_record(source_path=str(script))])

    load_registry(tmp_path, **paths)

    assert not sentinel.exists()


# -- invariant 2: writes stay inside .toolkit/capabilities -----------------


def test_register_writes_only_under_capabilities(tmp_path: Path) -> None:
    before = {path for path in tmp_path.rglob("*") if path.is_file()}

    register(
        tmp_path,
        {
            "id": "cli:manual/tool",
            "type": "cli",
            "name": "tool",
            "description": "A manual tool",
        },
    )

    after = {path for path in tmp_path.rglob("*") if path.is_file()}
    created = after - before
    assert created
    assert all(".toolkit" in path.parts and "capabilities" in path.parts for path in created)


# -- invariant 3: duplicate ids resolve deterministically ------------------


def test_project_scope_overrides_user(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write(paths["user_index"], [_record(description="user version")])
    _write(paths["project_index"], [_record(description="project version")])

    registry = load_registry(tmp_path, **paths)

    record = registry.get("skill:demo/demo")
    assert record is not None
    assert record.description == "project version"
    assert record.scope == "project"
    assert registry.winners["skill:demo/demo"] == "project"


def test_local_scope_overrides_project(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write(paths["project_index"], [_record(description="project version")])
    _write(paths["local_index"], [_record(description="local version")])

    registry = load_registry(tmp_path, **paths)

    record = registry.get("skill:demo/demo")
    assert record is not None
    assert record.description == "local version"
    assert registry.winners["skill:demo/demo"] == "local"


def test_merge_is_order_independent_for_unique_ids() -> None:
    one = record_from_dict(_record(id="skill:a/a"), scope="user")
    two = record_from_dict(_record(id="skill:b/b"), scope="project")

    forward = merge_scopes([("user", [one]), ("project", [two])])
    backward = merge_scopes([("project", [two]), ("user", [one])])

    assert [r.id for r in forward.records] == [r.id for r in backward.records]


# -- invariant 4: null verified_at is listable -----------------------------


def test_null_verified_at_is_still_listable() -> None:
    record = record_from_dict(_record(verified_at=None), scope="project")
    text = render_l0([record])
    assert "demo" in text


# -- invariant 5: no index means manual-only operation ---------------------


def test_missing_index_degrades_to_empty_registry(tmp_path: Path) -> None:
    registry = load_registry(tmp_path, **_paths(tmp_path))
    assert registry.records == ()
    text = render_l0(registry.records)
    assert "No capabilities registered" in text
    assert "octk capabilities register" in text


def test_malformed_record_is_skipped_not_fatal(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write(paths["project_index"], [_record(), {"id": "not-a-valid-id"}])

    registry = load_registry(tmp_path, **paths)

    assert len(registry.records) == 1
    assert registry.records[0].id == "skill:demo/demo"


# -- validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"id": "no-colon-slash"},
        {"id": "Skill:Demo/Demo"},
        {"type": "unknown_type"},
        {"name": ""},
        {"description": ""},
        {"description": "x" * 141},
        {"activation": "on"},
        {"provenance": "invented"},
        {"scope": "team"},
        {"verified_at": "09/11/2026"},
        {"cost": {"context_tokens": 5}},
        {"cost": {"context_tokens": 5, "measurement": "estimated"}},
        {"harness": "opencode"},
        {"invocation": "nope"},
        {"permissions": ["read_only"]},
    ],
)
def test_invalid_records_are_rejected(override: dict[str, object]) -> None:
    with pytest.raises(RegistryError):
        record_from_dict(_record(**override), scope="project")


def test_measured_cost_is_accepted() -> None:
    record = record_from_dict(
        _record(cost={"context_tokens": 100, "measurement": "measured"}),
        scope="project",
    )
    assert record.cost == {"context_tokens": 100, "measurement": "measured"}


def test_global_scope_alias_normalises_to_user() -> None:
    record = record_from_dict(_record(scope="global"), scope="project")
    assert record.scope == "user"


def test_file_location_overrides_declared_scope(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _write(paths["user_index"], [_record(scope="project")])

    registry = load_registry(tmp_path, **paths)

    assert registry.records[0].scope == "user"


# -- disclosure levels -----------------------------------------------------


def test_l0_lines_never_exceed_limit() -> None:
    record = record_from_dict(_record(description="x" * 140), scope="project")
    for text in (render_l0([record]), render_l0([record], query="demo")):
        for line in text.splitlines():
            assert len(line) <= MAX_L0_LINE


def test_l0_inventory_omits_descriptions() -> None:
    record = record_from_dict(_record(description="a very long description"), scope="project")
    text = render_l0([record])
    assert "a very long description" not in text
    assert "demo" in text


def test_l0_query_adds_description() -> None:
    record = record_from_dict(_record(description="a very long description"), scope="project")
    text = render_l0([record], query="demo")
    assert "a very long description" in text


def test_l0_query_description_is_capped() -> None:
    record = record_from_dict(_record(description="d" * 140), scope="project")
    text = render_l0([record], query="demo")
    entry = next(line for line in text.splitlines() if line.startswith("demo"))
    assert "d" * (L0_QUERY_DESC + 1) not in entry


def test_resolve_by_name() -> None:
    record = record_from_dict(_record(), scope="project")
    registry = merge_scopes([("project", [record])])

    found, candidates = registry.resolve("demo")

    assert found == record
    assert candidates == []


def test_resolve_ambiguous_name_returns_candidates() -> None:
    one = record_from_dict(_record(id="skill:a/demo"), scope="project")
    two = record_from_dict(_record(id="skill:b/demo"), scope="project")
    registry = merge_scopes([("project", [one, two])])

    found, candidates = registry.resolve("demo")

    assert found is None
    assert len(candidates) == 2


def test_render_resolves_bare_name() -> None:
    record = record_from_dict(_record(), scope="project")
    registry = merge_scopes([("project", [record])])

    text = render(registry, level="L1", capability_id="demo")

    assert '"id": "skill:demo/demo"' in text


def test_l2_returns_reference_not_body(tmp_path: Path) -> None:
    body = "SECRET INSTRUCTION BODY"
    doc = tmp_path / "doc.md"
    doc.write_text(body, encoding="utf-8")
    record = record_from_dict(_record(source_path=str(doc)), scope="project")

    text = render_l2(record)

    assert body not in text
    assert str(doc) in text
    assert "does not store or serve" in text


# -- discovery sync --------------------------------------------------------


def test_sync_preserves_manual_records(tmp_path: Path) -> None:
    register(
        tmp_path,
        {
            "id": "cli:manual/tool",
            "type": "cli",
            "name": "tool",
            "description": "A manual tool",
        },
    )
    discovered = [record_from_dict(_record(), scope="project")]

    merged = sync_discovered(tmp_path, discovered)

    ids = {record.id for record in merged}
    assert ids == {"cli:manual/tool", "skill:demo/demo"}
