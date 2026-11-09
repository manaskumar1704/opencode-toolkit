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

None of the A5 questions remain open. The following are **implementation gaps**,
not product questions, and are tracked in `ADR.md` and the implementation plan:

1. Capability Selector (ADR-007).
2. `browser_inspect` feature flag (ADR-005).
3. `check_spec_drift` Python-only declaration (ADR-006).
4. Adapter return type and discovery-failure reason (ADR-003, ADR-004).
5. `available` / `requires_approval` fields (ADR-010).
6. Remaining benchmark task categories (D4: 7 of 8 missing).
7. External benchmark selection (D8).
8. MCP surface ≤6 (ADR-002, approval-gated).
