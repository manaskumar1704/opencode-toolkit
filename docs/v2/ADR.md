# OCTK v2 — Architecture Decision Records

Records every place the implementation departs from `CODEX_HANDOFF.md`, and why.
Each entry states whether the deviation is **accepted** (deliberate, evidence-based)
or **open** (unintentional drift still to fix).

Status values: `Accepted` · `Open` · `Superseded`

---

## ADR-001 — L0 is a grouped name inventory, not a per-record payload

**Status:** Accepted
**Handoff:** B3 "Disclosure payloads", line 285 — L0 = `id, type, name, description, activation, available`
**Implementation:** `octk/capabilities.py::render_l0`

### Context

The handoff defines L0 as one line per capability carrying id, type, name,
description, activation, and availability. Implemented literally, that payload
measured **2,684 characters** for this repository's 19 capabilities.

The comparison target, `glance_pantry`, is 760 characters — but 671 of those
(88%) are `index.md` boilerplate, and it never lists `.opencode/skills` at all.
Measured variants:

| Variant | Chars |
|---|---:|
| id + `[type]` + desc140 | 2,684 |
| id + desc140 | 2,468 |
| name + desc80 | 1,592 |
| name + desc40 | 1,135 |
| grouped names | **526** |

Descriptions were 60% of the payload and full ids another 28%, of which 459
characters were redundant (`skill:design-taste-frontend/design-taste-frontend`).

### Decision

L0 without a query returns names grouped by type — the smallest useful
inventory. Descriptions appear at L0 **when `query=` narrows the field**
(capped at 60 chars), and always at L1. Bare names resolve at L1/L2 via
`Registry.resolve()`, so ids never need to appear at L0.

### Consequences

- L0 is 526 chars, 28 chars/item versus glance's 22 — a defensible ratio.
- The agent must pass a `query` to see descriptions, or call L1.
- Deviation from B3 is visible and reversible in one function.

---

## ADR-002 — MCP surface is 8 tools, not the ≤6 target

**Status:** Accepted (maintainer decision)
**Handoff:** B4, line 314 — "Target: ≤6 always-exposed MCP tools"
**Implementation:** `octk/server.py`

### Context

B4 names exactly two tools for demotion: `run_audit_workflow` and
`update_roadmap`. Both were demoted to CLI (`octk audit`, `octk roadmap`),
taking the surface from 10 to 8. Reaching 6 requires demoting two of the
seven tools B4 marks "Keep" — `browser_inspect` and `equip_external_mcp`
being the only plausible candidates.

### Decision

Stop at 8. The maintainer chose the minimal cut explicitly. Further reduction
is a separate approval-gated decision.

### Consequences

- Surface is 8, above target. Schema overhead is lower than the historical
  9-tool baseline but not at the ≤6 goal.
- `octk audit` and `octk roadmap {list,set}` are the replacements; agent prompts
  that called the MCP tools must be updated (covered in
  `MIGRATION_AND_COMPATIBILITY.md`).

---

## ADR-003 — Adapters return raw dicts; normalisation happens at the registry

**Status:** Open
**Handoff:** B2, line 222 — "Adapter output is normalised into `CapabilityRecord` before reaching core"
**Implementation:** `octk/adapters/base.py`, `octk/adapters/opencode.py`

### Context

The contract says adapters emit `CapabilityRecord`. The implementation has
adapters emit `dict[str, Any]`, which `record_from_dict()` validates in the
caller (`capabilities._read_index`, `cli.cmd_capabilities`).

### Why it happened

Discovery needs to produce records before validation rules exist in a shared
place; emitting dicts let the adapter stay dependency-free and made
malformed-record skipping (`_read_index` swallows `RegistryError`) trivial.

### Consequence / fix

Functionally equivalent, but the contract is violated and core now trusts
unvalidated dicts until the caller validates. Fix: have `discover_capabilities`
return `CapabilityRecord`, or rename the contract to `RawCapability` and
document the validation boundary.

---

## ADR-004 — Discovery failure returns an empty list with no reason

**Status:** Open
**Handoff:** B2, line 220 — "Discovery failure returns an empty set plus a reason"
**Implementation:** `octk/adapters/opencode.py::discover`

### Context

`discover()` returns `[]` when `detect()` is `None` or `opencode.json` is
malformed. No reason string is surfaced. `install_hints()` exists but is not
called on the failure path.

### Why it happened

The first slice only needed "no capabilities found" to be non-fatal; the
reason channel was not wired through.

### Consequence / fix

The agent cannot distinguish "no harness", "no skills", and "malformed
config". Fix: return `(records, reason)` or attach the reason to
`Registry`/the CLI output.

---

## ADR-005 — `browser_inspect` is not feature-flagged

**Status:** Open
**Handoff:** B4, line 305 — "Keep, feature-flagged"
**Implementation:** `octk/server.py`

### Context

B4 requires `browser_inspect` to be feature-flagged because Chromium is a
heavy dependency. It is currently always exposed; the tool degrades at call
time if Playwright/Chromium is missing.

### Why it happened

The tool predates v2 and was carried over unchanged to avoid breaking the
existing browser tests.

### Consequence / fix

Users without Chromium still pay the schema cost. Fix: gate registration on a
config key (e.g. `browser_enabled`, default false) or on Playwright import
success.

---

## ADR-006 — `check_spec_drift` does not declare Python-only coverage

**Status:** Open
**Handoff:** B4 line 306 and A4 line 137 — "Python-only must be stated in the tool description"
**Implementation:** `octk/server.py::check_spec_drift`

### Context

The tool docstring reads "AST spec-to-code drift scan (undocumented
symbols/routes vs specs)". It does not say Python-only, though `octk/drift.py`
scans `*.py` exclusively.

### Why it happened

Carried over from v1 without the description audit that v2 requires.

### Consequence / fix

An agent working in a non-Python repo may call it and get a misleading empty
result. Fix: one-line description change to "Python-only (`*.py`)".

---

## ADR-007 — Capability Selector is not implemented

**Status:** Open (remaining work, not a regression)
**Handoff:** A3.3 and B1 — Selector determines relevance, prefers native, explains skips
**Implementation:** absent

### Context

The architecture diagram and A3.3 describe a selector that decides relevance
and explains why a capability was selected or skipped. Only discovery and
retrieval (L0/L1/L2) exist.

### Why it happened

Phase 1 deliberately shipped the registry slice first (handoff E3 Phase 1).
Selection is Phase 2+ work and was not part of the approved slice.

### Consequence / fix

OCTK can list capabilities but cannot yet recommend or skip one. Remaining
work, tracked in the implementation plan.

---

## ADR-008 — Model/effort CLI commands are deprecated, not removed

**Status:** Accepted
**Handoff:** A4, line 139 — model selection "belongs to harness/user"
**Implementation:** `octk/cli.py::cmd_models`, `cmd_set_model`, `cmd_set_effort`

### Context

A4 says OCTK must not be a model router. The three commands remain functional
and print a deprecation notice to stderr.

### Decision

Keep them for one release with a visible warning; removal is a separate
user-facing breaking change.

### Consequences

The product still ships model-routing surface area, contrary to A4's spirit,
but no user breaks on upgrade. Removal is tracked as remaining work.

---

## ADR-009 — Repository layout stays flat

**Status:** Accepted
**Handoff:** B5, line 347 — "ship Phase 1–2 on the flat layout; restructure only when a second harness adapter exists"
**Implementation:** `octk/*.py` flat

### Context

B5 proposes `octk/core/...` and `octk/adapters/...` subpackages. We added
`octk/adapters/` and `octk/providers/` as boundary packages but did not move
core modules into `core/`.

### Decision

Follow B5's own recommendation: no `core/` restructure until a second harness
adapter exists.

### Consequences

Flat core is harder to enforce structurally, so a boundary test
(`tests/test_boundaries.py`) enforces the import rule instead.

---

## ADR-010 — `available` and `permissions.requires_approval` are not emitted

**Status:** Open (minor)
**Handoff:** B3 record example lines 255–258 and L0 payload line 285
**Implementation:** `octk/adapters/opencode.py`

### Context

The B3 example includes `permissions.requires_approval` and the L0 payload
includes `available`. Discovery emits `permissions.side_effects` only, and
`available` is not a stored field.

### Why it happened

`available` was treated as derivable from `activation`; `requires_approval`
was not needed by any consumer yet.

### Consequence / fix

Downstream code must infer both. Fix: emit `requires_approval: false` by
default and either store or document `available` as derived.

---

## Summary

| ADR | Deviation | Status |
|---|---|---|
| 001 | L0 grouped names instead of full payload | Accepted |
| 002 | 8 MCP tools, not ≤6 | Accepted |
| 003 | Adapters return dicts, not CapabilityRecord | **Open** |
| 004 | Discovery failure has no reason | **Open** |
| 005 | `browser_inspect` not feature-flagged | **Open** |
| 006 | `check_spec_drift` coverage undeclared | **Open** |
| 007 | Capability Selector absent | **Open** (remaining work) |
| 008 | Model CLI deprecated, not removed | Accepted |
| 009 | Flat layout retained | Accepted |
| 010 | `available` / `requires_approval` not emitted | **Open** (minor) |
