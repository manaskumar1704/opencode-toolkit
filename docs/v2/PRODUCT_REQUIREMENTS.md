# OCTK v2 — Product Requirements

**Status:** implemented baseline
**Source of truth for product intent:** `CODEX_HANDOFF.md` Part A
**This document:** what the product must do, expressed as testable requirements.

---

## 1. Definition

OCTK is an **information and diagnostics layer** for AI coding agents. The agent
is the pilot, the harness is the aircraft, and OCTK is the HUD.

> Give coding agents the right information, at the right time, in the right
> format, while reducing unnecessary context, searching, and diagnostic noise.

## 2. Non-goals

OCTK is **not**:

- a replacement for any coding harness;
- an autonomous software factory or agent swarm;
- a model router or quota optimiser;
- a prompt/skill marketplace;
- a requirement to migrate, reinstall, or surrender ownership of existing tools;
- an installer or mutator of user configuration.

## 3. Users and jobs

| User | Job |
|---|---|
| Agent (primary) | Find the right capability or spec without paying for every schema and document |
| Developer | Keep the agent's context small and its diagnostics honest |
| Maintainer | Prove the above with reproducible measurements |

## 4. Functional requirements

### FR-1 Capability inventory

- **FR-1.1** The system SHALL list known capabilities (skills, commands, plugins,
  MCP servers, MCP tools, native tools, CLI executables, OCTK-native docs).
- **FR-1.2** The inventory SHALL be read-only. Discovery SHALL NOT execute,
  install, update, or rewrite any capability.
- **FR-1.3** The inventory SHALL support manual registration when discovery is
  unavailable.
- **FR-1.4** Records SHALL carry: id, type, name, description, provider,
  version, scope, harness, activation, invocation, permissions, cost,
  provenance, verified_at, source_path.
- **FR-1.5** A record with `verified_at: null` SHALL remain listable.

### FR-2 Progressive disclosure

- **FR-2.1** L0 SHALL return a compact inventory.
- **FR-2.2** L0 with a `query` SHALL include a short description (≤60 chars).
- **FR-2.3** L1 SHALL return invocation metadata, permissions, harness, and cost.
- **FR-2.4** L2 SHALL return a **reference** to the original document, never its
  body.
- **FR-2.5** L0 SHALL resolve bare names for L1/L2 without requiring ids.

### FR-3 Scope resolution

- **FR-3.1** Scopes SHALL resolve in the order user → project → local, later
  overriding earlier.
- **FR-3.2** The winning scope SHALL be recorded.
- **FR-3.3** Duplicate ids SHALL resolve deterministically.

### FR-4 Context delivery

- **FR-4.1** `glance_pantry` SHALL return project index, specs, skills, external
  MCPs, and handoff pointer.
- **FR-4.2** `glance_pantry` SHALL prefer registry descriptions over file reads.
- **FR-4.3** Any fallback file read SHALL be bounded (≤4 KB head).
- **FR-4.4** Specs and skills SHALL load on demand only.

### FR-5 Diagnostics

- **FR-5.1** `debug_inspect` SHALL run allowlisted commands only, without a
  shell.
- **FR-5.2** Pruned output SHALL retain project frames, the error line, and
  locals.
- **FR-5.3** Each diagnostic result SHALL report whether required signals were
  retained.
- **FR-5.4** A two-strike breaker SHALL escalate, not silently weaken
  permissions.

### FR-6 Providers

- **FR-6.1** Graphify and Ponytail SHALL be detected, never bundled, forked, or
  reimplemented.
- **FR-6.2** Detection SHALL report availability and state without executing the
  tool.
- **FR-6.3** Absent providers SHALL degrade gracefully.

### FR-7 Project state

- **FR-7.1** A lightweight roadmap SHALL track task status.
- **FR-7.2** Marking a task `done` SHALL require a human approval token.
- **FR-7.3** Session handoff SHALL snapshot roadmap, git state, runtime signal,
  and approvals.

### FR-8 Telemetry

- **FR-8.1** Telemetry SHALL record tokens, timing, tool calls, and standing
  costs.
- **FR-8.2** Reports SHALL distinguish measured, counterfactual, and load
  metrics.
- **FR-8.3** Net effect SHALL be reported separately from gross savings.
- **FR-8.4** An incomplete baseline SHALL be reported as unknown, never as zero.

### FR-9 Harness independence

- **FR-9.1** Core modules SHALL NOT import harness SDKs, provider SDKs, or model
  provider SDKs.
- **FR-9.2** Harness-specific types SHALL appear only under `octk/adapters/`.
- **FR-9.3** A second adapter SHALL be addable without editing core.

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Python ≥3.11 |
| NFR-2 | No `shell=True`; subprocess allowlist enforced |
| NFR-3 | No silent config mutation |
| NFR-4 | Registry writes stay under `.toolkit/capabilities/` |
| NFR-5 | MCP tool schemas stay lean (8 tools, 2,499 chars) |
| NFR-6 | All tests pass in CI on Python 3.14 |
| NFR-7 | Package installs from PyPI and runs via `octk` / `octk-mcp` |
| NFR-8 | Existing user state files remain readable |

## 6. Acceptance criteria

- [x] Registry lists skills, commands, MCP servers, and specs in this repo.
- [x] L0 is smaller than `glance_pantry` inventory cost per item.
- [x] L2 never returns a document body.
- [x] Five B3 invariants have passing tests.
- [x] Diagnostics report signal retention.
- [x] Providers are detected without execution.
- [x] Core has no harness imports (boundary tests).
- [x] MCP surface is 8 tools.
- [x] Test suite is green.
- [ ] Capability Selector implemented (ADR-007).
- [ ] Benchmark suite covers all 8 task categories.

## 7. Compatibility

See `MIGRATION_AND_COMPATIBILITY.md`. Summary: user state files are unchanged;
two MCP tools moved to CLI; Python floor lowered.
