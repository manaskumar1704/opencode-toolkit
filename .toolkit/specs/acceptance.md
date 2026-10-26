# Acceptance

Primary command: `uv run pytest -q` (must pass with no failures).

Feature checks:

1. Circuit breaker: `tests/test_circuit_breaker.py` proves the second identical
   `debug_inspect` failure appends the bypass text, and success/new task resets.
2. Fast-path: `tests/test_scaffold.py` proves generated `AGENTS.md` contains the
   1-File Fast-Path rule, stays under 28 lines, and renders byte-identically.
3. Cache telemetry: `tests/test_cache_doctor.py` proves
   `octk task end --tokens-cached N` computes `cache_hit_rate`, the report shows
   the percentage in Markdown/JSON, and `octk doctor` flags unstable AGENTS.md
   text or missing deny rules.
4. Lazy external MCPs: `tests/test_external_mcp.py` proves configured servers are
   listed in the pantry, unconfigured names are rejected without spawning, and a
   successful schema load is logged as `kind=load`.
5. Handoff: `tests/test_handoff.py` proves `.toolkit/handoff.md` contains roadmap
   state, git status/diff stat, runtime signal, approvals, and loads through
   `equip_spec("handoff")`.

A task is NOT done until the user runs `octk approve "<task>"` and the agent
calls update_roadmap(task, "done"). Checks are objective pass/fail, never gut
feeling.
