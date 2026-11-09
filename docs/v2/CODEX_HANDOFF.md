# OCTK v2 — Codex Repository Handoff

## Part 0 — Document control

| Field | Value |
|---|---|
| Status | DRAFT — planning only |
| Owner | OCTK maintainer |
| Supersedes | `OCTK_v2_Codex_Handoff_and_Benchmark_Plan.md` (repository root, untracked, now removed) |
| Canonical location | `docs/v2/CODEX_HANDOFF.md` — this file. Do not keep copies elsewhere. |
| Execution harness | OpenCode |
| Initial model | `beam-free` (normally `opencode/beam-free`) — verify before use, see D2 |
| Assignment | Inspect and plan only. No refactor, no implementation, until the maintainer approves the plan. |

### Audience map

| Reader | Reads | Skips |
|---|---|---|
| Maintainer | Part 0, A, D3, A5 | C, E1 |
| Codex (audit agent) | Part 0, C, E, F1 — plus A and B for constraints | — |
| Benchmark operator | D, F2 | A, B |

### What this document is

A handoff from maintainer to coding agent. It carries **product decisions that are already settled**, **historical claims that must be verified against source**, and **evaluation requirements** that constrain the plan.

### What this document is not

- Not a specification of the current code. Part C is a list of claims, not facts.
- Not an implementation plan. Codex produces that (E2).
- Not a benchmark result. Part C4 contains historical numbers explicitly excluded from v2 claims.
- Not permission to modify the repository.

### Rules of engagement

1. The repository is the source of truth for implementation facts. This document is the source of truth for product intent.
2. Where the two disagree, report the disagreement. Do not silently pick one.
3. Do not invent paths, test results, benchmark scores, API support, or integration capabilities.
4. Anything unverifiable is labelled `UNKNOWN` with a stated verification method.
5. Distinguish measured facts, estimates, and hypotheses in every deliverable.

---

## Part A — Product (locked)

Sections A1–A4 are decisions. They are not open for re-litigation without evidence. Section A5 lists what genuinely remains undecided.

### A1. Definition, mental model, non-goals

**OCTK is an information and diagnostics layer for AI coding agents.**

- LLM = pilot.
- Coding harness = aircraft.
- OCTK = the HUD: it organises and presents the right information at the right time.

Core promise:

> Give coding agents the right information, at the right time, in the right format, while reducing unnecessary context, searching, and diagnostic noise.

**OCTK is not:**

- A replacement for OpenCode, Codex, Claude Code, or any harness.
- An autonomous software factory or agent swarm.
- A model router for choosing models or optimising quotas.
- A prompt/skill marketplace.
- A requirement that users migrate, reinstall, or surrender ownership of existing tools.

OCTK must be additive, optional, and useful alongside skills, plugins, workflows, MCP servers, and repository conventions that already exist.

### A2. Principles

1. **Harness-independent core.** OpenCode is the first evaluation harness, not an architectural dependency.
2. **Additive, not possessive.** Never require users to replace existing tools or configuration.
3. **Discovery is not execution.** Knowing a capability exists does not mean OCTK invokes it.
4. **Progressive disclosure.** Keep always-loaded instructions and tool schemas small; load detail on demand.
5. **Native before wrapper.** Prefer the user's existing capability unless OCTK adds measurable value — pruning, policy, normalisation, provenance, instrumentation, or selection.
6. **Do less when appropriate.** OCTK must be able to recommend *not* using an integration.
7. **Human control.** No silent installation, removal, config rewrite, or consequential action.
8. **Evidence over claims.** Correctness is a hard gate; efficiency never compensates for regression.
9. **Honest measurements.** Separate measured, estimated/counterfactual, and overhead metrics.
10. **No mandatory agent swarm.** Plan/build/explore/verifier subagents are not a product requirement.

### A3. Locked v2 decisions

#### A3.1 Capability Registry

A local, read-mostly registry describing the user's existing ecosystem **without taking ownership of it**.

Capability types: skill / instruction set, slash command or workflow, harness plugin, MCP server, MCP tool, harness-native tool, CLI executable, OCTK-native capability.

Registry metadata covers, where discoverable: identity, type, description, provider, version, invocation, activation, permissions, harness support, measured cost, availability, and provenance. The field-level specification is **B3** — do not maintain a second list here.

Store metadata and references. Never copy third-party skill bodies or proprietary instructions.

#### A3.2 Progressive disclosure levels

- **L0 — Inventory.** Compact name, type, short description, availability.
- **L1 — Invocation metadata.** Command, parameters, permissions, output shape.
- **L2 — Full instructions / schema / docs.** Loaded only when the task needs them.

Discovery adapters are host-specific. Universal discovery is impossible because harnesses expose different config and plugin formats. Support documented adapters plus manual registration.

#### A3.3 Selection and conflict handling

OCTK should determine whether a capability is relevant; prefer a native capability that already solves the problem; avoid loading overlapping instructions or invoking duplicate tools; explain why it selected or skipped a capability; and never automatically install, remove, update, or rewrite anything.

Instruction precedence:

1. Platform and security constraints.
2. Current user task instructions.
3. Repository / team policies.
4. User-selected skills and workflows.
5. OCTK defaults.

Security enforcement is separate from instruction precedence. A prompt cannot override a permission boundary.

#### A3.4 Ponytail and Graphify are external providers

**Do not bundle, fork, or reimplement either tool.**

*Ponytail* — stays user-installed in its native form. Detect presence, version, and mode where possible. Do not duplicate its rules or review prompts. Invoke only where over-engineering/code-reuse review is relevant. Record available / selected / invoked / version.

*Graphify* — optional repository-intelligence provider. Prefer the local engine for reproducible benchmarks. Use for structural questions: call paths, symbol relationships, affected components, dependency relationships. Do not run for every task. Track cold index, warm query, and incremental update costs separately. Never conflate local Graphify with Graphify Cloud.

OCTK's differentiator is intelligent selection and integration, not ownership of these tools.

#### A3.5 Core architecture direction

Components: Context Engine, Capability Registry, Capability Selector, Diagnostic Engine, Project Intelligence, Project State, Telemetry/Evaluation, Harness Adapters (OpenCode first). Detail in B1.

### A4. Reassess and drop

| Item | Disposition | Requirement |
|---|---|---|
| TTY approval gate | Reassess | Configurable policy scoped to consequential actions. Roadmap checkbox approval is not the product's identity. |
| Roadmap | Reassess | Keep lightweight. |
| AST drift scanner | Reassess | Extensible; declare language coverage explicitly. Never imply Python AST covers other languages. |
| Graphify | Reassess | Optional provider, never a hard dependency. |
| Model selection | Reassess | Belongs to harness/user. OCTK may record model/provider/effort for analysis. No model router. |
| Agent scaffolding | Replace | Small harness adapter plus optional setup helper. |
| Circuit breaker | Reassess | Escalate safely or offer documented bypass. Never silently weaken shell or permission boundaries. |
| MCP surface | Reassess | Lean set only. Schema overhead must not exceed value. See B4. |
| Mandatory subagents | **Drop** | — |
| Multi-model quota routing | **Drop** | — |
| Agent-factory positioning | **Drop** | — |
| Prompt collection as main product | **Drop** | — |
| OpenCode-only assumptions | **Drop** | — |
| Mandatory wrappers around every external tool | **Drop** | — |
| Automatic mutation of user capability ecosystem | **Drop** | — |

### A5. Open questions for the maintainer

Codex must not resolve these unilaterally. Each has a recommended default; the maintainer's decision goes in `docs/v2/OPEN_QUESTIONS.md`.

| # | Question | Recommended default | Consequence if wrong |
|---|---|---|---|
| Q1 | Registry storage: single JSON index or SQLite? | JSON index (B3) | Migration cost if capability counts exceed ~1k records |
| Q2 | Registry scope precedence: project over user, or user over project? | Project overrides user | Wrong default makes per-repo capability pinning impossible |
| Q3 | Is the approval gate retained in v2? For which actions? | Retained, limited to destructive/irreversible actions | Removing it weakens safety story; keeping it broadly reproduces the old friction |
| Q4 | Does v2 ship a roadmap at all? | Yes, minimal, no gating | Dropping it breaks existing users' workflow |
| Q5 | Minimum Python version? | 3.11 (README claims 3.14) | 3.14-only sharply limits adoption; lowering changes syntax/dep constraints |
| Q6 | Distribution: PyPI `octk` + `octk-mcp` entry points, or uvx-only? | Both entry points | Packaging rework later |
| Q7 | Is the MCP server mandatory or optional (CLI-only mode)? | Optional | Mandatory server reproduces the schema-overhead problem |
| Q8 | Telemetry default: local-only, opt-in export? | Local-only, export opt-in | Compliance and trust risk if default is otherwise |
| Q9 | Which harness is second? Codex or Claude Code? | Codex | Wrong pick delays the harness-independence proof |
| Q10 | If `beam-free` disappears mid-benchmark: abort, or relabel cohort? | Abort and relabel | Silent substitution invalidates every comparison (D2) |

---

## Part B — Target architecture

### B1. Component map and boundary rule

```text
+-------------------------------------------------------------+
|  Harness adapter (OpenCode)   |  Harness adapter (Codex)     |
|  - detection, discovery, injection hints                     |
+------------------------------+------------------------------+
                               |  CapabilityRecord / ContextBundle
+------------------------------v------------------------------+
|  Core (harness-neutral, no harness SDK imports)              |
|                                                              |
|  Context Engine  ->  Capability Registry  ->  Selector       |
|         |                    |                   |           |
|         +--------------------+-------------------+           |
|                              v                               |
|  Diagnostic Engine     Project Intelligence     Project State|
|                              |                               |
|  Telemetry / Evaluation -----+-------------------------------+|
+--------------------------------------------------------------+
                               |
        Providers (external, optional): Graphify, Ponytail
```

**Architecture rule:** core modules depend on abstract interfaces. Core must not import OpenCode APIs, Graphify, Ponytail, or any model provider SDK. Harness-specific types appear only inside `adapters/`.

**Degradation rule:** if an adapter or provider is absent, the system still works with manual registration. No component may require an external tool to function.

### B2. Harness adapter contract

Minimum interface Codex must specify precisely. Shape is illustrative, not final:

```python
class HarnessAdapter(Protocol):
    id: str                                   # "opencode", "codex"

    def detect(self) -> HarnessInfo | None:
        """Return version/config summary, or None if harness absent."""

    def discover_capabilities(self) -> Iterable[CapabilityRecord]:
        """Read-only. Must never execute a discovered capability."""

    def install_hints(self) -> list[str]:
        """Text suggestions for the user. Never applied automatically."""
```

Requirements:

- `discover_capabilities` is strictly read-only and idempotent.
- Discovery failure returns an empty set plus a reason; it never raises into core.
- Adapters never write to user configuration. `install_hints` returns text only.
- Adapter output is normalised into `CapabilityRecord` (B3) before reaching core.
- A second adapter must be addable without touching core.

### B3. Capability Registry — proposed schema

Codex validates and amends this. Do not replace it with an unconstrained design without stating why.

**Storage and scope resolution** (project overrides user):

```text
~/.config/octk/capabilities/index.json     user scope
<repo>/.toolkit/capabilities/index.json    project scope (committed)
<repo>/.toolkit/capabilities/local.json    machine-local (gitignored)
```

**Record:**

```json
{
  "id": "skill:ponytail/review",
  "type": "skill",
  "name": "Ponytail review",
  "description": "Over-engineering and code-reuse review. <=140 chars.",
  "provider": "ponytail",
  "version": "1.4.2",
  "scope": "project",
  "harness": ["opencode"],
  "activation": "enabled",
  "invocation": {
    "method": "skill",
    "command": null,
    "schema_ref": ".opencode/skills/ponytail/SKILL.md"
  },
  "permissions": {
    "side_effects": ["read_only"],
    "requires_approval": false
  },
  "cost": {
    "context_tokens": 812,
    "measurement": "measured"
  },
  "provenance": "discovered",
  "verified_at": "2026-11-08",
  "source_path": ".opencode/skills/ponytail"
}
```

**Field rules:**

| Field | Constraint |
|---|---|
| `id` | Stable, namespaced `type:provider/name`. Never derived from display name. |
| `type` | One of the A3.1 enumeration. Unknown types are rejected, not coerced. |
| `description` | ≤140 chars. This is the L0 payload. |
| `version` | `null` when undiscoverable. Never guessed. |
| `activation` | `enabled` / `disabled` / `unknown`. `unknown` is legitimate. |
| `cost` | Present only with `measurement: "measured"`. Estimated values are rejected. |
| `provenance` | `discovered` / `manual` / `octk_provided`. |
| `verified_at` | ISO date, or `null`. `null` means "listed but unverified" and is a first-class state. |
| `source_path` | Used for re-discovery. Must not contain secrets. |

**Disclosure payloads:**

- **L0** — `id`, `type`, `name`, `description`, `activation`, `available`.
- **L1** — L0 plus `invocation`, `permissions`, `harness`, `cost`.
- **L2** — a *reference* to the original document or schema. OCTK does not store or serve third-party instruction bodies.

**Invariants** (testable, and Codex should specify the tests):

1. Registry load never executes a capability.
2. Registry write never touches user-owned files outside `.toolkit/capabilities/`.
3. Duplicate IDs across scopes resolve deterministically and record which scope won.
4. A record with `verified_at: null` is still listable at L0.
5. Removing the registry file leaves OCTK functional with manual registration only.

### B4. MCP surface — keep, demote, add

| Tool | Disposition | Rationale |
|---|---|---|
| `glance_pantry` | Keep | Core value; L0 inventory |
| `equip_spec` | Keep | JIT retrieval |
| `equip_skill` | Keep | JIT retrieval |
| `debug_inspect` | Keep | Core diagnostics |
| `browser_inspect` | Keep, feature-flagged | Heavy dependency; not every user needs Chromium |
| `check_spec_drift` | Keep, declare coverage | Python-only must be stated in the tool description |
| `equip_external_mcp` | Keep, lazy + read-only default | Matches A2.3 |
| `run_audit_workflow` | Demote to CLI | Workflow orchestration, not per-turn agent need |
| `update_roadmap` | Demote to CLI | Consequential action; approval lives in the CLI |
| Session handoff | CLI only | Not an agent-turn capability |
| Telemetry | No tool | Internal |
| **`capability_registry`** | **Add** | L0/L1/L2 retrieval — the v2 thesis |

**Target: ≤6 always-exposed MCP tools.** Every additional schema is a standing cost paid on every turn (C4 documents +908 tokens from the previous surface).

### B5. Repository structure

Current layout is flat. This is a **hypothesis**, sequenced late (E3 Phase 5), not a precondition for v2.

```text
octk/                        # current, flat — 21 modules
  pantry.py  server.py  drift.py  runtime/  audit.py  roadmap.py
  handoff.py  mcp_proxy.py  metrics.py  approvals.py  scaffold.py
  cli.py  bench.py  config.py  report.py  sentinel.py  templates.py
  doctor.py  __init__.py

docs/                        # current: DESIGN.md only
  v2/                        # this handoff + Codex deliverables

tests/                       # current: 16 test modules + conftest
benchmarks/                  # current: dogfood.py + results/
reports/                     # current: BENCH_TOOLS.md + test-results/
skills/  scripts/  .toolkit/  .opencode/
```

Proposed target, **only after the vertical slice proves the thesis**:

```text
octk/
  core/           context/ capabilities/ diagnostics/ project_state/
                  telemetry/ evaluation/
  adapters/       harnesses/{opencode,codex}/  providers/{graphify,ponytail}/
                  discovery/
  server/  cli/
```

Codex must state the migration cost of this move and whether the slice can ship on the flat layout. Recommendation: **ship Phase 1–2 on the flat layout**; restructure only when a second harness adapter exists.

---

## Part C — Current state: verification checklist

### C1. Why a checklist, not a narrative

The previous draft called this section "source-of-truth baseline" and then warned that the README may not match the code. Those two statements cannot both be true. Each claim below is therefore an **audit action with an ID**, not a fact. Codex resolves every row and reports `CONFIRMED`, `DRIFTED`, `ABSENT`, or `UNKNOWN`.

### C2. Claim table

"Verify against" paths come from a directory listing, not a code read. Codex must confirm the module actually implements the claim.

| ID | Claim (from README) | Verify against | Resolve |
|---|---|---|---|
| C-01 | `glance_pantry` returns a compact index of specs and skills | `octk/pantry.py`, `tests/test_pantry.py` | |
| C-02 | `equip_spec` loads a spec on demand | `octk/pantry.py` | |
| C-03 | `equip_skill` loads a supplemental skill on demand | `octk/pantry.py` | |
| C-04 | A small `AGENTS.md` acts as the always-loaded traffic cop | `AGENTS.md` (21 lines claimed) | |
| C-05 | Ideate mode is a workflow, not a separate agent | `.opencode/commands/ideate.md` | |
| C-06 | `debug_inspect` runs allowlisted Python/pytest and prunes third-party frames | `octk/runtime/`, `tests/test_debugger.py` | |
| C-07 | `browser_inspect` summarises selectors, console errors, HTTP 4xx/5xx | `tests/test_browser.py` | |
| C-08 | `check_spec_drift` uses Python AST to compare code to docs | `octk/drift.py` | |
| C-09 | `run_audit_workflow` enforces graph freshness + Graphify/Ponytail review | `octk/audit.py`, `tests/test_audit.py` | |
| C-10 | `update_roadmap` tracks roadmap state | `octk/roadmap.py`, `tests/test_roadmap_gate.py` | |
| C-11 | Session handoff snapshots roadmap, git state, runtime signal, approvals | `octk/handoff.py`, `tests/test_handoff.py` | |
| C-12 | `equip_external_mcp` lazily connects to stdio MCP servers | `octk/mcp_proxy.py`, `tests/test_external_mcp.py` | |
| C-13 | Telemetry tracks tokens, timing, cache, turns, and metric categories | `octk/metrics.py`, `tests/test_metrics_report.py` | |
| C-14 | Safety: TTY-gated one-use approval token; subprocess allowlist without `shell=True`; two-strike circuit breaker | `octk/approvals.py`, `tests/test_safety.py`, `tests/test_circuit_breaker.py` | |
| C-15 | `octk init` scaffolds OpenCode-specific agents, commands, config | `octk/scaffold.py`, `tests/test_scaffold.py` | |
| C-16 | MCP surface exposes exactly 9 named tools | `octk/server.py`, `tests/test_server.py` | |
| C-17 | Python 3.14, FastMCP, Playwright, Pytest, `uv` | `pyproject.toml`, `uv.lock` | |
| C-18 | Test count: badge says 123, development section says 95 | `uv run pytest -q` (count collected) | |
| C-19 | Design conventions live in `docs/DESIGN.md` | `docs/DESIGN.md` | |
| C-20 | Generated benchmark reports live under `reports/` | `reports/`, `benchmarks/results/` | |
| C-21 | `.toolkit/metrics.json`, `.toolkit/approvals.json`, `graphify-out/`, `.venv/` are gitignored | `.gitignore` | |

### C3. Drift already observed

These are known before the audit and should not be re-discovered as surprises:

1. Package is **flat** `octk/*.py`, not `src/octk/core/...`. The previous draft's structure section was aspirational.
2. `docs/` contains only `DESIGN.md`. `docs/v2/` did not exist before this file.
3. The handoff document was untracked at the repository root, and has been relocated here.
4. Repository root also contains `benchmarks/`, `reports/`, `skills/`, `scripts/`, `tests/`, `.toolkit/`, `.opencode/` — the old README may not describe these.
5. `git status` shows substantial uncommitted modifications under `.opencode/skills/`. **Do not revert, stash, or clean these.** They are user work.

### C4. Historical benchmark results — quarantined

**These are not v2 claims.** They were produced by the previous implementation and must not be cited as evidence for the v2 design.

| Task | Duration | Tokens | Note |
|---|---:|---:|---|
| roadmap-gate | +25.7% | +33.0% | improved |
| pantry-desc | +0.5% | −18.1% | added tokens |
| metrics-tokens | −19.4% | +16.3% | tokens improved, time regressed |
| debugger-locals | −50.8% | −86.5% | acknowledged self-referential failure — not normal behaviour |
| scaffold-gitignore | −10.0% | −40.1% | added tokens |

Exact Turn-1 standing cost: bare 6,823 input tokens; OCTK 7,731; **overhead +908 tokens**.

Interpretation carried forward into v2 design:

- Results are mixed. Simple tasks lose to schema and instruction overhead.
- The debugger result is a defect, not a data point.
- No universal token or time savings may be claimed.
- The +908 figure is the concrete justification for the B4 target of ≤6 MCP tools.

Reproduce the old baseline if practical. **Do not overwrite historical reports.**

### C5. Provenance — built vs integrated

| Category | Items |
|---|---|
| **Built by OCTK** | FastMCP pantry router and JIT loading; runtime traceback and browser/DOM pruners; AST spec-drift scanner; approval and telemetry engine; CLI, project state, session handoff |
| **Integrated** | OpenCode (first harness); Graphify (repository intelligence); Ponytail (code-reuse audit) |
| **Underlying libraries** | FastMCP / MCP SDK, Playwright, Pytest |
| **Adapted methodologies** | Elephant-Goldfish Model concepts — deep-context planning, independent review, spec-to-code drift, sentinel-block upserting. OCTK does **not** recreate EGM's agent swarm. MCP Code Mode / progressive disclosure — expose a small index, not many large schemas. |

---

## Part D — Evaluation

Two tracks. The controlled internal suite is primary evidence. One external benchmark is a credibility check.

### D1. Unit of a result

A result belongs to the **complete configuration**: model + harness + toolchain + OCTK condition. Never report an OCTK result as if the model and harness were constants.

### D2. Fixed configuration and availability protocol

**Configuration:** OpenCode harness, `beam-free` model.

Before any run:

- [ ] Capture OpenCode version (`opencode --version`).
- [ ] Confirm `beam-free` appears in `opencode models` and is selectable.
- [ ] Record exact provider/model ID and metadata.
- [ ] Record provider rate limits, retry behaviour, and free-tier terms.
- [ ] Snapshot effective config: permissions, plugins, MCP servers, skills, environment.
- [ ] Confirm tool-calling support and note that behaviour can change across provider updates.

**Fallback policy:** if `beam-free` is unavailable, do **not** substitute. Mark the run `BLOCKED`, or start a separately labelled model cohort with its own report. Free models are rate-limited and can be withdrawn; results are tied to a snapshot date and are not model-independent findings.

### D3. Factorial design and cost model

| Arm | OCTK | Ponytail | Graphify |
|---|:--:|:--:|:--:|
| A | off | off | off |
| B | off | on | off |
| C | off | off | on |
| D | off | on | on |
| E | on | off | off |
| F | on | on | off |
| G | on | off | on |
| H | on | on | on |

This isolates each contribution independently and tests whether OCTK still adds value when the other tools are present.

**Staged gates.** 8 arms × 8 categories × 5 reps = **320 runs**. Run it in stages, not at once:

| Stage | Arms | Runs (8 cat × 5 reps) | Proceed only if |
|---|---|---:|---|
| 1 | A, E | 80 | OCTK shows a non-negative effect on correctness and a measurable efficiency signal |
| 2 | + B, C | 160 cumulative | External tools show independent effect worth testing interactions |
| 3 | + D, F, G, H | 320 cumulative | Interaction effects appear plausible from Stage 2 variance |

**Stop rule:** if Stage 1 shows a correctness regression in any category, stop and fix before spending on Stages 2–3. Correctness is a hard gate (A2.8).

**Cost honesty:** per-run wall-clock and token cost are `UNKNOWN` until measured in Stage 1. Do not publish an estimated total before then. Record the measured Stage 1 mean and extrapolate explicitly, labelled as extrapolation.

### D4. Task suite

Deterministic, replayable tasks with a **hidden acceptance oracle**:

1. Simple isolated bug — one file, minimal exploration.
2. Multi-file feature — several modules and tests.
3. Repository exploration — locate behaviour and explain the call path.
4. Refactor — simplify without behaviour regression.
5. Test-failure diagnosis — root cause plus verified fix.
6. Browser issue — local app with a known console/network/UI failure.
7. Architecture drift — implementation versus documented contract.
8. Capability overlap — Ponytail vs existing review skill; Graphify vs native search and the OCTK AST scanner.

Constraints: more than one repository and language over time; start with a small stable set; no live external services; no dependence on changing upstream state.

**Oracle rules:** acceptance tests are not visible to the agent under test; they are versioned; they are never used to tune OCTK (D7).

### D5. Controls and isolation

Per paired run:

- Same base commit, clean worktree.
- Same task prompt and acceptance tests.
- Same OpenCode version, model ID, provider, permissions, environment.
- Same external skills/plugins/MCPs within each arm.
- Pinned Ponytail and Graphify versions, with configuration and mode recorded.
- Graphify state labelled: cold index / warm query / incremental update.
- Randomised run order to reduce provider-load bias.
- Isolated git worktrees or containers. **Never** allow parallel runs in one repository.
- ≥5 repetitions per task/arm for the pilot; 10 when variance is high.
- Preserve raw transcripts, tool traces, diffs, test output, timings, token usage, environment manifests.
- Record provider errors, rate limits, retries, and incomplete runs separately.
- Identical task-level instructions across arms; only the condition differs.
- Same model for the primary comparison; a second model is a later robustness cohort.

### D6. Metrics

**Correctness — hard gate**

Acceptance-test pass rate; regression-test pass rate; task completion; patch correctness and hidden-test outcomes; security/permission violations; reverts or destructive actions; human maintainability score.

**Efficiency**

Total input tokens; cached and uncached input tokens where exposed; output tokens; tool calls by type; files read and search operations; diagnostic bytes before/after pruning; repeated or overlapping capability calls; wall-clock duration; provider latency and retries; estimated monetary cost where meaningful.

**Context quality**

Required-signal retention; irrelevant-context reduction; relevant file/symbol discovery precision; correct capability selected; unnecessary capability avoided.

**Integration overhead**

OCTK tool-schema and instruction overhead; registry discovery latency; Graphify indexing/query time; Ponytail injected context and execution cost; **net token delta after subtracting all overhead**.

Report gross bytes/tokens pruned and net total-token change **separately**. Character savings are not token savings.

### D7. Integrity — pre-registration checklist

A run does not count unless every box is ticked **before** execution.

- [ ] Base commit SHA and clean-worktree state recorded.
- [ ] OpenCode version, model ID, provider, and date recorded.
- [ ] Arm label and Ponytail/Graphify version recorded.
- [ ] Task prompt hash and acceptance-test hash recorded.
- [ ] Randomisation seed and resulting run order recorded.
- [ ] Isolation verified (distinct worktree or container per run).
- [ ] Raw transcript output path exists and is writable.
- [ ] Correctness computed by the hidden oracle, not agent self-report.
- [ ] Rate-limit and error handling defined for this run.

Post-run obligations:

- Report **all** tasks, including losses and failures.
- Include medians, ranges/variance, and sample counts.
- Distinguish exact provider token usage from `chars/4` approximations.
- Never compare across different model snapshots as if only OCTK changed.
- Never cite Ponytail's published benchmark as evidence for OCTK.
- Never exclude a task post hoc without a documented reason.
- Keep raw data and a reproducible report generator in the repository.

### D8. External benchmark — pick one

| Option | Fit | Cost | Verdict |
|---|---|---|---|
| **Terminal-Bench 2.0** | Terminal tasks in Docker; scores complete agent configurations | Medium, if an OpenCode runner is feasible | **Preferred** — verify the runner interface first |
| **SWE-bench Lite** | Real GitHub issue fixing | High (repo envs + Docker) | Fallback — small labelled pilot subset only |
| **SWE-bench Verified** | 500 human-validated instances | Highest | Not first |

**Procedure:**

1. Verify whether Terminal-Bench 2.0 has a maintainable OpenCode adapter path.
2. If not, assess a small SWE-bench Lite pilot with an OpenCode runner.
3. Choose exactly one. Do not build two integrations in the first milestone.
4. Label every external result as a full model+harness+toolchain result, never an isolated OCTK result.

References: F3.

---

## Part E — Execution

### E1. Audit protocol

Run in order. Record the command and the output artefact path for each step.

| Step | Action | Artefact |
|---|---|---|
| 1 | Inspect repository tree, including hidden dirs. Do not dump secrets. | `docs/v2/audit/tree.txt` |
| 2 | Read README, `docs/DESIGN.md`, `pyproject.toml`, `uv.lock`, CLI entry points, `octk/server.py`, adapters, tests, benchmark code, reports, CI. | reading log |
| 3 | Inspect git status, recent commits, branches, uncommitted changes. **Do not reset, stash, checkout, clean, or overwrite user work.** | `docs/v2/audit/git-state.txt` |
| 4 | Run the existing test suite as-is if safe. Record failures and environment limits. Do not fix during audit. | `docs/v2/audit/test-run.txt` |
| 5 | Resolve every row in C2 to `CONFIRMED` / `DRIFTED` / `ABSENT` / `UNKNOWN`. | `CURRENT_STATE_AUDIT.md` §claims |
| 6 | Identify dead code, duplicate responsibilities, brittle boundaries, hidden OpenCode coupling, security assumptions, dependency risks, documentation drift. | `CURRENT_STATE_AUDIT.md` §risks |
| 7 | Inspect how OpenCode loads MCP servers, plugins, skills, commands, permissions — from **current** official docs. | citations |
| 8 | Inspect Graphify and Ponytail integration points without installing, updating, or mutating global config. | `docs/v2/integrations/` |
| 9 | Inspect benchmark scripts and raw reports. Reconcile sample sizes; separate historical from reproducible. | `BENCHMARK_PLAN.md` §baseline |
| 10 | Determine which data comes from OpenCode session logs/provider usage and which needs instrumentation. | `ARCHITECTURE.md` §telemetry |
| 11 | Define run isolation: worktrees/containers, contamination prevention. | `BENCHMARK_PLAN.md` §controls |
| 12 | Produce a capability inventory and a current-state architecture diagram. | `CURRENT_STATE_AUDIT.md` |

**Redaction:** never expose `.env`, API keys, tokens, credentials, private user data, or secret-bearing config in any report.

### E2. Deliverables matrix

Write to `docs/v2/`. Create a planning branch only if the maintainer explicitly approves; otherwise leave the working tree unchanged.

| # | Document | Depends on | Satisfies DoD |
|---|---|---|---|
| 1 | `CURRENT_STATE_AUDIT.md` — architecture, module map, feature-to-code mapping, tests, dependencies, risks, doc drift | E1 | D1, D2 |
| 2 | `PRODUCT_REQUIREMENTS.md` — definition, non-goals, user stories, registry requirements, disclosure, integration behaviour, security, compatibility | A | D3, D4 |
| 3 | `ARCHITECTURE.md` — component boundaries, data flow, interfaces, adapter contracts, persistence, MCP surface, security boundaries, diagrams | B | D3, D5 |
| 4 | `ADR.md` — decisions with rationale and alternatives | A, B | D3 |
| 5 | `BENCHMARK_PLAN.md` — factorial design, tasks, metrics, controls, sample counts, reporting plan, external choice, cost risk | D | D6, D7 |
| 6 | `IMPLEMENTATION_PLAN.md` — ordered epics, tasks, dependencies, migration, estimates, acceptance criteria, risks, DoD | all | D8 |
| 7 | `MIGRATION_AND_COMPATIBILITY.md` — how existing users keep config, skills, plugins, MCP servers, workflows, project files | 1, 3 | D4 |
| 8 | `OPEN_QUESTIONS.md` — only decisions needing maintainer input, with recommended default and consequence | A5 | D9 |

`IMPLEMENTATION_PLAN.md` must classify every item as: **keep as-is / refactor / replace / deprecate / drop / new capability.**

Every proposed task must include: why it is needed; likely affected modules (mark uncertain paths as hypotheses); dependencies; tests; acceptance criteria; risk and rollback; whether it changes user-facing behaviour or config.

**Do not produce a large speculative backlog.** Prioritise one vertical slice that proves the thesis.

### E3. Phases

| Phase | Scope | Exit criterion |
|---|---|---|
| 0 — Audit and baseline | Reproducible tests, baseline benchmark, compatibility contract | C2 fully resolved; test command documented |
| 1 — Capability Registry slice | Read-only inventory, manual registration + one OpenCode adapter, L0/L1/L2, no execution, no config mutation | Registry lists native skills, MCP servers, and plugins; B3 invariants tested |
| 2 — Context Engine | Compact inventory, JIT loading, relevance, token/byte accounting | Net overhead reported explicitly; no regression on C4 baseline tasks |
| 3 — Provider adapters | Graphify local adapter; Ponytail detection/metadata/invocation; no duplicate injection | Provider absent ⇒ graceful manual fallback |
| 4 — Diagnostics | Preserve debugger/browser, stable result schemas, signal-retention tests, safe escalation | Pruning benchmarks pass signal-retention gate |
| 5 — Harness adapter and compatibility | OpenCode first; core stays neutral; user config preserved | A second adapter can be added without touching core |
| 6 — Benchmark and evaluation | Runner, report generator, factorial run, one external pilot | D7 checklist complete for every reported run |
| 7 — Release hardening | Security review, licence audit, docs, migration guide, packaging, CI | DoD (E4) fully green |

### E4. Definition of Done — planning task

- [ ] Repository inspected directly, not inferred from this document.
- [ ] Every C2 claim resolved to CONFIRMED / DRIFTED / ABSENT / UNKNOWN.
- [ ] Existing features classified accurately.
- [ ] Architecture keeps core harness-independent (B1 rule).
- [ ] Existing user tools and configuration preserved.
- [ ] Ponytail and Graphify remain optional external providers.
- [ ] Discovery is not confused with invocation.
- [ ] Benchmark design isolates OCTK, Ponytail, and Graphify.
- [ ] OpenCode + `beam-free` specified, with availability and version recording (D2).
- [ ] One external benchmark selected from actual runner feasibility (D8).
- [ ] Plan includes tests, migration, security, and rollback.
- [ ] Uncertainties and assumptions explicit.
- [ ] No implementation or destructive repository change made without approval.

---

## Appendix

### F1. Codex kickoff prompt

Paste this after reading the whole document. It references sections by ID rather than restating them.

```text
You are the lead engineer for the OCTK v2 repository audit and architecture planning.

Read docs/v2/CODEX_HANDOFF.md in full before acting. Do not skim.

This is PLANNING ONLY. Do not implement, refactor, update dependencies, install
plugins, modify global OpenCode config, delete files, reset git state, or
overwrite user work. Uncommitted changes under .opencode/skills/ are user work.

The repository is the source of truth for implementation facts. The handoff is
the source of truth for product intent. Report disagreements; do not resolve
them silently.

Order of work:
1. E1 audit protocol. Resolve every C2 claim to CONFIRMED / DRIFTED / ABSENT /
   UNKNOWN.
2. Treat A and B as constraints. A1-A4 are settled; A5 is for the maintainer.
3. Validate or amend the B3 registry schema; state any invariants you add.
4. Specify the B2 adapter contract precisely enough to implement.
5. Reassess the B4 MCP surface against the C4 overhead evidence.
6. Produce the eight E2 deliverables, respecting the E2 traceability matrix.
7. Design the D3 factorial with staged gates and stop rule intact. Do not
   publish a total cost estimate before Stage 1 is measured.
8. Apply D7 as a gate: a run that fails it is not evidence.
9. Recommend exactly one external benchmark per D8, from verified runner
   feasibility. Cite current official documentation.
10. End with a decision memo: preserve / change / drop, the smallest useful
    vertical slice, and the first three engineering tasks.

Hard constraints: no subagent swarm, no model router, never trade correctness
for tokens. Label every statement measured / estimated / hypothesis. Mark
unverifiable items UNKNOWN with a verification method. Do not invent paths,
results, scores, or API support. If a tool is unavailable, continue and report
the blocker.

Do not ask broad questions before completing the audit. Stop before implementation.

Final response: evidence summary, generated documents, proposed architecture,
benchmark design, unresolved questions, and explicit confirmation that no
implementation changes were made.
```

### F2. OpenCode setup notes

Verify against current documentation before editing configuration:

- Config and MCP servers: <https://opencode.ai/docs/config>
- Agents and permissions: <https://opencode.ai/docs/agents>
- Model IDs use `provider/model-id`.
- Observed Beam Free catalogue entry: `beam-free`. Confirm locally with `opencode models`.

Do not copy the old README's OpenCode configuration blindly — its MCP schema and permission syntax may be stale. Current documentation takes precedence.

### F3. References

**External benchmarks**

- Terminal-Bench 2.0 — <https://www.tbench.ai/?version=2.0>
- Terminal-Bench methodology — <https://epoch.ai/benchmarks/terminal-bench>
- SWE-bench Lite — <https://www.swebench.com/lite>
- SWE-bench Verified — <https://www.swebench.com/verified>
- SWE-bench quickstart — <https://www.swebench.com/SWE-bench/guides/quickstart/>

Use external benchmarks to test generalisation, not to replace the controlled suite. The controlled comparison holds model, harness, repository snapshot, task prompt, permissions, and acceptance criteria constant.
