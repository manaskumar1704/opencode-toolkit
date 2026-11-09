# OCTK v2 — Architecture

**Status:** as implemented (2026-11-09)
**Companion:** `ADR.md` records every deviation from the target in `CODEX_HANDOFF.md` Part B.

---

## 1. Component map

```text
+-------------------------------------------------------------+
|  Harness adapter (OpenCode)                                  |
|  adapters/opencode.py          discovery                     |
|  adapters/opencode_scaffold.py config, agents, permissions   |
+------------------------------+------------------------------+
                               |  raw capability records
+------------------------------v------------------------------+
|  Core (harness-neutral)                                      |
|                                                              |
|  pantry (Context Engine) <--> capabilities (Registry)        |
|         |                          |                         |
|         |                          +--> diagnostics          |
|         |                          +--> metrics/report       |
|         +--> roadmap, approvals, handoff, drift, audit       |
|                                                              |
|  providers/graphify, providers/ponytail  (detection only)    |
+--------------------------------------------------------------+
                               |
                     server.py (8 MCP tools)
                     cli.py    (16 command groups)
```

**Boundary rule:** core modules never import `octk.adapters.*`,
`octk.providers.*`, or a model provider SDK. Enforced by
`tests/test_boundaries.py`.

---

## 2. Data flow

### Discovery (explicit, never automatic)

```text
octk capabilities discover --write
  -> adapters.opencode.discover()
     -> skills, commands, opencode.json MCP, .toolkit specs/skills
     -> providers.graphify/ponytail records
  -> capabilities.record_from_dict()  (validation)
  -> capabilities.sync_discovered()   (preserves manual records)
  -> .toolkit/capabilities/index.json
```

### Retrieval (per turn)

```text
capability_registry(level, query, capability_id)
  -> capabilities.load_registry(root)
     -> user index, project index, local index
     -> merge_scopes (user -> project -> local)
  -> capabilities.render(level)
     -> L0 grouped names (or names + 60-char desc when query set)
     -> L1 JSON metadata
     -> L2 reference path only
```

### Context glance

```text
glance_pantry()
  -> pantry.glance(root)
     -> .toolkit/index.md
     -> registry descriptions (bounded 4 KB head read fallback)
     -> external MCP names from config
     -> handoff pointer
  -> PantryResult(text, raw_chars, pruned_chars)
```

### Diagnostics

```text
debug_inspect(command)
  -> runtime.debugger.run_smart_debugger()
     -> runtime.safety.run_command()  (allowlist, no shell, timeout)
     -> prune_output()                (project frames + signals)
  -> DebugResult.diagnostic(required_signals)
     -> DiagnosticResult(signal_retained, dropped_signals, truncated)
  -> metrics.record_debug_call() + breaker escalation
```

---

## 3. Interfaces

### 3.1 Harness adapter (`adapters/base.py`)

```python
class HarnessAdapter(Protocol):
    id: str
    def detect(self) -> dict[str, Any] | None: ...
    def discover_capabilities(self) -> Iterable[dict[str, Any]]: ...
    def install_hints(self) -> list[str]: ...
```

Contract requirements from B2:

| Requirement | Status |
|---|---|
| Discovery is read-only and idempotent | met |
| Failure returns empty set plus reason | **not met** (ADR-004) |
| Never writes user config | met |
| Output normalised to `CapabilityRecord` before core | **partial** (ADR-003) |
| Second adapter addable without core edits | met |

### 3.2 Capability record (`capabilities.CapabilityRecord`)

Frozen dataclass with 15 fields matching B3. Validation rules:

- `id` matches `^[a-z_]+:[^/\s]+/[^/\s]+$`
- `type` ∈ 8-value enumeration
- `description` ≤140 chars
- `activation` ∈ {enabled, disabled, unknown}
- `provenance` ∈ {discovered, manual, octk_provided}
- `cost` requires `measurement: "measured"`
- `verified_at` ISO date or null

### 3.3 Diagnostics (`diagnostics.DiagnosticResult`)

Frozen dataclass: `kind`, `text`, `raw_chars`, `pruned_chars`,
`required_signals`, `kept_signals`, `truncated`. Derived: `signal_retained`,
`signal_retention`, `dropped_signals`, `savings_pct`.

### 3.4 Metrics store (`metrics.MetricsStore`)

JSON-backed. Schema: `active_task`, `tasks`, `unattributed`, `standing_costs`,
`breaker_events`, `debug_state`.

---

## 4. Persistence

| Path | Scope | Committed |
|---|---|---|
| `.toolkit/config.json` | project | yes |
| `.toolkit/index.md` | project | yes |
| `.toolkit/specs/*.md` | project | yes |
| `.toolkit/skills/*.md` | project | yes |
| `.toolkit/capabilities/index.json` | project | yes |
| `.toolkit/capabilities/local.json` | machine | no (gitignored) |
| `~/.config/octk/capabilities/index.json` | user | n/a |
| `.toolkit/metrics.json` | project | no |
| `.toolkit/approvals.json` | project | no |
| `.toolkit/handoff.md` | project | no |

Resolution order: user → project → local, later wins.

---

## 5. MCP surface (8 tools)

| Tool | Purpose |
|---|---|
| `glance_pantry` | Compact project inventory |
| `capability_registry` | L0/L1/L2 capability retrieval |
| `equip_spec` | Load one spec |
| `equip_skill` | Load one extra skill |
| `check_spec_drift` | Python-AST drift scan |
| `debug_inspect` | Allowlisted run + pruned output |
| `browser_inspect` | Headless Chromium summary |
| `equip_external_mcp` | Lazy external MCP inspection |

Demoted to CLI (T7.1): `run_audit_workflow` → `octk audit`,
`update_roadmap` → `octk roadmap set`.

Schema cost: 2,499 chars, ≈624 tokens at chars/4.

---

## 6. Security boundaries

| Boundary | Implementation |
|---|---|
| Subprocess | `runtime/safety.py`: allowlist, no `shell=True`, timeout |
| Approval | TTY-gated, time-limited, one-use token |
| File protection | `.toolkit/approvals.json`, `.toolkit/metrics.json` deny rules |
| Registry writes | only under `.toolkit/capabilities/` |
| Provider detection | `shutil.which` only; never executes |
| Discovery | read-only; never invokes a capability |
| Breaker | escalation text only; does not widen permissions (tested) |

Instruction precedence (A3.3): platform/security → user task → repo policy →
user skills → OCTK defaults. Security enforcement is separate and cannot be
overridden by a prompt.

---

## 7. Degradation

| Missing component | Behaviour |
|---|---|
| No registry index | empty inventory + manual registration hint |
| No harness detected | discovery returns empty list |
| No Graphify | record `activation: disabled`, state `cold` |
| No Ponytail | no record |
| No Chromium | `browser_inspect` returns an error string |
| No metrics file | store starts empty |

No component requires an external tool to function.

---

## 8. Repository layout

Flat by decision (ADR-009). Boundary packages are `octk/adapters/` and
`octk/providers/`. A `core/` restructure is deferred until a second harness
adapter exists (handoff B5).

---

## 9. Extension points

1. **Second harness:** add `octk/adapters/<harness>.py` implementing the
   protocol; re-export neutral names from `octk/adapters/__init__.py`.
2. **Second provider:** add `octk/providers/<name>.py` with `detect()` and
   `capability_record()`.
3. **New capability type:** extend `CAPABILITY_TYPES` and the discovery adapter.
4. **New diagnostic:** implement `diagnostic()` returning `DiagnosticResult`.
