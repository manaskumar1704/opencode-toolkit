"""Lazy external MCP config listing, strict validation, and proxy tool wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import octk.server as server
from octk.config import ToolkitPaths, load_config, read_json
from octk.mcp_proxy import (
    ExternalMcpError,
    ExternalMcpResult,
    parse_arguments,
    resolve_server,
)
from octk.pantry import glance


def _configure_external(root: Path) -> None:
    path = ToolkitPaths(root).config
    config = load_config(root)
    config["external_mcps"] = {
        "supabase": {
            "command": ["npx", "-y", "@supabase/mcp-server"],
            "description": "Supabase DB & Auth tools",
        }
    }
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


async def _external_tool():
    await server.mcp.list_tools()
    registry = server.mcp._tool_manager._tools
    return registry["equip_external_mcp"]


@pytest.fixture
def server_root(tmp_root: Path, monkeypatch) -> Path:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    return tmp_root


def test_glance_lists_external_mcps_without_schemas(tmp_root) -> None:
    _configure_external(tmp_root)
    result = glance(tmp_root)
    assert "External MCPs (lazy; use equip_external_mcp): supabase (Supabase DB & Auth tools)" in result.text
    assert '"type":"object"' not in result.text


def test_glance_omits_external_line_when_unconfigured(tmp_root) -> None:
    assert "External MCPs" not in glance(tmp_root).text


def test_resolve_rejects_unconfigured_and_bad_names(tmp_root) -> None:
    _configure_external(tmp_root)
    with pytest.raises(ExternalMcpError, match="not configured"):
        resolve_server(tmp_root, "github")
    with pytest.raises(ExternalMcpError, match="invalid external MCP"):
        resolve_server(tmp_root, "../supabase")


async def test_tool_rejects_unconfigured_server(server_root) -> None:
    tool = await _external_tool()
    result = await tool.fn("github")
    assert result.startswith("octk error: ExternalMcpError:")
    assert "not configured" in result


async def test_schema_load_is_compact_and_logged(server_root, monkeypatch) -> None:
    _configure_external(server_root)
    captured: dict[str, str] = {}

    async def fake_inspect(root: Path, name: str) -> ExternalMcpResult:
        captured["name"] = name
        text = "- query\n  schema: {\"type\":\"object\"}\n"
        return ExternalMcpResult(text=text, raw_chars=len(text), pruned_chars=len(text))

    monkeypatch.setattr(server, "inspect_external_mcp", fake_inspect)
    tool = await _external_tool()
    result = await tool.fn("supabase")
    assert captured["name"] == "supabase"
    assert "query" in result
    metrics = read_json(ToolkitPaths(server_root).metrics)
    assert metrics["unattributed"][-1]["tool"] == "equip_external_mcp"
    assert metrics["unattributed"][-1]["kind"] == "load"


async def test_tool_invocation_forwards_json_arguments(server_root, monkeypatch) -> None:
    _configure_external(server_root)
    captured: dict[str, object] = {}

    async def fake_invoke(root: Path, name: str, tool: str, arguments: dict) -> ExternalMcpResult:
        captured.update(name=name, tool=tool, arguments=arguments)
        return ExternalMcpResult(text="ok\n", raw_chars=3, pruned_chars=3)

    monkeypatch.setattr(server, "invoke_external_mcp", fake_invoke)
    tool = await _external_tool()
    result = await tool.fn("supabase", "query", '{"sql": "select 1"}')
    assert result == "ok\n"
    assert captured == {"name": "supabase", "tool": "query", "arguments": {"sql": "select 1"}}


def test_parse_arguments_requires_json_object() -> None:
    assert parse_arguments("{}") == {}
    with pytest.raises(ExternalMcpError, match="not valid JSON"):
        parse_arguments("{")
    with pytest.raises(ExternalMcpError, match="JSON object"):
        parse_arguments("[]")
