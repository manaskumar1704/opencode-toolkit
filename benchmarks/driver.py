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

import fcntl
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from benchmarks.manifest import RunManifest, hash_text, now_iso, save_manifest
from benchmarks.preflight import EFFORT_REQUIRED, MODEL_ID, run_preflight
from benchmarks.runner import RESULTS_DIR, list_tasks, safe_id
from benchmarks.workspace import (
    bwrap_available,
    create_workspace,
    oracle_leaks,
    remove_workspace,
    tool_input_text,
    wrap_command,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

ARMS = ("A", "B", "C", "D", "E", "F", "G", "H")
MIN_REPS = 5
DEFAULT_REPS = 5
DEFAULT_SEED = 20261109
DEFAULT_TIMEOUT_S = 1800

# Gate thresholds. A difference must clear both a confidence test and a minimum
# effect size; otherwise it is noise. v1 (+908 turn-1 tokens) and v2 Stage 1
# (0.1s "win") both showed what happens without this.
MIN_TOKEN_REDUCTION = 0.05
MIN_DURATION_REDUCTION = 0.10
MIN_PAIRS = 5
BOOTSTRAP_SAMPLES = 5000

# Handoff D3 staged gates. Stage N is cumulative: stage 2 re-runs stage 1 arms.
STAGE_ARMS: dict[int, tuple[str, ...]] = {
    1: ("A", "E"),
    2: ("A", "B", "C", "E"),
    3: ARMS,
}

# Which arm is the no-OCTK baseline used by the gate comparison.
BASELINE_ARM = "A"


# -- arms ------------------------------------------------------------------


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


def task_reps(task: dict[str, Any], default: int) -> int:
    """How many reps a task asks for.

    A fixture may raise its own floor - ``spec_selection`` needs 20 to resolve
    a small effect - while the rest of the suite runs at 5. The floor is
    ``MIN_REPS`` so no task can silently drop below the handoff requirement.
    """
    try:
        value = int(task.get("reps", default))
    except (TypeError, ValueError):
        return default
    return max(value, MIN_REPS)


def build_schedule(
    arms: Iterable[str],
    tasks: Sequence[dict[str, Any]],
    reps: int | None = None,
    seed: int = DEFAULT_SEED,
) -> list[RunSpec]:
    """Build a seeded, randomised run queue.

    ``reps`` overrides every task. When it is None each task uses the count in
    its own fixture, so the standard suite can run one task at higher power
    without a separate "block" that has to be merged by hand afterwards.

    The full cross-product is shuffled once; ``order`` is then assigned 1..N.
    Same inputs + same seed always produce the same queue.
    """
    if not tasks:
        raise ValueError("no tasks supplied")

    counts: list[tuple[dict[str, Any], int]] = []
    for task in tasks:
        count = int(reps) if reps is not None else task_reps(task, DEFAULT_REPS)
        if count < MIN_REPS:
            raise ValueError(f"reps must be >= {MIN_REPS} (handoff D3); got {count}")
        counts.append((task, count))

    combos: list[tuple[str, dict[str, Any], int]] = [
        (arm, task, rep)
        for arm in sorted(arms)
        for task, count in counts
        for rep in range(1, count + 1)
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
        desired = {"type": "local", "command": ["octk-mcp"], "codemode": False}
        if servers.get("octk") != desired:
            servers["octk"] = desired
            changed.append("enabled octk MCP server (rewrote command)")
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
    tokens_reasoning: int | None = None
    tokens_cached: int | None = None
    provider_errors: list[str] = field(default_factory=list)
    rate_limit_log: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# executor(spec, worktree, prompt, timeout_s) -> AgentResult
Executor = Callable[[RunSpec, Path, str, int], AgentResult]


@dataclass(frozen=True)
class TokenTotals:
    """Run-level token usage summed from OpenCode ``step_finish`` events."""

    input: int | None = None
    output: int | None = None
    reasoning: int | None = None
    cache_read: int | None = None

    @property
    def known(self) -> bool:
        return self.input is not None


def extract_token_totals(text: str) -> TokenTotals:
    """Sum per-step usage from an OpenCode ``--format json`` stream.

    Each ``step_finish`` event reports that step's *new* tokens. Summing gives
    the run total; taking the last event reports one step only (measured: 169
    vs 43,602 input tokens on a single run). Cache reads are summed because
    providers bill them per token processed.
    """
    total_in = total_out = total_reason = total_cache = 0
    found = False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "step_finish":
            continue
        part = event.get("part")
        tokens = part.get("tokens") if isinstance(part, dict) else None
        if not isinstance(tokens, dict):
            continue
        step_in = tokens.get("input")
        step_out = tokens.get("output")
        if not (isinstance(step_in, int) and isinstance(step_out, int)):
            continue
        found = True
        total_in += step_in
        total_out += step_out
        reasoning = tokens.get("reasoning")
        if isinstance(reasoning, int):
            total_reason += reasoning
        cache = tokens.get("cache")
        if isinstance(cache, dict) and isinstance(cache.get("read"), int):
            total_cache += cache["read"]
    if not found:
        return TokenTotals()
    return TokenTotals(total_in, total_out, total_reason, total_cache)


def extract_token_usage(text: str) -> tuple[int | None, int | None]:
    """Return run-level (input, output) tokens, or ``(None, None)`` if unknown."""
    totals = extract_token_totals(text)
    return totals.input, totals.output


def opencode_executor(
    spec: RunSpec,
    worktree: Path,
    prompt: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> AgentResult:
    """Run the real agent in the workspace, with the host repo masked."""
    command = wrap_command(
        [
            "opencode",
            "--standalone",
            "run",
            "--model",
            MODEL_ID,
            "--agent",
            "build",
            "--format",
            "json",
            "--auto",
            prompt,
        ],
        worktree,
        REPO_ROOT,
    )
    started = time.monotonic()
    env = dict(os.environ)
    venv_bin = REPO_ROOT / ".venv" / "bin"
    if venv_bin.is_dir():
        env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    try:
        proc = subprocess.run(
            command,
            cwd=worktree,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_s,
            check=False,
            env=env,
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

    totals = extract_token_totals(proc.stdout)
    return AgentResult(
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        exit_code=proc.returncode,
        duration_s=time.monotonic() - started,
        tokens_input=totals.input,
        tokens_output=totals.output,
        tokens_reasoning=totals.reasoning,
        tokens_cached=totals.cache_read,
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
    if not (destination / "acceptance.py").is_file():
        listing = ", ".join(sorted(p.name for p in worktree.iterdir()))
        return False, f"oracle vanished after copy; workspace holds: {listing}"
    python = python_executable or sys.executable
    try:
        proc = subprocess.run(
            [python, "-m", "pytest", "oracle/acceptance.py", "-q"],
            cwd=worktree,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_s,
            check=False,
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
        check=False,
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


# One driver per results directory. An interrupted run can survive as an
# orphan; two drivers then share workspace paths, and create_workspace deletes
# the directory from under the other run. Measured: two runs failed with
# ModuleNotFoundError because a second driver had rebuilt their workspace.
_LOCK_HANDLES: dict[str, object] = {}


def lock_results(results: Path) -> None:
    """Take an exclusive lock, or exit with a clear message.

    Locks are per process: nested stage runs (``run_all_stages``) reuse the
    handle already held for the same directory.
    """
    results.mkdir(parents=True, exist_ok=True)
    key = str(results.resolve())
    if key in _LOCK_HANDLES:
        return
    path = results / ".driver.lock"
    # The handle owns the lock for the process lifetime; closing it releases.
    handle = open(path, "w", encoding="utf-8")  # noqa: SIM115
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise SystemExit(
            f"another benchmark driver holds {path}; wait for it to finish "
            "(or kill it) before starting a second run"
        )
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    _LOCK_HANDLES[key] = handle


def existing_outcome(results: Path, spec: RunSpec) -> RunOutcome | None:
    """Load a finished run for ``--resume``; ``None`` if it is absent or broken.

    A block can be interrupted (the operator restarts the host, the tool
    times out). Re-spending model calls on completed runs is waste, but a
    half-written manifest must never be trusted.
    """
    run_id = f"bench-{safe_id(spec.arm)}-{safe_id(spec.task)}-r{spec.rep}"
    path = results / "manifests" / f"{run_id}.json"
    if not path.is_file():
        return None
    try:
        manifest = RunManifest.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, TypeError):
        return None
    if manifest.tokens_input is None or manifest.duration_s is None:
        return None
    return RunOutcome(
        spec,
        manifest,
        str(path),
        bool(manifest.correctness.get("acceptance_passed")),
    )


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
        worktree = create_workspace(repo, run_id)
    except (OSError, RuntimeError) as exc:
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
        try:
            oracle_rel = str(acceptance_path.relative_to(REPO_ROOT))
        except ValueError:
            oracle_rel = str(acceptance_path)
        setup_patch = task_dir / "setup.patch"
        visible_text = (
            setup_patch.read_text(encoding="utf-8") if setup_patch.is_file() else ""
        )
        agent_text = (agent.stdout or "") + (agent.stderr or "")
        # Prefer tool inputs: a doc that *mentions* the oracle is not a leak,
        # a command that reads it is. Fall back to raw text so an unknown
        # harness can over-flag rather than silently pass.
        evidence = tool_input_text(agent_text) or agent_text
        leaks = oracle_leaks(evidence, acceptance_text, oracle_rel, visible_text)
        # A harness stall is not evidence about the agent. With a 30 minute
        # ceiling and tasks that normally finish in under three, a timeout
        # means infrastructure, so the run is excluded rather than failed.
        timed_out = bool(error and error.startswith("agent timed out"))
        invalid_reason = error if timed_out else None
        valid = not leaks and invalid_reason is None
        # Validity is a separate channel: never overwrite the oracle result.
        # A leaked run is excluded from aggregates, but its correctness is
        # still recorded honestly.
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
                "valid": valid,
                "invalid_reason": invalid_reason,
                "oracle_leaked": leaks,
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
            tokens_cached=agent.tokens_cached or 0,
            tokens_reasoning=agent.tokens_reasoning or 0,
            wall_clock_s=agent.duration_s,
            environment_manifest={
                "worktree": str(worktree),
                "sandbox": "bwrap" if bwrap_available() else "none",
                "arm_flags": arm_flags(spec.arm),
                "python": python_executable or sys.executable,
                "model_id": MODEL_ID,
                "effort": EFFORT_REQUIRED,
            },
        )
        save_manifest(manifest_path, manifest)
    finally:
        if not keep_worktree:
            remove_workspace(worktree)

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
    effect: dict[str, Any] = field(default_factory=dict)
    per_task_effect: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pass_rates(outcomes: Sequence[RunOutcome]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, list[bool]]] = {}
    for outcome in outcomes:
        if outcome.manifest.correctness.get("valid") is False:
            continue
        totals.setdefault(outcome.spec.task, {}).setdefault(outcome.spec.arm, []).append(
            outcome.passed
        )
    return {
        task: {arm: sum(values) / len(values) for arm, values in arms.items()}
        for task, arms in totals.items()
    }


def _bootstrap_ci(diffs: Sequence[float], seed: int) -> tuple[float, float]:
    """95% percentile bootstrap CI for the mean of paired differences."""
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(BOOTSTRAP_SAMPLES))
    low = means[int(0.025 * BOOTSTRAP_SAMPLES)]
    high = means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]
    return low, high


def _task_balanced_ci(
    groups: Sequence[Sequence[float]], seed: int
) -> tuple[float, float]:
    """95% CI for the mean of per-task means, resampling tasks then reps.

    Tasks carry different numbers of pairs, so a flat bootstrap over all pairs
    would let the task with the most reps decide the aggregate. This samples
    tasks with replacement and then reps within each sampled task, which gives
    every task the same weight in the pooled number.
    """
    rng = random.Random(seed)
    n_tasks = len(groups)
    means: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        drawn = [rng.choice(groups) for _ in range(n_tasks)]
        task_means = []
        for group in drawn:
            resampled = rng.choices(group, k=len(group))
            task_means.append(sum(resampled) / len(resampled))
        means.append(sum(task_means) / len(task_means))
    means.sort()
    low = means[int(0.025 * BOOTSTRAP_SAMPLES)]
    high = means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]
    return low, high


def _paired_effect(
    outcomes: Sequence[RunOutcome],
    baseline: str,
    candidate: str,
    field_name: str,
    seed: int,
) -> dict[str, Any] | None:
    """Paired (task, rep) difference for one metric, with a bootstrap CI.

    Returns ``None`` when there are fewer than ``MIN_PAIRS`` usable pairs, so a
    thin sample can never be called a signal.
    """
    index = {(o.spec.task, o.spec.rep, o.spec.arm): o for o in outcomes}
    pairs: list[tuple[float, float]] = []
    by_task: dict[str, list[tuple[float, float]]] = {}
    for (task, rep, arm), outcome in index.items():
        if arm != candidate:
            continue
        if outcome.manifest.correctness.get("valid") is False:
            continue
        base = index.get((task, rep, baseline))
        if base is None:
            continue
        if base.manifest.correctness.get("valid") is False:
            continue
        a = getattr(base.manifest, field_name)
        b = getattr(outcome.manifest, field_name)
        if a is None or b is None:
            continue
        pairs.append((float(a), float(b)))
        by_task.setdefault(task, []).append((float(a), float(b)))

    if len(pairs) < MIN_PAIRS:
        return None

    diffs = [b - a for a, b in pairs]
    mean_base = statistics.mean(a for a, _ in pairs)
    mean_diff = statistics.mean(diffs)
    if len(by_task) > 1:
        # Equal task weight: mean of the per-task means, not mean of the pairs.
        per_task_diff = [
            statistics.mean(b - a for a, b in group) for group in by_task.values()
        ]
        per_task_base = [
            statistics.mean(a for a, _ in group) for group in by_task.values()
        ]
        mean_diff = statistics.mean(per_task_diff)
        mean_base = statistics.mean(per_task_base)
        diff_groups = [
            [b - a for a, b in group] for group in by_task.values()
        ]
        low, high = _task_balanced_ci(diff_groups, seed)
    else:
        low, high = _bootstrap_ci(diffs, seed)
    reduction = (-mean_diff / mean_base) if mean_base else 0.0
    reduction_low = (-high / mean_base) if mean_base else 0.0
    reduction_high = (-low / mean_base) if mean_base else 0.0
    return {
        "n": len(pairs),
        "baseline_mean": mean_base,
        "mean_difference": mean_diff,
        "reduction": reduction,
        "reduction_ci_low": reduction_low,
        "reduction_ci_high": reduction_high,
        "ci_low": low,
        "ci_high": high,
        "improvement": high < 0,
        "regression": low > 0,
        "significant": high < 0 or low > 0,
    }


def _describe(effect: dict[str, Any] | None) -> str:
    if effect is None:
        return "insufficient paired data"
    return (
        f"{effect['reduction'] * 100:+.1f}% "
        f"(95% CI {effect['reduction_ci_low'] * 100:+.1f}%.."
        f"{effect['reduction_ci_high'] * 100:+.1f}%, n={effect['n']})"
    )


def _per_task_effects(
    outcomes: Sequence[RunOutcome],
    arms: Sequence[str],
    seed: int,
) -> dict[str, Any]:
    """Per-task paired effects, so an aggregate cannot hide the story.

    Each task is resampled with its own deterministic seed; sharing one stream
    across tasks of different sizes would correlate the intervals.
    """
    tasks = sorted({o.spec.task for o in outcomes})
    result: dict[str, Any] = {}
    for index, task in enumerate(tasks):
        subset = [o for o in outcomes if o.spec.task == task]
        row: dict[str, Any] = {}
        for arm in arms:
            row[arm] = {
                "tokens": _paired_effect(
                    subset, BASELINE_ARM, arm, "tokens_input", seed + index + 1
                ),
                "duration": _paired_effect(
                    subset, BASELINE_ARM, arm, "duration_s", seed + index + 1
                ),
            }
        result[task] = row
    return result


def evaluate_gate(
    stage: int,
    outcomes: Sequence[RunOutcome],
    seed: int = DEFAULT_SEED,
) -> GateDecision:
    """Apply the handoff D3 gate with a real effect-size test.

    A difference counts only when the paired bootstrap CI excludes zero *and*
    clears the minimum effect size. Stage 1 of both v1 and v2 showed why: a
    0.1s median difference was being accepted as a "measurable signal".
    """
    if stage not in STAGE_ARMS:
        raise ValueError(f"unknown stage: {stage!r}")

    per_task = _pass_rates(outcomes)
    if stage == 3:
        return GateDecision(3, True, False, "final stage; no further gate", per_task)

    if not per_task:
        return GateDecision(stage, False, False, "no valid runs recorded", per_task)

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

    effect: dict[str, Any] = {}
    passing: list[str] = []
    for arm in signal_arms:
        tokens = _paired_effect(outcomes, BASELINE_ARM, arm, "tokens_input", seed)
        duration = _paired_effect(outcomes, BASELINE_ARM, arm, "duration_s", seed)
        effect[arm] = {"tokens": tokens, "duration": duration}
        token_signal = bool(
            tokens
            and tokens["improvement"]
            and tokens["reduction"] >= MIN_TOKEN_REDUCTION
        )
        duration_signal = bool(
            duration
            and duration["improvement"]
            and duration["reduction"] >= MIN_DURATION_REDUCTION
        )
        if token_signal or duration_signal:
            parts = []
            if token_signal:
                parts.append("tokens " + _describe(tokens))
            if duration_signal:
                parts.append("duration " + _describe(duration))
            passing.append(f"arm {arm}: " + "; ".join(parts))

    per_task_effect = _per_task_effects(outcomes, signal_arms, seed)

    if stage == 1:
        if not passing:
            detail = "; ".join(
                f"arm {arm} tokens {_describe(effect[arm]['tokens'])}, "
                f"duration {_describe(effect[arm]['duration'])}"
                for arm in signal_arms
            )
            return GateDecision(
                1,
                False,
                False,
                "no measurable efficiency signal in Stage 1: " + detail,
                per_task,
                effect,
                per_task_effect,
            )
        return GateDecision(
            1,
            True,
            False,
            "correctness non-negative; " + "; ".join(passing),
            per_task,
            effect,
            per_task_effect,
        )

    if not passing:
        return GateDecision(
            2,
            False,
            False,
            "external tools show no independent effect; interactions not worth testing",
            per_task,
            effect,
            per_task_effect,
        )
    return GateDecision(
        2,
        True,
        False,
        "external tools show an independent effect; " + "; ".join(passing),
        per_task,
        effect,
        per_task_effect,
    )


# -- cost honesty ----------------------------------------------------------


def cost_projection(
    outcomes: Sequence[RunOutcome],
    *,
    reps: int | None = None,
    n_tasks: int | None = None,
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
    # Reps can differ per task now, so the projection counts the reps that
    # were actually run rather than assuming a flat rate.
    if reps is not None and n_tasks is not None:
        total_reps = n_tasks * reps
    else:
        per_task_reps: dict[str, int] = {}
        for outcome in stage1:
            per_task_reps[outcome.spec.task] = max(
                per_task_reps.get(outcome.spec.task, 0), outcome.spec.rep
            )
        total_reps = sum(per_task_reps.values())
    remaining_stage2 = 2 * total_reps
    remaining_stage3 = 4 * total_reps
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
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "runs": len(self.outcomes),
            "passed": sum(1 for o in self.outcomes if o.passed),
            "invalid": sum(
                1
                for o in self.outcomes
                if o.manifest.correctness.get("valid") is False
            ),
            "gate": self.gate.to_dict(),
            "cost": self.cost,
            "results_dir": self.results_dir,
            "label": self.label,
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


def run_stage(
    stage: int,
    repo: Path,
    *,
    reps: int | None = None,
    seed: int = DEFAULT_SEED,
    executor: Executor | None = None,
    results_dir: Path | None = None,
    python_executable: str | None = None,
    tasks: Sequence[dict[str, Any]] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    preflight: bool = True,
    label: str = "",
    resume: bool = False,
    progress: Callable[[RunOutcome, int, int], None] | None = None,
) -> StageReport:
    """Run one stage: preflight, schedule, execute, gate, persist.

    ``label`` suffixes the persisted report names, so a stage can be run in
    several blocks (a powered task, then the rest) without clobbering.
    """
    results = results_dir or RESULTS_DIR
    lock_results(results)
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
        if resume:
            done = existing_outcome(results, spec)
            if done is not None:
                outcomes.append(done)
                if progress is not None:
                    progress(done, index, len(schedule))
                continue
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

    gate = evaluate_gate(stage, outcomes, seed=seed)
    cost = cost_projection(outcomes, reps=reps, n_tasks=len(task_list))
    report = StageReport(
        stage=stage,
        outcomes=outcomes,
        gate=gate,
        cost=cost,
        results_dir=str(results),
        label=label,
    )

    results.mkdir(parents=True, exist_ok=True)
    stem = f"stage-{stage}" + (f"-{label}" if label else "")
    (results / f"{stem}.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    (results / f"{stem}.md").write_text(render_stage_report(report), encoding="utf-8")
    return report


def run_all_stages(
    repo: Path,
    *,
    start_stage: int = 1,
    reps: int | None = None,
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


def _verdict(effect: dict[str, Any]) -> str:
    if effect["improvement"]:
        return "improvement"
    if effect["regression"]:
        return "regression"
    return "noise"


def _effect_row(prefix: str, effect: dict[str, Any] | None) -> str:
    if not effect:
        return f"| {prefix} | - | insufficient data | - | noise |"
    return (
        f"| {prefix} | {effect['n']} | "
        f"{effect['reduction'] * 100:+.1f}% | "
        f"{effect['reduction_ci_low'] * 100:+.1f}%.."
        f"{effect['reduction_ci_high'] * 100:+.1f}% | {_verdict(effect)} |"
    )


def render_stage_report(report: StageReport) -> str:
    suffix = f" — {report.label}" if report.label else ""
    lines = [
        f"# Benchmark Stage {report.stage}{suffix}",
        "",
        (
            f"Runs: {len(report.outcomes)}  "
            f"Passed: {sum(1 for o in report.outcomes if o.passed)}"
        ),
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
    if report.gate.effect:
        lines += [
            "",
            "## Effect (paired by task and rep)",
            "",
            "Reduction is relative to arm A. Positive means the arm used fewer",
            "tokens or less time; negative means it used more.",
            "",
            "| arm | metric | n | reduction | 95% CI | verdict |",
            "|---|---|---:|---:|---|---|",
        ]
        for arm in sorted(report.gate.effect):
            for metric in ("tokens", "duration"):
                effect = report.gate.effect[arm].get(metric)
                lines.append(_effect_row(f"{arm} | {metric}", effect))
    if report.gate.per_task_effect:
        lines += [
            "",
            "## Per-task effect (paired by task and rep)",
            "",
            "An aggregate can hide a strong effect on one task. Every task is",
            "reported with its own confidence interval.",
            "",
            "| task | metric | n | reduction | 95% CI | verdict |",
            "|---|---|---:|---:|---|---|",
        ]
        for task in sorted(report.gate.per_task_effect):
            for arm in sorted(report.gate.per_task_effect[task]):
                for metric in ("tokens", "duration"):
                    effect = report.gate.per_task_effect[task][arm].get(metric)
                    lines.append(_effect_row(f"{task} | {metric}", effect))
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
    reps: int | None = None,
    seed: int = DEFAULT_SEED,
    tasks: Sequence[dict[str, Any]] | None = None,
) -> list[RunSpec]:
    """Build the schedule without creating worktrees or spending tokens."""
    task_list = list(tasks) if tasks is not None else list_tasks()
    return build_schedule(stage_arms(stage), task_list, reps=reps, seed=seed)


# -- command line ----------------------------------------------------------


def select_tasks(spec: str) -> list[dict[str, Any]] | None:
    """Filter the suite by name; ``""`` means the whole suite.

    Block runs need this: a single task can be powered to 20 reps without
    touching the other fixtures. Unknown names are an error, never silent.
    """
    wanted = [name.strip() for name in spec.split(",") if name.strip()]
    if not wanted:
        return None
    available = {str(task["name"]): task for task in list_tasks()}
    unknown = [name for name in wanted if name not in available]
    if unknown:
        raise SystemExit(
            f"unknown task(s): {', '.join(unknown)}\n"
            f"available: {', '.join(sorted(available))}"
        )
    return [available[name] for name in wanted]


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m benchmarks.driver`` — dev-only, never shipped in the wheel."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.driver",
        description="Run the OCTK factorial benchmark (handoff D3).",
    )
    parser.add_argument("--stage", default="1", choices=["1", "2", "3", "all"])
    parser.add_argument(
        "--reps",
        type=int,
        default=None,
        help=(
            "override the rep count for every task; by default each task uses "
            "its own count from its fixture (spec_selection runs 20, the rest 5)"
        ),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--results-dir", default=None)
    parser.add_argument(
        "--tasks",
        default="",
        help="comma-separated task names; default is the whole suite",
    )
    parser.add_argument(
        "--label",
        default="",
        help="report suffix: --label spec writes stage-1-spec.md",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse completed manifests instead of re-running them",
    )
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
    selected = select_tasks(args.tasks)

    if args.dry_run:
        stages = [1, 2, 3] if args.stage == "all" else [int(args.stage)]
        for stage in stages:
            schedule = dry_run(
                stage, reps=args.reps, seed=args.seed, tasks=selected
            )
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
            tasks=selected,
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
                tasks=selected,
                label=args.label,
                resume=args.resume,
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
