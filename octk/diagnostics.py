"""Shared diagnostic result schema.

A pruned diagnostic is only useful if it keeps the signal. Every diagnostic
result therefore records which required signals were found in the output, so
"we saved 90% of the bytes" can never be reported without "and the root cause
survived".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

TRUNCATION_MARKER = "[truncated"


@dataclass(frozen=True)
class DiagnosticResult:
    """What a diagnostic showed, and whether the required signal survived."""

    kind: str
    text: str
    raw_chars: int
    pruned_chars: int
    required_signals: tuple[str, ...] = ()
    kept_signals: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def dropped_signals(self) -> tuple[str, ...]:
        return tuple(
            signal for signal in self.required_signals if signal not in self.kept_signals
        )

    @property
    def signal_retained(self) -> bool:
        return not self.dropped_signals

    @property
    def signal_retention(self) -> float:
        if not self.required_signals:
            return 1.0
        return len(self.kept_signals) / len(self.required_signals)

    @property
    def savings_pct(self) -> float:
        if self.raw_chars <= 0:
            return 0.0
        saved = (self.raw_chars - self.pruned_chars) / self.raw_chars
        return round(max(0.0, saved * 100.0), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "raw_chars": self.raw_chars,
            "pruned_chars": self.pruned_chars,
            "savings_pct": self.savings_pct,
            "signal_retention": self.signal_retention,
            "signal_retained": self.signal_retained,
            "dropped_signals": list(self.dropped_signals),
            "truncated": self.truncated,
        }


def build_result(
    kind: str,
    text: str,
    raw_chars: int,
    required_signals: Iterable[str] = (),
) -> DiagnosticResult:
    """Measure a diagnostic against the signals it was required to keep."""
    required = tuple(required_signals)
    kept = tuple(signal for signal in required if signal in text)
    return DiagnosticResult(
        kind=kind,
        text=text,
        raw_chars=int(raw_chars),
        pruned_chars=len(text),
        required_signals=required,
        kept_signals=kept,
        truncated=TRUNCATION_MARKER in text,
    )
