"""Tool bench: run octk pruners against generated fixtures; honest numbers.

Cases build throwaway projects in temp dirs, run one tool, and score two
things: character savings (raw vs pruned) and signal retention (are the
required signals still present in the pruned text?). The CLI fails when
retention < 1.0 on a non-skipped case.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import socket
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import pantry
from .config import load_config
from .metrics import approx_tokens
from .runtime.browser import inspect_url
from .runtime.debugger import run_smart_debugger

CASE_NAMES = ("pantry_glance", "debug_pruning", "browser_pruning")

DEBUG_SENTINEL = "octk-signal-9f27c1"

PANTRY_FILLER = "bench note: module contract line with enough words to fill context"

BROKEN_TEST = f"""\
import json



def probe(raw):
    return json.loads(raw)



def test_decode_signal():
    raw = '{{"items": [1, 2, "{DEBUG_SENTINEL}"'
    return probe(raw)
"""

BROWSER_HTML = """\
<!doctype html><html><head><title>Bench</title></head><body>
<div id="result"></div>
<button id="submit" onclick="document.getElementById('result').innerText='clicked';">
  Click
</button>
<script>
console.error('boom');
fetch('/missing.json');
for (let i = 0; i < 3000; i++) {
  const d = document.createElement('div');
  d.textContent = 'filler ' + i;
  document.body.appendChild(d);
}
</script>
</body></html>
"""


def _signal_check(text: str, expected: list[str]) -> dict[str, Any]:
    """found/missed/total/retention for required signal substrings."""
    found = [s for s in expected if s in text]
    missed = [s for s in expected if s not in text]
    total = len(expected)
    retention = (len(found) / total) if total else 1.0
    return {"found": found, "missed": missed, "total": total, "retention": retention}


def _mk_case(
    name: str, kind: str, raw: int, pruned: int, signals: dict[str, Any],
    skipped: str | None = None,
) -> dict[str, Any]:
    saved = max(raw - pruned, 0)
    return {
        "name": name,
        "kind": kind,
        "raw_chars": raw,
        "pruned_chars": pruned,
        "saved_chars": saved,
        "pct_reduction": ((saved / raw * 100.0) if raw else 0.0),
        "approx_tokens_saved": approx_tokens(saved),
        "signals": signals,
        "skipped": skipped,
    }


def _make_debug_fixture(root: Path) -> None:
    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "test_broken.py").write_text(BROKEN_TEST, encoding="utf-8")


def _make_pantry_fixture(root: Path) -> None:
    """Scaffold a toolkit and inflate spec/skill files so glance has real raw."""
    from .scaffold import init_repo

    init_repo(root)
    sizes = {"architecture.md": 400, "user_flow.md": 300, "acceptance.md": 200}
    for name, lines in sizes.items():
        path = root / ".toolkit" / "specs" / name
        filler = "\n".join(f"{PANTRY_FILLER} {i:04d}" for i in range(lines))
        path.write_text(path.read_text(encoding="utf-8") + "\n" + filler + "\n", encoding="utf-8")
    skills = root / ".toolkit" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    filler = "\n".join(f"{PANTRY_FILLER} {i:04d}" for i in range(200))
    (skills / "extra_notes.md").write_text(
        "description: bench extra skill\n\n" + filler + "\n", encoding="utf-8"
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_browser_fixture(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serve the heavy page locally; returns (server, url)."""
    (directory / "index.html").write_text(BROWSER_HTML, encoding="utf-8")
    handler = lambda *args, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(directory), **kw
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/index.html"


async def _chromium_probe() -> bool:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _case_pantry() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_pantry_fixture(root)
        out = pantry.glance(root)
        stems = [p.stem for p in (root / ".toolkit" / "specs").glob("*.md")]
        signals = _signal_check(out.text, [*stems, "extra_notes"])
    return _mk_case("pantry_glance", "counterfactual", out.raw_chars, out.pruned_chars, signals)


def _case_debug() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _make_debug_fixture(root)
        config = load_config(root)
        out = run_smart_debugger("pytest tests/test_broken.py", root, config)
        expected = ["test_decode_signal", "JSONDecodeError", DEBUG_SENTINEL]
        signals = _signal_check(out.text, expected)
    return _mk_case("debug_pruning", "measured", out.raw_chars, out.pruned_chars, signals)


def _case_browser() -> dict[str, Any]:
    if not asyncio.run(_chromium_probe()):
        signals = {"found": [], "missed": [], "total": 3, "retention": None}
        return _mk_case(
            "browser_pruning", "measured", 0, 0, signals,
            skipped="chromium not installed",
        )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        server, url = _make_browser_fixture(root)
        try:
            out = asyncio.run(inspect_url(url, wait_ms=300))
        finally:
            server.shutdown()
        signals = _signal_check(out.text, ["boom", "/missing.json", "#submit"])
    return _mk_case("browser_pruning", "measured", out.raw_chars, out.pruned_chars, signals)


_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "pantry_glance": _case_pantry,
    "debug_pruning": _case_debug,
    "browser_pruning": _case_browser,
}


def _schema_overhead() -> dict[str, Any]:
    """Bytes the octk MCP server adds to the model-visible tool list."""
    import octk.server as server_mod

    tools = asyncio.run(server_mod.mcp.list_tools())
    names = sum(len(t.name) for t in tools)
    descriptions = sum(len(t.description or "") for t in tools)
    schemas = sum(len(json.dumps(t.inputSchema)) if t.inputSchema else 0 for t in tools)
    return {
        "tools": len(tools),
        "name_bytes": names,
        "description_bytes": descriptions,
        "schema_bytes": schemas,
        "total_bytes": names + descriptions + schemas,
    }


def run_tool_bench(root: Path, cases: list[str] | None = None) -> dict[str, Any]:
    """Run bench cases and return the results dict (JSON-serializable)."""
    unknown = [n for n in (cases or []) if n not in CASE_NAMES]
    if unknown:
        raise ValueError(f"unknown case(s): {unknown}; choose from {list(CASE_NAMES)}")
    names = list(cases) if cases else list(CASE_NAMES)
    agents_bytes: int | None = None
    agents = root / "AGENTS.md"
    if agents.exists():
        agents_bytes = agents.stat().st_size
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": [_BUILDERS[n]() for n in names],
        "schema_overhead": _schema_overhead(),
        "agents_md_bytes": agents_bytes,
    }


_KIND_NOTE = {
    "measured": "real run; raw = unpruned bytes captured, pruned = what octk returned",
    "counterfactual": "estimate; raw = bytes of files a full load would have brought, pruned = real glance output",
    "load": "context octk itself adds; no pruning involved",
}


def format_bench(results: dict[str, Any]) -> str:
    """Markdown report for a bench results dict. No invented numbers."""
    out = [
        "# octk tool bench report",
        "",
        f"Generated {results['timestamp']}. All sizes are characters "
        "(approx tokens uses the chars/4 proxy). Retention < 1.0 means a required "
        "signal was lost in the pruned output.",
        "",
        "## Cases",
        "",
        "| case | kind | raw chars | pruned chars | saved % | retention | skipped |",
        "|---|---|---|---|---|---|---|",
    ]
    for case in results["cases"]:
        retention = case["signals"]["retention"]
        out.append(
            f"| {case['name']} | {case['kind']} | {case['raw_chars']} | "
            f"{case['pruned_chars']} | {case['pct_reduction']:.1f}% | "
            f"{'-' if retention is None else f'{retention:.2f}'} | "
            f"{case['skipped'] or '-'} |"
        )
    out += ["", "## Signal detail", ""]
    for case in results["cases"]:
        sig = case["signals"]
        missed = ", ".join(sig["missed"]) or "(none)"
        out.append(
            f"- **{case['name']}** (kind={case['kind']}): "
            f"{len(sig['found'])}/{sig['total']} signals kept; missed: {missed}. "
            f"{_KIND_NOTE.get(case['kind'], '')}"
        )
    head = results["schema_overhead"]
    out += [
        "",
        "## Schema overhead (what the octk MCP server adds to the tool list)",
        "",
        f"{head['tools']} tools: names {head['name_bytes']} B, descriptions "
        f"{head['description_bytes']} B, JSON schemas {head['schema_bytes']} B "
        f"= {head['total_bytes']} B total (approx {approx_tokens(head['total_bytes'])} tokens).",
    ]
    agents = results.get("agents_md_bytes")
    if agents is None:
        out.append("AGENTS.md root injection: not present in bench root.")
    else:
        out.append(
            f"AGENTS.md root injection: {agents} B (approx {approx_tokens(agents)} tokens)."
        )
    out += [
        "",
        "## Honesty",
        "",
        "- Savings are measured on this machine, on generated fixtures, at this date; ",
        "  they are not a distribution claim. Retention is scored, never assumed.",
        "- The raw side of kind=counterfactual is an estimate, not a measured run.",
        "- Skipped cases are listed, not silently dropped.",
    ]
    return "\n".join(out) + "\n"
