"""Terminal-Bench 2.0 external benchmark: cohort lock and command builder.

R-3 decision: use Terminal-Bench 2.0 through Harbor, dataset
``terminal-bench/terminal-bench-2`` (89 containerised tasks).

Scope is deliberately narrow. The eight-arm factorial stays internal; the
external benchmark answers one question: *does the OCTK effect generalise
beyond fixtures we wrote ourselves?* That is an OCTK-on (E) versus OCTK-off
(A) comparison, five attempts per task, same model and effort as the internal
cohort.

Nothing here runs on import. It builds and validates commands so the run can be
pre-registered (D7) before it costs money.
"""

from __future__ import annotations

import json
import platform
import shutil
from dataclasses import asdict, dataclass
from typing import Any

from benchmarks.preflight import EFFORT_REQUIRED, MODEL_ID

DATASET = "terminal-bench/terminal-bench-2"
DATASET_ALIAS = "terminal-bench@2.0"
TASK_COUNT = 89
EXTERNAL_ARMS = ("A", "E")
MIN_ATTEMPTS = 5
DEFAULT_JOBS_DIR = "benchmarks/results/external"

# Harbor's built-in OpenCode agent. A thin OCTK subclass is still required to
# install the package and register the MCP server inside the task container;
# see docs/v2/EXTERNAL_BENCHMARK.md.
HARBOR_AGENT = "opencode"


@dataclass(frozen=True)
class ExternalCohort:
    """A locked external cohort. ``validate()`` returns every violation."""

    dataset: str = DATASET_ALIAS
    agent: str = HARBOR_AGENT
    model_id: str = MODEL_ID
    effort: str = EFFORT_REQUIRED
    arm: str = "E"
    attempts: int = MIN_ATTEMPTS
    n_concurrent: int = 4
    task_limit: int | None = None
    probe: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.dataset not in (DATASET, DATASET_ALIAS):
            errors.append(f"dataset must be {DATASET_ALIAS!r}, got {self.dataset!r}")
        if self.model_id != MODEL_ID:
            errors.append(f"model must be {MODEL_ID!r}, got {self.model_id!r}")
        if self.effort != EFFORT_REQUIRED:
            errors.append(f"effort must be {EFFORT_REQUIRED!r}, got {self.effort!r}")
        if self.arm not in EXTERNAL_ARMS:
            errors.append(
                f"external arm must be one of {EXTERNAL_ARMS}; "
                "the 8-arm factorial is internal only"
            )
        if self.attempts < MIN_ATTEMPTS and not self.probe:
            errors.append(f"attempts must be >= {MIN_ATTEMPTS} (pass@k reporting)")
        if self.n_concurrent < 1:
            errors.append("n_concurrent must be >= 1")
        if self.task_limit is not None and self.task_limit < 1:
            errors.append("task_limit must be >= 1 when set")
        return errors

    @property
    def ok(self) -> bool:
        return not self.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def octk_config_content(*, model_id: str = MODEL_ID) -> str:
    """OpenCode config injected into the container for the OCTK arm.

    The container must already have ``octk-mcp`` installed (see the adapter
    note in the docs). Arm A injects no octk entry at all.
    """
    return json.dumps(
        {
            "$schema": "https://opencode.ai/config.json",
            "model": model_id,
            "mcp": {
                "servers": {
                    "octk": {
                        "type": "local",
                        "command": ["octk-mcp"],
                        "codemode": False,
                    }
                }
            },
        },
        separators=(",", ":"),
    )


def build_harbor_command(
    cohort: ExternalCohort,
    *,
    jobs_dir: str = DEFAULT_JOBS_DIR,
    include_task: str | None = None,
    oracle_only: bool = False,
) -> list[str]:
    """Build a ``harbor run`` argv. Never executes it."""
    errors = cohort.validate()
    if errors:
        raise ValueError("invalid external cohort: " + "; ".join(errors))

    command = [
        "harbor",
        "run",
        "-d",
        cohort.dataset,
        "-a",
        "oracle" if oracle_only else cohort.agent,
        "-n",
        str(cohort.n_concurrent),
        "-k",
        str(cohort.attempts),
        "--jobs-dir",
        jobs_dir,
    ]
    if not oracle_only:
        command += ["-m", cohort.model_id]
    if include_task:
        command += ["--include-task-name", include_task]
    if cohort.task_limit is not None:
        command += ["-l", str(cohort.task_limit)]
    if not oracle_only and cohort.arm == "E":
        command += [
            "--ae",
            f"OPENCODE_CONFIG_CONTENT={octk_config_content(model_id=cohort.model_id)}",
        ]
    return command


def smoke_ladder(cohort: ExternalCohort) -> list[dict[str, Any]]:
    """The ordered feasibility ladder. Each rung must pass before the next."""
    return [
        {
            "step": 1,
            "name": "oracle smoke test (5 tasks)",
            "command": build_harbor_command(
                cohort, include_task=None, oracle_only=True
            )
            + ["-l", "5"],
            "passes_when": "the reference solutions score 1.0 on all five tasks",
        },
        {
            "step": 2,
            "name": "one task, OpenCode, no OCTK",
            "command": build_harbor_command(
                ExternalCohort(arm="A", attempts=1, probe=True), include_task="fix-git"
            ),
            "passes_when": "the agent runs end to end and the verifier writes a reward",
        },
        {
            "step": 3,
            "name": "one task, OpenCode, OCTK mounted",
            "command": build_harbor_command(
                ExternalCohort(arm="E", attempts=1, probe=True), include_task="fix-git"
            ),
            "passes_when": "the agent starts and the octk MCP tools are listed in its logs",
        },
        {
            "step": 4,
            "name": "five-task pilot, both arms",
            "command": build_harbor_command(cohort, include_task=None) + ["-l", "5"],
            "passes_when": "all runs complete; no unclassified provider errors",
        },
        {
            "step": 5,
            "name": "full 89-task run, both arms",
            "command": build_harbor_command(cohort),
            "passes_when": "pre-registration recorded; correctness compared first",
        },
    ]


def preregistration(cohort: ExternalCohort) -> dict[str, Any]:
    """D7-style record to write *before* the external run starts."""
    if cohort.probe:
        raise ValueError("probe cohorts are feasibility checks, not reportable evidence")
    return {
        "benchmark": "Terminal-Bench 2.0",
        "dataset": cohort.dataset,
        "dataset_tasks": TASK_COUNT,
        "dataset_version_hash": "FILL_AFTER_DOWNLOAD",
        "agent": cohort.agent,
        "agent_adapter": "opencode + OCTK MCP mount (arm E only)",
        "model_id": cohort.model_id,
        "effort": cohort.effort,
        "arm": cohort.arm,
        "attempts": cohort.attempts,
        "n_concurrent": cohort.n_concurrent,
        "task_limit": cohort.task_limit,
        "container": "docker (x86_64)",
        "isolation": "one container per task trial",
        "opencode_version": "FILL_AFTER_SMOKE_TEST",
        "credential_env_var": "FILL_AFTER_SMOKE_TEST",
        "cost_status": "UNKNOWN until the five-task pilot is measured",
        "stopping_rule": (
            "abort and relabel if the model or dataset changes mid-run (handoff Q10); "
            "a correctness regression stops the comparison"
        ),
        "claims_allowed": (
            "correctness parity or improvement, plus a measured efficiency signal; "
            "no efficiency claim without correctness"
        ),
    }


def feasibility_checks() -> dict[str, dict[str, Any]]:
    """Local preconditions. Reports, never installs anything."""
    arch = platform.machine()
    return {
        "docker": {
            "ok": shutil.which("docker") is not None,
            "detail": "Docker must be running; TB 2.0 task images are amd64-only",
        },
        "uv": {
            "ok": shutil.which("uv") is not None,
            "detail": "uv tool install harbor",
        },
        "harbor": {
            "ok": shutil.which("harbor") is not None,
            "detail": "harbor is the official Terminal-Bench 2.0 harness",
        },
        "architecture": {
            "ok": arch in ("x86_64", "amd64"),
            "detail": f"detected {arch!r}; emulation invalidates reward numbers",
        },
        "opencode": {
            "ok": shutil.which("opencode") is not None,
            "detail": "host binary is not used inside the container, but confirms the CLI shape",
        },
    }
