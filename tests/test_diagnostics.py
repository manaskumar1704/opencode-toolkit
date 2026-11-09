"""Diagnostic result schema: signal retention is measured, never assumed."""

from __future__ import annotations

from octk.diagnostics import build_result
from octk.runtime.browser import BrowserResult


def test_signal_retained_when_all_present() -> None:
    result = build_result("debug", "E ValueError: boom\nframe", 100, ["boom", "frame"])

    assert result.signal_retained is True
    assert result.signal_retention == 1.0
    assert result.dropped_signals == ()


def test_dropped_signal_is_reported() -> None:
    result = build_result("debug", "E ValueError: boom", 100, ["boom", "payload"])

    assert result.signal_retained is False
    assert result.dropped_signals == ("payload",)
    assert result.signal_retention == 0.5


def test_no_required_signals_is_trivially_retained() -> None:
    result = build_result("browser", "Title: x", 10)

    assert result.signal_retained is True
    assert result.signal_retention == 1.0


def test_savings_and_truncation_are_measured() -> None:
    text = "x" * 50 + "[truncated 100 chars]" + "y" * 50
    result = build_result("debug", text, 400)

    expected = round((400 - len(text)) / 400 * 100, 1)
    assert result.savings_pct == expected
    assert result.truncated is True


def test_zero_raw_chars_has_zero_savings() -> None:
    assert build_result("debug", "", 0).savings_pct == 0.0


def test_to_dict_shape() -> None:
    data = build_result("debug", "boom", 100, ["boom", "missing"]).to_dict()

    assert data["kind"] == "debug"
    assert data["signal_retained"] is False
    assert data["dropped_signals"] == ["missing"]
    assert data["pruned_chars"] == 4


def test_browser_result_exposes_diagnostic() -> None:
    result = BrowserResult(
        text="Console errors (max 10):\n  E boom",
        raw_chars=5000,
        pruned_chars=36,
    )

    diagnostic = result.diagnostic(required_signals=("boom",))

    assert diagnostic.kind == "browser"
    assert diagnostic.signal_retained is True
