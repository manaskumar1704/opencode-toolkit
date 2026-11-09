"""Capability Selector: heuristic, explainable relevance ranking.

Deliberately simple: token overlap over name/description/id, a native-before-
wrapper type preference, and de-duplication by name. No model calls, no hidden
scoring. Every decision carries a reason so the agent can see why a capability
was selected or skipped (handoff A3.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .capabilities import CapabilityRecord

_TOKEN_RE = re.compile(r"[a-z0-9_]+")

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "into",
        "using",
        "use",
        "when",
        "what",
        "which",
        "should",
        "need",
        "needs",
        "make",
        "add",
        "fix",
        "run",
        "all",
        "any",
        "can",
        "not",
        "but",
        "are",
        "was",
        "were",
        "will",
        "have",
        "has",
        "its",
        "our",
        "you",
        "your",
    }
)

# Native-before-wrapper preference (handoff A2.5): lower wins ties.
TYPE_PRIORITY = {
    "native_tool": 0,
    "skill": 1,
    "command": 1,
    "cli": 1,
    "plugin": 2,
    "mcp_tool": 2,
    "mcp_server": 3,
    "octk_native": 4,
}


@dataclass(frozen=True)
class Candidate:
    record: CapabilityRecord
    score: float
    reason: str


@dataclass(frozen=True)
class Selection:
    selected: tuple[Candidate, ...]
    skipped: tuple[Candidate, ...]
    task_terms: tuple[str, ...]

    @property
    def empty(self) -> bool:
        return not self.selected

    def to_text(self) -> str:
        lines = [f"Task terms: {', '.join(self.task_terms) or '(none)'}"]
        if self.selected:
            lines.append(f"Selected ({len(self.selected)}):")
            for candidate in self.selected:
                lines.append(
                    f"  {candidate.record.name} [{candidate.record.type}] "
                    f"score={candidate.score:.2f} - {candidate.reason}"
                )
        else:
            lines.append("Selected: (none)")
        if self.skipped:
            lines.append(f"Skipped ({len(self.skipped)}):")
            for candidate in self.skipped:
                lines.append(
                    f"  {candidate.record.name} [{candidate.record.type}] - {candidate.reason}"
                )
        return "\n".join(lines)


def _terms(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.casefold())
        if len(token) > 2 and token not in _STOPWORDS
    }


def select(
    task: str,
    records: Iterable[CapabilityRecord],
    *,
    limit: int = 3,
) -> Selection:
    """Rank available capabilities against a task description."""
    terms = _terms(task)
    if not terms:
        return Selection((), (), ())

    scored: list[tuple[float, int, CapabilityRecord, set[str]]] = []
    for record in records:
        if not record.available:
            continue
        haystack = _terms(f"{record.name} {record.description} {record.id}")
        overlap = terms & haystack
        if not overlap:
            continue
        score = len(overlap) / len(terms)
        scored.append((score, TYPE_PRIORITY.get(record.type, 5), record, overlap))

    scored.sort(key=lambda item: (-item[0], item[1], item[2].name.casefold()))

    selected: list[Candidate] = []
    skipped: list[Candidate] = []
    seen_names: set[str] = set()

    for score, _priority, record, overlap in scored:
        key = record.name.casefold()
        matched = ", ".join(sorted(overlap))
        if key in seen_names:
            skipped.append(
                Candidate(
                    record,
                    score,
                    f"duplicate name; already represented by a selected {record.type}",
                )
            )
            continue
        seen_names.add(key)
        if len(selected) < limit:
            selected.append(Candidate(record, score, f"matched {matched}"))
        else:
            skipped.append(
                Candidate(record, score, f"lower rank than the selected set (matched {matched})")
            )

    return Selection(tuple(selected), tuple(skipped), tuple(sorted(terms)))
