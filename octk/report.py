"""Markdown + data report builders. Pure: no printing, no metric logging."""

from __future__ import annotations

from pathlib import Path
from statistics import median, mean
from typing import Any

from .config import read_json
from .metrics import approx_tokens

RESUME_MIN_PAIRS = 5


def _collect_tasks(paths: list[Path]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for path in paths:
        data = read_json(path, None)
        if isinstance(data, dict):
            tasks.extend(data.get("tasks", []) or [])
    return tasks


def _collect_unattributed(paths: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in paths:
        data = read_json(path, None)
        if isinstance(data, dict):
            out.extend(data.get("unattributed", []) or [])
    return out


def _collect_standing(paths: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in paths:
        data = read_json(path, None)
        if isinstance(data, dict):
            out.extend(data.get("standing_costs", []) or [])
    return out


def _task_tokens(task: dict[str, Any]) -> int:
    tin, tout = task.get("tokens_in"), task.get("tokens_out")
    if tin is not None or tout is not None:
        return int(tin or 0) + int(tout or 0)
    raw = sum(int(c.get("raw_chars", 0)) for c in task.get("tool_calls", []))
    return approx_tokens(raw)


def _pct_delta(with_value: float, without_value: float) -> float:
    """(without - with) / without, as percent; negative means octk was worse."""
    if not without_value:
        return 0.0
    return (without_value - with_value) / without_value * 100.0


def _pct_text(value: Any) -> str | None:
    return None if value is None else f"{float(value) * 100:.1f}%"


def _summary_by_mode(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mode in ("with_octk", "without_octk"):
        group = [t for t in tasks if t.get("mode") == mode and t.get("status") != "active"]
        durations = [float(t["duration_s"]) for t in group if t.get("duration_s") is not None]
        tokens = [_task_tokens(t) for t in group]
        cached = [
            float(t["cache_hit_rate"])
            for t in group
            if t.get("cache_hit_rate") is not None
        ]
        costs = [float(t["cost_usd"]) for t in group if t.get("cost_usd") is not None]
        turns = [int(t["turns"]) for t in group if t.get("turns") is not None]
        checked = [t for t in group if t.get("check_cmd")]
        passed = [t for t in checked if t.get("check_passed")]
        out[mode] = {
            "n": len(group),
            "pass_rate": (len(passed) / len(checked)) if checked else None,
            "n_checked": len(checked),
            "median_duration_s": median(durations) if durations else None,
            "mean_duration_s": mean(durations) if durations else None,
            "median_tokens": median(tokens) if tokens else None,
            "median_cache_hit_rate": median(cached) if cached else None,
            "median_cache_hit_rate_pct": _pct_text(median(cached) if cached else None),
            "median_cost_usd": median(costs) if costs else None,
            "median_turns": median(turns) if turns else None,
            "median_tool_calls": (
                median([len(t.get("tool_calls", [])) for t in group]) if group else None
            ),
        }
    return out


def _paired_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, dict[str, Any]]] = {}
    for t in tasks:
        if t.get("status") == "active":
            continue
        by_name.setdefault(str(t.get("name")), {}).setdefault(str(t.get("mode")), t)
    paired = []
    for name, modes in by_name.items():
        if "with_octk" in modes and "without_octk" in modes:
            paired.append(
                {
                    "name": name,
                    "with_octk": modes["with_octk"],
                    "without_octk": modes["without_octk"],
                }
            )
    return paired


def _paired_rows(paired: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for p in paired:
        w, o = p["with_octk"], p["without_octk"]
        rows.append(
            {
                "task": p["name"],
                "duration_s": {"with": w.get("duration_s"), "without": o.get("duration_s")},
                "duration_delta_pct": _pct_delta(
                    float(w.get("duration_s") or 0), float(o.get("duration_s") or 0)
                ),
                "tokens": {"with": _task_tokens(w), "without": _task_tokens(o)},
                "tokens_delta_pct": _pct_delta(
                    float(_task_tokens(w) or 0), float(_task_tokens(o) or 0)
                ),
                "cache_hit_rate": {
                    "with": w.get("cache_hit_rate"),
                    "without": o.get("cache_hit_rate"),
                },
                "cache_hit_rate_pct": {
                    "with": _pct_text(w.get("cache_hit_rate")),
                    "without": _pct_text(o.get("cache_hit_rate")),
                },
                "turns": {"with": w.get("turns"), "without": o.get("turns")},
                "turns_delta_pct": _pct_delta(
                    float(w.get("turns") or 0), float(o.get("turns") or 0)
                ),
                "check_passed": {
                    "with": w.get("check_passed"),
                    "without": o.get("check_passed"),
                },
            }
        )
    return rows


def _cache_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-task cache telemetry, newest last (metrics order)."""
    rows: list[dict[str, Any]] = []
    for task in tasks:
        if task.get("status") == "active" or task.get("cache_hit_rate") is None:
            continue
        rows.append(
            {
                "task": str(task.get("name")),
                "mode": task.get("mode"),
                "tokens_in": task.get("tokens_in"),
                "tokens_cached": task.get("tokens_cached", 0),
                "cache_hit_rate": task.get("cache_hit_rate"),
                "cache_hit_rate_pct": _pct_text(task.get("cache_hit_rate")),
            }
        )
    return rows


def _measured_tool_savings(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for t in tasks:
        for call in t.get("tool_calls", []):
            if call.get("kind") != "measured":
                continue
            slot = agg.setdefault(
                call["tool"], {"tool": call["tool"], "calls": 0, "raw_chars": 0, "pruned_chars": 0}
            )
            slot["calls"] += 1
            slot["raw_chars"] += int(call.get("raw_chars", 0))
            slot["pruned_chars"] += int(call.get("pruned_chars", 0))
    rows = []
    for slot in agg.values():
        raw, pruned = slot["raw_chars"], slot["pruned_chars"]
        slot["pct_reduction"] = ((raw - pruned) / raw * 100.0) if raw else 0.0
        slot["approx_tokens_saved"] = approx_tokens(max(raw - pruned, 0))
        rows.append(slot)
    return sorted(rows, key=lambda r: r["raw_chars"], reverse=True)


def _counterfactual_rows(paths: list[Path]) -> list[dict[str, Any]]:
    calls = _collect_unattributed(paths) + [
        c
        for t in _collect_tasks(paths)
        for c in t.get("tool_calls", [])
        if c.get("kind") == "counterfactual"
    ]
    agg: dict[str, dict[str, Any]] = {}
    for call in calls:
        if call.get("kind") != "counterfactual":
            continue
        slot = agg.setdefault(
            call["tool"], {"tool": call["tool"], "calls": 0, "raw_chars": 0, "pruned_chars": 0}
        )
        slot["calls"] += 1
        slot["raw_chars"] += int(call.get("raw_chars", 0))
        slot["pruned_chars"] += int(call.get("pruned_chars", 0))
    rows = []
    for slot in agg.values():
        raw, pruned = slot["raw_chars"], slot["pruned_chars"]
        slot["pct_reduction"] = ((raw - pruned) / raw * 100.0) if raw else 0.0
        slot["approx_tokens_saved"] = approx_tokens(max(raw - pruned, 0))
        rows.append(slot)
    return rows


def _load_total(paths: list[Path]) -> dict[str, int]:
    calls = [
        c
        for t in _collect_tasks(paths)
        for c in t.get("tool_calls", [])
        if c.get("kind") == "load"
    ] + [c for c in _collect_unattributed(paths) if c.get("kind") == "load"]
    return {
        "calls": len(calls),
        "chars": sum(int(c.get("pruned_chars", 0)) for c in calls),
        "approx_tokens": approx_tokens(sum(int(c.get("pruned_chars", 0)) for c in calls)),
    }


def _standing_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for entry in _collect_standing(paths):
        label = str(entry.get("label"))
        slot = rows.setdefault(label, {"label": label, "tokens_in": 0, "samples": 0})
        slot["tokens_in"] += int(entry.get("tokens_in", 0))
        slot["samples"] += 1
    bare = rows.get("bare", {}).get("tokens_in", 0)
    for slot in rows.values():
        slot["delta_vs_bare"] = slot["tokens_in"] - bare if "bare" in rows else None
    return [rows[k] for k in sorted(rows)]


def build_report_data(paths: list[Path]) -> dict[str, Any]:
    """Same numbers as the markdown report, as a dict."""
    tasks = _collect_tasks(paths)
    paired = _paired_tasks(tasks)
    return {
        "summary": _summary_by_mode(tasks),
        "paired": _paired_rows(paired),
        "measured_tools": _measured_tool_savings(tasks),
        "counterfactual": _counterfactual_rows(paths),
        "load": _load_total(paths),
        "cache": _cache_rows(tasks),
        "standing": _standing_rows(paths),
        "models": sorted({str(t.get("model")) for t in tasks if t.get("model")}),
        "n_paired": len(paired),
    }


def _num(value: Any, suffix: str = "") -> str:
    return "-" if value is None else f"{value:g}{suffix}"


def _fmt_pct(value: Any) -> str:
    return "-" if value is None else f"{float(value) * 100:.1f}%"


def _fmt_duration(seconds: Any) -> str:
    return "-" if seconds is None else f"{float(seconds):.3f}s"


def build_report(paths: list[Path]) -> str:
    """Honest markdown report from one or more metrics files."""
    import time

    data = build_report_data(paths)
    out = ["# octk report", ""]

    out += ["## Run summary", ""]
    out += [
        "| mode | n | pass rate | median duration | median approx tokens | median cache hit | median cost | median turns | median tool calls |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for mode, s in data["summary"].items():
        pass_rate = (
            f"{s['pass_rate'] * 100:.0f}% (of {s['n_checked']})" if s["pass_rate"] is not None else "-"
        )
        out.append(
            f"| {mode} | {s['n']} | {pass_rate} | {_fmt_duration(s['median_duration_s'])} | "
            f"{_num(s['median_tokens'])} | {_fmt_pct(s.get('median_cache_hit_rate'))} | "
            f"{_num(s['median_cost_usd'])} | "
            f"{_num(s['median_turns'])} | {_num(s['median_tool_calls'])} |"
        )

    out += ["", "## Paired tasks (with_octk vs without_octk)", ""]
    out += [
        "| task | duration w | duration wo | dur % | tokens w | tokens wo | tok % | cache w | cache wo | turns w | turns wo | turn % | pass w | pass wo |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in data["paired"]:
        out.append(
            f"| {row['task']} | {_fmt_duration(row['duration_s']['with'])} | "
            f"{_fmt_duration(row['duration_s']['without'])} | {row['duration_delta_pct']:+.1f}% | "
            f"{row['tokens']['with']} | {row['tokens']['without']} | {row['tokens_delta_pct']:+.1f}% | "
            f"{_fmt_pct(row['cache_hit_rate']['with'])} | {_fmt_pct(row['cache_hit_rate']['without'])} | "
            f"{_num(row['turns']['with'])} | {_num(row['turns']['without'])} | {row['turns_delta_pct']:+.1f}% | "
            f"{row['check_passed']['with']} | {row['check_passed']['without']} |"
        )

    out += ["", "## Measured tool-level savings (kind=measured) ", ""]
    out += ["| tool | calls | raw chars | pruned chars | % reduction | approx tokens saved |", "|---|---|---|---|---|---|"]
    for row in data["measured_tools"]:
        out.append(
            f"| {row['tool']} | {row['calls']} | {row['raw_chars']} | {row['pruned_chars']} | "
            f"{row['pct_reduction']:.1f}% | {row['approx_tokens_saved']} |"
        )
    if not data["measured_tools"]:
        out.append("(no measured tool calls recorded)")

    out += ["", "## Prefix-cache hit rate", ""]
    out += ["| task | mode | tokens in | tokens cached | cache hit |", "|---|---|---|---|---|"]
    for row in data["cache"]:
        out.append(
            f"| {row['task']} | {row['mode']} | {row['tokens_in']} | "
            f"{row['tokens_cached']} | {_fmt_pct(row['cache_hit_rate'])} |"
        )
    if not data["cache"]:
        out.append("(no cache token data recorded; use `octk task end --tokens-cached N`)")

    out += ["", "## Counterfactual estimate (not measured)", ""]
    out += ["| tool | calls | raw chars | pruned chars | % reduction | approx tokens saved |", "|---|---|---|---|---|---|"]
    for row in data["counterfactual"]:
        out.append(
            f"| {row['tool']} | {row['calls']} | {row['raw_chars']} | {row['pruned_chars']} | "
            f"{row['pct_reduction']:.1f}% | {row['approx_tokens_saved']} |"
        )
    if not data["counterfactual"]:
        out.append("(no counterfactual records)")

    out += ["", "## Context loaded via octk (kind=load)", ""]
    out.append(
        f"{data['load']['calls']} calls, {data['load']['chars']} chars delivered "
        f"(approx {data['load']['approx_tokens']} tokens)."
    )

    out += ["", "## Standing context cost (turn-1 input tokens)", ""]
    out += ["| label | turn-1 input tokens | delta vs bare |", "|---|---|---|"]
    for row in data["standing"]:
        delta = row["delta_vs_bare"]
        out.append(
            f"| {row['label']} | {row['tokens_in']} | "
            f"{'-' if delta is None else ('%-+d' % delta if isinstance(delta, int) else delta)} |"
        )
    if not data["standing"]:
        out.append("(no standing costs recorded; use `octk standing add <label> --tokens-in N`)")
    else:
        out.append("Label figures are exact recorded turn-1 input tokens (not the chars/4 proxy).")

    out += ["", "## Caveats", ""]
    out.append(
        f"n={data['n_paired']} paired tasks; models: "
        f"{', '.join(data['models']) or 'mixed/unrecorded'}; "
        "task-level tokens recorded when available, otherwise approx chars/4; "
        "tool-level 'approx tokens' uses the chars/4 proxy."
    )

    out += ["", "## Resume line", ""]
    n = data["n_paired"]
    if n < RESUME_MIN_PAIRS:
        out.append(f"Not enough paired tasks ({n}/{RESUME_MIN_PAIRS})")
    else:
        out.append(_resume_line(data) + f"\n_generated {time.strftime('%Y-%m-%d %H:%M:%S')}_")

    return "\n".join(out) + "\n"


def _resume_line(data: dict[str, Any]) -> str:
    """Deterministic resume line; worst-case honest."""
    pairs = data["paired"]
    dur = _mean_of([p["duration_delta_pct"] for p in pairs if p["duration_s"]["with"] is not None])
    tok = _mean_of([p["tokens_delta_pct"] for p in pairs if p["tokens"]["with"] is not None])
    turns = _mean_of([p["turns_delta_pct"] for p in pairs if p["turns"]["with"] is not None])
    pass_w = sum(1 for p in pairs if p["check_passed"]["with"])
    pass_o = sum(1 for p in pairs if p["check_passed"]["without"])
    models = ", ".join(data["models"]) or "unrecorded"
    line = (
        f"octk on {data['n_paired']} paired tasks"
        f" ({models}): mean duration {dur:+.1f}%, approx tokens {tok:+.1f}%,"
        f" turns {turns:+.1f}% vs without octk;"
        f" acceptance {pass_w}/{data['n_paired']} vs {pass_o}/{data['n_paired']}."
    )
    if (dur is not None and dur < 0) or (tok is not None and tok < 0) or (turns is not None and turns < 0):
        line += " Note: octk was worse on at least one metric - see the paired table."
    return line


def _mean_of(values: list[float]) -> float | None:
    return mean(values) if values else None
