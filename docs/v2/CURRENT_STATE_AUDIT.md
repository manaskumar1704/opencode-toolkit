# OCTK v2 — Current State Audit

**Audit date:** 2026-11-09
**Method:** direct inspection of source, tests, config, and git history. Nothing
in this document is inferred from the README.

---

## 1. Repository tree

```text
octk/                     21 modules, 5,263 lines
  __init__.py
  adapters/               opencode.py (302), opencode_scaffold.py (213), base.py
  providers/              graphify.py (110), ponytail.py (137)
  runtime/                debugger.py (235), browser.py (139), safety.py (59),
                          _trace_wrapper.py (66)
  approvals.py (86)       audit.py (96)        bench.py (297)
  capabilities.py (529)   cli.py (629)         config.py (140)
  diagnostics.py (82)     doctor.py (103)      drift.py (152)
  handoff.py (153)        mcp_proxy.py (131)   metrics.py (251)
  pantry.py (155)         report.py (442)      roadmap.py (132)
  scaffold.py (132)       sentinel.py (58)     server.py (241)
  templates.py (109)

tests/                    24 modules + conftest.py
benchmarks/               manifest.py, preflight.py, runner.py, report.py,
                          tasks/simple_bug/, results/
docs/                     DESIGN.md, v2/
reports/                  BENCH_TOOLS.md, test-results/
scripts/                  test_batches.py
skills/  .toolkit/  .opencode/  .github/workflows/
```

---

## 2. Module map

### Core (harness-neutral)

| Module | Responsibility |
|---|---|
| `capabilities.py` | Capability Registry: records, validation, scope merge, L0/L1/L2 |
| `config.py` | `ToolkitPaths`, `DEFAULT_CONFIG`, deep-merge, atomic JSON, user paths |
| `diagnostics.py` | `DiagnosticResult`, signal-retention measurement |
| `pantry.py` | `glance` / `equip` JIT context routing |
| `metrics.py` | Task runs, tool calls, standing costs, breaker events |
| `report.py` | Markdown/JSON metrics report, net-effect section |
| `roadmap.py` | Roadmap parse, gated status updates, line-ending preservation |
| `drift.py` | Python-AST spec-to-code drift scan |
| `approvals.py` | TTY-gated one-use approval tokens |
| `handoff.py` | Session handoff snapshot |
| `sentinel.py` | Sentinel-block upsert |
| `audit.py` | Graph-freshness + audit workflow |
| `mcp_proxy.py` | External stdio MCP inspection/invocation |
| `doctor.py` | Prefix-cache and gate health checks |
| `bench.py` | Tool-level pruning benchmarks, schema overhead |

### Boundary (harness / provider specific)

| Module | Responsibility |
|---|---|
| `adapters/base.py` | `HarnessAdapter` protocol |
| `adapters/opencode.py` | OpenCode discovery: skills, commands, MCP, specs |
| `adapters/opencode_scaffold.py` | OpenCode config, agent files, ideate command, permissions gate |
| `providers/graphify.py` | Graphify detection: binary, index cold/warm/stale |
| `providers/ponytail.py` | Ponytail detection: skill, plugin, config entry |

### Surfaces

| Module | Responsibility |
|---|---|
| `server.py` | FastMCP server, 8 tools |
| `cli.py` | 16 CLI command groups |
| `scaffold.py` | Harness-neutral `octk init` orchestration |
| `templates.py` | AGENTS.md, index, spec templates |

---

## 3. Feature-to-code mapping (C2 resolution)

| ID | Claim | Verdict | Evidence |
|---|---|---|---|
| C-01 | `glance_pantry` compact index | CONFIRMED | `pantry.glance`, `tests/test_pantry.py` |
| C-02 | `equip_spec` loads a spec | CONFIRMED | `pantry.equip_spec` |
| C-03 | `equip_skill` loads an extra skill | CONFIRMED | `pantry.equip_skill` |
| C-04 | AGENTS.md traffic cop | CONFIRMED | `AGENTS.md`, 21 lines, static |
| C-05 | Ideate mode is a workflow | CONFIRMED | `.opencode/commands/ideate.md` |
| C-06 | `debug_inspect` prunes tracebacks | CONFIRMED | `runtime/debugger.py` |
| C-07 | `browser_inspect` summarises errors | CONFIRMED | `runtime/browser.py` |
| C-08 | `check_spec_drift` uses Python AST | CONFIRMED | `drift.py`, `ast` import |
| C-09 | `run_audit_workflow` graph-first | CONFIRMED | `audit.py`; MCP tool demoted to `octk audit` |
| C-10 | `update_roadmap` tracks state | CONFIRMED | `roadmap.set_status`; MCP tool demoted to `octk roadmap set` |
| C-11 | Session handoff snapshot | CONFIRMED | `handoff.py` |
| C-12 | `equip_external_mcp` lazy connect | CONFIRMED | `mcp_proxy.py` |
| C-13 | Telemetry tracks tokens/time | CONFIRMED | `metrics.py` |
| C-14 | TTY gate, allowlist, 2-strike breaker | CONFIRMED | `approvals.py`, `runtime/safety.py`, `server.py` |
| C-15 | `octk init` scaffolds OpenCode | CONFIRMED | `scaffold.py` → adapter |
| C-16 | MCP surface = 9 tools | **DRIFTED** | was 9; v2 added `capability_registry` (10) then demoted 2 (8) |
| C-17 | Python 3.14, FastMCP, Playwright, Pytest, uv | **DRIFTED** | Python floor lowered to 3.11; rest confirmed |
| C-18 | Test count 123 vs 95 | **RESOLVED** | 123 collected at baseline: 118 pass, 3 fail, 2 skip |
| C-19 | Design conventions in `docs/DESIGN.md` | CONFIRMED | 74 lines |
| C-20 | Generated reports under `reports/` | CONFIRMED | `BENCH_TOOLS.md`, `test-results/` |
| C-21 | Machine state gitignored | CONFIRMED | `.gitignore` lists all four |

---

## 4. Test inventory

**Baseline (before v2):** 123 collected — 118 passed, 3 failed, 2 skipped.

The 3 failures were real defects, not environment noise:

| Test | Root cause | Fixed in |
|---|---|---|
| `test_std_traceback_sample_prunes_nonproject` | Windows drive paths treated as relative on POSIX | Phase 4 |
| `test_all_dropped_fallback` | same `_norm` bug | Phase 4 |
| `test_line_endings_preserved` | `Path.read_text` universal newlines destroyed CRLF before write | Phase 4 |

**Current:** 238 collected — **236 passed, 2 skipped, 0 failed.**

Test modules: `test_audit`, `test_bench`, `test_benchmarks`, `test_boundaries`,
`test_browser`, `test_cache_doctor`, `test_capabilities`, `test_circuit_breaker`,
`test_cli`, `test_config`, `test_debugger`, `test_diagnostics`, `test_discovery`,
`test_external_mcp`, `test_handoff`, `test_metrics_report`, `test_octk`,
`test_pantry`, `test_providers`, `test_roadmap_gate`, `test_safety`,
`test_scaffold`, `test_server`.

---

## 5. Dependencies

| Package | Constraint | Purpose |
|---|---|---|
| `mcp` | `>=1.2,<2` | FastMCP server |
| `playwright` | `>=1.49` | Browser inspection |
| `pytest` (dev) | `>=8.3` | Tests |
| `pytest-asyncio` (dev) | `>=0.25` | Async tests |

Build: setuptools ≥75. Python: **≥3.11**.

---

## 6. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Capability Selector | Resolved | `octk/selector.py` — heuristic, explainable ranking (ADR-007) |
| Discovery failure gives no reason | Resolved | `DiscoveryResult.reason` (ADR-004) |
| `browser_inspect` always exposed | Resolved | `OCTK_BROWSER=0` drops the tool (ADR-005) |
| Adapter returns raw dicts | Resolved | Adapters emit validated `CapabilityRecord` (ADR-003) |
| Benchmark suite incomplete (1 of 8 categories) | High for evaluation validity | No v2 performance claim may be made yet |
| No external benchmark selected | Medium | Generalisation unproven |
| MCP surface 8 > target 6 | Low | Accepted; schema cost measured at 2,499 chars |

---

## 7. Documentation drift

| Document | Drift |
|---|---|
| `README.md` | Python badge updated to 3.11; other v1 claims not re-audited |
| `AGENTS.md` | Updated: no longer references demoted MCP tools |
| `docs/DESIGN.md` | v1 design doc; not updated for v2 components |
| `docs/v2/CODEX_HANDOFF.md` | Corrected model ID to `opencode-go/beam-free`; effort lock added |
| `reports/BENCH_TOOLS.md` | Historical; not a v2 claim |

---

## 8. What v2 changed in the repository

| Area | Before | After |
|---|---|---|
| Capability registry | absent | `octk/capabilities.py` + index |
| Harness boundary | OpenCode logic in core | `octk/adapters/` |
| Providers | not detected | `octk/providers/` |
| Diagnostics | text only | `DiagnosticResult` with retention |
| Net accounting | gross only | gross + net in report |
| MCP surface | 9 tools | 8 tools |
| Python floor | 3.14 | 3.11 |
| Packaging | uv-only | PyPI + uvx |
| CI | none | GitHub Actions |
