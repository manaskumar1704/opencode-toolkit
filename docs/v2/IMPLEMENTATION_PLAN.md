# OCTK v2 — Implementation Plan

**Status:** Phases 0–6 complete, Phase 7 partially complete
**Source:** `CODEX_HANDOFF.md` Parts A, B, D, E
**Live task board:** kept in the working plan during execution; this document is
the durable record.

---

## 1. Classification of every v1 item

| Item | Classification | Notes |
|---|---|---|
| `glance_pantry` / `equip_spec` / `equip_skill` | Keep | Core JIT context |
| `debug_inspect` / `browser_inspect` | Keep | Core diagnostics |
| `check_spec_drift` | Refactor | Must declare Python-only (ADR-006) |
| `run_audit_workflow` | Replace | MCP tool → `octk audit` CLI |
| `update_roadmap` | Replace | MCP tool → `octk roadmap set` CLI |
| Session handoff | Keep | CLI-only, as intended |
| TTY approval gate | Refactor | Scoped to consequential actions |
| Roadmap | Keep | Lightweight, no gating beyond `done` |
| AST scanner | Keep | Python-only; extensible later |
| Graphify | Replace | Hard coupling → optional provider |
| Ponytail | Replace | Implicit → explicit detection |
| Model selection CLI | Deprecate | Warns; removal later (ADR-008) |
| Agent scaffolding | Replace | Core assumption → adapter |
| Circuit breaker | Refactor | Documented escalation, logged |
| MCP surface | Refactor | 9 → 10 → 8 tools |
| Mandatory subagents | **Drop** | — |
| Multi-model quota routing | **Drop** | — |
| Agent-factory positioning | **Drop** | — |
| Prompt collection as product | **Drop** | — |
| OpenCode-only assumptions | **Drop** | — |
| Mandatory tool wrappers | **Drop** | — |
| Auto-mutation of user tools | **Drop** | — |
| Capability Registry | **New** | The v2 thesis |
| Capability Selector | **New (deferred)** | ADR-007 |
| Diagnostic result schema | **New** | Signal retention |
| Provider detection | **New** | Graphify + Ponytail |
| Benchmark harness | **New** | Manifest, preflight, runner, report |

---

## 2. Phases and status

### Phase 0 — Audit and baseline ✅

| Task | Result |
|---|---|
| Test baseline | 123 collected: 118 pass, 3 fail, 2 skip |
| MCP schema cost | 9 tools, 2,499 chars |
| Config snapshot | 12 keys |

### Phase 1 — Capability Registry ✅

| Task | Deliverable |
|---|---|
| T1.1 | User-scope paths (`OCTK_USER_CONFIG` / XDG / `~/.config`) |
| T1.2 | `CapabilityRecord` + validation |
| T1.3 | Scope merge user → project → local |
| T1.4 | L0/L1/L2 rendering |
| T1.5 | OpenCode discovery adapter |
| T1.6 | `capability_registry` MCP tool |
| T1.7 | `octk capabilities {list,show,discover,verify,register}` |

**Exit gate:** 19 records; L0 = 526 chars vs glance inventory 22 chars/item.

### Phase 2 — Context Engine ✅

| Task | Deliverable |
|---|---|
| T2.1 | `glance` uses registry descriptions, bounded 4 KB fallback |
| T2.2 | Net effect section (gross − load − standing overhead) |
| T2.3 | `octk standing schema` |

### Phase 3 — Provider adapters ✅

| Task | Deliverable |
|---|---|
| T3.1 | Graphify detection: binary, cold/warm/stale |
| T3.2 | Ponytail detection: skill / plugin / config |
| T3.3 | Provider records in registry |

### Phase 4 — Diagnostics ✅

| Task | Deliverable |
|---|---|
| T4.1 | `DiagnosticResult` |
| T4.2 | Signal-retention tests |
| T4.3 | Breaker logging + documented bypass |
| — | Fixed 3 pre-existing failures (Windows paths, CRLF) |

### Phase 5 — Harness adapter ✅

| Task | Deliverable |
|---|---|
| T5.1 | Adapter protocol |
| T5.2 | OpenCode logic behind `octk/adapters/` |
| T5.3 | Model CLI deprecated |
| T5.4 | `opencode.json` + agents moved out of `scaffold.py` |
| — | Boundary tests added |

### Phase 6 — Benchmark harness ✅ (harness only)

| Task | Deliverable |
|---|---|
| T6.0 | Pre-flight model/effort check |
| T6.1 | Worktree isolation |
| T6.2 | `simple_bug` fixture + hidden oracle |
| T6.3 | Checklist-enforcing report |

**Not done:** factorial driver, 7 task categories, external benchmark.

### Phase 7 — Release hardening ◐

| Task | Status |
|---|---|
| T7.1 MCP surface reduction | ✅ 10 → 8 |
| T7.2 Python floor | ✅ 3.14 → 3.11 |
| T7.3 Packaging | ✅ PyPI metadata + publish workflow |
| T7.4 Migration guide | ✅ `MIGRATION_AND_COMPATIBILITY.md` |
| Security review | not done |
| Licence audit | not done (MIT declared) |

---

## 3. Remaining work

### R-1 Close open ADRs ✅

| ADR | Task | Status |
|---|---|---|
| 003 | Return `CapabilityRecord` from adapters | ✅ done |
| 004 | Discovery failure returns a reason | ✅ done |
| 005 | Feature-flag `browser_inspect` | ✅ done (`OCTK_BROWSER`) |
| 006 | Declare Python-only coverage | ✅ done |
| 007 | Capability Selector | ✅ done (`octk/selector.py`) |
| 010 | Emit `available` / `requires_approval` | ✅ done |

### R-2 Complete the benchmark suite ◐

- [x] All 8 task fixtures (D4 categories 1–8).
- [x] Factorial driver with staged gates and stop rule (`benchmarks/driver.py`).
- [x] Randomised run order, ≥5 reps, transcript capture.
- [x] Isolation repaired: standalone workspace, bwrap host mask, oracle
      exclusion, `--standalone` server, leak detection (S-12/S-13).
- [x] Execute Stage 1 core block (8 tasks, 5 reps): 72/72 valid runs correct,
      **no efficiency signal** (tokens −13.1%, CI −71.1%..+30.4%). Partial:
      4 provider-stall exclusions, 4 cells unrun. See `BENCHMARK_RESULTS.md`.
- [x] Power the large-context task (`spec_selection`, 20 reps/arm): 40/40
      correct; **−38.5% tokens** (CI +4.5%..+82.4%) and −73.3% duration.
      First result to clear the gate.
- [ ] Resume the 4 missing core cells once provider quota resets.
- [ ] Stage 2 proceeds on the large-context result; the core block stays neutral.

### R-3 External benchmark ✅ (selected)

- [x] Terminal-Bench 2.0 chosen (Harbor, `terminal-bench@2.0`, 89 tasks).
- [x] Cohort lock and command builder (`benchmarks/external.py`).
- [x] Feasibility ladder and pre-registration template
      (`docs/v2/EXTERNAL_BENCHMARK.md`).
- [ ] Close the container adapter gap and run the ladder.

### R-4 Release hardening ◐

- [x] Security review opened; scanner in CI; four findings fixed
      (`docs/v2/SECURITY_REVIEW.md`).
- [ ] Phase B security fixes (S-05, S-07, S-10).
- [ ] Licence audit.
- [ ] Update `docs/DESIGN.md` for v2 components.

---

## 4. Risks and rollback

| Risk | Rollback |
|---|---|
| Registry index corrupt | delete `.toolkit/capabilities/`; manual mode works |
| Adapter regression | revert `octk/adapters/`; core is unchanged |
| MCP demotion breaks agent | restore tool in `server.py`; CLI remains |
| Python floor too low | raise `requires-python`; no code change needed |

---

## 5. Definition of Done

- [x] Repository inspected directly.
- [x] C2 claims resolved (see `CURRENT_STATE_AUDIT.md`).
- [x] Features classified.
- [x] Core harness-independent (boundary tests).
- [x] User tools/config preserved.
- [x] Ponytail/Graphify optional.
- [x] Discovery ≠ invocation.
- [x] Benchmark design isolates the three components.
- [x] OpenCode + `beam-free` + `high` specified.
- [ ] One external benchmark selected.
- [x] Tests, migration, security notes, rollback documented.
- [x] Uncertainties explicit (ADR + open questions).
- [x] No destructive change without approval.
