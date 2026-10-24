"""Async browser inspector with a pure snapshot summarizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_ELEMENT_TEXT = 60


@dataclass
class BrowserResult:
    text: str
    raw_chars: int
    pruned_chars: int


def _short(text: Any, limit: int) -> str:
    raw = str(text or "")
    return raw[:limit] + ("..." if len(raw) > limit else "")


def summarize_snapshot(snapshot: dict, max_elements: int = 40) -> str:
    """Compact text summary of a browser snapshot."""
    out: list[str] = []
    title = str(snapshot.get("title", ""))
    out.append(f"Title: {title}")
    out.append(f"URL: {snapshot.get('url', '')}")
    errors: list[str] = []
    for err in snapshot.get("console_errors", []):
        msg = str(err)
        if msg not in errors:
            errors.append(msg)
    out.append("Console errors (max 10):")
    out.extend(f"  E {msg}" for msg in errors[:10])
    net = snapshot.get("network_errors", [])
    if net:
        out.append("Network 4xx/5xx (max 10):")
        for entry in net[:10]:
            if isinstance(entry, dict):
                out.append(f"  {entry.get('status')} {entry.get('url')}")
            else:
                out.append(f"  {entry}")
    elements = snapshot.get("elements", [])[:max_elements]
    out.append(f"Interactive elements ({len(elements)} shown):")
    for el in elements:
        if not isinstance(el, dict):
            continue
        text_part = _short(el.get("text"), MAX_ELEMENT_TEXT)
        out.append(f"  {el.get('tag')} {text_part} [{el.get('selector')}]")
    return "\n".join(out)


_ELEMENT_JS = """
() => {
  const nodes = document.querySelectorAll('button, a, input, select, textarea, [role=button]');
  const out = [];
  let counts = {};
  for (const node of nodes) {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    if (rect.width === 0 && rect.height === 0) continue;
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const tag = node.tagName.toLowerCase();
    const text = (node.innerText || node.value || '').trim();
    let selector = null;
    if (node.id) selector = '#' + node.id;
    else if (node.dataset && node.dataset.testid) selector = `[data-testid=${node.dataset.testid}]`;
    else if (node.getAttribute('name')) selector = `${tag}[name=${node.getAttribute('name')}]`;
    if (selector === null && text) selector = `${tag}:has-text(${JSON.stringify(text.slice(0, 40))})`;
    if (selector === null) {
      counts[tag] = (counts[tag] || 0) + 1;
      selector = `${tag}:nth-of-type(${counts[tag]})`;
    }
    out.push({tag, text: text.slice(0, 200), selector});
  }
  return out;
}
"""


async def inspect_url(url: str, wait_ms: int = 1000) -> BrowserResult:
    """Load URL in headless Chromium and summarize errors + interactive UI."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("only http/https URLs are allowed")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        msg = f"octk browser error: playwright missing ({exc})"
        return BrowserResult(text=msg, raw_chars=len(msg), pruned_chars=len(msg))
    console_errors: list[str] = []
    network_errors: list[dict] = []
    raw_chars = 0
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: console_errors.append(str(e)))
                page.on(
                    "response",
                    lambda r: network_errors.append({"status": r.status, "url": r.url})
                    if r.status >= 400
                    else None,
                )
                page.on("requestfailed", lambda r: console_errors.append(f"requestfailed {r.url}"))
                await page.goto(url)
                await page.wait_for_timeout(wait_ms)
                raw_chars = len(await page.content())
                title = await page.title()
                console_errors = [str(m) for m in console_errors]
                snapshot = _merge_snapshot(
                    title, page.url, console_errors, network_errors,
                    await page.evaluate(_ELEMENT_JS),
                )
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001 - missing chromium / navigation failure
        msg = f"octk browser error: {type(exc).__name__}: {exc}"
        return BrowserResult(text=msg, raw_chars=raw_chars or len(msg), pruned_chars=len(msg))
    text = summarize_snapshot(snapshot)
    return BrowserResult(text=text, raw_chars=raw_chars, pruned_chars=len(text))


def _merge_snapshot(title: str, url: str, console_errors: list[str], network_errors: list[dict], elements: list) -> dict:
    return {
        "title": title,
        "url": url,
        "console_errors": console_errors,
        "network_errors": network_errors,
        "elements": elements,
    }
