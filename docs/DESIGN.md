# octk design (docs/DESIGN.md)

octk keeps an AI coding agent's context small, gates roadmap completion behind
human approval, and records honest benchmark metrics. Package: `octk`; CLI:
`octk`; MCP server: `octk-mcp` (FastMCP, stdio).

This document is the **binding rules**: how code in this repository is written,
what the benchmark harness is allowed to assume, and what a number is allowed
to claim. It complements `docs/v2/ARCHITECTURE.md` (what the system does) and
`docs/v2/ADR.md` (why each structural decision was made).

---

## 1. Layers

```
octk/cli.py        octk/server.py      <- only modules that touch cwd / OCTK_ROOT
      |                   |
      +--------+----------+
               |
        logic modules      <- pure-ish: take root: Path, return values
               |
   +-----------+-----------+
   |                       |
octk/runtime/        octk/adapters/  octk/providers/
(shell, pruning)      (harness)       (external tools)
```

| Module | Responsibility |
|---|---|
| `octk/config.py` | `ToolkitPaths(root)`, `DEFAULT_CONFIG`, `load_config`, atomic JSON io |
| `octk/templates.py` | String templates only, no logic |
| `octk/scaffold.py` | `init_repo(root, force)` — idempotent scaffold |
| `octk/sentinel.py` | Stable markers delimiting managed blocks in generated files |
| `octk/approvals.py` | Approval records, TTL validity, atomic consume |
| `octk/roadmap.py` | `parse_roadmap`, `set_status` (the approval gate) |
| `octk/capabilities.py` | `CapabilityRecord`, `DiscoveryResult`, registry normalisation |
| `octk/selector.py` | Heuristic, explainable relevance ranking — every pick and skip carries a reason |
| `octk/pantry.py` | `glance`, `equip_spec`, `equip_skill` |
| `octk/mcp_proxy.py` | Strict configured-name validation, lazy stdio `list_tools` / `call_tool` |
| `octk/diagnostics.py` | Diagnostic result types shared by the runtime tools |
| `octk/drift.py` | Python-AST spec-to-code drift report, capped at 20 items per section |
| `octk/metrics.py` | `MetricsStore`, `approx_tokens`, standing costs, debug streak |
| `octk/report.py` | `build_report`, `build_report_data` |
| `octk/doctor.py` | Prefix-cache, config and approval-gate health checks |
| `octk/handoff.py` | Deterministic resume snapshot in `.toolkit/handoff.md` |
| `octk/cli.py` | argparse CLI; the only place allowed to touch `Path.cwd()` |
| `octk/server.py` | Thin FastMCP wrappers over the 8 public tools |
| `octk/runtime/safety.py` | Allowlisted subprocess runner (no shell, timeout, cwd=root) |
| `octk/runtime/debugger.py` | Output pruner (project frames, signals) + pytest/python routing |
| `octk/runtime/browser.py` | Headless-Chromium visit summarizer |
| `octk/runtime/_trace_wrapper.py` | runpy wrapper printing project frames with locals |
| `octk/adapters/base.py` | Harness interface + `DiscoveryResult` |
| `octk/adapters/opencode.py` | OpenCode discovery adapter |
| `octk/adapters/opencode_scaffold.py` | Managed `AGENTS.md` / `opencode.json` output, permission gate |
| `octk/providers/{graphify,ponytail}.py` | Optional external tool providers |
| `benchmarks/driver.py` | The factorial harness: schedule, execute, gate, report |
| `benchmarks/workspace.py` | Standalone copy, `bwrap` mask, oracle-leak detection |
| `benchmarks/manifest.py` | Run manifest schema and atomic persistence |
| `benchmarks/preflight.py` | Cohort checks the runner refuses to start without |

---

## 2. Conventions (binding)

1. Logic modules take `root: Path` as an argument. Only `cli.py` and `server.py`
   may call `Path.cwd()` or read env var `OCTK_ROOT`.
2. Logic functions are pure: they return values and never print or log metrics.
   `cli.py` / `server.py` callers log metrics.
3. Functions <= 60 lines, one responsibility per module, type hints, one-line
   docstrings.
4. No `shell=True` anywhere. Subprocesses: `shlex.split`, timeout, `cwd=root`,
   and the allowlist applies.
5. Spec/skill names must match `^[A-Za-z0-9_-]+$` (rejects path traversal).
6. Metric kinds: `measured` (raw vs pruned output actually produced),
   `counterfactual` (estimate vs a hypothetical full load), `load` (context
   octk itself delivered; raw == pruned).
7. `approx_tokens = ceil(chars / 4)`, `(chars + 3) // 4`. Token figures are
   always labelled "approx".
8. All JSON writes are atomic (temp file in same dir, then `os.replace`).
   Approval state is written `0o600`.
9. The managed block in `AGENTS.md` stays under 30 lines and contains no
   timestamps, no volatile text, and no live task state — it is a prefix
   cache, and changing it costs tokens on every turn.

### Added in v2

10. **Adapters emit validated `CapabilityRecord` objects** (ADR-003). A
    malformed record is dropped inside the adapter, with a reason, rather than
    passed on to be trusted.
11. **A discovery failure returns an empty list *with a reason*** (ADR-004).
    "Nothing found" and "could not look" are different answers.
12. **The MCP surface is 8 tools** (ADR-002). Anything demoted to the CLI
    (`run_audit_workflow`, `update_roadmap`) still exists; it just does not
    spend schema on every turn.
13. **The selector explains itself.** Every selection and every skip carries a
    reason string. A ranking nobody can interrogate is a guess.

---

## 3. Security rules

1. **The command allowlist matches the invoked path, not its name.** A file or
   symlink called `pytest` in an unexpected directory is not the allowlisted
   `pytest` (S-07).
2. **Every subprocess in the project goes through `runtime/safety.run_command`**,
   including `octk task end --check` (S-05). A second path to `subprocess` is
   a second policy.
3. **`external_mcps` is trusted input.** Its `command` array is executed
   verbatim. Documented in the README, in `DEFAULT_CONFIG`, and in
   `octk doctor`.
4. **The approval gate is policy-enforced, not a sandbox.** Say so wherever it
   is described, and keep
   `docs/v2/APPROVAL_GATE_THREAT_MODEL.md` accurate.
5. **CI fails on a known-vulnerable dependency** (`uv audit`, S-10) and on a
   static scan finding (`scripts/security_scan.py`).
6. `browser_inspect` refuses cloud metadata endpoints (S-02).

---

## 4. Benchmark rules

These exist because the harness is trusted to be wrong quietly. Every one of
them was added after it was not.

1. **Isolation is a standalone copy, not a worktree.** A linked git worktree
   shares `.git`, so the agent walks back to the host project. `bwrap` masks
   the host tree; `/tmp` is private (S-12).
2. **One driver per results directory.** An interrupted driver survives as an
   orphan; two drivers then share `bench-<arm>-<task>-r<rep>` paths and
   corrupt each other's workspaces. `lock_results()` takes an exclusive
   `flock`.
3. **The oracle is copied in only after the agent exits**, and leaks are judged
   from tool **inputs** — a document that *mentions* the oracle is not a leak,
   a command that *reads* it is.
4. **Validity and correctness are separate channels.** A run can be correct and
   invalid. An agent timeout is infrastructure, not a verdict: the run is
   excluded with `valid=False` and an `invalid_reason`, never scored as a
   failure (S-06's cousin).
5. **Reps are per task.** A fixture may declare its own count; the floor is 5;
   `--reps` overrides every task.
6. **Aggregation is per task, not per pair.** The gate resamples tasks and then
   reps within each task. Pair-weighted pooling lets the task with the most
   reps decide the headline — with `spec_selection` at 20 reps that turned a
   −11.6% aggregate into a spurious +6.5%.
7. **Cost is `UNKNOWN` until Stage 1 is measured.** Any later figure is labelled
   as extrapolation, never as a measurement.
8. **A run that never happened is reported as not run**, not as a failure, and
   never quietly dropped from a denominator.

---

## 5. Report honesty rules

- Headline numbers use `measured` records only.
- Counterfactual estimates appear in a separate section labelled
  "estimate, not measured".
- The "Resume line" is generated only from recorded data and only when >= 5
  paired tasks exist; otherwise "Not enough paired tasks (k/5)". If octk was
  worse, the report says so.
- Token-proxy caveats: `chars/4` is a proxy, n small, single model.
- A CI excludes zero **and** clears a minimum effect size. "Not significant" is
  never reported as "no difference", and "significant" is never reported
  without the interval.
- Per-task results are always shown next to an aggregate, because an aggregate
  can hide a strong effect on one task and a null result on eight.

---

## 6. Decisions of record

Structural decisions live in `docs/v2/ADR.md` and are not re-litigated here:

| ADR | Decision |
|---|---|
| 001 | L0 is a grouped name inventory, not a per-record payload |
| 002 | The MCP surface is 8 tools, not the ≤6 target |
| 003 | Adapters emit validated `CapabilityRecord` objects |
| 004 | A discovery failure returns an empty list *with a reason* |
| 005 | `browser_inspect` is feature-flagged via `OCTK_BROWSER`, on by default |
| 006 | `check_spec_drift` declares Python-only coverage in its tool description |
| 007 | The Capability Selector is heuristic and explainable |
| 008 | Model/effort CLI commands are deprecated, not removed |
| 009 | The repository layout stays flat |
| 010 | `available` and `permissions.requires_approval` are not emitted |
