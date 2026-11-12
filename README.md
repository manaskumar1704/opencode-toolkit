# octk — the information layer for coding agents

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-322%20passing-brightgreen?logo=pytest&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-8%20tools-orange)
![OpenCode](https://img.shields.io/badge/OpenCode-first%20harness-111827)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Status](https://img.shields.io/badge/status-alpha-yellow)

**Give coding agents the right information, at the right time, in the right
format — and prove it with numbers you can check.**

`octk` is a local CLI (`octk`) plus an MCP server (`octk-mcp`) that describes
the tools you already have, loads detail only when a task needs it, gates
consequential actions behind a human, and measures what actually happened.

> [!IMPORTANT]
> **Where the numbers are, and where they aren't.** Across 112 valid runs,
> OCTK kept correctness at **112/112** and cut input tokens by **38.5%**
> (95% CI +4.5%..+82.4%) on large-context selection — and showed **no signal**
> on small single-file edits. Both results are published, including the four
> runs we had to exclude. Full method and numbers:
> [`docs/v2/BENCHMARK_RESULTS.md`](docs/v2/BENCHMARK_RESULTS.md).

---

## Why this exists

Coding agents fail in three predictable ways:

| Failure | What it looks like | What octk does |
|---|---|---|
| **Context dumping** | Every spec, skill, and tool schema is injected on turn 1 | A tiny pantry index; specs load on demand |
| **Unverified self-approval** | The agent marks its own roadmap task `[x]` | A TTY-gated, spend-once approval token |
| **Unverifiable claims** | "90% fewer tokens" with no raw numbers | Every metric tagged `measured`, `counterfactual`, or `load` |

The fourth failure is the one we hit ourselves: **building the wrong benchmark**.
That is why the result above is published, not hidden.

## What it does

| Pillar | What you get |
|---|---|
| **Capability Registry** | A read-only inventory of skills, commands, plugins, MCP servers, and CLIs — with L0/L1/L2 detail |
| **Capability Selector** | Explainable relevance ranking: why a capability was picked or skipped |
| **Pantry** | `glance_pantry` inventory + `equip_spec` / `equip_skill` on demand |
| **Human gate** | `octk approve "<task>"` in a real terminal; the agent cannot self-approve |
| **Diagnostics** | Pruned tracebacks and browser snapshots with scored signal retention |
| **Honest telemetry** | Gross vs net, measured vs estimated, per task and per tool |

## Architecture

```mermaid
flowchart TB
  subgraph Harness["OpenCode (first harness)"]
    A["AGENTS.md<br/>conditional rules"]
    S["native skills<br/>.opencode/skills"]
  end

  subgraph Boundary["octk/adapters — harness boundary"]
    AD["HarnessAdapter<br/>detect · discover · install hints"]
  end

  subgraph Core["octk core — harness-neutral"]
    REG["Capability Registry<br/>L0 / L1 / L2"]
    SEL["Selector<br/>explainable ranking"]
    PAN["Pantry<br/>glance · equip"]
    DIAG["Diagnostics<br/>pruners + retention"]
    MET["Telemetry<br/>measured / counterfactual / load"]
  end

  subgraph Providers["external providers — detected, never bundled"]
    P1["Ponytail"]
    P2["Graphify"]
  end

  A --> AD
  S --> AD
  AD --> REG
  REG --> SEL
  REG --> PAN
  PAN --> DIAG
  DIAG --> MET
  AD -.-> P1
  AD -.-> P2
  MET --> R["octk report"]
```

**Boundary rule:** core never imports a harness. Adding a second harness means
adding one adapter, not editing the core. `tests/test_boundaries.py` enforces it.

## Quickstart

```bash
# 1. Install (from source; PyPI packaging is prepared but not published)
git clone https://github.com/manaskumar1704/opencode-toolkit
cd opencode-toolkit
uv tool install --editable .

# 2. Scaffold a project
cd path/to/your-project
octk init

# 3. Print the OpenCode config and merge it
octk mcp-config
```

`octk init` creates:

- `AGENTS.md` — a short, static traffic-cop file
- `.toolkit/` — specs, roadmap, config, metrics, approvals
- `.opencode/agents/` — `plan`, `build`, `explore`, `verifier`
- `opencode.json` — the MCP entry, using the portable `octk-mcp` command

Then run `opencode` and ask for work. When the agent wants to mark a roadmap
item done:

```bash
octk approve "build-login"   # human terminal only
```

## Benchmark: what we measured

**Stage 1** — 112 valid runs, 9 tasks, 2 arms.
Cohort: OpenCode 2.2.7, `opencode-go/beam-free`, effort `high`.
Isolation: standalone workspace, `bwrap`, private `/tmp`, hidden oracle.
Gate: paired bootstrap, 5,000 resamples, minimum 5% token or 10% duration effect.

| Metric | Result |
|---|---|
| Correctness | **112 / 112 valid runs passed.** No task regressed |
| Large-context selection (n=20) | **38.5% fewer tokens** (CI +4.5%..+82.4%), **73.3% faster** (CI +0.5%..+187.0%) |
| Small-edit tasks (n=32 paired) | **No signal.** Tokens −13.1% (CI −71.1%..+30.4%) |
| Worst case, large-context block | A: 37,203 tokens · 286s — E: **8,598 tokens · 11.4s** |
| Worst case, small-edit block | E: 89,610 tokens / 543s (one run) — A: 36,488 tokens, 288.8s max duration |

### The result that clears the gate

`spec_selection`: choose the right specs from a 20-service inventory. The
baseline has to read its way there; the pantry publishes an index.

| statistic | A (OCTK off) | E (OCTK on) | change |
|---|---:|---:|---:|
| median tokens | 7,426 | 6,260 | **−15.7%** |
| mean tokens | 10,057 | 6,187 | **−38.5%** |
| p90 tokens | 17,051 | 7,977 | **−53.2%** |
| max tokens | 37,203 | 8,598 | **−76.9%** |
| max duration | 286.2s | 11.4s | **−96.0%** |

The mean gap comes from five A runs between 13.8k and 37.2k tokens. No E run
left a narrow band. **The pantry's win is tail containment:** it removes the
expensive search, and the expensive search is what blows up the worst case.

### The block that does not clear it

Eight small-repo tasks, 5 reps per arm: no measurable effect (tokens
−13.1%, CI −71.1%..+30.4%). Four runs were excluded as provider stalls, four
cells never ran before the free-tier quota ran out. **Reported as partial, not
as a win.**

The mean is misleading at this sample size: one E run burned 89,610 tokens on
`multi_file_feature`, which flips the token mean to E's disadvantage, while the
median favours E (6,328 → 5,690). Drop that single run and the means are
9,287 vs 9,808. When a task is small enough to finish from first principles, a
context tool has little to save — and either arm can still have a bad run.

### What we learned

| Layer | Finding |
|---|---|
| **Architecture** | A fixed MCP schema tax of **~500 tokens per run**. v1 measured the same floor: bare 6,823 → octk 7,731 (**+908 turn-1 tokens**) |
| **Implementation** | `check_spec_drift` dumped 11k chars per call; `glance_pantry` was mandatory and called 25 times. Both capped |
| **Harness** | Two drivers once shared a workspace and produced a **fake correctness regression**. Now `flock`-guarded; timeouts are excluded, not scored as failures |
| **Benchmark design** | The original 8 tasks could not exercise the pantry at all. The 9th was added to test the intended use case — and that is where the signal appeared |

**Verdict:** correctness parity holds across 112 runs. Efficiency is proven
where context selection is genuinely expensive, and unproven everywhere else —
so the external benchmark decides the general claim, not this suite.

### v1 was mixed too

| v1 task | With OCTK | Without | Δ |
|---|---:|---:|---:|
| roadmap-gate | 61,645 | 91,957 | −33.0% |
| metrics-tokens | 85,011 | 101,565 | −16.3% |
| pantry-desc | 102,380 | 86,718 | +18.1% |
| scaffold-gitignore | 96,948 | 69,201 | +40.1% |

The same pattern: wins where exploration is expensive, losses where the task is
small enough that the fixed tax dominates.

## Capability registry

The registry describes what you already have. It never copies skill bodies and
never invokes anything during discovery.

```bash
$ octk capabilities discover          # dry run
$ octk capabilities discover --write  # update .toolkit/capabilities/index.json
$ octk capabilities list --level L1
$ octk capabilities select "review frontend design"
```

```
Task terms: design, frontend, review
Selected (3):
  design-taste-frontend [skill] score=0.67 - matched design, frontend
  imagegen-frontend-web [skill] score=0.67 - matched design, frontend
  free-tier-deploy [skill] score=0.33 - matched frontend
Skipped (2):
  high-end-visual-design [skill] - lower rank than the selected set (matched design)
  imagegen-frontend-mobile [skill] - lower rank than the selected set (matched frontend)
```

Disclosure levels:

| Level | Contents | When |
|---|---|---|
| **L0** | Grouped names only | Always |
| **L1** | Invocation, permissions, availability | When asked |
| **L2** | Full instructions / schema | Only when the task needs it |

## The approval gate

```mermaid
flowchart TB
  A["Agent wants a roadmap item marked [x]"] --> G{"Valid open approval?"}
  G -->|Yes| W["Write status, consume token"]
  G -->|No| E["GateError: agent must ask the human"]
  H["Human: octk approve 'task' (TTY)"] -->|"time-limited, spend-once"| G
```

The gate is **policy-enforced**, not a sandbox: an agent with unrestricted shell
access can still edit files. `octk doctor` checks that the OpenCode deny rules
are present, and the README says so plainly.

## MCP surface — 8 tools

| Tool | Purpose | Cost |
|---|---|---|
| `glance_pantry` | Compact inventory | small |
| `equip_spec` | Load one spec | medium |
| `equip_skill` | Load one extra skill | medium |
| `equip_external_mcp` | Inspect/call a configured external MCP | on demand |
| `debug_inspect` | Pruned test traceback | measured |
| `browser_inspect` | Headless Chromium summary | measured |
| `check_spec_drift` | Python-AST drift report (capped at 20 items/section) | measured |
| `capability_registry` | L0/L1/L2 registry view | small |

Demoted to CLI to keep the schema lean:

- `run_audit_workflow` → `octk audit`
- `update_roadmap` → `octk roadmap set`

`OCTK_BROWSER=0` drops `browser_inspect` and its schema.

## Honest measurement model

Every number is tagged:

- **measured** — raw bytes in, pruned bytes out, provider token readouts
- **counterfactual** — what *would* have been loaded, clearly separated
- **load** — the overhead OCTK itself adds

Rules:

1. Correctness is a hard gate. Efficiency never compensates for a regression.
2. Gross and net savings are reported separately.
3. Character savings are not token savings.
4. A run missing any integrity field is `INVALID`, not defaulted.
5. No performance claim without a measured run.

## CLI reference

| Command | Purpose |
|---|---|
| `octk init [--force]` | Scaffold `AGENTS.md`, `.toolkit/`, agents, `opencode.json` |
| `octk mcp-config` | Print the MCP + permissions snippet |
| `octk capabilities {list,show,discover,verify,select,register}` | Registry and selector |
| `octk providers` | Ponytail / Graphify status (detect only) |
| `octk task start` / `task end` | Task bookkeeping and acceptance check |
| `octk approve "<task>"` | Mint a TTY-gated, spend-once approval |
| `octk report [--json]` | Markdown/JSON telemetry report |
| `octk doctor` | Prefix-cache and gate health |
| `octk handoff` | Deterministic resume snapshot |
| `octk standing add` | Record an exact turn-1 token cost |
| `octk audit` | Graph-freshness + audit workflow |
| `octk roadmap set` | Gate-enforced roadmap status |
| `octk bench tools` | Pruner + signal-retention benchmark |
| `python -m benchmarks.driver --stage 1 --dry-run` | Inspect the factorial queue (dev-only) |

## Status

- **v2 core:** registry, selector, adapters, providers, diagnostics, telemetry — done.
- **Stage 1:** 112/112 valid runs correct. **38.5% fewer tokens** on
  large-context selection (n=20, CI excludes zero); **no signal** on the 8
  small-edit tasks. Core block is partial: 4 provider-stall exclusions, 4 cells
  awaiting quota.
- **Next:** finish the 4 missing cells, then the Terminal-Bench 2.0 adapter
  (the arbiter for the general claim), then Phase B security.
- **Not shipped:** PyPI release, second harness (Codex), MCP reduction below 8.

## Provenance

`octk` is built, not borrowed. Ponytail and Graphify are **external providers**:
detected if installed, never bundled, forked, or reimplemented. Discovery never
executes a capability; no config is mutated silently.

## License

MIT. See [`LICENSE`](LICENSE).
