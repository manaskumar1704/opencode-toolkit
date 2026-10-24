"""octk CLI. The only module allowed to touch Path.cwd() / OCTK_ROOT."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import report as report_mod
from .approvals import create_approval, list_approvals
from .config import ToolkitPaths, load_config
from .metrics import MetricsStore
from .roadmap import parse_roadmap, set_status
from .scaffold import init_repo


def get_root() -> Path:
    """Resolve project root (OCTK_ROOT or cwd) - CLI only."""
    return Path(os.environ.get("OCTK_ROOT") or Path.cwd()).resolve()


def _metrics(paths: ToolkitPaths) -> MetricsStore:
    return MetricsStore(paths.metrics)


def cmd_init(args: argparse.Namespace) -> int:
    paths = ToolkitPaths(get_root())
    created = init_repo(paths.root, force=args.force)
    cfg = load_config(paths.root)
    print(json.dumps({"created": created["created"], "skipped": created["skipped"], **kwargs(cfg)}, indent=2))
    return 0


def kwargs(cfg: dict) -> dict:
    # helper keeps cmd_init short; stable JSON output for humans/CI
    return {
        "always_on_skills": cfg.get("always_on_skills", []),
        "server_name": cfg.get("server_name", "octk"),
        "audit_mode": cfg.get("audit_mode", "instruct"),
    }


def _roadmap_lines(root: Path) -> list[str]:
    return [str(e["text"]) for e in parse_roadmap(root)]


def _match_lines(lines: list[str], needle: str) -> list[str]:
    folded = needle.casefold()
    out: list[str] = []
    for line in lines:
        if folded in line.casefold() and line not in out:
            out.append(line)
    return out


def cmd_approve(args: argparse.Namespace) -> int:
    paths = ToolkitPaths(get_root())
    if args.list:
        approvals = list_approvals(paths.root)
        for a in approvals:
            state = "consumed" if a.get("consumed_at") else "open"
            print(f"{a['id']}  {state}  {a['task_substring']}")
        return 0
    if not sys.stdin.isatty():
        print("octk approve must be run by a human in a terminal (TTY required)", file=sys.stderr)
        return 2
    matches = _match_lines(_roadmap_lines(paths.root), args.task)
    if not matches:
        print(f"no roadmap line matches: {args.task}", file=sys.stderr)
        return 1
    print("Matching roadmap line:")
    for m in matches:
        print(f"  {m}")
    answer = input("Approve? [y/N] ")
    if answer.strip().lower() != "y":
        print("not approved")
        return 1
    approval = create_approval(paths.root, args.task)
    print(f"approval created: {approval['id']}")
    return 0


def cmd_task(args: argparse.Namespace) -> int:
    paths = ToolkitPaths(get_root())
    store = _metrics(paths)
    if args.task_command == "start":
        store.start_task(args.name, mode=args.mode, model=args.model)
        print(f"started: {args.name} ({args.mode})")
        return 0
    check_cmd = args.check
    check_passed: bool | None = None
    if check_cmd:
        check_passed = _run_check(check_cmd, paths.root)
        print(f"check exit code 0: {check_passed}")
    store.end_task(
        status=args.status,
        notes=args.notes,
        tokens_in=args.tokens_in,
        tokens_out=args.tokens_out,
        cost_usd=args.cost_usd,
        turns=args.turns,
        check_cmd=check_cmd,
        check_passed=check_passed,
    )
    print("task ended")
    return 0


def _run_check(check_cmd: str, root: Path) -> bool:
    argv = shlex.split(check_cmd)
    if shutil.which(argv[0]):
        argv[0] = str(Path(shutil.which(argv[0])))
    try:
        proc = subprocess.run(argv, cwd=root, timeout=600, capture_output=True)
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def cmd_report(args: argparse.Namespace) -> int:
    paths = ToolkitPaths(get_root())
    files = [Path(p).expanduser().resolve() for p in (args.files or [str(paths.metrics)])]
    if args.json:
        data = report_mod.build_report_data(files)
        text = json.dumps(data, indent=2, default=str)
    else:
        text = report_mod.build_report(files)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"report written: {out}")
    else:
        print(text)
    return 0


def cmd_standing(args: argparse.Namespace) -> int:
    paths = ToolkitPaths(get_root())
    entry = _metrics(paths).add_standing(args.label, args.tokens_in)
    print(f"standing recorded: {entry['label']} = {entry['tokens_in']} input tokens")
    return 0


def mcp_config_json() -> dict:
    """OpenCode V2 snippet: mcp.servers + permissions rule array."""
    exe = shutil.which("octk-mcp")
    command = [exe] if exe else [sys.executable, "-m", "octk.server"]
    return {
        "mcp": {
            "servers": {
                "octk": {"type": "local", "command": command, "codemode": False},
            }
        },
        "permissions": [
            {"action": "shell", "resource": "octk approve *", "effect": "deny"},
            {"action": "edit", "resource": ".toolkit/approvals.json", "effect": "deny"},
            {"action": "edit", "resource": ".toolkit/metrics.json", "effect": "deny"},
            {"action": "edit", "resource": ".toolkit/specs/roadmap.md", "effect": "ask"},
        ],
    }


def cmd_mcp_config(_args: argparse.Namespace) -> int:
    print(json.dumps(mcp_config_json(), indent=2))
    print(
        "\n# notes\n"
        "# - these rules stop a drifting agent, not a determined one (the agent still has shell access)\n"
        "# - if OpenCode launches the server from elsewhere, add \"environment\": {\"OCTK_ROOT\": \"<abs project path>\"}"
    )
    return 0


def cmd_bench_tools(args: argparse.Namespace) -> int:
    """Run the tool bench; write the report; exit 1 on lost signals."""
    from . import bench as bench_mod

    root = get_root()
    results = bench_mod.run_tool_bench(root)
    if args.json:
        print(json.dumps(results, indent=2))
    out_path = Path(args.out) if args.out else root / "reports" / "BENCH_TOOLS.md"
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(bench_mod.format_bench(results), encoding="utf-8")
    note = f"bench report written: {out_path}"
    print(note, file=sys.stderr) if args.json else print(note)
    failed = [
        case["name"]
        for case in results["cases"]
        if not case["skipped"] and case["signals"]["retention"] < 1.0
    ]
    if failed:
        print("octk bench FAILED (signals lost): " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="octk")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="scaffold octk files")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_approve = sub.add_parser("approve", help="create an approval (human, TTY required)")
    p_approve.add_argument("task", nargs="?", help="roadmap task substring")
    p_approve.add_argument("--list", action="store_true")
    p_approve.set_defaults(func=cmd_approve)

    p_task = sub.add_parser("task", help="task run bookkeeping")
    task_sub = p_task.add_subparsers(dest="task_command", required=True)
    p_start = task_sub.add_parser("start")
    p_start.add_argument("name")
    p_start.add_argument("--mode", choices=["with_octk", "without_octk"], default="with_octk")
    p_start.add_argument("--model")
    p_start.set_defaults(func=cmd_task)
    p_end = task_sub.add_parser("end")
    p_end.add_argument("--status", choices=["completed", "failed", "abandoned"], default="completed")
    p_end.add_argument("--notes")
    p_end.add_argument("--tokens-in", type=int)
    p_end.add_argument("--tokens-out", type=int)
    p_end.add_argument("--cost-usd", type=float)
    p_end.add_argument("--turns", type=int)
    p_end.add_argument("--check")
    p_end.set_defaults(func=cmd_task, notes="")

    p_report = sub.add_parser("report", help="build metrics report")
    p_report.add_argument("--files", nargs="*")
    p_report.add_argument("--json", action="store_true")
    p_report.add_argument("--out")
    p_report.set_defaults(func=cmd_report)

    p_standing = sub.add_parser("standing", help="standing context costs")
    standing_sub = p_standing.add_subparsers(dest="standing_command", required=True)
    p_add = standing_sub.add_parser("add")
    p_add.add_argument("label")
    p_add.add_argument("--tokens-in", type=int, required=True)
    p_add.set_defaults(func=cmd_standing)

    p_mcp = sub.add_parser("mcp-config", help="print the opencode.json snippet (V2 syntax)")
    p_mcp.set_defaults(func=cmd_mcp_config)

    p_bench = sub.add_parser("bench", help="tool-level benchmarks")
    bench_sub = p_bench.add_subparsers(dest="bench_command", required=True)
    p_tools = bench_sub.add_parser("tools", help="score pruners on generated fixtures")
    p_tools.add_argument("--out", default=None, help="report path (default reports/BENCH_TOOLS.md)")
    p_tools.add_argument("--json", action="store_true", help="also print raw results as JSON")
    p_tools.set_defaults(func=cmd_bench_tools)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
