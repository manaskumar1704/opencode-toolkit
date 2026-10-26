# Architecture (HLD)

`octk` is a local Python CLI plus a FastMCP stdio server. The CLI owns
human-gated state changes and report generation; the MCP server exposes lazy
context loading, runtime pruners, roadmap updates, and an on-demand external
MCP proxy. Everything lives under the project root.

## LLD

- `octk/server.py` - nine MCP tools; `debug_inspect` persists a 2-strike
  failure signature and appends an explicit bypass after two identical failures.
- `octk/runtime/debugger.py` - allowlisted pytest/python runner, project-frame
  pruner, failure-signature hashing, and first-error extraction.
- `octk/metrics.py` - task/tool telemetry, cache-hit math, and the persisted
  `debug_state` streak.
- `octk/pantry.py` - glance/equip, external MCP inventory lines, and
  `equip_spec("handoff")`.
- `octk/mcp_proxy.py` - strict configured-name validation and lazy stdio
  `list_tools` / `call_tool`.
- `octk/handoff.py` - deterministic roadmap, git, runtime-signal, and approval
  snapshot written to `.toolkit/handoff.md`.
- `octk/doctor.py` - static AGENTS.md, config, and approval-permission checks.
- `octk/report.py` / `octk/cli.py` - Markdown/JSON reports, doctor, handoff, and
  task bookkeeping.

## Schema

- `.toolkit/metrics.json`: `active_task`, `tasks[]`, `unattributed[]`,
  `standing_costs[]`, and `debug_state{active_task, signature, strikes, detail}`.
- Task cache fields: `tokens_cached`, `cache_hit_rate`.
- `.toolkit/config.json`: `external_mcps{name: {command[], description}}`,
  `external_mcp_timeout_s`.
- `.toolkit/handoff.md`: generated resume snapshot (not a spec).
- `AGENTS.md`: static sentinel-wrapped rules; no timestamps or live task state.
