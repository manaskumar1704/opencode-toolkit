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
{SENTINEL_END}
"""

# --- /ideate command (4-Step Elephant-Goldfish HITL flow) -------------------

IDEATE_COMMAND_TEMPLATE = """\
---
description: Interview, stress-test, then scaffold a project plan with octk
---

Run this four-step Elephant-Goldfish human-in-the-loop flow. You are the
interviewer and architect.

## Step 1 - Elephant Discovery Interview (one message, then WAIT)

Ask all of these in a single message, then WAIT for the answers:

- Problem: what are we building, and for whom?
- Expected user flow, start to end.
- Architecture: high-level design (HLD) and low-level design (LLD).
- Data schema.
- Acceptance criteria: what does "accepted" look like? Exact commands that must
  pass.
- Pantry inventory: which skills/specs already exist to reuse (from
  `glance_pantry`)?

## Step 2 - Goldfish Stress-Test via `@verifier`

Spawn `@verifier` with ZERO conversational history. Pass it ONLY the proposed
blueprint summary (architecture, schema, acceptance). It pokes holes in edge
cases, schema gaps, and failure modes. Record its findings.

## Step 3 - HITL Blueprint Gate

Present the blueprint PLUS the resolved Goldfish critique to the user. Ask for
explicit approval before writing any file. Write nothing until approved.

## Step 4 - Artifact Generation

Populate, in order, preserving user text outside `<!-- OCTK:START -->` blocks:

- `AGENTS.md` (via `octk init --force` when rules must be re-rendered)
- `.toolkit/index.md` (Project, Specs, Skills, Commands, Current task)
- `.toolkit/specs/architecture.md` (HLD, LLD, schema)
- `.toolkit/specs/user_flow.md`
- `.toolkit/specs/acceptance.md`
- `.toolkit/specs/roadmap.md` - `- [ ] item` lines; `- [~]` current; `- [x]`
  done (never write `[x]` yourself; only the user can grant it with
  `octk approve "<task>"`).
"""

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

# --- agents -----------------------------------------------------------------

AGENT_NAMES = [
    "plan",
    "build",
    "explore",
    "verifier",
]

AGENT_DEFAULTS: dict[str, dict[str, str]] = {
    "plan": {"mode": "primary", "model": "opencode-go/mimo-v2.6-pro", "effort": "high"},
    "build": {"mode": "primary", "model": "opencode-go/deepseek-v4-pro", "effort": "high"},
    "explore": {"mode": "subagent", "model": "opencode-go/muse-spark-1.3-contributor", "effort": "medium"},
    "verifier": {"mode": "subagent", "model": "opencode-go/deepseek-v4.1-flash", "effort": "high"},
}

AGENT_DESCRIPTIONS: dict[str, str] = {
    "plan": "Deep-context Elephant architect for /ideate and .toolkit/specs/* design.",
    "build": "Primary coding workhorse; lazy-loads octk-mcp; offloads search to @explore and verification to @verifier.",
    "explore": "Fast codebase search, import tracing, and long-file/log summarization (<30-line output).",
    "verifier": "Unified zero-context Goldfish verifier for spec critique and runtime verification.",
}

AGENT_BODIES: dict[str, str] = {
    "plan": (
        "You are the architect. Lead /ideate discovery, weigh architecture and "
        "schema trade-offs, and produce .toolkit/specs blueprints. Stress-test "
        "plans via @verifier before presenting them to the user. Gate on "
        "explicit user approval before writing files."
    ),
    "build": (
        "You are the coding workhorse. Call glance_pantry first, lazy-load specs "
        "and skills on demand, and apply the user's taste skill. Delegate codebase "
        "search and long-file/log summarization to @explore, and runtime "
        "verification to @verifier. Never mark a roadmap item done without HITL "
        "approval."
    ),
    "explore": (
        "You are a fast codebase scout. Find files by pattern, trace imports, and "
        "summarize long files or logs. Keep output under 30 lines. Do not edit files."
    ),
    "verifier": (
        "You are a unified zero-context Goldfish verifier. In /ideate, critique "
        "draft architecture.md and acceptance.md for missing edge cases, schema "
        "gaps, and failure modes. After coding, verify at runtime: equip the "
        "acceptance spec, then use debug_inspect, browser_inspect, "
        "check_spec_drift, and run_audit_workflow. 2-Strike Circuit Breaker Rule: "
        "if you fail the exact same test TWICE in a row, STOP immediately and "
        "return the failure summary to @build rather than looping endlessly."
    ),
}


def render_agent_md(name: str) -> str:
    """Render a full `.opencode/agents/<name>.md` (frontmatter + sentinel body)."""
    default = AGENT_DEFAULTS[name]
    desc = AGENT_DESCRIPTIONS[name]
    body = AGENT_BODIES[name]
    lines = [
        "---",
        f"description: {desc}",
        f"mode: {default['mode']}",
        f"model: {default['model']}#{default['effort']}",
        f"effort: {default['effort']}",
    ]
    if name == "plan":
        lines += [
            "permissions:",
            "  - action: edit",
            "    resource: AGENTS.md",
            "    effect: allow",
            "  - action: edit",
            "    resource: .toolkit/**",
            "    effect: allow",
        ]
    lines += [
        "---",
        "",
        SENTINEL_START,
        body,
        SENTINEL_END,
        "",
    ]
    return "\n".join(lines)


def render_agents_md(server_name: str, always_on: list[str]) -> str:
    """Render AGENTS.md for a server name and always-on skill list."""
    label = ", ".join(always_on) if always_on else "none"
    return AGENTS_MD_TEMPLATE.replace("{server_name}", server_name).replace(
        "{{ALWAYS_ON}}", label
    )
