"""octk MCP server: thin wrappers; every tool logs its savings honestly."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import audit as audit_mod
from . import drift as drift_mod
from . import pantry, roadmap as roadmap_mod
from .config import ToolkitPaths, load_config
from .mcp_proxy import (
    ExternalMcpError,
    inspect_external_mcp,
    invoke_external_mcp,
    parse_arguments,
)
from .metrics import MetricsStore
from .runtime.browser import inspect_url
from .runtime.debugger import failure_signature, normalize_command, run_smart_debugger

mcp = FastMCP("OpenCodeToolkit")

DEBUG_BREAKER = (
    "[OCTK CIRCUIT BREAKER: 2 identical failures detected in debug_inspect. "
    "You are now authorized to bypass octk_debug_inspect and run raw pytest/python "
    "via shell or escalate to the user.]"
)
_DEBUG_LOCK = threading.Lock()


def get_root() -> Path:
    """Resolve project root (OCTK_ROOT or cwd) - server only."""
    return Path(os.environ.get("OCTK_ROOT") or Path.cwd())


def _log(tool: str, kind: str, raw_chars: int, pruned_chars: int) -> None:
    metrics_path = ToolkitPaths(get_root()).metrics
    try:
        MetricsStore(metrics_path).log_tool_call(tool, raw_chars, pruned_chars, kind=kind)
    except Exception:  # noqa: BLE001 - metrics must never break a tool call
        pass


def _record_debug_call(
    signature: str | None,
    detail: str,
    raw_chars: int,
    pruned_chars: int,
) -> int:
    """Persist one debug result and return its consecutive-failure strike count."""
    try:
        with _DEBUG_LOCK:
            return MetricsStore(ToolkitPaths(get_root()).metrics).record_debug_call(
                signature,
                detail,
                raw_chars,
                pruned_chars,
            )
    except Exception:  # noqa: BLE001 - metrics must never break a tool call
        return 0


def _debug_detail(command: str, returncode: int | None, error_line: str) -> str:
    return f"{normalize_command(command)} | rc={returncode} | {error_line or '(no error line)'}"


def _with_breaker(text: str, signature: str | None, strikes: int) -> str:
    if signature is None or strikes < 2:
        return text
    return text.rstrip() + "\n\n" + DEBUG_BREAKER + "\n"


@mcp.tool()
def glance_pantry() -> str:
    """Look up the toolkit index and inventory without loading full files."""
    try:
        result = pantry.glance(get_root())
        _log("glance_pantry", "counterfactual", result.raw_chars, result.pruned_chars)
        return result.text
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
def equip_spec(spec_name: str) -> str:
    """Load one spec file (.toolkit/specs/<name>.md) on demand."""
    try:
        text = pantry.equip_spec(get_root(), spec_name)
        _log("equip_spec", "load", len(text), len(text))
        return text
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
def equip_skill(skill_name: str) -> str:
    """Load one extra skill file (.toolkit/skills/<name>.md) on demand."""
    try:
        text = pantry.equip_skill(get_root(), skill_name)
        _log("equip_skill", "load", len(text), len(text))
        return text
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
def update_roadmap(task_substring: str, new_status: str) -> str:
    """Update one roadmap line; 'done' needs prior `octk approve` (human)."""
    try:
        line = roadmap_mod.set_status(get_root(), task_substring, new_status)
        _log("update_roadmap", "measured", 0, len(line))
        return line
    except Exception as exc:  # noqa: BLE001 - GateError/RoadmapError become strings
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
def check_spec_drift() -> str:
    """AST spec-to-code drift scan (undocumented symbols/routes vs specs)."""
    try:
        result = drift_mod.check_drift(get_root())
        _log("check_spec_drift", "counterfactual", result.raw_chars, result.pruned_chars)
        return result.report
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
def run_audit_workflow(audit_cmd: str = "") -> str:
    """Run graph-freshness then audit; instruct mode advises, never executes."""
    try:
        result = audit_mod.run_audit_workflow(get_root(), load_config(get_root()), audit_cmd=audit_cmd)
        kind = "measured" if load_config(get_root()).get("audit_mode") == "subprocess" else "load"
        _log("run_audit_workflow", kind, result.raw_chars, result.pruned_chars)
        return result.text
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
async def debug_inspect(command: str) -> str:
    """Run a validated pytest/python command and return pruned failure output."""
    try:
        cfg = load_config(get_root())
        result = await asyncio.to_thread(run_smart_debugger, command, get_root(), cfg)
        signature = (
            failure_signature(command, result.returncode, result.error_line)
            if result.returncode != 0
            else None
        )
        strikes = _record_debug_call(
            signature,
            _debug_detail(command, result.returncode, result.error_line),
            result.raw_chars,
            result.pruned_chars,
        )
        return _with_breaker(result.text, signature, strikes)
    except Exception as exc:  # noqa: BLE001
        message = f"octk error: {type(exc).__name__}: {exc}"
        detail = (
            f"{normalize_command(command) if isinstance(command, str) else command!r} | "
            f"exception {type(exc).__name__}: {exc}"
        )
        signature = failure_signature(
            command if isinstance(command, str) else str(command),
            None,
            f"{type(exc).__name__}: {exc}",
        )
        strikes = _record_debug_call(signature, detail, 0, len(message))
        return _with_breaker(message, signature, strikes)


@mcp.tool()
async def equip_external_mcp(
    server_name: str,
    tool_name: str = "",
    arguments_json: str = "{}",
) -> str:
    """Inspect or invoke one configured external stdio MCP server on demand."""
    try:
        if tool_name:
            arguments = parse_arguments(arguments_json)
            result = await invoke_external_mcp(
                get_root(), server_name, tool_name, arguments
            )
        else:
            result = await inspect_external_mcp(get_root(), server_name)
        _log("equip_external_mcp", "load", result.raw_chars, result.pruned_chars)
        return result.text
    except ExternalMcpError as exc:
        return f"octk error: ExternalMcpError: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


@mcp.tool()
async def browser_inspect(url: str, wait_ms: int = 1000) -> str:
    """Load a URL in headless Chromium and summarize errors/a11y/elements."""
    try:
        result = await inspect_url(url, wait_ms=wait_ms)
        _log("browser_inspect", "measured", result.raw_chars, result.pruned_chars)
        return result.text
    except Exception as exc:  # noqa: BLE001
        return f"octk error: {type(exc).__name__}: {exc}"


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
