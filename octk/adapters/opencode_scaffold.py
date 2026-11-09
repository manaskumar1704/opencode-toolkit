"""OpenCode-specific scaffolding: config, agents, and the ideate command.

This module is the only place that knows OpenCode's on-disk layout and config
schema. Core modules ask ``octk.adapters`` for neutral names; they never import
this module directly.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ..sentinel import SENTINEL_END, SENTINEL_START

CONFIG_REL = "opencode.json"
AGENTS_DIR = ".opencode/agents"
COMMANDS_DIR = ".opencode/commands"

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

AGENT_NAMES = ["plan", "build", "explore", "verifier"]

AGENT_DEFAULTS: dict[str, dict[str, str]] = {
    "plan": {"mode": "primary", "model": "opencode-go/mimo-v2.6-pro", "effort": "high"},
    "build": {"mode": "primary", "model": "opencode-go/deepseek-v4-pro", "effort": "high"},
    "explore": {
        "mode": "subagent",
        "model": "opencode-go/muse-spark-1.3-contributor",
        "effort": "medium",
    },
    "verifier": {
        "mode": "subagent",
        "model": "opencode-go/deepseek-v4.1-flash",
        "effort": "high",
    },
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

REQUIRED_PERMISSIONS = (
    ("shell", "octk approve *"),
    ("edit", ".toolkit/approvals.json"),
)


def render_agent_md(name: str) -> str:
    """Render a full agent file (frontmatter + sentinel body)."""
    default = AGENT_DEFAULTS[name]
    lines = [
        "---",
        f"description: {AGENT_DESCRIPTIONS[name]}",
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
    lines += ["---", "", SENTINEL_START, AGENT_BODIES[name], SENTINEL_END, ""]
    return "\n".join(lines)


def opencode_json() -> dict[str, Any]:
    """OpenCode V2 config: mcp.servers + permissions rule array."""
    exe = shutil.which("octk-mcp")
    command = [exe] if exe else [sys.executable, "-m", "octk.server"]
    return {
        "mcp": {
            "servers": {
                "octk": {"type": "local", "command": command, "codemode": False},
            }
        },
        "small_model": "opencode-go/deepseek-v4.1-flash",
        "permissions": [
            {"action": "shell", "resource": "octk approve *", "effect": "deny"},
            {"action": "edit", "resource": ".toolkit/approvals.json", "effect": "deny"},
            {"action": "edit", "resource": ".toolkit/metrics.json", "effect": "deny"},
            {"action": "edit", "resource": ".toolkit/specs/roadmap.md", "effect": "ask"},
        ],
    }


def managed_files() -> list[tuple[str, str, str]]:
    """Harness files as ``(relpath, content, write_mode)``.

    ``write_mode`` is ``sentinel`` for files whose body the user may edit, and
    ``plain`` for generated config.
    """
    files: list[tuple[str, str, str]] = [
        (f"{COMMANDS_DIR}/ideate.md", IDEATE_COMMAND_TEMPLATE, "plain"),
    ]
    for name in AGENT_NAMES:
        files.append((f"{AGENTS_DIR}/{name}.md", render_agent_md(name), "sentinel"))
    files.append(
        (CONFIG_REL, json.dumps(opencode_json(), indent=2) + "\n", "plain")
    )
    return files


def permissions_gate(root: Path) -> tuple[str, str]:
    """Return ``(status, detail)`` for the harness permission rules."""
    path = root / CONFIG_REL
    if not path.exists():
        return "warn", f"{CONFIG_REL} missing; run `octk init`"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "warn", f"{CONFIG_REL} is not valid JSON"
    rules = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        return "warn", f"{CONFIG_REL} has no permissions rule list"
    missing = [
        f"{action}:{resource}"
        for action, resource in REQUIRED_PERMISSIONS
        if not any(
            isinstance(rule, dict)
            and rule.get("action") == action
            and rule.get("resource") == resource
            and rule.get("effect") == "deny"
            for rule in rules
        )
    ]
    if missing:
        return "warn", "missing deny rules: " + ", ".join(missing)
    return "pass", "approval gate deny rules are present"
