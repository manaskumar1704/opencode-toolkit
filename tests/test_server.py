"""Server tests: tool names, safe schemas, error strings, metric logging."""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

import octk.server as server
from octk.config import ToolkitPaths, read_json

EXPECTED_TOOLS = {
    "glance_pantry",
    "capability_registry",
    "equip_spec",
    "equip_skill",
    "check_spec_drift",
    "debug_inspect",
    "browser_inspect",
    "equip_external_mcp",
}


@pytest.fixture
def server_root(tmp_root: Path, monkeypatch) -> Path:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    monkeypatch.setenv("OCTK_USER_CONFIG", str(tmp_root / "userconfig"))
    return tmp_root


async def _tools() -> dict[str, object]:
    """Tool name -> SimpleNamespace(fn, model); SimpleNamespace avoids
    binding the raw function as a method (functions are descriptors)."""
    listed = {t.name: t for t in await server.mcp.list_tools()}
    registry = server.mcp._tool_manager._tools
    return {
        name: types.SimpleNamespace(fn=registry[name].fn, model=model)
        for name, model in listed.items()
    }


async def _tools_models() -> dict[str, object]:
    return {t.name: t for t in await server.mcp.list_tools()}


async def test_expected_tools_exposed(server_root) -> None:
    tools = await _tools_models()
    assert set(tools) == EXPECTED_TOOLS


async def test_capability_registry_lists_discovered(server_root) -> None:
    from octk import capabilities
    from octk.adapters.opencode import OpenCodeAdapter

    skill = server_root / ".opencode" / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\ndescription: Demo skill\n---\n", encoding="utf-8"
    )
    discovered = [
        capabilities.record_from_dict(item, scope="project")
        for item in OpenCodeAdapter(server_root).discover_capabilities()
    ]
    capabilities.sync_discovered(server_root, discovered)

    tools = await _tools()
    result = tools["capability_registry"].fn()

    assert "demo" in result
    assert "Capabilities (" in result


async def test_capability_registry_unknown_id_is_an_error_string(server_root) -> None:
    tools = await _tools()
    result = tools["capability_registry"].fn(capability_id="skill:no/such")
    assert result.startswith("octk error:")


async def test_equip_spec_rejects_traversal(server_root) -> None:
    tools = await _tools()
    result = tools["equip_spec"].fn("../etc/passwd")
    assert result.startswith("octk error:") or "invalid" in result


async def test_glance_and_equip_log_records(server_root) -> None:
    tools = await _tools()
    tools["glance_pantry"].fn()
    tools["equip_spec"].fn("architecture")
    data = read_json(ToolkitPaths(server_root).metrics)
    kinds = [c["kind"] for c in data["unattributed"]]
    assert "counterfactual" in kinds
    assert "load" in kinds


