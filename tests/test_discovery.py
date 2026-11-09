"""OpenCode adapter tests: discovery coverage, read-only behaviour, safety."""

from __future__ import annotations

import json
from pathlib import Path

from octk.adapters.opencode import OpenCodeAdapter, discover


def _skill(root: Path, name: str, description: str, fm_name: str | None = None) -> None:
    directory = root / ".opencode" / "skills" / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    if fm_name:
        lines.append(f"name: {fm_name}")
    lines += [f"description: {description}", "---", f"# {name}"]
    (directory / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")


def _command(root: Path, name: str, description: str) -> None:
    directory = root / ".opencode" / "commands"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(
        f"---\ndescription: {description}\n---\n", encoding="utf-8"
    )


def _opencode_json(root: Path, servers: dict) -> None:
    (root / "opencode.json").write_text(
        json.dumps({"mcp": servers}), encoding="utf-8"
    )


def test_detect_returns_none_without_harness(tmp_path: Path) -> None:
    assert OpenCodeAdapter(tmp_path).detect() is None
    assert discover(tmp_path) == []


def test_detect_reports_opencode_json(tmp_path: Path) -> None:
    _opencode_json(tmp_path, {})
    detected = OpenCodeAdapter(tmp_path).detect()
    assert detected is not None
    assert detected["opencode_json"] is True


def test_discovers_skills_commands_mcp_and_specs(tmp_root: Path) -> None:
    _skill(tmp_root, "ponytail", "Code reuse review", fm_name="ponytail")
    _command(tmp_root, "review", "Review the current diff")
    _opencode_json(
        tmp_root,
        {"context7": {"type": "local", "command": ["npx", "-y", "context7"]}},
    )

    records = discover(tmp_root)
    ids = {record["id"] for record in records}

    assert "skill:ponytail/ponytail" in ids
    assert "command:opencode/review" in ids
    assert "mcp_server:context7/context7" in ids
    assert any(item.startswith("octk_native:octk/spec-") for item in ids)


def test_descriptions_are_truncated(tmp_path: Path) -> None:
    _skill(tmp_path, "long", "y" * 400)
    records = discover(tmp_path)
    skill = next(r for r in records if r["type"] == "skill")
    assert len(skill["description"]) <= 140


def test_mcp_arguments_are_not_stored(tmp_path: Path) -> None:
    _opencode_json(
        tmp_path,
        {
            "secret": {
                "type": "local",
                "command": ["node", "--token", "SUPERSECRET"],
            }
        },
    )

    records = discover(tmp_path)

    assert "SUPERSECRET" not in json.dumps(records)
    server = next(r for r in records if r["type"] == "mcp_server")
    assert server["invocation"]["command"] == "node"


def test_malformed_opencode_json_is_tolerated(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text("{not json", encoding="utf-8")
    records = discover(tmp_path)
    # Provider records are still emitted; the malformed MCP block is skipped.
    assert not any(record["type"] == "mcp_server" for record in records)


def test_discovery_is_read_only(tmp_path: Path) -> None:
    _skill(tmp_path, "demo", "Demo skill")
    _command(tmp_path, "go", "Go")
    before = {
        (path, path.stat().st_mtime_ns, path.stat().st_size)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    first = discover(tmp_path)
    second = discover(tmp_path)

    after = {
        (path, path.stat().st_mtime_ns, path.stat().st_size)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert [r["id"] for r in first] == [r["id"] for r in second]


def test_install_hints_point_at_missing_pieces(tmp_path: Path) -> None:
    adapter = OpenCodeAdapter(tmp_path)
    hints = adapter.install_hints()
    assert any("opencode.json" in hint for hint in hints)
    assert any("SKILL.md" in hint for hint in hints)
