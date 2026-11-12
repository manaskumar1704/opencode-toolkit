"""Re-judge archived benchmark runs and render a stage report.

Validity (did the agent see the hidden oracle?) is decided by the leak
detector at run time. When that detector is corrected, archived runs must be
*re-judged*, not re-run: re-running only the flagged runs would bias the
sample toward whichever runs happened to be flagged.

Both commands read ``benchmarks/results/manifests/*.json``.

    python scripts/bench_evidence.py revalidate --dry-run
    python scripts/bench_evidence.py revalidate --write
    python scripts/bench_evidence.py report --label spec
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from benchmarks.driver import (
    RunOutcome,
    RunSpec,
    StageReport,
    cost_projection,
    evaluate_gate,
    render_stage_report,
)
from benchmarks.manifest import RunManifest
from benchmarks.workspace import oracle_leaks, tool_input_text

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = REPO / "benchmarks" / "results"


def _task_text(task: str) -> tuple[str, str, str]:
    """(oracle text, oracle relpath, visible setup text) for one task."""
    task_dir = REPO / "benchmarks" / "tasks" / task
    oracle = task_dir / "oracle" / "acceptance.py"
    oracle_text = oracle.read_text(encoding="utf-8") if oracle.is_file() else ""
    try:
        oracle_rel = str(oracle.relative_to(REPO))
    except ValueError:
        oracle_rel = str(oracle)
    setup = task_dir / "setup.patch"
    visible = setup.read_text(encoding="utf-8") if setup.is_file() else ""
    return oracle_text, oracle_rel, visible


def _leaks(manifest: RunManifest) -> list[str]:
    oracle_text, oracle_rel, visible = _task_text(manifest.task)
    transcript = Path(manifest.transcript_path)
    if not transcript.is_file():
        return ["transcript missing"]
    raw = transcript.read_text(encoding="utf-8", errors="ignore")
    return oracle_leaks(tool_input_text(raw) or raw, oracle_text, oracle_rel, visible)


def _load(results: Path) -> list[tuple[Path, RunManifest]]:
    loaded = []
    for path in sorted((results / "manifests").glob("*.json")):
        loaded.append((path, RunManifest.from_dict(json.loads(path.read_text()))))
    if not loaded:
        raise SystemExit(f"no manifests under {results / 'manifests'}")
    return loaded


def _spec(path: Path, manifest: RunManifest) -> RunSpec:
    rep = int(path.stem.rsplit("-r", 1)[1])
    return RunSpec(
        manifest.arm,
        manifest.task,
        manifest.task_category,
        str(REPO / "benchmarks" / "tasks" / manifest.task),
        rep,
        manifest.randomization_seed,
        manifest.run_order,
    )


def revalidate(results: Path, write: bool) -> int:
    changed = 0
    for path, manifest in _load(results):
        leaks = _leaks(manifest)
        valid = not leaks
        if manifest.correctness.get("valid") is valid:
            continue
        changed += 1
        print(
            f"{path.name}: valid {manifest.correctness.get('valid')} -> {valid}"
            f"  leaks={leaks}"
        )
        if write:
            manifest.correctness["valid"] = valid
            manifest.correctness["oracle_leaked"] = leaks
            path.write_text(
                json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
            )
    print(f"{changed} run(s) re-judged" + ("" if write else " (dry run)"))
    return 0


def report(results: Path, stage: int, label: str, tasks: list[str]) -> int:
    outcomes: list[RunOutcome] = []
    for path, manifest in _load(results):
        if tasks and manifest.task not in tasks:
            continue
        outcomes.append(
            RunOutcome(
                _spec(path, manifest),
                manifest,
                str(path),
                bool(manifest.correctness.get("acceptance_passed")),
            )
        )
    if not outcomes:
        raise SystemExit("no runs matched")

    gate = evaluate_gate(stage, outcomes)
    cost = cost_projection(
        outcomes,
        n_tasks=len({o.spec.task for o in outcomes}),
    )
    stage_report = StageReport(
        stage=stage,
        outcomes=outcomes,
        gate=gate,
        cost=cost,
        results_dir=str(results),
        label=label,
    )
    stem = f"stage-{stage}" + (f"-{label}" if label else "")
    (results / f"{stem}.json").write_text(
        json.dumps(stage_report.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    text = render_stage_report(stage_report)
    (results / f"{stem}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["revalidate", "report"])
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stage", type=int, default=1)
    parser.add_argument("--label", default="")
    parser.add_argument("--tasks", default="")
    args = parser.parse_args(argv)

    results = Path(args.results_dir)
    if args.command == "revalidate":
        return revalidate(results, write=args.write and not args.dry_run)
    tasks = [name.strip() for name in args.tasks.split(",") if name.strip()]
    return report(results, args.stage, args.label, tasks)


if __name__ == "__main__":
    sys.exit(main())
