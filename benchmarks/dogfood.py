"""Paired dogfood runs: inject a bug, run opencode headless, score the fix.

Arms: `with_octk` (worktree retains the octk mount) and `without_octk`
(octk surface stripped). Every run is transcript-captured to
benchmarks/results/*.jsonl (gitignored); tokens and turns come from the
OpenCode session DB; results are written with MetricsStore so
`octk report` can aggregate them honestly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WITH = REPO.parent / "otk-with"
BARE = REPO.parent / "otk-bare"
RESULTS = REPO / "benchmarks" / "results"
BARE_METRICS = RESULTS / "bare_metrics.json"
OPENCODE = shutil.which("opencode") or "opencode"
DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
MODEL = "opencode-go/deepseek-v4.1-flash"
PROMPT = (
    "In this repository, `{test}` fails. Find and fix the source bug so that "
    "`{test}` passes. Do not modify test files. Run that command once at the "
    "end to confirm, then stop."
)

TASKS = [
    {
        "name": "roadmap-gate",
        "file": "octk/roadmap.py",
        "old": (
            "        granted = approvals.find_valid_approval(root, task_text, now)\n"
            "        if granted is None:\n"
            '            raise GateError(f"no valid approval for: {task_text}")\n'
            "        approvals.consume_approval(root, granted, now)"
        ),
        "new": (
            "        granted = approvals.find_valid_approval(root, task_text, now)\n"
            "        if granted is not None:\n"
            "            approvals.consume_approval(root, granted, now)"
        ),
        "test": "tests/test_roadmap_gate.py",
    },
    {
        "name": "pantry-desc",
        "file": "octk/pantry.py",
        "old": '        r"(?m)^description:\\s*(.+)$", text',
        "new": '        r"^description:\\s*(.+)$", text',
        "test": "tests/test_pantry.py",
    },
    {
        "name": "metrics-tokens",
        "file": "octk/metrics.py",
        "old": "    return (int(chars) + 3) // 4",
        "new": "    return int(chars) // 4",
        "test": "tests/test_metrics_report.py",
    },
    {
        "name": "debugger-locals",
        "file": "octk/runtime/debugger.py",
        "old": 'LOCALS_RE = re.compile(r"^\\s{2,}(local\\s+\\w+\\s*=|\\w+\\s*=\\s)")',
        "new": 'LOCALS_RE = re.compile(r"^\\s{2,}local\\s+\\w+\\s*=")',
        "test": "tests/test_debugger.py",
    },
    {
        "name": "scaffold-gitignore",
        "file": "octk/scaffold.py",
        "old": '    wanted = (".toolkit/metrics.json", ".toolkit/approvals.json")',
        "new": '    wanted = (".toolkit/metrics.json",)',
        "test": "tests/test_scaffold.py",
    },
]


def _git(worktree: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=worktree, capture_output=True, text=True, check=False
    )


def reset(worktree: Path, arm: str) -> None:
    """Restore tracked files, keep envs/metrics, strip octk for the bare arm."""
    _git(worktree, "checkout", "--", ".")
    _git(worktree, "clean", "-fdq", "-e", ".venv", "-e", ".toolkit", "-e", ".pytest_cache")
    if arm == "without_octk":
        for rel in ("AGENTS.md", "opencode.json", ".toolkit", ".opencode/commands"):
            path = worktree / rel
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()


def fix_with_config() -> None:
    """Point the with-arm MCP server at the with-worktree's own code."""
    path = WITH / "opencode.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mcp"]["servers"]["octk"]["command"] = [
        str(WITH / ".venv" / "Scripts" / "octk-mcp.EXE")
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def apply_mutation(worktree: Path, task: dict) -> None:
    path = worktree / task["file"]
    text = path.read_text(encoding="utf-8")
    if task["old"] not in text:
        raise SystemExit(f"mutation anchor missing in {task['file']}")
    path.write_text(text.replace(task["old"], task["new"], 1), encoding="utf-8")


def _find_session(stdout: str) -> str | None:
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = event.get("sessionID") or event.get("session_id")
        if isinstance(session_id, str):
            return session_id
    return None


def run_agent(worktree: Path, task: dict, arm: str) -> dict:
    prompt = PROMPT.format(test=task["test"])
    started = time.monotonic()
    proc = subprocess.run(
        [
            OPENCODE, "run", "--model", MODEL, "--format", "json",
            "--title", f"dogfood:{task['name']}:{arm}", prompt,
        ],
        cwd=str(worktree), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    duration = round(time.monotonic() - started, 3)
    (RESULTS / f"{task['name']}_{arm}.jsonl").write_text(proc.stdout, encoding="utf-8")
    return {
        "session": _find_session(proc.stdout),
        "duration_s": duration,
        "exit": proc.returncode,
        "stderr_tail": proc.stderr[-400:],
    }


def _parts(session_id: str) -> list[dict]:
    import sqlite3

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT data FROM part WHERE session_id = ? ORDER BY time_created", (session_id,)
    ).fetchall()
    con.close()
    out = []
    for (raw,) in rows:
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def collect(session_id: str, jsonl_path: Path | None = None) -> dict:
    """Token usage + turns from the session DB (exact, no char proxy)."""
    import sqlite3

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    row = con.execute(
        "SELECT tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, "
        "tokens_cache_write, time_created, time_updated FROM session_v2 WHERE id = ?",
        (session_id,),
    ).fetchone()
    con.close()
    if row is None:
        raise SystemExit(f"session not found in DB: {session_id}")
    tin, tout, reason, cache_read, cache_write, created, updated = row
    turns = 0
    first_turn_in = None
    if jsonl_path is not None and jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "step_finish":
                continue
            turns += 1
            part = event.get("part", {})
            tokens = part.get("tokens", {})
            cache = tokens.get("cache", {})
            step_in = (
                int(tokens.get("input", 0))
                + int(cache.get("read", 0))
                + int(cache.get("write", 0))
            )
            if first_turn_in is None:
                first_turn_in = step_in
    return {
        "tokens_in": int(tin) + int(cache_read) + int(cache_write),
        "tokens_out": int(tout) + int(reason),
        "turns": turns,
        "first_turn_in": first_turn_in,
        "started_at": created / 1000.0,
        "ended_at": updated / 1000.0,
    }


def run_check(worktree: Path, task: dict) -> bool:
    py = worktree / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run(
        [str(py), "-m", "pytest", "-q", task["test"]],
        cwd=str(worktree), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    (RESULTS / f"{task['name']}_{worktree.name}.pytest.txt").write_text(
        proc.stdout + proc.stderr, encoding="utf-8"
    )
    return proc.returncode == 0


def _clear_active(store_path: Path) -> None:
    from octk.metrics import MetricsStore

    store = MetricsStore(store_path)
    if store._data.get("active_task"):
        store._data["active_task"] = None
        for t in store._data["tasks"]:
            if t.get("status") == "active":
                t["status"] = "aborted"
        store._save()


def run_pair(task: dict, arms: list[str]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    scores: dict[str, dict] = {}
    for arm in arms:
        worktree = WITH if arm == "with_octk" else BARE
        reset(worktree, arm)
        if arm == "with_octk":
            fix_with_config()
        apply_mutation(worktree, task)
        store_path = (
            (WITH / ".toolkit" / "metrics.json")
            if arm == "with_octk"
            else BARE_METRICS
        )
        _clear_active(store_path)
        from octk.metrics import MetricsStore

        pre = MetricsStore(store_path)
        pre.start_task(task["name"], mode=arm, model=MODEL, started_at=time.time())
        agent = run_agent(worktree, task, arm)
        if not agent["session"]:
            _clear_active(store_path)
            raise SystemExit(
                f"no session id captured for {task['name']}/{arm}; "
                f"stderr tail: {agent['stderr_tail']}"
            )
        usage = collect(agent["session"], RESULTS / f"{task['name']}_{arm}.jsonl")
        passed = run_check(worktree, task)
        store = MetricsStore(store_path)
        for t in reversed(store._data["tasks"]):
            if t.get("name") == task["name"] and t.get("status") == "active":
                t["started_at"] = usage["started_at"]
                break
        store.end_task(
            status="completed",
            check_cmd=task["test"],
            check_passed=passed,
            tokens_in=usage["tokens_in"],
            tokens_out=usage["tokens_out"],
            turns=usage["turns"],
            ended_at=usage["ended_at"],
        )
        scores[arm] = {
            "session": agent["session"],
            "passed": passed,
            "duration_s": round(usage["ended_at"] - usage["started_at"], 3),
            "tokens_in": usage["tokens_in"],
            "tokens_out": usage["tokens_out"],
            "turns": usage["turns"],
        }
        print(
            f"[{task['name']}/{arm}] passed={passed} turns={usage['turns']} "
            f"tok_in={usage['tokens_in']} tok_out={usage['tokens_out']} "
            f"dur={scores[arm]['duration_s']}s"
        )
    (RESULTS / f"{task['name']}.json").write_text(
        json.dumps(scores, indent=2), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dogfood")
    parser.add_argument("--task", help="task name (default: all)")
    parser.add_argument(
        "--arms", default="with_octk,without_octk",
        help="comma-separated arms",
    )
    args = parser.parse_args(argv)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ("with_octk", "without_octk")]
    if unknown:
        parser.error(f"unknown arms: {unknown}")
    names = [t["name"] for t in TASKS]
    if args.task:
        if args.task not in names:
            parser.error(f"unknown task {args.task!r}; choose from {names}")
        selected = [t for t in TASKS if t["name"] == args.task]
    else:
        selected = TASKS
    for task in selected:
        run_pair(task, arms)
    return 0


if __name__ == "__main__":
    sys.exit(main())
