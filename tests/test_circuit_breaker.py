"""debug_inspect 2-strike circuit breaker: signature, latch, reset."""

from __future__ import annotations

from pathlib import Path

import pytest

import octk.server as server
from octk.config import ToolkitPaths
from octk.metrics import MetricsStore
from octk.runtime.debugger import DebugResult


async def _tool():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    registry = server.mcp._tool_manager._tools
    return registry["debug_inspect"].fn


def _failure(text: str = "E   ValueError: boom", command: str = "pytest x") -> DebugResult:
    return DebugResult(
        text=text,
        raw_chars=len(text),
        pruned_chars=len(text),
        returncode=1,
        error_line=text,
    )


@pytest.fixture
def server_root(tmp_root: Path, monkeypatch) -> Path:
    monkeypatch.setenv("OCTK_ROOT", str(tmp_root))
    return tmp_root


async def test_second_identical_failure_appends_breaker(server_root, monkeypatch) -> None:
    fn = await _tool()
    monkeypatch.setattr(server, "run_smart_debugger", lambda *a, **k: _failure())

    first = await fn("pytest x")
    second = await fn("pytest x")
    third = await fn("pytest x")

    assert server.DEBUG_BREAKER not in first
    assert server.DEBUG_BREAKER in second
    assert server.DEBUG_BREAKER in third


async def test_success_resets_strikes(server_root, monkeypatch) -> None:
    fn = await _tool()
    state = {"fail": True}

    def runner(*_args, **_kwargs):
        if state["fail"]:
            return _failure()
        return DebugResult(text="1 passed", raw_chars=8, pruned_chars=8, returncode=0)

    monkeypatch.setattr(server, "run_smart_debugger", runner)
    assert server.DEBUG_BREAKER not in await fn("pytest x")
    assert server.DEBUG_BREAKER in await fn("pytest x")

    state["fail"] = False
    assert server.DEBUG_BREAKER not in await fn("pytest x")

    state["fail"] = True
    assert server.DEBUG_BREAKER not in await fn("pytest x")


async def test_different_failure_resets_streak(server_root, monkeypatch) -> None:
    fn = await _tool()
    outputs = iter(
        [
            _failure("E   ValueError: one"),
            _failure("E   ValueError: two"),
            _failure("E   ValueError: two"),
        ]
    )
    monkeypatch.setattr(server, "run_smart_debugger", lambda *a, **k: next(outputs))

    assert server.DEBUG_BREAKER not in await fn("pytest x")
    assert server.DEBUG_BREAKER not in await fn("pytest x")
    assert server.DEBUG_BREAKER in await fn("pytest x")


async def test_new_task_resets_strikes(server_root, monkeypatch) -> None:
    fn = await _tool()
    monkeypatch.setattr(server, "run_smart_debugger", lambda *a, **k: _failure())

    await fn("pytest x")
    assert server.DEBUG_BREAKER in await fn("pytest x")

    MetricsStore(ToolkitPaths(server_root).metrics).start_task("next")
    assert server.DEBUG_BREAKER not in await fn("pytest x")


async def test_repeated_exception_appends_breaker(server_root, monkeypatch) -> None:
    fn = await _tool()

    def broken(*_args, **_kwargs):
        raise RuntimeError("debugger itself is broken")

    monkeypatch.setattr(server, "run_smart_debugger", broken)
    first = await fn("pytest x")
    second = await fn("pytest x")

    assert first.startswith("octk error: RuntimeError")
    assert server.DEBUG_BREAKER not in first
    assert server.DEBUG_BREAKER in second
