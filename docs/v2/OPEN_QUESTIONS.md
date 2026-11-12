# OCTK v2 — Open Questions

Status of every question from handoff A5. Resolved items record the decision and
the date. Unresolved items are genuinely blocking and marked **OPEN**.

| # | Question | Decision | Status |
|---|---|---|---|
| Q1 | Registry storage: JSON or SQLite? | JSON index (`.toolkit/capabilities/index.json`) | **Resolved** — implemented |
| Q2 | Registry scope precedence | Project overrides user overrides local-fallback | **Resolved** — implemented |
| Q3 | Approval gate scope | Retained, limited to consequential/irreversible actions | **Resolved** — roadmap `done` still requires `octk approve` |
| Q4 | Does v2 ship a roadmap? | Yes, minimal, no gating beyond `done` | **Resolved** — retained |
| Q5 | Minimum Python version | 3.11 (lowered from 3.14) | **Resolved** — `pyproject.toml` |
| Q6 | Distribution | PyPI `octk` + `octk-mcp`, uvx-compatible | **Resolved** — publish workflow added |
| Q7 | Is the MCP server mandatory? | Optional; CLI-only mode works | **Resolved** — `octk` CLI has no MCP dependency |
| Q8 | Telemetry default | Local-only, export opt-in | **Resolved** — metrics stay in `.toolkit/metrics.json` |
| Q9 | Second harness | Codex | **Resolved (deferred)** — no second adapter yet |
| Q10 | If `beam-free` disappears mid-benchmark | Abort and relabel cohort | **Resolved** — preflight refuses to substitute |

## Still open

None of the A5 questions remain open. The implementation gaps that were listed
here have since been closed:

1. Capability Selector (ADR-007) — implemented, `octk capabilities select`.
2. `browser_inspect` feature flag (ADR-005) — `OCTK_BROWSER=0` drops the tool.
3. `check_spec_drift` Python-only declaration (ADR-006) — in the tool description.
4. Adapter return type and discovery-failure reason (ADR-003, ADR-004) — the
   adapter emits validated records and carries a `reason`.
5. `available` / `requires_approval` fields (ADR-010) — decided: not emitted.
6. Benchmark task categories (D4) — all 8 fixtures implemented and verified,
   plus a 9th (`spec_selection`) that is now part of the standard suite.
7. External benchmark selection (D8) — Terminal-Bench 2.0 chosen; the adapter
   is still to be built.

Two items remain genuinely open:

8. MCP surface ≤6 (ADR-002) — currently 8, accepted with the schema cost
   measured rather than guessed.
9. The Terminal-Bench 2.0 adapter — needs a container runtime, which is not
   available in the current environment.
