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
