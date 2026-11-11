"""Factorial benchmark driver — the thing that actually runs the eight arms.

Handoff D3 specifies 8 arms x 8 categories x 5 reps = 320 runs, executed in
three staged gates. Stage 1 (A, E) is the cheapest test of the core thesis; the
stop rule protects the budget when correctness regresses.

Rules encoded here:

- randomised run order, seeded and recorded, so order effects are not
  confounded with arm identity;
- every run gets a fresh git worktree (D5 isolation) and is thrown away after;
- the acceptance oracle lives outside the worktree and is copied in only after
  the agent has finished, so the agent cannot read it;
- a missing or malformed field marks the run INVALID rather than silently
  defaulting (D7);
- cost is ``UNKNOWN`` until Stage 1 has been measured. No estimates before
  that, and any later projection is labelled as extrapolation (D3).
"""

from __future__ import annotations

import json
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from benchmarks.manifest import RunManifest, hash_text, now_iso, save_manifest
from benchmarks.preflight import EFFORT_REQUIRED, MODEL_ID, run_preflight
from benchmarks.runner import (
    RESULTS_DIR,
    TASKS_DIR,
    create_worktree,
    list_tasks,
    remove_worktree,
)

ARMS = ("A", "B", "C", "D", "E", "F", "G", "H")
MIN_REPS = 5
DEFAULT_REPS = 5
DEFAULT_SEED = 20261109
DEFAULT_TIMEOUT_S = 1800

# Handoff D3 staged gates. Stage N is cumulative: stage 2 re-runs stage 1 arms.
STAGE_ARMS: dict[int, tuple[str, ...]] = {
    1: ("A", "E"),
    2: ("A", "B", "C", "E"),
    3: ARMS,
}

# Which arm is the no-OCTK baseline used by the gate comparison.
BASELINE_ARM = "A"


# -- arms ------------------------------------------------------------------


def safe_id(value: str) -> str:
    """Reduce a task/arm name to one filesystem-safe path segment.

    Task metadata is repo-controlled, but a benchmark driver that joins it into
    paths must not trust it: ``../../etc`` is one bad fixture away.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return cleaned or "run"


def arm_flags(arm: str) -> dict[str, bool]:
    """Return the on/off flags for an arm (handoff D3 table)."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm!r}")
    return {
        "octk": arm in ("E", "F", "G", "H"),
        "ponytail": arm in ("B", "D", "F", "H"),
        "graphify": arm in ("C", "D", "G", "H"),
    }


def stage_arms(stage: int) -> tuple[str, ...]:
    if stage not in STAGE_ARMS:
        raise ValueError(f"unknown stage: {stage!r} (expected 1, 2, or 3)")
    return STAGE_ARMS[stage]


# -- schedule --------------------------------------------------------------


@dataclass(frozen=True)
class RunSpec:
    """One scheduled run. ``order`` is its position in the randomised queue."""

    arm: str
    task: str
    category: str
    task_dir: str
    rep: int
    seed: int
    order: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_schedule(
    arms: Iterable[str],
    tasks: Sequence[dict[str, Any]],
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
) -> list[RunSpec]:
    """Build a seeded, randomised run queue.

    The full cross-product is shuffled once; ``order`` is then assigned 1..N.
    Same inputs + same seed always produce the same queue.
    """
    if reps < MIN_REPS:
        raise ValueError(f"reps must be >= {MIN_REPS} (handoff D3); got {reps}")
    if not tasks:
        raise ValueError("no tasks supplied")

    combos: list[tuple[str, dict[str, Any], int]] = [
        (arm, task, rep)
        for arm in sorted(arms)
        for task in tasks
        for rep in range(1, reps + 1)
    ]
    random.Random(seed).shuffle(combos)

    return [
        RunSpec(
            arm=arm,
            task=str(task["name"]),
            category=str(task.get("category", "unknown")),
            task_dir=str(task.get("path", "")),
            rep=rep,
            seed=seed,
            order=index,
        )
        for index, (arm, task, rep) in enumerate(combos, start=1)
    ]


# -- per-arm worktree configuration ---------------------------------------


def _load_opencode_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _mcp_servers(config: dict[str, Any]) -> dict[str, Any]:
    """Return the mutable server mapping, supporting both config shapes."""
    mcp = config.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        mcp = {}
        config["mcp"] = mcp
    servers = mcp.setdefault("servers", {})
    if not isinstance(servers, dict):
        servers = {}
        mcp["servers"] = servers
    return servers


def apply_arm(worktree: Path, arm: str) -> dict[str, Any]:
    """Configure one throwaway worktree for an arm. Returns what changed.

    Only ever called on a disposable git worktree, never on the user's tree.
    """
    flags = arm_flags(arm)
    changed: list[str] = []

    config_path = worktree / "opencode.json"
    config = _load_opencode_json(config_path)
    servers = _mcp_servers(config)

    if flags["octk"]:
        if "octk" not in servers:
            servers["octk"] = {
                "type": "local",
                "command": ["octk-mcp"],
                "codemode": False,
            }
            changed.append("enabled octk MCP server")
    elif "octk" in servers:
        servers.pop("octk")
        changed.append("disabled octk MCP server")

    if not flags["graphify"]:
        for key in [k for k in servers if "graphify" in k.casefold()]:
            servers.pop(key)
            changed.append(f"disabled graphify server {key!r}")

    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    if not flags["ponytail"]:
        for pattern in (
            ".opencode/skills/ponytail*",
            ".opencode/plugins/ponytail*",
            ".opencode/plugin/ponytail*",
        ):
            for path in sorted(worktree.glob(pattern)):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                changed.append(f"disabled ponytail path {path.relative_to(worktree)}")

    return {"arm": arm, "flags": flags, "changed": changed}


# -- execution -------------------------------------------------------------


@dataclass
class AgentResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_s: float = 0.0
    tokens_input: int | None = None
    tokens_output: int | None = None
    provider_errors: list[str] = field(default_factory=list)
    rate_limit_log: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# executor(spec, worktree, prompt, timeout_s) -> AgentResult
Executor = Callable[[RunSpec, Path, str, int], AgentResult]


def _walk(node: Any) -> Iterable[Any]:
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def extract_token_usage(text: str) -> tuple[int | None, int | None]:
    """Return (input, output) tokens from the last OpenCode JSON event.

    OpenCode's JSON format is not a stable contract, so this is deliberately
    tolerant. When nothing is found the answer is ``(None, None)`` — unknown,
    never zero.
    """
    best: tuple[int | None, int | None] = (None, None)
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for node in _walk(event):
            if not isinstance(node, dict):
                continue
            tokens = node.get("tokens")
            if not isinstance(tokens, dict):
                continue
            tokens_in = tokens.get("input")
            tokens_out = tokens.get("output")
            if isinstance(tokens_in, int) and isinstance(tokens_out, int):
                best = (tokens_in, tokens_out)
    return best


def opencode_executor(
    spec: RunSpec,
    worktree: Path,
    prompt: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> AgentResult:
    """Run the real agent in the worktree. Confined to a disposable checkout."""
    command = [
        "opencode",
        "run",
        "--model",
        MODEL_ID,
        "--agent",
        "build",
        "--format",
        "json",
        "--auto",
        prompt,
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=worktree,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return AgentResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=-1,
            duration_s=time.monotonic() - started,
            error=f"agent timed out after {timeout_s}s",
        )
    except FileNotFoundError as exc:
        return AgentResult(
            exit_code=127,
            duration_s=time.monotonic() - started,
            error=f"opencode binary not found: {exc}",
        )

    tokens_in, tokens_out = extract_token_usage(proc.stdout)
    return AgentResult(
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        exit_code=proc.returncode,
        duration_s=time.monotonic() - started,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        provider_errors=[proc.stderr.strip()] if proc.returncode != 0 and proc.stderr else [],
    )


def run_oracle(
    worktree: Path,
    task_dir: Path,
    python_executable: str | None = None,
    timeout_s: int = 600,
) -> tuple[bool, str]:
    """Copy the hidden oracle in and run it. The agent never sees this file."""
    source = task_dir / "oracle" / "acceptance.py"
    if not source.is_file():
        return False, f"oracle missing: {source}"
    destination = worktree / "oracle"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, destination / "acceptance.py")
    python = python_executable or sys.executable
    try:
        proc = subprocess.run(
            [python, "-m", "pytest", "oracle/acceptance.py", "-q"],
            cwd=worktree,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"oracle timed out after {timeout_s}s"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output


def _apply_setup_patch(worktree: Path, task_dir: Path) -> str | None:
    patch = task_dir / "setup.patch"
    if not patch.is_file():
        return f"setup patch missing: {patch}"
    proc = subprocess.run(
        ["git", "apply", str(patch)],
        cwd=worktree,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if proc.returncode != 0:
        return f"git apply failed: {(proc.stderr or proc.stdout).strip()}"
    return None


def _detect_providers(worktree: Path) -> dict[str, Any]:
    ponytail_available = any(
        worktree.glob(".opencode/skills/ponytail*")
    ) or any(worktree.glob(".opencode/plugins/ponytail*"))
    config = _load_opencode_json(worktree / "opencode.json")
    graphify_available = any(
        "graphify" in key.casefold() for key in _mcp_servers(config)
    ) or shutil.which("graphify") is not None
    return {
        "ponytail_available": ponytail_available,
        "graphify_available": graphify_available,
        "graphify_state": "cold" if graphify_available else None,
    }


def _write_transcript(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event, default=str) + "\n" for event in events),
        encoding="utf-8",
    )


@dataclass
class RunOutcome:
    spec: RunSpec
    manifest: RunManifest
    manifest_path: str
    passed: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "manifest": self.manifest.to_dict(),
            "manifest_path": self.manifest_path,
            "passed": self.passed,
            "error": self.error,
        }


def execute_run(
    spec: RunSpec,
    repo: Path,
    *,
    executor: Executor | None = None,
    results_dir: Path | None = None,
    python_executable: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    opencode_version: str = "",
    keep_worktree: bool = False,
) -> RunOutcome:
    """Execute one scheduled run end to end and persist its manifest."""
    executor = executor or opencode_executor
    results = results_dir or RESULTS_DIR
    task_dir = Path(spec.task_dir)
    run_id = f"bench-{safe_id(spec.arm)}-{safe_id(spec.task)}-r{spec.rep}"
    transcript_path = results / "transcripts" / f"{run_id}.jsonl"
    manifest_path = results / "manifests" / f"{run_id}.json"

    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    prompt = ""
    try:
        prompt = str(json.loads((task_dir / "task.json").read_text(encoding="utf-8"))["prompt"])
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        prompt = ""
        prompt_error = f"task prompt unreadable: {exc}"
    else:
        prompt_error = None

    try:
        worktree = create_worktree(repo, run_id)
    except RuntimeError as exc:
        events = [
            {"event": "start", "spec": spec.to_dict(), "at": now_iso()},
            {"event": "error", "error": str(exc), "at": now_iso()},
        ]
        _write_transcript(transcript_path, events)
        manifest = RunManifest(
            arm=spec.arm,
            task=spec.task,
            task_category=spec.category,
            base_commit=base_commit,
            opencode_version=opencode_version,
            model_id=MODEL_ID,
            effort=EFFORT_REQUIRED,
            randomization_seed=spec.seed,
            run_order=spec.order,
            isolation_verified=False,
            transcript_path=str(transcript_path),
            graphify_state=None,
            ponytail_available=False,
            graphify_available=False,
            correctness={"acceptance_passed": False, "error": str(exc)},
            started_at=now_iso(),
            ended_at=now_iso(),
        )
        save_manifest(manifest_path, manifest)
        return RunOutcome(spec, manifest, str(manifest_path), False, str(exc))

    events = [
        {"event": "start", "spec": spec.to_dict(), "at": now_iso(), "worktree": str(worktree)}
    ]
    error = prompt_error
    agent = AgentResult()
    manifest = RunManifest()
    passed = False

    try:
        if error is None:
            error = _apply_setup_patch(worktree, task_dir)
        if error is None:
            arm_state = apply_arm(worktree, spec.arm)
            events.append({"event": "arm", **arm_state})

        if error is None:
            agent = executor(spec, worktree, prompt, timeout_s)
            events.append(
                {
                    "event": "agent",
                    "exit_code": agent.exit_code,
                    "duration_s": agent.duration_s,
                    "tokens_input": agent.tokens_input,
                    "tokens_output": agent.tokens_output,
                    "error": agent.error,
                }
            )
            if agent.stdout:
                events.append({"event": "agent_stdout", "data": agent.stdout})
            if agent.stderr:
                events.append({"event": "agent_stderr", "data": agent.stderr})
            if agent.error:
                error = agent.error

        if error is None:
            passed, oracle_output = run_oracle(
                worktree, task_dir, python_executable=python_executable
            )
        else:
            passed, oracle_output = False, ""

        events.append({"event": "oracle", "passed": passed, "output": oracle_output})
        events.append({"event": "end", "at": now_iso()})
        _write_transcript(transcript_path, events)

        acceptance_path = task_dir / "oracle" / "acceptance.py"
        acceptance_text = (
            acceptance_path.read_text(encoding="utf-8") if acceptance_path.is_file() else ""
        )
        providers = _detect_providers(worktree)

        manifest = RunManifest(
            arm=spec.arm,
            task=spec.task,
            task_category=spec.category,
            base_commit=base_commit,
            opencode_version=opencode_version,
            model_id=MODEL_ID,
            effort=EFFORT_REQUIRED,
            task_prompt_hash=hash_text(prompt),
            acceptance_test_hash=hash_text(acceptance_text),
            randomization_seed=spec.seed,
            run_order=spec.order,
            isolation_verified=True,
            transcript_path=str(transcript_path),
            ponytail_version=None,
            graphify_version=None,
            graphify_state=providers["graphify_state"],
            ponytail_available=providers["ponytail_available"],
            graphify_available=providers["graphify_available"],
            correctness={
                "acceptance_passed": passed,
                "oracle_exit_code": 0 if passed else 1,
                "agent_exit_code": agent.exit_code,
                "oracle_output": oracle_output[-4000:],
            },
            rate_limit_log=list(agent.rate_limit_log),
            provider_errors=list(agent.provider_errors),
            started_at=now_iso(),
            ended_at=now_iso(),
            duration_s=agent.duration_s,
            tokens_input=agent.tokens_input,
            tokens_output=agent.tokens_output,
            wall_clock_s=agent.duration_s,
            environment_manifest={
                "worktree": str(worktree),
                "arm_flags": arm_flags(spec.arm),
                "python": python_executable or sys.executable,
                "model_id": MODEL_ID,
                "effort": EFFORT_REQUIRED,
            },
        )
        save_manifest(manifest_path, manifest)
    finally:
        if not keep_worktree:
            remove_worktree(repo, worktree)

    if error is not None and not transcript_path.exists():
        _write_transcript(
            transcript_path, events + [{"event": "error", "error": error, "at": now_iso()}]
        )

    return RunOutcome(
        spec=spec,
        manifest=manifest,
        manifest_path=str(manifest_path),
        passed=passed,
        error=error,
    )


# -- gates -----------------------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    stage: int
    proceed: bool
    blocking: bool
    reason: str
    per_task: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pass_rates(outcomes: Sequence[RunOutcome]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, list[bool]]] = {}
    for outcome in outcomes:
        totals.setdefault(outcome.spec.task, {}).setdefault(outcome.spec.arm, []).append(
            outcome.passed
        )
    return {
        task: {arm: sum(values) / len(values) for arm, values in arms.items()}
        for task, arms in totals.items()
    }


def _median_tokens(outcomes: Sequence[RunOutcome], arm: str) -> float | None:
    values = [
        outcome.manifest.tokens_input
        for outcome in outcomes
        if outcome.spec.arm == arm and outcome.manifest.tokens_input is not None
    ]
    return statistics.median(values) if values else None


def _median_duration(outcomes: Sequence[RunOutcome], arm: str) -> float | None:
    values = [
        outcome.manifest.duration_s
        for outcome in outcomes
        if outcome.spec.arm == arm and outcome.manifest.duration_s is not None
    ]
    return statistics.median(values) if values else None


def evaluate_gate(stage: int, outcomes: Sequence[RunOutcome]) -> GateDecision:
    """Apply the handoff D3 gate for one stage.

    Stage 1: proceed only when OCTK shows no correctness regression AND a
    measurable efficiency signal. A regression is blocking (stop and fix).
    Stage 2: same correctness rule against the baseline, and at least one
    external tool must show an independent effect worth testing interactions.
    Stage 3: terminal stage; nothing to gate.
    """
    if stage not in STAGE_ARMS:
        raise ValueError(f"unknown stage: {stage!r}")

    per_task = _pass_rates(outcomes)
    if stage == 3:
        return GateDecision(3, True, False, "final stage; no further gate", per_task)

    if not per_task:
        return GateDecision(stage, False, False, "no runs recorded", per_task)

    candidates = [arm for arm in stage_arms(stage) if arm != BASELINE_ARM]
    # Stage 2 asks whether the *external* tools add an independent effect;
    # OCTK's own arm was already gated in Stage 1.
    signal_arms = (
        candidates
        if stage == 1
        else [arm for arm in candidates if not arm_flags(arm)["octk"]]
    )
    regressions: list[str] = []
    for task, arms in sorted(per_task.items()):
        baseline = arms.get(BASELINE_ARM)
        if baseline is None:
            continue
        for arm in candidates:
            value = arms.get(arm)
            if value is not None and value < baseline:
                regressions.append(
                    f"{task}: arm {arm} {value:.2f} < baseline {baseline:.2f}"
                )
    if regressions:
        return GateDecision(
            stage,
            False,
            True,
            "correctness regression: " + "; ".join(regressions),
            per_task,
        )

    baseline_tokens = _median_tokens(outcomes, BASELINE_ARM)
    baseline_duration = _median_duration(outcomes, BASELINE_ARM)
    signals: list[str] = []
    for arm in signal_arms:
        tokens = _median_tokens(outcomes, arm)
        duration = _median_duration(outcomes, arm)
        if tokens is not None and baseline_tokens is not None and tokens < baseline_tokens:
            signals.append(f"arm {arm}: {baseline_tokens - tokens:.0f} fewer input tokens")
        if (
            duration is not None
            and baseline_duration is not None
            and duration < baseline_duration
        ):
            signals.append(f"arm {arm}: {baseline_duration - duration:.1f}s faster")

    if stage == 1:
        if not signals:
            return GateDecision(
                1,
                False,
                False,
                "no measurable efficiency signal in Stage 1; do not spend on later stages",
                per_task,
            )
        return GateDecision(
            1, True, False, "correctness non-negative; " + "; ".join(signals), per_task
        )

    if not signals:
        return GateDecision(
            2,
            False,
            False,
            "external tools show no independent effect; interactions not worth testing",
            per_task,
        )
    return GateDecision(
        2,
        True,
        False,
        "external tools show an independent effect; " + "; ".join(signals),
        per_task,
    )


# -- cost honesty ----------------------------------------------------------


def cost_projection(
    outcomes: Sequence[RunOutcome],
    *,
    reps: int = DEFAULT_REPS,
    n_tasks: int = 8,
) -> dict[str, Any]:
    """Measured Stage 1 cost, or UNKNOWN. Extrapolation is labelled as such."""
    stage1 = [o for o in outcomes if o.spec.arm in stage_arms(1)]
    measured = [
        o for o in stage1 if o.manifest.tokens_input is not None and o.manifest.duration_s
    ]
    if not measured:
        return {
            "status": "UNKNOWN",
            "reason": "no measured Stage 1 runs with token and duration data",
            "stage1_runs": len(stage1),
        }

    mean_tokens = statistics.mean(o.manifest.tokens_input or 0 for o in measured)
    mean_duration = statistics.mean(o.manifest.duration_s or 0.0 for o in measured)
    remaining_stage2 = 2 * n_tasks * reps
    remaining_stage3 = 4 * n_tasks * reps
    return {
        "status": "MEASURED",
        "stage1_runs": len(stage1),
        "measured_runs": len(measured),
        "mean_tokens_input": mean_tokens,
        "mean_duration_s": mean_duration,
        "projection": {
            "label": "extrapolation from measured Stage 1 mean; not a measurement",
            "stage2_remaining_runs": remaining_stage2,
            "stage3_remaining_runs": remaining_stage3,
            "stage2_remaining_tokens_input": mean_tokens * remaining_stage2,
            "stage3_remaining_tokens_input": mean_tokens * remaining_stage3,
        },
    }


# -- stage / suite orchestration -------------------------------------------


@dataclass
class StageReport:
    stage: int
    outcomes: list[RunOutcome]
    gate: GateDecision
    cost: dict[str, Any]
    results_dir: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "runs": len(self.outcomes),
            "passed": sum(1 for o in self.outcomes if o.passed),
            "gate": self.gate.to_dict(),
            "cost": self.cost,
            "results_dir": self.results_dir,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


def run_stage(
    stage: int,
    repo: Path,
    *,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
    executor: Executor | None = None,
    results_dir: Path | None = None,
    python_executable: str | None = None,
    tasks: Sequence[dict[str, Any]] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    preflight: bool = True,
    progress: Callable[[RunOutcome, int, int], None] | None = None,
) -> StageReport:
    """Run one stage: preflight, schedule, execute, gate, persist."""
    results = results_dir or RESULTS_DIR
    if preflight:
        outcome = run_preflight(repo)
        if not outcome.ok:
            raise RuntimeError(
                "pre-flight failed:\n" + "\n".join(f"  - {e}" for e in outcome.errors)
            )
        opencode_version = outcome.opencode_version
    else:
        opencode_version = "unverified"

    task_list = list(tasks) if tasks is not None else list_tasks()
    schedule = build_schedule(stage_arms(stage), task_list, reps=reps, seed=seed)

    outcomes: list[RunOutcome] = []
    for index, spec in enumerate(schedule, start=1):
        outcome = execute_run(
            spec,
            repo,
            executor=executor,
            results_dir=results,
            python_executable=python_executable,
            timeout_s=timeout_s,
            opencode_version=opencode_version,
        )
        outcomes.append(outcome)
        if progress is not None:
            progress(outcome, index, len(schedule))

    gate = evaluate_gate(stage, outcomes)
    cost = cost_projection(outcomes, reps=reps, n_tasks=len(task_list))
    report = StageReport(
        stage=stage,
        outcomes=outcomes,
        gate=gate,
        cost=cost,
        results_dir=str(results),
    )

    results.mkdir(parents=True, exist_ok=True)
    (results / f"stage-{stage}.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    (results / f"stage-{stage}.md").write_text(render_stage_report(report), encoding="utf-8")
    return report


def run_all_stages(
    repo: Path,
    *,
    start_stage: int = 1,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
    executor: Executor | None = None,
    results_dir: Path | None = None,
    python_executable: str | None = None,
    tasks: Sequence[dict[str, Any]] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    preflight: bool = True,
    progress: Callable[[RunOutcome, int, int], None] | None = None,
) -> list[StageReport]:
    """Run stages in order, stopping on a blocking correctness regression."""
    reports: list[StageReport] = []
    for stage in range(start_stage, 4):
        report = run_stage(
            stage,
            repo,
            reps=reps,
            seed=seed,
            executor=executor,
            results_dir=results_dir,
            python_executable=python_executable,
            tasks=tasks,
            timeout_s=timeout_s,
            preflight=preflight,
            progress=progress,
        )
        reports.append(report)
        if not report.gate.proceed:
            break
    return reports


def render_stage_report(report: StageReport) -> str:
    lines = [
        f"# Benchmark Stage {report.stage}",
        "",
        f"Runs: {len(report.outcomes)}  "
        f"Passed: {sum(1 for o in report.outcomes if o.passed)}",
        "",
        "## Gate",
        "",
        f"- Proceed: **{report.gate.proceed}**",
        f"- Blocking: **{report.gate.blocking}**",
        f"- Reason: {report.gate.reason}",
        "",
        "## Pass rate by task and arm",
        "",
    ]
    arms = sorted({arm for row in report.gate.per_task.values() for arm in row})
    lines.append("| task | " + " | ".join(arms) + " |")
    lines.append("|---|" + "---|" * len(arms))
    for task, row in sorted(report.gate.per_task.items()):
        cells = [f"{row[arm]:.2f}" if arm in row else "-" for arm in arms]
        lines.append(f"| {task} | " + " | ".join(cells) + " |")
    lines += ["", "## Cost", "", f"- Status: **{report.cost.get('status')}**"]
    for key in ("mean_tokens_input", "mean_duration_s"):
        if key in report.cost:
            lines.append(f"- {key}: {report.cost[key]:.2f}")
    projection = report.cost.get("projection")
    if projection:
        lines.append(f"- Projection: {projection['label']}")
    lines.append("")
    return "\n".join(lines)


def render_schedule(schedule: Sequence[RunSpec]) -> str:
    lines = [
        "| order | arm | task | category | rep |",
        "|---:|---|---|---|---:|",
    ]
    for spec in schedule:
        lines.append(
            f"| {spec.order} | {spec.arm} | {spec.task} | {spec.category} | {spec.rep} |"
        )
    return "\n".join(lines)


def dry_run(
    stage: int,
    *,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
    tasks: Sequence[dict[str, Any]] | None = None,
) -> list[RunSpec]:
    """Build the schedule without creating worktrees or spending tokens."""
    task_list = list(tasks) if tasks is not None else list_tasks()
    return build_schedule(stage_arms(stage), task_list, reps=reps, seed=seed)


# -- command line ----------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m benchmarks.driver`` — dev-only, never shipped in the wheel."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.driver",
        description="Run the OCTK factorial benchmark (handoff D3).",
    )
    parser.add_argument("--stage", default="1", choices=["1", "2", "3", "all"])
    parser.add_argument("--reps", type=int, default=DEFAULT_REPS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--dry-run", action="store_true", help="print the queue only")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm a real run; without it nothing is executed",
    )
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[1]
    results = Path(args.results_dir) if args.results_dir else None

    if args.dry_run:
        stages = [1, 2, 3] if args.stage == "all" else [int(args.stage)]
        for stage in stages:
            schedule = dry_run(stage, reps=args.reps, seed=args.seed)
            print(f"# Stage {stage} — {len(schedule)} runs")
            print(render_schedule(schedule))
            print()
        return 0

    if not args.yes:
        print(
            "refusing to execute without --yes: this spends real model calls.\n"
            "Use --dry-run to inspect the schedule first.",
            file=sys.stderr,
        )
        return 2

    if args.stage == "all":
        reports = run_all_stages(
            repo,
            reps=args.reps,
            seed=args.seed,
            results_dir=results,
            timeout_s=args.timeout,
            progress=_print_progress,
        )
    else:
        reports = [
            run_stage(
                int(args.stage),
                repo,
                reps=args.reps,
                seed=args.seed,
                results_dir=results,
                timeout_s=args.timeout,
                progress=_print_progress,
            )
        ]

    for report in reports:
        print(render_stage_report(report))
        if report.gate.blocking:
            print("STOP: correctness regression. Fix before spending more.", file=sys.stderr)
            return 1
    return 0


def _print_progress(outcome: RunOutcome, index: int, total: int) -> None:
    status = "PASS" if outcome.passed else "FAIL"
    print(
        f"[{index}/{total}] arm {outcome.spec.arm} {outcome.spec.task} "
        f"rep {outcome.spec.rep} -> {status}",
        file=sys.stderr,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
