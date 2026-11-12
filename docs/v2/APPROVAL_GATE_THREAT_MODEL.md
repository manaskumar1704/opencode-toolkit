# Approval Gate — Threat Model

**Scope:** the mechanism that stops a coding agent from marking its own roadmap
items complete.
**Status:** policy-enforced, not a sandbox. This document says exactly what it
does and, more importantly, what it does not do.

---

## 1. What the gate is

```
octk approve "<task>"        # human, real TTY only, time-limited token
octk roadmap set "<task>" done  # agent; refuses without a valid token
```

Three properties make it worth having:

| Property | Mechanism | Where |
|---|---|---|
| **Only a human can mint one** | `octk approve` exits with code 2 when stdin is not a TTY | `octk/cli.py` `cmd_approve` |
| **Spend-once** | The token is marked `consumed_at` the moment it is used | `octk/approvals.py` `consume_approval` |
| **Time-limited** | Default TTL 120 minutes (`approval_ttl_minutes`) | `octk/approvals.py` `_valid` |

The token also binds to the task: `find_valid_approval` only accepts an
approval whose substring appears in the roadmap line being completed.

## 2. What it protects

Roadmap integrity. Without it, an agent that failed a task could write `[x]`
and the project record would be false. With it, a completed item is a fact
some human asserted.

## 3. Threats considered

| # | Threat | Mitigation | Residual risk |
|---|---|---|---|
| T1 | Agent edits `.toolkit/approvals.json` to forge a token | Harness deny rule `edit .toolkit/approvals.json`; file written `0o600` | **Real.** An agent with unrestricted shell access can still write the file. The gate raises the cost of self-approval; it does not prevent it |
| T2 | Agent runs `octk approve` itself | Requires a TTY; no TTY → exit 2 | **Partial.** An agent that allocates a pseudo-terminal (`script`, `socat`) can satisfy the TTY check. The harness deny rule `shell: octk approve *` is the real defence, and it is policy |
| T3 | Token replay — one approval completes several items | Token is consumed on use; TTL bounds its lifetime | Low. A second use of the same token fails |
| T4 | Token minted for the wrong item | Approval binds by substring; `octk roadmap set` refuses ambiguous substrings | **Medium.** Approval scope is a *substring* of the line, so approving a short or common word ("fix", "update") authorises any roadmap line containing it. Approve a distinctive phrase |
| T5 | Half-written approval file breaks the gate | All JSON writes are atomic (temp file, then `os.replace`) | None |
| T6 | Agent marks items done by editing the roadmap file directly | Harness deny rule `edit .toolkit/specs/roadmap.md` is `ask`, not `deny` — the human is prompted | Policy only |

## 4. Explicitly out of scope

- **It is not a sandbox.** An agent with shell access can edit files, run
  commands, and tamper with anything the harness does not deny.
- **It does not protect the metrics.** `.toolkit/metrics.json` is denied to
  the agent by rule, but that is a harness policy, not an OS boundary.
- **It does not stop a human from approving the wrong thing.** A careless
  approval is still a false record.
- **It does not apply to the benchmark harness.** The benchmark runs the agent
  with `--auto` inside a disposable, `bwrap`-masked workspace, deliberately
  outside this gate.

## 5. How to check it

```bash
octk doctor
```

The `permissions_gate` check reports whether the OpenCode deny rules required
by the gate are present:

```
- [pass] permissions_gate: approval gate deny rules are present; ...
```

If a rule is missing, the check warns and names the missing rules, because a
gate whose deny rules were dropped is not a gate.

## 6. Residual risk, stated plainly

The approval gate is a **speed bump with a receipt**, not a lock. Its value is
that self-approval is now a *visible, unusual* act: an approval that appears
without a human at a terminal is a signal worth investigating. Its value is
not that the agent *cannot* cheat. Anyone telling you this tool makes agents
incorruptible is overselling it — see `SECURITY_REVIEW.md` §4 for the full
finding list, including the ones we accepted rather than fixed.
