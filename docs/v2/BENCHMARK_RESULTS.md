# Benchmark Results — Stage 1

**Run date:** 2026-11-11
**Design:** 8 tasks × 2 arms × 5 reps = **80 runs**
**Cohort:** OpenCode 2.2.6 · `opencode-go/beam-free` · effort `high`
**Isolation:** standalone workspace under `~/.cache/octk-bench`, `bwrap`,
private `/tmp`
**Gate:** paired bootstrap (5,000 resamples) with a minimum effect size

---

## 1. Verdict

| Claim | Result |
|---|---|
| Correctness | **80 / 80 passed** (A 40/40, E 40/40) |
| Token efficiency | **No measurable signal.** E used **+21.3%** input tokens; 95% CI −46.7%..+0.8% |
| Duration | **Significant regression.** E was **49.8% slower**; 95% CI −106.7%..−2.5% |
| Gate decision | **Do not proceed to Stage 2.** No correctness regression, but no efficiency signal |

The point estimate is worse for OCTK and the confidence interval crosses zero.
A 49.8% slowdown is a real cost, not noise.

## 2. Per-task medians

| Task | A tokens | E tokens | Δ | Read |
|---|---:|---:|---:|---|
| architecture_drift | 6,442 | 8,381 | +30.1% | Worse |
| browser_issue | 3,183 | 3,589 | +12.8% | Worse |
| capability_overlap | 2,999 | 3,443 | +14.8% | Worse |
| multi_file_feature | 18,577 | 28,690 | +54.4% | Worse |
| refactor | 6,296 | 4,673 | **−25.8%** | Better |
| repo_exploration | 8,709 | 9,598 | +10.2% | Worse |
| simple_bug | 5,110 | 3,805 | **−25.5%** | Better |
| test_diagnosis | 22,214 | 24,824 | +11.7% | Worse |

Arm means: A 10,003 tokens / 29.5s · E 12,130 tokens / 44.2s.

## 3. Where the tokens go

Measured from the transcripts:

| Component | Measurement |
|---|---|
| Fixed schema tax | First-step input: A 2,854 → E 3,361 = **+507 tokens/run** |
| Tool calls | A 306 → E 449 (+143). E made **48 OCTK calls** across 40 runs |
| `check_spec_drift` | 56,241 chars over 5 calls before the cap (11k per call) |
| `glance_pantry` | 19,000 chars over 25 calls |
| `equip_spec` | 14,959 chars over 14 calls |

The fixed tax is real but small (~4.7% of A's mean). The dominant cost is
**more tool calls and more steps**, not the schema alone.

## 4. Architecture or implementation?

| Layer | Finding | Evidence |
|---|---|---|
| **Architecture** | A fixed ~500-token MCP tax per run. v1 measured the same floor: bare 6,823 → octk 7,731 = **+908 turn-1 tokens** | First-step deltas; v1 `octk standing` record |
| **Implementation** | `check_spec_drift` dumped 11k chars per call; `glance_pantry` was mandatory and called 25 times; `equip_spec` added 1k chars per call | Tool-call and output measurements |
| **Harness** | `/tmp` exposed pytest artifacts containing oracle copies; the agent spent 22 extra steps hunting them in the pre-fix run | Pre-fix transcript: `find /`, `cat /tmp/pytest-of-.../oracle/acceptance.py` |
| **Benchmark design** | All 8 tasks are small-repo edits. The pantry only pays off when the baseline would otherwise load many specs/skills | No large-context task exists |

**Conclusion:** the fixed overhead is architectural but modest. The gap is
mostly implementation (tool output volume and extra steps) plus a benchmark
suite that cannot exercise the pantry's intended win. The architecture is not
disproven; it is untested at the scale where it matters.

## 5. Validity notes

- A too-broad leak detector flagged 7 runs because the agent grepped our own
  documentation, which mentions `oracle/acceptance.py`. Re-evaluated with the
  corrected detector: **all 80 runs valid**.
- The driver previously overwrote the oracle result when a leak was flagged.
  Fixed: validity and correctness are separate channels.
- The pre-fix Stage 1 run (before the private `/tmp` sandbox) contained one
  genuine oracle read from `/tmp/pytest-of-...`. It is **not** part of this
  dataset.
- Generated manifests and transcripts are not committed; this summary is the
  versioned evidence.

## 6. What this proves and does not prove

**Proves**

- Correctness parity across all 8 task categories, 5 reps each.
- The harness is stable: 80/80 valid, no provider errors, no missing tokens.
- The pantry flow can help: the pre-fix pilot showed −47% on
  `architecture_drift` and −25% on `repo_exploration`.

**Does not prove**

- That OCTK reduces tokens on small tasks. It does not.
- That the pantry helps on a large repository. That case is not in the suite.

## 7. Next

1. Add a large-context task: ~20 specs/skills that a naive baseline must load.
2. Consider a minimal OCTK surface (`glance` + `equip` only) to separate the
   architecture from the 8-tool surface.
3. Re-run Stage 1 only after those changes; Stage 2 remains blocked.
