"""Templates rendered by scaffold.init_repo. String constants only, no logic."""

AGENTS_MD_TEMPLATE = """\
# Project instructions (octk)

Rules, in order:

1. Call {server_name}_glance_pantry before scanning the repo.
2. Lazy-load: {server_name}_equip_spec / {server_name}_equip_skill only when the
   current task needs them; never preload anything.
3. Always-on skills: {{ALWAYS_ON}}. Every other skill loads on demand via
   OpenCode's `skill` tool. {server_name}_equip_skill is ONLY for extra files in
   `.toolkit/skills/` - never duplicate a native `.opencode/skills` skill there.
4. For audits call {server_name}_run_audit_workflow (it enforces
   graph-before-audit).
5. Use MCP {server_name}_debug_inspect and {server_name}_browser_inspect
   instead of grep/print output loops.
6. Never mark a roadmap item done yourself: ask the user to run
   `octk approve "<task>"` in their terminal, then call
   {server_name}_update_roadmap(task, "done").
"""

IDEATE_COMMAND_TEMPLATE = """\
---
description: Interview, blueprint, then scaffold a project plan with octk
---

Run this three-step human-in-the-loop flow. You are the interviewer.

## Step 1 - Interview (one message, then WAIT)

Ask all of these in a single message, then WAIT for the answers:

- What are we building, and for whom?
- Expected user flow, start to end.
- Architecture: high-level design and low-level design.
- Data schema.
- What does "accepted" look like? Testable acceptance criteria and the exact
  acceptance commands that must pass.
- Which Pantry items to equip (skills the user drops into `.toolkit/skills/`)?
- Should any skill be always-on? (Default: none.)

## Step 2 - Blueprint (WAIT for APPROVE)

Summarize the blueprint (architecture, schema, acceptance commands, chosen
specs/skills) and WAIT for the user to type APPROVE. Write no files before
that.

## Step 3 - Scaffold

Populate, in order:

- `AGENTS.md` (via `octk init --force` when rules must be re-rendered)
- `.toolkit/index.md` (Project, Specs, Skills, Commands, Current task)
- `.toolkit/config.json` (always_on_skills ONLY if the user asked)
- `.toolkit/specs/architecture.md` (HLD, LLD, schema)
- `.toolkit/specs/user_flow.md`
- `.toolkit/specs/acceptance.md`
- `.toolkit/specs/roadmap.md` - `- [ ] item` lines; `- [~]` current; `- [x]`
  done (never write `[x]` yourself; only the user can grant it with
  `octk approve "<task>"`).
"""

INDEX_MD_TEMPLATE = """\
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
"""

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
