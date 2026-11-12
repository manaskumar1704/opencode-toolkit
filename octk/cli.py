"""octk CLI. The only module allowed to touch Path.cwd() / OCTK_ROOT."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path

from . import report as report_mod
from .adapters import agent_names, agents_dir, mcp_config
from .approvals import create_approval, list_approvals
from .audit import run_audit_workflow as run_audit
from .config import ToolkitPaths, load_config
from .doctor import format_doctor, run_doctor
from .handoff import generate_handoff
from .metrics import MetricsStore, approx_tokens
from .roadmap import parse_roadmap, set_status
from .runtime import safety
from .scaffold import init_repo

CHECK_TIMEOUT_S = 600


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
        config = load_config(paths.root)
        allowed = list(config.get("allowed_commands", []))
        check_passed, detail = _run_check(check_cmd, paths.root, allowed)
        print(f"check exit code 0: {check_passed} ({detail})")
    store.end_task(
        status=args.status,
        notes=args.notes,
        tokens_in=args.tokens_in,
        tokens_out=args.tokens_out,
        tokens_cached=args.tokens_cached,
        cost_usd=args.cost_usd,
        turns=args.turns,
        check_cmd=check_cmd,
        check_passed=check_passed,
    )
    print("task ended")
    return 0


def _run_check(check_cmd: str, root: Path, allowed: list[str]) -> tuple[bool, str]:
    """Run a verification command under the same allowlist as every other command.

    This used to call ``subprocess.run`` directly, so ``--check`` could run
    anything on PATH with no allowlist at all. It now goes through
    ``runtime.safety.run_command`` like every other subprocess in the project.
    """
    argv = shlex.split(check_cmd)
    if not argv:
        return False, "empty command"
    try:
        result = safety.run_command(argv, root, allowed, timeout_s=CHECK_TIMEOUT_S)
    except safety.CommandNotAllowed as exc:
        return False, str(exc)
    if result.timed_out:
        return False, f"timed out after {CHECK_TIMEOUT_S}s"
    return result.returncode == 0, f"exit code {result.returncode}"


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
    store = _metrics(paths)

    if getattr(args, "standing_command", None) == "schema":
        from . import bench as bench_mod

        head = bench_mod.schema_overhead()
        schema_tokens = approx_tokens(head["total_bytes"])
        store.add_standing("octk-schema", schema_tokens)
        recorded: dict[str, object] = {
            "octk-schema": schema_tokens,
            "tools": head["tools"],
            "schema_bytes": head["total_bytes"],
            "basis": "chars/4 proxy, not provider-measured",
        }
        agents = get_root() / args.agents_md
        if agents.exists():
            agents_tokens = approx_tokens(agents.stat().st_size)
            store.add_standing("octk-agents-md", agents_tokens)
            recorded["octk-agents-md"] = agents_tokens
            recorded["agents_md_bytes"] = agents.stat().st_size
        print(json.dumps(recorded, indent=2))
        return 0

    entry = store.add_standing(args.label, args.tokens_in)
    print(f"standing recorded: {entry['label']} = {entry['tokens_in']} input tokens")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    data = run_doctor(get_root())
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_doctor(data), end="")
    return 0 if data["status"] == "pass" else 1


def cmd_handoff(args: argparse.Namespace) -> int:
    paths = ToolkitPaths(get_root())
    out = Path(args.out) if args.out else paths.handoff
    if not out.is_absolute():
        out = paths.root / out
    text = generate_handoff(paths.root, out)
    print(text, end="")
    print(f"handoff written: {out}", file=sys.stderr)
    return 0


def mcp_config_json() -> dict:
    """Harness MCP config snippet: mcp.servers + permissions rule array."""
    return mcp_config()


def cmd_mcp_config(args: argparse.Namespace) -> int:
    print(json.dumps(mcp_config_json(), indent=2))
    if getattr(args, "json", False):
        # Pure JSON, so it can be redirected into a config file.
        return 0
    print(
        "\n# notes\n"
        "# - these rules stop a drifting agent, not a determined one (the agent still has shell access)\n"
        "# - if the harness launches the server from elsewhere, add \"environment\": {\"OCTK_ROOT\": \"<abs project path>\"}"
    )
    return 0


AGENTS_DIR = agents_dir
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def _agent_path(root: Path, name: str) -> Path:
    return root / AGENTS_DIR / f"{name}.md"


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter, body). Frontmatter is the leading --- fenced YAML."""
    if text.startswith("---"):
        idx = text.find("\n---", 3)
        if idx != -1:
            return text[: idx + 4], text[idx + 4 :]
    return "", text


def _frontmatter_field(fm: str, key: str) -> str:
    match = re.search(rf"(?m)^{key}:\s*(\S+)", fm)
    return match.group(1) if match else "-"


def _check_agent(name: str) -> int | None:
    """Return an exit code on an invalid agent name, else None."""
    if name in agent_names:
        return None
    print(f"unknown agent: {name!r} (choose from {', '.join(agent_names)})", file=sys.stderr)
    return 1


def _load_agent_file(root: Path, name: str) -> tuple[Path, str, str] | None:
    """Return (path, frontmatter, body), or None after printing an error."""
    path = _agent_path(root, name)
    if not path.exists():
        print(f"agent file not found: {path} (run `octk init`)", file=sys.stderr)
        return None
    text = path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    return path, fm, body


DEPRECATION_NOTICE = (
    "octk: warning: model/effort commands belong to the harness, not OCTK. "
    "They will be removed in a future release; use your harness configuration."
)


def _warn_deprecated() -> None:
    print(DEPRECATION_NOTICE, file=sys.stderr)


def cmd_models(_args: argparse.Namespace) -> int:
    _warn_deprecated()
    root = get_root()
    header = f"{'AGENT':<12} {'MODE':<9} {'MODEL':<38} EFFORT"
    print(header)
    for name in agent_names:
        path = _agent_path(root, name)
        if not path.exists():
            print(f"{name:<12} {'-':<9} {'-':<38} -")
            continue
        fm, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
        mode = _frontmatter_field(fm, "mode")
        model = _frontmatter_field(fm, "model")
        effort = _frontmatter_field(fm, "effort")
        print(f"{name:<12} {mode:<9} {model:<38} {effort}")
    return 0


def cmd_set_model(args: argparse.Namespace) -> int:
    _warn_deprecated()
    code = _check_agent(args.agent_name)
    if code is not None:
        return code
    loaded = _load_agent_file(get_root(), args.agent_name)
    if loaded is None:
        return 1
    path, fm, body = loaded
    new_fm = re.sub(r"(?m)^model:\s*.*$", f"model: {args.model_id}", fm, count=1)
    if "model:" not in new_fm:
        print(f"no `model:` line in {path}", file=sys.stderr)
        return 1
    path.write_text(new_fm + body, encoding="utf-8")
    print(f"{args.agent_name} model: {args.model_id}")
    return 0


def cmd_set_effort(args: argparse.Namespace) -> int:
    _warn_deprecated()
    code = _check_agent(args.agent_name)
    if code is not None:
        return code
    loaded = _load_agent_file(get_root(), args.agent_name)
    if loaded is None:
        return 1
    path, fm, body = loaded
    level = args.level
    new_fm = re.sub(r"(?m)^effort:\s*.*$", f"effort: {level}", fm, count=1)
    if "effort:" not in new_fm:
        new_fm = re.sub(
            r"(?m)^(model:\s*[^\n]*)$", rf"\1\neffort: {level}", new_fm, count=1
        )
    # Keep the model line's #variant suffix in sync with effort.
    new_fm = re.sub(
        r"(?m)^(model:\s*[^\s#]+)(?:#\S+)?(\s*)$",
        rf"\1#{level}\2",
        new_fm,
        count=1,
    )
    path.write_text(new_fm + body, encoding="utf-8")
    print(f"{args.agent_name} effort: {level}")
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


def cmd_capabilities(args: argparse.Namespace) -> int:
    """Inspect, discover, verify, or manually register capabilities."""
    from . import capabilities as caps_mod
    from .adapters import OpenCodeAdapter

    root = get_root()
    sub = args.capabilities_command
    paths = ToolkitPaths(root)

    if sub == "discover":
        adapter = OpenCodeAdapter(root)
        outcome = adapter.discover_capabilities()
        if not outcome.records and outcome.reason:
            print(f"nothing to discover: {outcome.reason}", file=sys.stderr)
            return 1
        discovered = list(outcome)
        if outcome.reason:
            print(f"note: {outcome.reason}", file=sys.stderr)
        if args.write:
            merged = caps_mod.sync_discovered(root, discovered)
            print(f"wrote {len(merged)} capabilities to {paths.capabilities_index}")
        else:
            print(caps_mod.render_l0(discovered))
            print("\n(dry run; pass --write to update the project index)", file=sys.stderr)
        return 0

    if sub == "select":
        from .selector import select as select_capabilities

        registry = caps_mod.load_registry(root)
        result = select_capabilities(args.task, registry.records, limit=args.limit)
        print(result.to_text())
        return 0

    registry = caps_mod.load_registry(root)

    if sub == "list":
        print(caps_mod.render(registry, level=args.level, query=args.query))
        return 0

    if sub == "show":
        text = caps_mod.render(
            registry, level=args.level, capability_id=args.capability_id
        )
        print(text)
        return 1 if text.startswith("octk error:") else 0

    if sub == "verify":
        adapter = OpenCodeAdapter(root)
        discovered_ids: set[str] = set()
        outcome = adapter.discover_capabilities()
        if outcome.reason:
            print(f"note: {outcome.reason}", file=sys.stderr)
        for record in outcome:
            discovered_ids.add(record.id)
        registered_ids = {record.id for record in registry.records}
        new = sorted(discovered_ids - registered_ids)
        stale = sorted(registered_ids - discovered_ids)
        print(f"registered: {len(registered_ids)}  discovered: {len(discovered_ids)}")
        if new:
            print("new (discovered, not registered):")
            for item in new:
                print(f"  {item}")
        if stale:
            print("stale (registered, no longer discovered):")
            for item in stale:
                print(f"  {item}")
        if not new and not stale:
            print("registry matches discovery")
        return 0 if not stale else 1

    if sub == "register":
        data: dict[str, object] = {
            "id": args.id,
            "type": args.type,
            "name": args.name,
            "description": args.description,
            "provider": args.provider,
        }
        if args.source_path:
            data["source_path"] = args.source_path
        record = caps_mod.register(root, data)
        print(f"registered {record.id} -> {paths.capabilities_index}")
        return 0

    print(f"unknown capabilities command: {sub}", file=sys.stderr)
    return 2


def cmd_providers(args: argparse.Namespace) -> int:
    """Report external provider status. Detection only; runs nothing."""
    from .providers import graphify, ponytail

    root = get_root()
    cfg = load_config(root)
    statuses = [graphify.detect(root, cfg), ponytail.detect(root, cfg)]

    if args.json:
        print(json.dumps([status.to_dict() for status in statuses], indent=2))
        return 0

    for status in statuses:
        state = f", state={status.state}" if status.state else ""
        version = f", version={status.version}" if status.version else ""
        available = "available" if status.available else "absent"
        print(f"{status.id}: {available}{state}{version}")
        print(f"  {status.detail}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Run the audit workflow (graph freshness + Ponytail review)."""
    paths = ToolkitPaths(get_root())
    cfg = load_config(paths.root)
    result = run_audit(paths.root, cfg, audit_cmd=args.audit_cmd)
    print(result.text)
    return 0


def cmd_roadmap(args: argparse.Namespace) -> int:
    """Roadmap operations: list or set a line's status."""
    paths = ToolkitPaths(get_root())
    if args.roadmap_command == "list":
        for line in _roadmap_lines(paths.root):
            print(line)
        return 0
    try:
        line = set_status(paths.root, args.task_substring, args.new_status)
        print(line)
        return 0
    except Exception as exc:  # noqa: BLE001 - GateError/RoadmapError become strings
        print(f"octk error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    from .capabilities import CAPABILITY_TYPES

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
    p_end.add_argument(
        "--tokens-cached",
        "--cache-read",
        dest="tokens_cached",
        type=int,
        default=0,
        help="cached input tokens (cache.read); default 0",
    )
    p_end.add_argument("--cost-usd", type=float)
    p_end.add_argument("--turns", type=int)
    p_end.add_argument("--check")
    p_end.set_defaults(func=cmd_task, notes="")

    p_report = sub.add_parser("report", help="build metrics report")
    p_report.add_argument("--files", nargs="*")
    p_report.add_argument("--json", action="store_true")
    p_report.add_argument("--out")
    p_report.set_defaults(func=cmd_report)

    p_doctor = sub.add_parser("doctor", help="check prefix-cache safety and gate integrity")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    p_handoff = sub.add_parser("handoff", help="write a deterministic session handoff snapshot")
    p_handoff.add_argument("--out", default=None, help="default .toolkit/handoff.md")
    p_handoff.set_defaults(func=cmd_handoff)

    p_standing = sub.add_parser("standing", help="standing context costs")
    standing_sub = p_standing.add_subparsers(dest="standing_command", required=True)
    p_add = standing_sub.add_parser("add")
    p_add.add_argument("label")
    p_add.add_argument("--tokens-in", type=int, required=True)
    p_add.set_defaults(func=cmd_standing)

    p_schema = standing_sub.add_parser(
        "schema", help="record the MCP tool-schema and AGENTS.md standing cost"
    )
    p_schema.add_argument("--agents-md", default="AGENTS.md")
    p_schema.set_defaults(func=cmd_standing)

    p_mcp = sub.add_parser("mcp-config", help="print the harness MCP config snippet")
    p_mcp.add_argument(
        "--json",
        action="store_true",
        help="emit pure JSON with no trailing notes, so it can be piped",
    )
    p_mcp.set_defaults(func=cmd_mcp_config)

    p_models = sub.add_parser("models", help="list the 4 octk agents and their model/effort")
    p_models.set_defaults(func=cmd_models)

    p_set_model = sub.add_parser("set-model", help="set an agent's model")
    p_set_model.add_argument("agent_name")
    p_set_model.add_argument("model_id")
    p_set_model.set_defaults(func=cmd_set_model)

    p_set_effort = sub.add_parser("set-effort", help="set an agent's effort level")
    p_set_effort.add_argument("agent_name")
    p_set_effort.add_argument("level", choices=sorted(EFFORT_LEVELS))
    p_set_effort.set_defaults(func=cmd_set_effort)

    p_caps = sub.add_parser("capabilities", help="inspect the capability registry")
    caps_sub = p_caps.add_subparsers(dest="capabilities_command", required=True)

    p_caps_list = caps_sub.add_parser("list", help="list capabilities (L0/L1/L2)")
    p_caps_list.add_argument("--level", default="L0", choices=["L0", "L1", "L2"])
    p_caps_list.add_argument("--query", default="")
    p_caps_list.set_defaults(func=cmd_capabilities)

    p_caps_show = caps_sub.add_parser("show", help="show one capability")
    p_caps_show.add_argument("capability_id")
    p_caps_show.add_argument("--level", default="L1", choices=["L0", "L1", "L2"])
    p_caps_show.set_defaults(func=cmd_capabilities)

    p_caps_discover = caps_sub.add_parser("discover", help="dry-run harness discovery")
    p_caps_discover.add_argument("--write", action="store_true")
    p_caps_discover.set_defaults(func=cmd_capabilities)

    p_caps_verify = caps_sub.add_parser("verify", help="compare registry with discovery")
    p_caps_verify.set_defaults(func=cmd_capabilities)

    p_caps_select = caps_sub.add_parser("select", help="recommend capabilities for a task")
    p_caps_select.add_argument("task")
    p_caps_select.add_argument("--limit", type=int, default=3)
    p_caps_select.set_defaults(func=cmd_capabilities)

    p_caps_register = caps_sub.add_parser("register", help="manually register a capability")
    p_caps_register.add_argument("--id", required=True)
    p_caps_register.add_argument("--type", required=True, choices=sorted(CAPABILITY_TYPES))
    p_caps_register.add_argument("--name", required=True)
    p_caps_register.add_argument("--description", required=True)
    p_caps_register.add_argument("--provider", default="unknown")
    p_caps_register.add_argument("--source-path", dest="source_path", default=None)
    p_caps_register.set_defaults(func=cmd_capabilities)

    p_providers = sub.add_parser("providers", help="report external provider status")
    p_providers.add_argument("--json", action="store_true")
    p_providers.set_defaults(func=cmd_providers)

    p_audit = sub.add_parser("audit", help="run graph-freshness + audit workflow")
    p_audit.add_argument("--audit-cmd", default="", help="override audit command")
    p_audit.set_defaults(func=cmd_audit)

    p_roadmap = sub.add_parser("roadmap", help="roadmap operations")
    roadmap_sub = p_roadmap.add_subparsers(dest="roadmap_command", required=True)
    p_roadmap_list = roadmap_sub.add_parser("list", help="list roadmap lines")
    p_roadmap_list.set_defaults(func=cmd_roadmap)
    p_roadmap_set = roadmap_sub.add_parser("set", help="set a roadmap line's status")
    p_roadmap_set.add_argument("task_substring")
    p_roadmap_set.add_argument("new_status")
    p_roadmap_set.set_defaults(func=cmd_roadmap)

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
