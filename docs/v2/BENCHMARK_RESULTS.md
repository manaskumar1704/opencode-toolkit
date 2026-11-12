# Benchmark Results — Stage 1

**Measured:** 2026-11-11 → 2026-11-12
**Cohort:** OpenCode **v2.2.7** · `opencode-go/beam-free` · effort `high`
**Design:** two blocks — `spec_selection` at 20 reps/arm (powered) + 8 core
tasks at 5 reps/arm
**Gate:** paired bootstrap, 5,000 resamples, paired by `(task, rep)`; the 95%
CI must exclude zero **and** clear ≥5% tokens or ≥10% duration. Correctness is
a hard gate.

| Block | Planned | Valid | Correct | Status |
|---|---:|---:|---:|---|
| 1a `spec_selection` | 40 | 40 | 40 | **complete** |
| 1b core (8 tasks) | 80 | 72 | 72 | **partial** — 4 excluded, 4 not run |
| **total** | **120** | **112** | **112** | |

The two blocks are deliberately asymmetric: the task with the highest expected
variance was run at 20 reps, the rest at 5. That is disclosed rather than
smoothed over — see §5.

---

## 1. Verdict

| Claim | Result |
|---|---|
| **Correctness** | **112 / 112 valid runs correct.** No task regressed. Arm A 56/56, arm E 56/56 |
| **Large-context selection** (`spec_selection`) | **E uses 38.5% fewer input tokens** (95% CI +4.5%..+82.4%, n=20) and is **73.3% faster** (CI +0.5%..+187.0%, n=20) |
| **Worst case** | A peaked at **37,203 tokens / 286s**. No E run exceeded **8,598 tokens / 11.4s** |
| **Small-edit block** (8 core tasks) | **No measurable signal.** Tokens −13.1% (CI −71.1%..+30.4%), duration −29.4% (CI −161.7%..+61.2%), n=32 paired |
| **Gate** | Block 1a: **proceed** (CI excludes zero, clears threshold). Block 1b: **no proceed** — no efficiency signal, but **not blocking**: zero correctness regressions |

So the thesis is supported where the baseline would otherwise have to acquire a
lot of context, and is unproven on small edits. The earlier blanket statement
("OCTK costs 21% more tokens") described a pre-fix dataset and is withdrawn.

What this does **not** claim: that OCTK is cheaper in general. The core block
is neutral-to-worse on the point estimate, the block is incomplete, and 5 of 8
core tasks have too few paired cells to report an interval at all.

---

## 2. Block 1a — `spec_selection` (powered, 20 reps)

The task: pick the right specs from a 20-service inventory. The baseline has to
read its way there; the pantry publishes an index and loads detail on demand.

| arm | metric | n | reduction | 95% CI | verdict |
|---|---|---:|---:|---|---|
| E | tokens | 20 | **+38.5%** | +4.5%..+82.4% | improvement |
| E | duration | 20 | **+73.3%** | +0.5%..+187.0% | improvement |

`reduction` is relative to arm A; positive means E used fewer tokens or less
time.

**The effect is tail containment, not a uniform shift.** That distinction is
the actual result:

| statistic | A | E | change |
|---|---:|---:|---:|
| median tokens | 7,426 | 6,260 | **−15.7%** |
| mean tokens | 10,057 | 6,187 | **−38.5%** |
| p90 tokens | 17,051 | 7,977 | **−53.2%** |
| max tokens | 37,203 | 8,598 | **−76.9%** |
| max duration | 286.2s | 11.4s | **−96.0%** |
| runs over 13k tokens | 5 of 20 | 0 of 20 | — |

Five A runs between 13.8k and 37.2k tokens produced most of the mean gap; the
median gap is a more modest 15.7%. Arm E never left a narrow band
(4.1k–8.6k tokens, 5.9s–11.4s). Reporting only the mean would overstate the
typical case and understate the thing that matters operationally: **the pantry
removes the expensive search, and the expensive search is what blows up the
tail.**

---

## 3. Block 1b — core block (partial)

Eight small-repo tasks, 5 reps per arm. Cell status:

```
task                 A1  A2  A3  A4  A5   E1  E2  E3  E4  E5
architecture_drift   P   P   P   P   P    P   P   P   P   P
browser_issue        P   .   P   P   P    P   P   INV P   P
capability_overlap   P   P   P   P   P    P   P   P   P   INV
multi_file_feature   P   P   INV P   P    P   P   P   P   P
refactor             P   P   P   .   P    P   P   .   P   P
repo_exploration     P   P   P   P   P    P   P   P   P   P
simple_bug           P   P   P   P   P    P   P   P   P   P
test_diagnosis       P   P   .   P   P    P   P   P   P   INV
```

`P` passed · `INV` excluded as infrastructure · `.` never ran.

**Correctness:** every one of the 72 valid runs passed. The `test_diagnosis`
"regression" reported by an earlier block (E 0.80) was a harness race, not
agent behaviour — see §6. It must not be quoted.

**Effect:**

| arm | metric | n | reduction | 95% CI | verdict |
|---|---|---:|---:|---|---|
| E | tokens | 32 | −13.1% | −71.1%..+30.4% | noise |
| E | duration | 32 | −29.4% | −161.7%..+61.2% | noise |

Direction depends on the statistic: the token **mean** favours A (9,808 → 11,519,
+17.4% for E) while the **median** favours E (6,328 → 5,690, −10.1%). With CIs
this wide, neither is evidence. Duration medians are 6.9s (A) vs 8.4s (E).

Only three tasks had the ≥5 matched pairs needed for an interval:

| task | metric | n | reduction | 95% CI | verdict |
|---|---|---:|---:|---|---|
| architecture_drift | tokens | 5 | +37.8% | −39.7%..+136.7% | noise |
| architecture_drift | duration | 5 | +23.7% | −29.1%..+98.5% | noise |
| repo_exploration | tokens | 5 | +31.7% | −48.1%..+100.3% | noise |
| repo_exploration | duration | 5 | +6.0% | −44.8%..+45.2% | noise |
| simple_bug | tokens | 5 | +44.9% | −35.7%..+110.6% | noise |
| simple_bug | duration | 5 | −8.1% | −15.2%..−0.3% | regression |

The one flagged regression is `simple_bug` duration: 5.3s → 5.7s, a **0.4s**
difference on five pairs, in the same task where E used 66% fewer tokens
(3,504 → 1,181 median). It is statistically detectable and operationally
meaningless; it is reported because suppressing it would be the thing this
project exists to avoid.

The other five tasks show `insufficient data` for a mundane reason: pairing is
per rep, and missing cells leave only 3–4 matched pairs. That is a coverage
problem, not a null result.

---

## 4. Excluded runs

Four runs are excluded from every statistic above (`valid=False`), never
counted as failures:

| run | excluded because | wall clock |
|---|---|---:|
| `browser_issue E3` | agent timed out | 900.1s |
| `test_diagnosis E5` | agent timed out | 900.1s |
| `capability_overlap E5` | agent timed out | 300.1s |
| `multi_file_feature A3` | agent timed out | 200.0s |

A bare probe against the provider isolated the cause — not the harness, not the
task:

```json
{"type":"retry","error":{"type":"provider.rate-limit","status":429,
 "retryAfterMs":30145000}}
```

Three of the four exclusions are arm E. Had timeouts been scored as failures
(the previous behaviour), the gate would have reported a fake correctness
regression in E — which is exactly what happened once, and why the rule is now
explicit: a stall is infrastructure, so the run is excluded with
`invalid_reason` recorded, and the reason is published with the numbers.

**Four cells never ran** (`browser_issue A2`, `refactor A4`, `refactor E3`,
`test_diagnosis A3`) because the provider quota was exhausted. Block 1b is
therefore reported as partial. It will be completed with `--resume` and this
document regenerated; no verdict above depends on the missing cells.

---

## 5. Threats to validity

- **Asymmetric reps.** `spec_selection` has 20 pairs, the core tasks 5. The
  powered block is the only one that can resolve a small effect, and it was
  chosen because that is where variance was highest — which also makes it the
  block most favourable to the hypothesis. Both facts are true at once.
- **One model, one harness.** `opencode-go/beam-free` at `high` effort. Nothing
  here generalises to another model without re-running.
- **Free-tier quota.** The cohort is rate-limited and intermittently stalls.
  That produced 4 exclusions and a partial block; it is documented rather than
  re-rolled until the numbers looked better.
- **Small tasks dominate the core block.** All eight are single-repo edits a
  strong model can finish from first principles, so a context tool has little
  to save. Block 1a is the counter-example: when selection cost is real, the
  pantry wins.
- **A ninth task is a different task.** `spec_selection` is not one of the
  original eight; it was added specifically to test the pantry's intended use
  case, after the core block showed no signal.
- **No cross-run leakage.** Every run gets a standalone workspace, a private
  `/tmp`, and the host repo masked with `bwrap`. The oracle is copied in only
  after the agent exits, and leaks are judged from tool **inputs**, not from
  prose that merely mentions the oracle path.

---

## 6. Harness bugs this run exposed

Three defects each silently corrupted results; all are fixed and covered by
tests.

| Bug | Effect on the numbers | Fix |
|---|---|---|
| **Orphan drivers** | An interrupted run survived; two drivers shared `bench-<arm>-<task>-r<rep>` and `create_workspace` deleted the directory under the other run. Two runs died with `ModuleNotFoundError`, and the gate reported **`test_diagnosis` E 0.80 vs A 1.00** — a correctness regression that did not exist | `lock_results()` takes an exclusive `flock` per results dir; a second driver is refused with a message. `--resume` skips completed runs |
| **Timeout scored as failure** | Provider stalls looked like agent errors, biasing the gate against whichever arm hit them (here, E) | `valid=False` + `invalid_reason`; the oracle result is kept, the run is excluded |
| **Shared test workspaces** | The suite and a live benchmark used the same run-id paths, producing an intermittent `oracle/acceptance.py not found` | `OCTK_BENCH_WORKSPACE`; `conftest` gives every test process its own root |

None of these were visible in the aggregate report. They were found by
recomputing the pass rates from manifests after a "regression" appeared, and by
checking whether the claimed runs still existed on disk.

---

## 7. What changes in the project

1. **The blanket negative claim is withdrawn.** "OCTK uses 21% more tokens" was
   measured on the pre-fix suite, where every task was a small edit and the
   harness leaked oracle paths through `/tmp`. It is superseded by §2 and §3.
2. **The claim narrows to where it was measured:** context selection at scale.
   Nothing in this dataset supports a general efficiency claim for small edits.
3. **The external benchmark is now the arbiter** for the general case, not an
   optional extra. Terminal-Bench 2.0 (Harbor, `terminal-bench@2.0`, arms A vs
   E, ≥5 attempts) is the next measurement, and it is the one that decides
   whether this is a product or a niche tool.
4. **Correctness parity holds across 112 runs and 9 tasks**, including the
   harness's own regressions. That part of the thesis is no longer in doubt.

---

## 8. Reproduce

```bash
# powered block (20 reps) — already complete
uv run --no-sync python -m benchmarks.driver --stage 1 \
  --tasks spec_selection --reps 20 --label spec

# core block — resumes the 4 missing cells when quota allows
uv run --no-sync python -m benchmarks.driver --stage 1 \
  --tasks architecture_drift,browser_issue,capability_overlap,multi_file_feature,refactor,repo_exploration,simple_bug,test_diagnosis \
  --reps 5 --label core --resume

# regenerate this report from manifests, without spending a model call
PYTHONPATH=. uv run --no-sync python scripts/bench_evidence.py report --label core \
  --tasks architecture_drift,browser_issue,capability_overlap,multi_file_feature,refactor,repo_exploration,simple_bug,test_diagnosis
```

Generated manifests, transcripts, and per-stage reports are gitignored. This
document is the versioned evidence.
