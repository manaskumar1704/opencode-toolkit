"""Resumable batched test runner (stdlib only).

Usage:
    python scripts/test_batches.py            # run all batches, stop on first failure
    python scripts/test_batches.py --resume   # skip already-green batches
    python scripts/test_batches.py --batch 2  # run a single batch (1-based)

Each batch writes full output to ``reports/test-results/batch-<N>.log``, a JUnit
``batch-<N>.xml``, and updates ``reports/test-results/manifest.json`` so progress
survives any session/model cutoff and can be resumed from disk.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "reports" / "test-results"
MANIFEST = RESULTS / "manifest.json"

BATCHES: list[tuple[str, list[str]]] = [
    ("new EGM + agents + set-effort tests", ["tests/test_octk.py"]),
    (
        "modified legacy (scaffold + server)",
        ["tests/test_scaffold.py", "tests/test_server.py"],
    ),
    (
        "roadmap / pantry / cli",
        ["tests/test_roadmap_gate.py", "tests/test_pantry.py", "tests/test_cli.py"],
    ),
    (
        "remaining regression",
        [
            "tests/test_audit.py",
            "tests/test_metrics_report.py",
            "tests/test_debugger.py",
            "tests/test_browser.py",
            "tests/test_safety.py",
            "tests/test_bench.py",
        ],
    ),
]


def _load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"batches": {}}
    return {"batches": {}}


def _save_manifest(manifest: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _run_batch(index: int) -> int:
    label, files = BATCHES[index]
    num = index + 1
    RESULTS.mkdir(parents=True, exist_ok=True)
    log = RESULTS / f"batch-{num}.log"
    xml = RESULTS / f"batch-{num}.xml"
    cmd = [sys.executable, "-m", "pytest", *files, "-q", f"--junitxml={xml}"]
    print(f"[batch {num}] {label}")
    with log.open("w", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(cmd) + "\n\n")
        fh.flush()
        proc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode


def main() -> int:
    argv = sys.argv[1:]
    resume = "--resume" in argv
    only: int | None = None
    if "--batch" in argv:
        only = int(argv[argv.index("--batch") + 1]) - 1

    manifest = _load_manifest()
    indices = [only] if only is not None else range(len(BATCHES))

    for index in indices:
        key = str(index + 1)
        if resume and manifest["batches"].get(key, {}).get("passed"):
            print(f"[batch {index + 1}] already green; skipped")
            continue
        code = _run_batch(index)
        passed = code == 0
        manifest["batches"][key] = {
            "label": BATCHES[index][0],
            "passed": passed,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _save_manifest(manifest)
        print(f"[batch {index + 1}] {'passed' if passed else 'FAILED'}")
        if not passed:
            print(f"  -> see reports/test-results/batch-{index + 1}.log")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
