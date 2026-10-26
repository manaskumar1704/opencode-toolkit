"""Lazy stdio MCP proxy: inspect or invoke only explicitly configured servers."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import load_config

SERVER_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ExternalMcpError(ValueError):
    """Raised for unknown servers or invalid proxy arguments."""


@dataclass
class ExternalMcpResult:
    text: str
    raw_chars: int
    pruned_chars: int


def resolve_server(root: Path, server_name: str) -> dict[str, Any]:
    """Return the configured server spec, rejecting everything else."""
    if not isinstance(server_name, str) or not SERVER_RE.match(server_name):
        raise ExternalMcpError(f"invalid external MCP server name: {server_name!r}")
    configured = load_config(root).get("external_mcps", {})
    if not isinstance(configured, dict) or server_name not in configured:
        available = ", ".join(sorted(configured)) if isinstance(configured, dict) else "(none)"
        raise ExternalMcpError(
            f"external MCP {server_name!r} is not configured. Available: {available}"
        )
    spec = configured[server_name]
    if not isinstance(spec, dict):
        raise ExternalMcpError(f"external MCP {server_name!r} config must be an object")
    command = spec.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise ExternalMcpError(
            f"external MCP {server_name!r} command must be a non-empty string list"
        )
    return spec


def _params(root: Path, spec: dict[str, Any]) -> StdioServerParameters:
    command = list(spec["command"])
    return StdioServerParameters(command=command[0], args=command[1:], cwd=str(root))


def _tool_line(tool: Any) -> str:
    name = str(getattr(tool, "name", "?"))
    description = " ".join(str(getattr(tool, "description", "") or "").split())[:100]
    schema = getattr(tool, "inputSchema", None) or {}
    compact_schema = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    suffix = f" - {description}" if description else ""
    return f"- {name}{suffix}\n  schema: {compact_schema}"


def _content_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        if getattr(item, "type", "") == "text":
            parts.append(str(getattr(item, "text", "")))
        else:
            dump = getattr(item, "model_dump_json", None)
            parts.append(dump() if callable(dump) else repr(item))
    structured = getattr(result, "structuredContent", None)
    if structured is not None and not parts:
        parts.append(json.dumps(structured, ensure_ascii=False, default=str))
    text = "\n".join(parts).strip() or "(empty result)"
    if getattr(result, "isError", False):
        text = "external MCP error:\n" + text
    return text


async def inspect_external_mcp(root: Path, server_name: str) -> ExternalMcpResult:
    """Connect on demand and return compact external tool names + schemas."""
    spec = resolve_server(root, server_name)
    timeout_s = int(load_config(root).get("external_mcp_timeout_s", 30))
    async with asyncio.timeout(timeout_s):
        async with stdio_client(_params(root, spec)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
    tools = list(getattr(listed, "tools", []) or [])
    lines = [f"External MCP {server_name}: {len(tools)} tool(s)"]
    lines.extend(_tool_line(tool) for tool in tools)
    text = "\n".join(lines) + "\n"
    return ExternalMcpResult(text=text, raw_chars=len(text), pruned_chars=len(text))


async def invoke_external_mcp(
    root: Path,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> ExternalMcpResult:
    """Execute one tool on a configured external stdio MCP server."""
    spec = resolve_server(root, server_name)
    if not tool_name:
        raise ExternalMcpError("tool_name is required when invoking an external MCP")
    timeout_s = int(load_config(root).get("external_mcp_timeout_s", 30))
    async with asyncio.timeout(timeout_s):
        async with stdio_client(_params(root, spec)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
    text = _content_text(result) + "\n"
    return ExternalMcpResult(text=text, raw_chars=len(text), pruned_chars=len(text))


def parse_arguments(arguments_json: str) -> dict[str, Any]:
    """Parse a JSON object for an external tool call."""
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        raise ExternalMcpError(f"arguments_json is not valid JSON: {exc}") from exc
    if not isinstance(arguments, dict):
        raise ExternalMcpError("arguments_json must decode to a JSON object")
    return arguments
