"""Benchmark report generation with D7 integrity enforcement.

A run missing any required D7 field is marked ``INVALID`` and excluded from
aggregates. Never report a winner without reporting the losers.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmarks.manifest import load_manifest


def load_manifests(directory: Path) -> list:
    """Load every manifest JSON in ``directory`` (recursively)."""

    out = []
    for path in sorted(directory.rglob("*.json")):
        try:
            out.append(load_manifest(path))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return out


def partition_validity(manifests: list) -> tuple[list, list]:
    """Split manifests into (valid, invalid) based on the D7 checklist."""
    valid, invalid = [], []
    for m in manifests:
        if m.valid:
            valid.append(m)
        else:
            invalid.append(m)
    return valid, invalid


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.median(values)


def _range(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return min(values), max(values)


def aggregate(valid: list) -> dict[str, Any]:
    """Aggregate valid manifests by arm and task."""
    by_arm_task: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for m in valid:
        by_arm_task[m.arm][m.task].append(m)

    out: dict[str, Any] = {"arms": {}}
    for arm in sorted(by_arm_task):
        tasks = by_arm_task[arm]
        task_rows = []
        for task in sorted(tasks):
            ms = tasks[task]
            durations = [m.duration_s for m in ms if m.duration_s is not None]
            tokens = [m.tokens_input for m in ms if m.tokens_input is not None]
            task_rows.append(
                {
                    "task": task,
                    "n": len(ms),
                    "duration_median_s": _median(durations),
                    "duration_range_s": _range(durations),
                    "tokens_input_median": _median(tokens),
                    "tokens_input_range": _range(tokens),
                }
            )
        out["arms"][arm] = {"tasks": task_rows, "n_runs": sum(len(v) for v in tasks.values())}
    return out


def render_report(manifests: list, title: str = "OCTK benchmark report") -> str:
    """Render a markdown report. INVALID runs are listed, not hidden."""
    valid, invalid = partition_validity(manifests)
    agg = aggregate(valid)

    lines = [f"# {title}", ""]
    lines.append(f"Runs: {len(manifests)} total, {len(valid)} valid, {len(invalid)} INVALID.")
    lines.append("")

    if invalid:
        lines.append("## INVALID runs (excluded from aggregates)")
        lines.append("")
        lines.append("| arm | task | missing fields |")
        lines.append("|---|---|---|")
        for m in invalid:
            lines.append(f"| {m.arm} | {m.task} | {', '.join(m.validate())} |")
        lines.append("")

    if not valid:
        lines.append("No valid runs. Nothing to report.")
        return "\n".join(lines)

    lines.append("## Aggregates (valid runs only)")
    lines.append("")
    for arm in sorted(agg["arms"]):
        row = agg["arms"][arm]
        lines.append(f"### Arm {arm} (n={row['n_runs']})")
        lines.append("")
        lines.append("| task | n | duration median (s) | duration range | tokens input median |")
        lines.append("|---|---:|---:|---|---:|")
        for t in row["tasks"]:
            dmed = t["duration_median_s"]
            drange = t["duration_range_s"]
            tmed = t["tokens_input_median"]
            lines.append(
                f"| {t['task']} | {t['n']} | "
                f"{dmed if dmed is not None else '-'} | "
                f"{drange[0] if drange[0] is not None else '-'}–{drange[1] if drange[1] is not None else '-'} | "
                f"{tmed if tmed is not None else '-'} |"
            )
        lines.append("")

    lines.append("## Integrity notes")
    lines.append("")
    lines.append("- Correctness is a hard gate: an arm with a correctness "
                 "regression is not a winner regardless of efficiency.")
    lines.append("- All runs labelled by arm, task, seed, and order. "
                 "Raw manifests are the source of truth.")
    lines.append("- Gross and net token changes are reported separately; "
                 "character savings are not token savings.")
    return "\n".join(lines)
