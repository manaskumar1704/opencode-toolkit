# Roadmap

Every line stays `- [ ]` until a **human** approves it:

```bash
octk approve "<task>"          # real terminal (TTY) only
octk roadmap set "<task>" done # the agent performs this, consuming the token
```

The agent cannot approve its own work — that is the point of the gate. Use a
distinctive phrase from the line; approvals match on substring.

## Completed — waiting on your approval

- [ ] Registry: L0/L1/L2 capability inventory with normalised records
- [ ] Selector: explainable relevance ranking for capabilities
- [ ] Pantry: glance_pantry, equip_spec, equip_skill lazy loading
- [ ] Approval gate: spend-once, time-limited tokens behind a TTY
- [ ] Diagnostics: debug_inspect, browser_inspect, check_spec_drift
- [ ] Telemetry: every number tagged measured, counterfactual, or load
- [ ] Benchmark harness: standalone workspace, bwrap, hidden oracle, per-task reps
- [ ] Stage 1 executed: 112 valid runs, 112 of 112 correct
- [ ] Large-context result: spec_selection at 20 reps, 38.5 percent fewer tokens
- [ ] Security Phase B: S-05, S-07 and S-10 fixed, S-08 and S-09 documented
- [ ] Approval-gate threat model published
- [ ] DESIGN.md rewritten for v2 with binding benchmark and security rules

## Open

- [ ] Stage 1 core cells: 4 runs still missing, waiting on provider quota
- [ ] Terminal-Bench 2.0 adapter: Harbor, dataset terminal-bench 2.0, arms A vs E
- [ ] Release: version bump, PyPI publish, uvx packaging
- [ ] Second harness adapter: Codex, to prove the boundary is really a boundary
