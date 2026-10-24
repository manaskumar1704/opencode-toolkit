# Project instructions (octk)

Rules, in order:

1. Call octk_glance_pantry before scanning the repo.
2. Lazy-load: octk_equip_spec / octk_equip_skill only when the
   current task needs them; never preload anything.
3. Always-on skills: none. Every other skill loads on demand via
   OpenCode's `skill` tool. octk_equip_skill is ONLY for extra files in
   `.toolkit/skills/` - never duplicate a native `.opencode/skills` skill there.
4. For audits call octk_run_audit_workflow (it enforces
   graph-before-audit).
5. Use MCP octk_debug_inspect and octk_browser_inspect
   instead of grep/print output loops.
6. Never mark a roadmap item done yourself: ask the user to run
   `octk approve "<task>"` in their terminal, then call
   octk_update_roadmap(task, "done").
