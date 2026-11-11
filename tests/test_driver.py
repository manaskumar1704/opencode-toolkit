"""Factorial driver tests: arms, schedule, gates, cost honesty, execution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.driver import (
    ARMS,
    DEFAULT_SEED,
    AgentResult,
    RunOutcome,
    RunSpec,
    apply_arm,
    arm_flags,
    build_schedule,
    cost_projection,
    dry_run,
    evaluate_gate,
    execute_run,
    extract_token_totals,
    extract_token_usage,
    run_all_stages,
    run_stage,
    stage_arms,
)
from benchmarks.manifest import RunManifest

TASKS = [
    {"name": "alpha", "category": "simple isolated bug", "path": "/tmp/alpha"},
    {"name": "beta", "category": "refactor", "path": "/tmp/beta"},
]


# -- arms and stages -------------------------------------------------------


def test_stage_arms_are_cumulative() -> None:
    assert stage_arms(1) == ("A", "E")
    assert stage_arms(2) == ("A", "B", "C", "E")
    assert stage_arms(3) == ARMS
    with pytest.raises(ValueError):
        stage_arms(4)


def test_arm_flags_match_handoff_table() -> None:
    assert arm_flags("A") == {"octk": False, "ponytail": False, "graphify": False}
    assert arm_flags("B") == {"octk": False, "ponytail": True, "graphify": False}
    assert arm_flags("C") == {"octk": False, "ponytail": False, "graphify": True}
    assert arm_flags("D") == {"octk": False, "ponytail": True, "graphify": True}
    assert arm_flags("E") == {"octk": True, "ponytail": False, "graphify": False}
    assert arm_flags("F") == {"octk": True, "ponytail": True, "graphify": False}
    assert arm_flags("G") == {"octk": True, "ponytail": False, "graphify": True}
    assert arm_flags("H") == {"octk": True, "ponytail": True, "graphify": True}
    with pytest.raises(ValueError):
        arm_flags("Z")


# -- schedule --------------------------------------------------------------


def test_schedule_covers_every_combination() -> None:
    schedule = build_schedule(stage_arms(1), TASKS, reps=5, seed=7)
    assert len(schedule) == 2 * 2 * 5
    assert {spec.arm for spec in schedule} == {"A", "E"}
    assert {spec.task for spec in schedule} == {"alpha", "beta"}
    assert {spec.rep for spec in schedule} == {1, 2, 3, 4, 5}
    assert sorted(spec.order for spec in schedule) == list(range(1, len(schedule) + 1))


def test_schedule_is_deterministic_for_same_seed() -> None:
    first = build_schedule(ARMS, TASKS, reps=5, seed=42)
    second = build_schedule(ARMS, TASKS, reps=5, seed=42)
    assert [spec.to_dict() for spec in first] == [spec.to_dict() for spec in second]


def test_schedule_order_changes_with_seed() -> None:
    first = build_schedule(ARMS, TASKS, reps=5, seed=1)
    second = build_schedule(ARMS, TASKS, reps=5, seed=2)
    assert [(s.arm, s.task, s.rep) for s in first] != [(s.arm, s.task, s.rep) for s in second]


def test_schedule_rejects_fewer_than_five_reps() -> None:
    with pytest.raises(ValueError, match="reps must be >= 5"):
        build_schedule(ARMS, TASKS, reps=4)


def test_schedule_rejects_empty_tasks() -> None:
    with pytest.raises(ValueError, match="no tasks"):
        build_schedule(ARMS, [], reps=5)


def test_dry_run_returns_schedule_without_side_effects(tmp_path: Path) -> None:
    schedule = dry_run(1, reps=5, seed=DEFAULT_SEED, tasks=TASKS)
    assert len(schedule) == 20
    assert not (tmp_path / "octk-bench").exists()


# -- worktree arm configuration -------------------------------------------


def test_apply_arm_disables_octk_server(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({"mcp": {"servers": {"octk": {"type": "local"}}}}),
        encoding="utf-8",
    )

    state = apply_arm(tmp_path, "A")

    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "octk" not in config["mcp"]["servers"]
    assert state["flags"]["octk"] is False
    assert any("disabled octk" in change for change in state["changed"])


def test_apply_arm_enables_octk_server(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text("{}", encoding="utf-8")

    apply_arm(tmp_path, "E")

    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert config["mcp"]["servers"]["octk"]["command"] == ["octk-mcp"]


def test_apply_arm_rewrites_an_existing_octk_command(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps(
            {
                "mcp": {
                    "servers": {
                        "octk": {
                            "type": "local",
                            "command": ["C:\\Users\\Lenovo\\octk-mcp.EXE"],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    apply_arm(tmp_path, "E")

    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert config["mcp"]["servers"]["octk"]["command"] == ["octk-mcp"]


def test_apply_arm_removes_ponytail_skill(tmp_path: Path) -> None:
    skill = tmp_path / ".opencode" / "skills" / "ponytail"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ponytail\n---\n", encoding="utf-8")

    apply_arm(tmp_path, "A")

    assert not skill.exists()


def test_apply_arm_keeps_ponytail_when_enabled(tmp_path: Path) -> None:
    skill = tmp_path / ".opencode" / "skills" / "ponytail"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ponytail\n---\n", encoding="utf-8")

    apply_arm(tmp_path, "B")

    assert skill.exists()


def test_apply_arm_removes_graphify_servers(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({"mcp": {"servers": {"graphify": {"type": "local"}}}}),
        encoding="utf-8",
    )

    apply_arm(tmp_path, "E")

    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "graphify" not in config["mcp"]["servers"]


# -- token extraction ------------------------------------------------------


def test_extract_token_totals_sums_every_step() -> None:
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "step_finish",
                    "part": {
                        "tokens": {
                            "input": 10,
                            "output": 2,
                            "reasoning": 1,
                            "cache": {"read": 0},
                        }
                    },
                }
            ),
            "not json",
            json.dumps(
                {
                    "type": "step_finish",
                    "part": {
                        "tokens": {
                            "input": 250,
                            "output": 40,
                            "reasoning": 9,
                            "cache": {"read": 100},
                        }
                    },
                }
            ),
            json.dumps({"type": "text", "part": {"text": "ignored"}}),
        ]
    )

    totals = extract_token_totals(stdout)

    assert (totals.input, totals.output, totals.reasoning, totals.cache_read) == (
        260,
        42,
        10,
        100,
    )


def test_extract_token_usage_returns_none_when_absent() -> None:
    assert extract_token_usage("plain text") == (None, None)


# -- gate ------------------------------------------------------------------


def _outcome(arm: str, task: str, passed: bool, tokens: int | None, duration: float) -> RunOutcome:
    manifest = RunManifest(
        arm=arm,
        task=task,
        task_category="simple isolated bug",
        tokens_input=tokens,
        duration_s=duration,
        correctness={"acceptance_passed": passed},
    )
    spec = RunSpec(arm, task, "simple isolated bug", "/tmp/x", 1, 1, 1)
    return RunOutcome(spec, manifest, "/tmp/m.json", passed)


def test_stage1_gate_proceeds_on_efficiency_signal() -> None:
    outcomes = [
        _outcome("A", "t", True, 1000, 100.0),
        _outcome("E", "t", True, 700, 90.0),
    ]
    gate = evaluate_gate(1, outcomes)
    assert gate.proceed is True
    assert gate.blocking is False
    assert "fewer input tokens" in gate.reason


def test_stage1_gate_blocks_on_correctness_regression() -> None:
    outcomes = [
        _outcome("A", "t", True, 1000, 100.0),
        _outcome("E", "t", False, 500, 50.0),
    ]
    gate = evaluate_gate(1, outcomes)
    assert gate.proceed is False
    assert gate.blocking is True
    assert "correctness regression" in gate.reason


def test_stage1_gate_refuses_without_signal() -> None:
    outcomes = [
        _outcome("A", "t", True, 1000, 100.0),
        _outcome("E", "t", True, 1000, 100.0),
    ]
    gate = evaluate_gate(1, outcomes)
    assert gate.proceed is False
    assert gate.blocking is False
    assert "no measurable efficiency signal" in gate.reason


def test_stage2_gate_requires_external_effect() -> None:
    outcomes = [
        _outcome("A", "t", True, 1000, 100.0),
        _outcome("B", "t", True, 1000, 100.0),
        _outcome("C", "t", True, 1000, 100.0),
        _outcome("E", "t", True, 900, 95.0),
    ]
    gate = evaluate_gate(2, outcomes)
    assert gate.proceed is False
    assert gate.blocking is False
    assert "no independent effect" in gate.reason


def test_stage3_gate_always_proceeds() -> None:
    gate = evaluate_gate(3, [_outcome("A", "t", True, 1000, 100.0)])
    assert gate.proceed is True


def test_gate_with_no_runs_does_not_proceed() -> None:
    gate = evaluate_gate(1, [])
    assert gate.proceed is False
    assert "no valid runs" in gate.reason


# -- cost honesty ----------------------------------------------------------


def test_cost_unknown_before_stage1_measurement() -> None:
    projection = cost_projection([])
    assert projection["status"] == "UNKNOWN"


def test_cost_measured_and_extrapolation_labelled() -> None:
    outcomes = [
        _outcome("A", "t", True, 1000, 100.0),
        _outcome("E", "t", True, 800, 90.0),
    ]
    projection = cost_projection(outcomes, reps=5, n_tasks=8)
    assert projection["status"] == "MEASURED"
    assert projection["mean_tokens_input"] == 900
    assert "extrapolation" in projection["projection"]["label"]
    assert projection["projection"]["stage2_remaining_runs"] == 80


# -- end-to-end execution --------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.com")
    _git(path, "config", "user.name", "t")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _make_task(path: Path) -> Path:
    (path / "oracle").mkdir(parents=True)
    (path / "task.json").write_text(
        json.dumps(
            {
                "name": path.name,
                "category": "simple isolated bug",
                "prompt": "Fix broken.py so the oracle passes.",
            }
        ),
        encoding="utf-8",
    )
    (path / "setup.patch").write_text(
        "diff --git a/broken.py b/broken.py\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        "+++ b/broken.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def value():\n"
        "+    return 1\n",
        encoding="utf-8",
    )
    (path / "oracle" / "acceptance.py").write_text(
        "from broken import value\n\n\ndef test_value():\n    assert value() == 2\n",
        encoding="utf-8",
    )
    return path


def _fixing_executor(tokens_by_arm: dict[str, int] | None = None):
    tokens_by_arm = tokens_by_arm or {}

    def executor(spec: RunSpec, worktree: Path, prompt: str, timeout_s: int) -> AgentResult:
        (worktree / "broken.py").write_text(
            "def value():\n    return 2\n", encoding="utf-8"
        )
        return AgentResult(
            stdout=json.dumps(
                {"tokens": {"input": tokens_by_arm.get(spec.arm, 100), "output": 5}}
            )
            + "\n",
            exit_code=0,
            duration_s=1.0,
            tokens_input=tokens_by_arm.get(spec.arm, 100),
            tokens_output=5,
        )

    return executor


def test_execute_run_writes_valid_manifest_and_transcript(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = _make_task(tmp_path / "task")
    results = tmp_path / "results"
    spec = RunSpec("A", "task", "simple isolated bug", str(task), 1, 1, 1)

    outcome = execute_run(
        spec,
        repo,
        executor=_fixing_executor(),
        results_dir=results,
        python_executable=sys.executable,
        opencode_version="2.2.6",
    )

    assert outcome.passed is True
    assert outcome.error is None
    assert outcome.manifest.valid, outcome.manifest.validate()
    assert Path(outcome.manifest.transcript_path).is_file()
    transcript = Path(outcome.manifest.transcript_path).read_text(encoding="utf-8")
    assert '"event": "oracle"' in transcript
    assert outcome.manifest.correctness["acceptance_passed"] is True
    # worktree is disposable
    assert not Path(outcome.manifest.environment_manifest["worktree"]).exists()


def test_execute_run_records_failure_as_invalid_not_crash(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = _make_task(tmp_path / "task")
    results = tmp_path / "results"
    spec = RunSpec("E", "task", "simple isolated bug", str(task), 1, 1, 1)

    def broken_executor(spec, worktree, prompt, timeout_s):
        return AgentResult(exit_code=1, duration_s=1.0, error="agent crashed")

    outcome = execute_run(
        spec,
        repo,
        executor=broken_executor,
        results_dir=results,
        python_executable=sys.executable,
        opencode_version="2.2.6",
    )

    assert outcome.passed is False
    assert outcome.error == "agent crashed"
    assert outcome.manifest.correctness["acceptance_passed"] is False


def test_run_stage_writes_report_and_applies_gate(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = _make_task(tmp_path / "task")
    results = tmp_path / "results"
    tasks = [{"name": "task", "category": "simple isolated bug", "path": str(task)}]

    report = run_stage(
        1,
        repo,
        reps=5,
        seed=3,
        executor=_fixing_executor({"A": 500, "E": 300}),
        results_dir=results,
        python_executable=sys.executable,
        tasks=tasks,
        preflight=False,
    )

    assert len(report.outcomes) == 10
    assert all(outcome.passed for outcome in report.outcomes)
    assert report.gate.proceed is True
    assert (results / "stage-1.json").is_file()
    assert (results / "stage-1.md").is_file()
    summary = json.loads((results / "stage-1.json").read_text(encoding="utf-8"))
    assert summary["runs"] == 10


def test_run_all_stages_stops_on_blocking_regression(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    task = _make_task(tmp_path / "task")
    results = tmp_path / "results"
    tasks = [{"name": "task", "category": "simple isolated bug", "path": str(task)}]

    def regressing_executor(spec, worktree, prompt, timeout_s):
        if spec.arm == "E":
            return AgentResult(exit_code=0, duration_s=1.0, tokens_input=10)
        (worktree / "broken.py").write_text("def value():\n    return 2\n", encoding="utf-8")
        return AgentResult(exit_code=0, duration_s=1.0, tokens_input=100)

    reports = run_all_stages(
        repo,
        reps=5,
        seed=3,
        executor=regressing_executor,
        results_dir=results,
        python_executable=sys.executable,
        tasks=tasks,
        preflight=False,
    )

    assert len(reports) == 1
    assert reports[0].gate.blocking is True


def test_safe_id_cannot_escape_a_directory() -> None:
    from benchmarks.driver import safe_id

    for hostile in ("../../etc", "..", "a/b", "a\\b", "."):
        cleaned = safe_id(hostile)
        assert "/" not in cleaned and "\\" not in cleaned
        assert cleaned not in {".", ".."}
        assert cleaned
    assert safe_id("normal-task_1") == "normal-task_1"
