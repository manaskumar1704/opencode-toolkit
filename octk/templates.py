"""Templates rendered by scaffold.init_repo. String constants only, no logic."""

from __future__ import annotations

from .sentinel import SENTINEL_END, SENTINEL_START

# --- AGENTS.md (sentinel-wrapped; <30 lines) -------------------------------

AGENTS_MD_TEMPLATE = f"""\
{SENTINEL_START}
# Project instructions (octk)

Rules, in order:

1. Always apply the user's `taste` skill rules.
2. Read `.toolkit/index.md` first ({{server_name}}_glance_pantry); lazy-load
   `.toolkit/specs/*` / `.toolkit/skills/*` on demand ({{server_name}}_equip_spec /
   {{server_name}}_equip_skill); never preload. Always-on skills: {{{{ALWAYS_ON}}}}.
3. Delegate by shape: codebase search, import tracing, and long-file/log
   summaries -> `@explore`; zero-context spec critique and runtime verification
   ({{server_name}}_debug_inspect, {{server_name}}_browser_inspect,
   {{server_name}}_check_spec_drift, {{server_name}}_run_audit_workflow) ->
   `@verifier`.
4. Never mark a roadmap item `[x]` yourself: pass verification first, then ask the
   user to run `octk approve "<task>"` and call
   {{server_name}}_update_roadmap(task, "done").
5. Fast-Path (1-File Trivial Edits): if the user prompt explicitly names a single
   target file and a self-contained 1-line/small fix that does not alter
   architecture or roadmap state, skip {{server_name}}_glance_pantry() /
   {{server_name}}_equip_spec() and apply the edit directly.
{SENTINEL_END}
"""

# --- /ideate command (4-Step Elephant-Goldfish HITL flow) -------------------

# --- .toolkit/index.md (sentinel-wrapped) -----------------------------------

INDEX_MD_TEMPLATE = f"""\
{SENTINEL_START}
**Current task:** none

## Project

Describe the project in one line.

## Specs

- architecture - HLD, LLD, data schema
- user_flow - expected user journey
- acceptance - testable acceptance criteria and commands
- roadmap - task states (`- [ ]`, `- [~]`, `- [x]`)

## Skills

(none yet - drop `.md` files into `.toolkit/skills/`)

## Commands

- /ideate - interview, blueprint, scaffold
- octk approve "<task>" - grant a one-time completion approval (human only)
- octk task start / octk task end - record a task run
- octk report - build the metrics report
- octk doctor - check prefix-cache and approval-gate integrity
- octk handoff - snapshot resume state for /clear
{SENTINEL_END}
"""

# --- spec templates ---------------------------------------------------------

ARCH_MD_TEMPLATE = """\
# Architecture (HLD)

Fill in: components, boundaries, tech choices.

## LLD

Fill in: modules, key functions, data flow.

## Schema

Fill in: tables/models/fields.
"""

FLOW_MD_TEMPLATE = """\
# User flow

Fill in: step-by-step user journey from entry point to result.
"""

ACCEPTANCE_MD_TEMPLATE = """\
# Acceptance

Fill in: for each feature, the command that must pass, e.g. `pytest -q tests/`.
A task is NOT done until the user runs `octk approve "<task>"` and the agent
calls update_roadmap(task, "done"). Checks gold objective pass/fail, never
gut feeling.
"""

ROADMAP_MD_TEMPLATE = """\
# Roadmap

- [ ] item
"""

def render_agents_md(server_name: str, always_on: list[str]) -> str:
    """Render AGENTS.md for a server name and always-on skill list."""
    label = ", ".join(always_on) if always_on else "none"
    return AGENTS_MD_TEMPLATE.replace("{server_name}", server_name).replace(
        "{{ALWAYS_ON}}", label
    )
