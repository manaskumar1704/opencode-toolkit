# OCTK v2 — Security Review

**Status:** review opened 2026-11-11. Phase A complete; Phases B–D planned.
**Scanner:** `scripts/security_scan.py` (dependency-free, AST-based)
**Tests:** `tests/test_security.py`, plus the browser and driver regressions
**CI:** the scanner runs on every push (`.github/workflows/ci.yml`)

---

## 1. Scope

In scope:

- `octk/` — every module that executes a process, writes state, or fetches a URL
- `.toolkit/` state — approvals, metrics, config, capability index
- MCP surfaces — the 8 octk tools and the external MCP proxy
- the benchmark driver — it runs an agent with `--auto` in a worktree
- packaging and CI

Out of scope for this pass:

- the security of OpenCode itself, Playwright/Chromium, or the model provider
- multi-tenant or remote deployment (OCTK is a local, single-user tool)
- supply-chain provenance of third-party MCP servers the user configures

## 2. Trust model

| Asset | Why it matters |
|---|---|
| User repository | OCTK can read and, via the agent, write files |
| `.toolkit/approvals.json` | Forging an approval defeats the human gate |
| `.toolkit/metrics.json` | Falsifying measurements defeats the honesty claim |
| Provider credentials | Present in the environment of any spawned process |
| External MCP config | `command` is executed verbatim |
| Benchmark transcripts | May contain prompts, code, and environment details |

Trust boundaries:

1. **User config is trusted.** `opencode.json` and `.toolkit/config.json` are
   written by the user. OCTK validates shape, not intent.
2. **Repository content is semi-trusted.** Skills, task fixtures, and specs are
   read; they must never be executed by discovery.
3. **Agent output is untrusted.** Tool results, tracebacks, and browser
   snapshots are data, never instructions.
4. **Network content is untrusted.** The browser pruner only fetches `http(s)`
   and now refuses cloud-metadata hosts.

## 3. Automated scan

```
$ python scripts/security_scan.py
No findings.
```

The scan covers: shell execution, `shell=True`, `eval`/`exec` on non-literals,
unsafe deserialisation, `yaml.load` without a safe loader, subprocess calls
without a timeout, permissive `chmod`, `tempfile.mktemp`, hardcoded credentials,
unbounded dependencies, and the presence of four mandatory guards
(MCP name validation, browser scheme check, metadata block, approval file mode).

It exits non-zero on any HIGH finding, so CI fails closed.

## 4. Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| S-01 | Medium | `approvals.json` inherited the process umask, so a loose umask could expose approval state | **Fixed** — `atomic_write_json(..., mode=0o600)` |
| S-02 | Medium | `browser_inspect` could fetch cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`) — the classic SSRF-to-credentials path | **Fixed** — `BLOCKED_HOSTS` check before navigation |
| S-03 | Medium | Benchmark task names were joined into worktree and transcript paths without sanitisation | **Fixed** — `safe_id()` in the driver, plus a second guard in `create_worktree` |
| S-04 | Low | `playwright` had no upper bound | **Fixed** — `playwright>=1.49,<2` |
| S-05 | Medium | `octk task end --check "<cmd>"` resolved the executable through `PATH` and applied no allowlist, unlike `runtime/safety.py` | **Fixed** — routed through `runtime/safety.run_command`; no `subprocess.run` left in `cli.py` |
| S-06 | Medium | The benchmark executor runs `opencode run --auto`, auto-approving every action | Accepted for now — disposable worktree, `--yes` required, no network isolation yet |
| S-07 | Low | `safety._allowed` matched the basename and stem, so any path ending in an allowed name passed | **Fixed** — the invoked path is compared, not its name; a symlink named `pytest` in an unexpected directory is rejected |
| S-08 | Low | `external_mcps` config executes arbitrary commands by design | **Documented** — README section, `DEFAULT_CONFIG` comment, and `octk doctor` output all state the config is trusted input |
| S-09 | Low | The approval gate is policy-enforced (OpenCode deny rules), not kernel-enforced | **Documented** — `APPROVAL_GATE_THREAT_MODEL.md`; README links it; `octk doctor` says so |
| S-10 | Low | CI ran no dependency vulnerability check | **Fixed** — CI runs `uv audit`; verified exit 1 on a pinned vulnerable release, exit 0 on a clean tree |
| S-11 | Info | No `shell=True`, `os.system`, `eval`, `exec`, `pickle`, or unsafe `yaml.load` anywhere in `octk/` | Verified |
| S-12 | High | Git worktrees are **not** isolation: they share `.git`, so OpenCode resolved the host project, loaded the host MCP config (arm A still had `glance_pantry`), and the agent read `benchmarks/tasks/*/oracle/acceptance.py` and edited the host repo | **Fixed** — standalone workspace copy, `benchmarks/` excluded, bwrap masks the host `benchmarks/` and `.git` |
| S-13 | Medium | The shared OpenCode background service stays bound to the host project, so a run's arm config (MCP on/off) was not applied | **Fixed** — `opencode --standalone` (flag before the subcommand) |
| S-14 | Medium | A public repository can be cloned from inside a run, exposing the oracles | **Detected** — `oracle_leaks()` marks the run invalid; network isolation is Phase C |

### Residual risk (must be stated, not hidden)

- An agent with shell access that is **not** constrained by the OpenCode deny
  rules can edit `.toolkit/approvals.json`. OCTK's gate raises the cost of
  self-approval; it is not a sandbox. `octk doctor` checks that the deny rules
  are present, and the README says so.
- `--auto` is appropriate for a benchmark and wrong for a user's repository.
  It is only reachable from the benchmark driver.

## 5. Plan of action

### Phase A — Baseline and cheap fixes (complete)

- [x] Build the static scanner and wire it into CI.
- [x] Fix S-01, S-02, S-03, S-04 with regression tests.
- [x] Fix S-12 and S-13 after the smoke test exposed host-project leakage;
      add S-14 detection.
- [x] Record residual risk in this document.
- [x] Add `tests/test_security.py` so fixes cannot silently regress.

### Phase B — Before the first PyPI release ✅ (complete)

| Task | Finding | Acceptance | Status |
|---|---|---|---|
| Route `octk task end --check` through `runtime/safety.run_command` | S-05 | No direct `subprocess.run` in `cli.py`; allowlist applies | ✅ `tests/test_cli.py` asserts a non-allowlisted command never executes |
| Tighten `_allowed` to compare the invoked path, not just the basename | S-07 | A symlink named `pytest` in an unexpected directory is rejected | ✅ `tests/test_safety.py` covers the symlink and the look-alike file |
| Add `uv audit` to CI | S-10 | CI fails on a known-vulnerable dependency | ✅ verified exit 1 on a pinned vulnerable release |
| Document `external_mcps` as trusted input in README and config comments | S-08 | Users see the warning where they configure it | ✅ README, `DEFAULT_CONFIG`, `octk doctor` |
| Publish a threat-model note for the approval gate | S-09 | README links to it; `octk doctor` explains the check | ✅ `APPROVAL_GATE_THREAT_MODEL.md` |

### Phase C — Before the Terminal-Bench 2.0 run

| Task | Why | Acceptance |
|---|---|---|
| Run the benchmark inside a network-isolated container | `--auto` plus network is unnecessary risk | No host network; provider endpoint is the only egress |
| Pass provider credentials through `--ae`, never into a committed file | Transcripts and configs are copied around | `git grep` finds no key material in `benchmarks/results/` |
| Redact transcripts before committing | They can contain repository content | A redaction pass plus a grep check in CI |
| Pin the OpenCode version used in the container | Reproducibility and known-good surface | Version recorded in the pre-registration |

### Phase D — Ongoing

- Scanner runs on every push; HIGH findings block merge.
- Re-run this review when a second harness adapter lands (the trust boundary
  changes).
- Re-run before any change to `approvals.py`, `mcp_proxy.py`, or `browser.py`.

## 6. Manual review checklist

A reviewer should be able to tick every line. Each maps to a file.

**Process execution**

- [ ] Every `subprocess` call passes an argv list, never a string.
- [ ] Every `subprocess` call has a timeout.
- [ ] `shell=True` appears nowhere.
- [ ] `cwd` is pinned to the project root or a disposable worktree.
- [ ] Executables that are policy-gated go through `runtime/safety.py`.

**Approvals**

- [ ] `approvals.json` is written atomically with mode `0o600`.
- [ ] Tokens are single-use and TTL-bound.
- [ ] The roadmap gate refuses when no valid token exists.
- [ ] `octk doctor` verifies the harness deny rules.

**MCP**

- [ ] External server names match `^[A-Za-z0-9_-]+$`.
- [ ] Only servers present in `external_mcps` can be reached.
- [ ] Discovery never invokes a capability.
- [ ] Tool schemas and arguments are not persisted in the registry.

**Browser**

- [ ] Only `http` and `https` are accepted.
- [ ] Metadata and link-local hosts are refused.
- [ ] Page content is summarised, not executed.

**State and paths**

- [ ] Every path segment derived from metadata is sanitised.
- [ ] Atomic writes are used for all JSON state.
- [ ] Temp directories are per-run and removed afterwards.

**Packaging and CI**

- [ ] Runtime dependencies have upper bounds.
- [ ] The scanner runs in CI and fails closed.
- [ ] No credential is committed or printed.

## 7. Sign-off

| Gate | Owner | State |
|---|---|---|
| Phase A complete, no HIGH findings | automated | ✅ 2026-11-11 |
| Phase B complete | maintainer | ☑ |
| Phase C complete | maintainer | ☐ |
| PyPI release approved | maintainer | ☐ |
