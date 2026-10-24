# octk design (docs/DESIGN.md)

octk keeps an AI coding agent's context small, gates roadmap completion behind
human approval, and records honest benchmark metrics. Package: `octk`; CLI:
`octk`; MCP server: `octk-mcp` (FastMCP, stdio).

## Conventions (binding)

1. Logic modules take `root: Path` as an argument. Only `cli.py` and `server.py`
   may call `Path.cwd()` or read env var `OCTK_ROOT`.
2. Logic functions are pure: they return values and never print or log metrics.
   `cli.py` / `server.py` callers log metrics.
3. Functions <= 60 lines, one responsibility per module, type hints, one-line
   docstrings.
4. No `shell=True` anywhere. Subprocesses: `shlex.split`, timeout, `cwd=root`.
5. Spec/skill names must match `^[A-Za-z0-9_-]+$` (rejects path traversal).
6. Metric kinds: `measured` (raw vs pruned output actually produced),
   `counterfactual` (estimate vs a hypothetical full load), `load` (context
   octk itself delivered; raw == pruned).
7. `approx_tokens = ceil(chars / 4)`, `(chars + 3) // 4`. Token figures are
   always labelled "approx".
8. All JSON writes are atomic (temp file in same dir, then `os.replace`).

## Additions incorporated (v2.1)

- `server_name` (default `octk`) is a config key; every rendered tool name in
  templates is `<server_name>_<tool>` (Prompt 1: AGENTS.md; opencode.json).
- `octk mcp-config` emits OpenCode V2 syntax: `mcp.servers` (no `enabled`
  field), `permissions` as an ordered rule array (`action`/`resource`/`effect`),
  `codemode: false`, and a `shell` action for `octk approve *`.
- Audit defaults: `audit_mode: "instruct"`;
  `graph_report_paths: ["graphify-out/GRAPH_REPORT.md", "graphify-out/graph.json"]`.
  Instruct text names the slash commands: `/graphify .` then `/ponytail-review`.
- Windows: roadmap parsing uses `splitlines()` and preserves the file's
  existing line endings on write; executables are located with `shutil.which`;
  the runtime pruner (Prompt 2) normalizes backslashes and excludes
  `Lib\site-packages` and `.venv\Scripts` as well as their POSIX twins.
- Standing costs (C7): MetricsStore stores `standing_costs`, CLI
  `octk standing add <label> --tokens-in N`, and the report shows "Standing
  context cost (turn-1 input tokens)" with delta vs the `bare` label.
- Benchmark fairness (C8): skills, MCP servers and plugins are identical in
  benchmark worktrees (or off in both); only octk's MCP entry, AGENTS.md rules
  and `.toolkit/` differ. See benchmarks/README.md (Phase H/I).

## Module map

| Module | Responsibility |
|---|---|
| `octk/config.py` | `ToolkitPaths(root)`, `DEFAULT_CONFIG`, `load_config`, atomic JSON io |
| `octk/templates.py` | String templates only, no logic |
| `octk/scaffold.py` | `init_repo(root, force)` — idempotent scaffold |
| `octk/approvals.py` | Approval records + TTL validity in `.toolkit/approvals.json` |
| `octk/roadmap.py` | `parse_roadmap`, `set_status` (approval gate) |
| `octk/pantry.py` | `glance`, `equip_spec`, `equip_skill` |
| `octk/metrics.py` | `MetricsStore`, `approx_tokens` |
| `octk/report.py` | `build_report`, `build_report_data` |
| `octk/cli.py` | argparse CLI; only place allowed to touch `Path.cwd()` |
| `octk/server.py` | Thin FastMCP wrappers (Prompt 2) |

## Report honesty rules

- Headline numbers use `measured` records only.
- Counterfactual estimates appear in a separate section labelled
  "estimate, not measured".
- The "Resume line" is generated only from recorded data and only when >= 5
  paired tasks exist; otherwise "Not enough paired tasks (k/5)". If octk was
  worse, the report says so.
- Token-proxy caveats: `chars/4` is a proxy, n small, single model.
