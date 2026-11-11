# OCTK v2 — Benchmark Plan

**Status:** harness implemented, runs not executed
**Primary evidence:** the controlled internal suite
**Secondary check:** one external benchmark (not yet selected)

---

## 1. Unit of a result

A result belongs to the complete configuration: **model + harness + toolchain +
OCTK condition**. An OCTK result is never reported as if the model and harness
were constants.

## 2. Fixed configuration

| Field | Value |
|---|---|
| Harness | OpenCode |
| Model | `opencode-go/beam-free` (catalogue `beam-free`) |
| Effort | `high` |
| Date | recorded per run |
| Permissions | recorded per run |
| Plugins / MCPs / skills | recorded per run |

### Pre-flight (enforced by `benchmarks/preflight.py`)

The runner refuses to start unless all of these pass:

1. `opencode` binary on PATH.
2. `opencode --version` succeeds.
3. `opencode-go/beam-free` appears in `opencode models`.
4. Every `.opencode/agents/*.md` has `effort: high`.
5. `opencode.json` exists and is valid.

### Fallback

If `beam-free` is unavailable: mark the run `BLOCKED`. Do not substitute. A
different model is a separately labelled cohort.

### Effort

The primary cohort is `beam-free` **and** `high`. Mixing effort levels
invalidates the comparison. `medium`/`max` are separate cohorts.

---

## 3. Factorial design

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

### Staged gates

| Stage | Arms | Runs (8 cat × 5 reps) | Proceed only if |
|---|---|---:|---|
| 1 | A, E | 80 | Correctness non-negative and an efficiency signal |
| 2 | + B, C | 160 cumulative | External tools show independent effect |
| 3 | + D, F, G, H | 320 cumulative | Interaction effects plausible |

**Stop rule:** a correctness regression in Stage 1 stops the run until fixed.
Correctness is a hard gate.

**Cost honesty:** per-run cost is `UNKNOWN` until Stage 1 is measured. No total
estimate is published before then.

---

## 4. Task suite

| # | Category | Fixture | Status |
|---|---|---|---|
| 1 | Simple isolated bug | `simple_bug` | implemented |
| 2 | Multi-file feature | `multi_file_feature` | implemented |
| 3 | Repository exploration | `repo_exploration` | implemented |
| 4 | Refactor | `refactor` | implemented |
| 5 | Test-failure diagnosis | `test_diagnosis` | implemented |
| 6 | Browser issue | `browser_issue` | implemented |
| 7 | Architecture drift | `architecture_drift` | implemented |
| 8 | Capability overlap | `capability_overlap` | implemented |

Each fixture: `task.json`, `setup.patch`, hidden `oracle/acceptance.py`.

**Oracle rules:** not visible to the agent under test; versioned; never used to
tune OCTK.

---

## 5. Controls and isolation

- One standalone workspace copy per run (`benchmarks/workspace.py`). A linked
  git worktree is not isolation: it shares `.git`, so OpenCode resolves the
  host project and the agent can walk back to it.
- The copy excludes `benchmarks/`, so the hidden oracles are not in the
  workspace, and it gets its own git history for `git apply` / `git diff`.
- `bwrap` masks the host `benchmarks/` and `.git` (oracle + history) and makes
  the host tree read-only. Recorded as `environment_manifest.sandbox`.
- `opencode --standalone` per run, so the shared background service (bound to
  the host project) cannot supply the wrong arm config.
- `oracle_leaks()` scans the transcript for unique oracle test names, the
  oracle path, and a clone of the public repository; a leaked run is marked
  `correctness.valid = false` and excluded from pass rates.
- Same base commit and clean worktree.
- Same prompt and acceptance tests across arms.
- Same OpenCode version, model, provider, permissions, environment.
- Pinned Ponytail and Graphify versions; Graphify state labelled cold / warm /
  incremental.
- Randomised run order, seeded and recorded (`benchmarks/driver.build_schedule`).
- ≥5 repetitions per task/arm, enforced by `build_schedule` (10 when variance
  is high).
- Preserve raw transcripts, diffs, test output, timings, token usage,
  environment manifests (`benchmarks/results/transcripts/`).
- Record provider errors, rate limits, retries separately.
- Never allow parallel runs in one repository.

---

## 6. Metrics

### Correctness (hard gate)

Acceptance pass rate, regression pass rate, task completion, hidden-test
outcomes, security violations, reverts, human maintainability score.

### Efficiency

Input/output/cached tokens, tool calls by type, files read, search ops,
diagnostic bytes before/after, repeated capability calls, wall-clock, latency,
retries, cost.

### Context quality

Signal retention, irrelevant-context reduction, discovery precision, correct
capability selected, unnecessary capability avoided.

### Integration overhead

Tool-schema cost, registry latency, Graphify indexing/query time, Ponytail
injected context, **net token delta after all overhead**.

Gross and net are reported separately. Character savings are not token savings.

---

## 7. Integrity (D7)

A run counts only if every field is present **before** execution. Enforced by
`benchmarks/manifest.RunManifest.validate()`.

Required fields (24): arm, task, task_category, base_commit, opencode_version,
model_id, effort, task_prompt_hash, acceptance_test_hash, randomization_seed,
run_order, isolation_verified, transcript_path, ponytail_version,
graphify_version, graphify_state, ponytail_available, graphify_available,
correctness, rate_limit_log, provider_errors.

Post-run obligations: report all tasks including losses; include medians,
ranges, sample counts; separate exact tokens from chars/4; never compare across
model snapshots; never cite Ponytail's benchmark as OCTK evidence; never exclude
a task post hoc without a reason; keep raw data and the report generator.

---

## 8. Reporting

`benchmarks/report.py` renders markdown:

- total / valid / INVALID counts;
- INVALID runs listed with missing fields (never hidden);
- aggregates by arm and task (median, range, n);
- integrity notes.

---

## 9. External benchmark

| Option | Fit | Verdict |
|---|---|---|
| Terminal-Bench 2.0 | Terminal tasks, Docker, scores full configurations | Preferred if an OpenCode runner is feasible |
| SWE-bench Lite | Real issue fixing, heavy environments | Fallback, small labelled pilot |
| SWE-bench Verified | 500 validated instances | Not first |

**Status:** not yet selected. This is the remaining DoD item.

Procedure: verify Terminal-Bench OpenCode runner → else SWE-bench Lite pilot →
choose exactly one → label every result as a full model+harness+toolchain
result.

---

## 10. Cost risk

- 320 runs at 5 reps is the full design; Stage 1 is 80.
- Free-model rate limits may force gaps; record them, do not hide them.
- Browser tasks require Chromium and add setup cost.
- Graphify cold indexing is measured separately from warm queries.

---

## 9. Driver

Stage 1 has been executed: **80 runs, 80/80 correct, no efficiency signal**
(E +21.3% tokens, 49.8% slower). Full numbers and the architecture-vs-
implementation breakdown are in [`BENCHMARK_RESULTS.md`](BENCHMARK_RESULTS.md).

`benchmarks/driver.py` runs the design above.

```bash
# inspect the queue without spending anything
python -m benchmarks.driver --stage 1 --dry-run

# execute a stage (requires explicit confirmation)
python -m benchmarks.driver --stage 1 --yes
python -m benchmarks.driver --stage all --yes
```

| Stage | Arms | Runs | Gate |
|---|---|---:|---|
| 1 | A, E | 80 | no correctness regression **and** a measurable efficiency signal |
| 2 | A, B, C, E | 160 | external tools show an independent effect |
| 3 | A–H | 320 | terminal stage |

- A correctness regression in any task makes the gate **blocking**: the driver
  stops and prints `STOP`, and no later stage runs.
- Cost is `UNKNOWN` until Stage 1 has measured runs; any later projection is
  labelled "extrapolation" in the report.
- Every run writes `benchmarks/results/manifests/*.json` and
  `benchmarks/results/transcripts/*.jsonl`; a missing D7 field marks the run
  `INVALID` rather than defaulting.

---

## 10. External benchmark

Terminal-Bench 2.0 via Harbor. Details, cohort lock, and the feasibility ladder
are in [`EXTERNAL_BENCHMARK.md`](EXTERNAL_BENCHMARK.md); the command builder is
`benchmarks/external.py`.
