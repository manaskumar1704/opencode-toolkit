"""Browser: snapshot summarizer (pure) + one real Chromium run (skippable)."""

from __future__ import annotations

import http.server
import socket
import threading

import pytest

from octk.runtime.browser import inspect_url, summarize_snapshot

SNAPSHOT = {
    "title": "Bench page",
    "url": "http://localhost/x",
    "console_errors": ["boom", "boom", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh"],
    "network_errors": [{"status": 404, "url": "http://localhost/missing.json"}] * 3
    + [{"status": 500, "url": "http://localhost/dead"}]
    + [{"status": 404, "url": "http://localhost/again"}] * 9,
    "elements": [
        {"tag": "button", "text": f"Item {i} " + "z" * 80, "selector": f"button:has-text(\"Item {i}\")"}
        for i in range(60)
    ] + [{"tag": "button", "text": "Submit", "selector": "#submit"}],
}


def test_summary_caps_elements() -> None:
    text = summarize_snapshot(SNAPSHOT, max_elements=40)
    lines = text.splitlines()
    element_lines = [l for l in lines if l.startswith("  ")]
    assert len([l for l in element_lines if "Item" in l or "Submit" in l]) == 40


def test_summary_dedup_console_errors() -> None:
    text = summarize_snapshot({**SNAPSHOT, "console_errors": ["boom", "boom", "other"]})
    assert text.count("E boom") == 1


def test_summary_truncates_text() -> None:
    text = summarize_snapshot(SNAPSHOT)
    long_line = [l for l in text.splitlines() if l.startswith("  button Item 0")][0]
    text_part = long_line.rsplit(" [", 1)[0]
    assert "z" * 80 not in text_part
    assert text_part.rstrip().endswith("...")


def test_summary_filters_shown_counts() -> None:
    text = summarize_snapshot(SNAPSHOT)
    assert "Interactive elements (40 shown):" in text
    assert "404 http://localhost/missing.json" in text
    assert "500 http://localhost/dead" in text


SPINNER_HTML = """\
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(tmp_path) -> http.server.ThreadingHTTPServer:
    handler = lambda *args, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *args, directory=str(tmp_path), **kw
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def _chromium_available() -> bool:
    """Async API probe - the test runs inside the pytest-asyncio loop."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.browser
async def test_inspect_url_survives_signals(tmp_path) -> None:
    if not await _chromium_available():
        pytest.skip("Chromium not installed")
    (tmp_path / "index.html").write_text(SPINNER_HTML, encoding="utf-8")
    server = _serve(tmp_path)
    try:
        result = await inspect_url(f"http://127.0.0.1:{server.server_address[1]}/index.html")
        assert result.pruned_chars < result.raw_chars
        assert "boom" in result.text
        assert "/missing.json" in result.text
        assert "#submit" in result.text
    finally:
        server.shutdown()
