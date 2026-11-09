"""Benchmark harness tests: manifest, preflight, isolation, report."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.manifest import RunManifest, load_manifest, save_manifest, hash_text
from benchmarks.preflight import check_effort, check_opencode_json, run_preflight
from benchmarks.runner import (
    arm_has,
    create_worktree,
    list_worktrees,
    remove_worktree,
    read_task_category,
    read_task_prompt,
)
from benchmarks.report import load_manifests, partition_validity, render_report


# -- manifest --------------------------------------------------------------


def test_manifest_valid_when_complete(tmp_path: Path) -> None:
    m = RunManifest(
        arm="A",
        task="simple_bug",
        task_category="simple isolated bug",
        base_commit="abc123",
        opencode_version="2.2.6",
        model_id="opencode-go/beam-free",
        effort="high",
        task_prompt_hash="a" * 64,
        acceptance_test_hash="b" * 64,
        randomization_seed=1,
        run_order=1,
        isolation_verified=True,
        transcript_path=str(tmp_path / "t.jsonl"),
        ponytail_version=None,
        graphify_version=None,
        graphify_state="cold",
        ponytail_available=False,
        graphify_available=False,
        correctness={"acceptance_passed": True},
    )
    (tmp_path / "t.jsonl").write_text("{}", encoding="utf-8")
    assert m.valid
    assert m.validate() == []


def test_manifest_invalid_when_missing_fields() -> None:
    m = RunManifest()
    missing = m.validate()
    assert "arm" in missing
    assert "task" in missing
    assert "isolation_verified" in missing


def test_manifest_round_trip(tmp_path: Path) -> None:
    m = RunManifest(arm="E", task="t", task_category="c", base_commit="abc")
    path = tmp_path / "m.json"
    save_manifest(path, m)
    loaded = load_manifest(path)
    assert loaded.arm == "E"
    assert loaded.task == "t"


def test_hash_text_is_stable() -> None:
    assert hash_text("hello") == hash_text("hello")
    assert hash_text("hello") != hash_text("world")


# -- preflight -------------------------------------------------------------


def test_check_effort_reads_frontmatter(tmp_path: Path) -> None:
    agents = tmp_path / ".opencode" / "agents"
    agents.mkdir(parents=True)
    (agents / "build.md").write_text("---\neffort: high\n---\n", encoding="utf-8")
    (agents / "plan.md").write_text("---\neffort: high\n---\n", encoding="utf-8")

    ok, values = check_effort(tmp_path)

    assert ok is True
    assert values == {"build": "high", "plan": "high"}


def test_check_effort_fails_on_non_high(tmp_path: Path) -> None:
    agents = tmp_path / ".opencode" / "agents"
    agents.mkdir(parents=True)
    (agents / "build.md").write_text("---\neffort: medium\n---\n", encoding="utf-8")

    ok, values = check_effort(tmp_path)

    assert ok is False
    assert values == {"build": "medium"}


def test_check_effort_fails_without_agents_dir(tmp_path: Path) -> None:
    ok, values = check_effort(tmp_path)
    assert ok is False
    assert values == {}


def test_check_opencode_json(tmp_path: Path) -> None:
    assert check_opencode_json(tmp_path) is False
    (tmp_path / "opencode.json").write_text('{"permissions": []}', encoding="utf-8")
    assert check_opencode_json(tmp_path) is True
    (tmp_path / "opencode.json").write_text("{bad", encoding="utf-8")
    assert check_opencode_json(tmp_path) is False


def test_preflight_fails_without_opencode_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    result = run_preflight(tmp_path)
    assert result.ok is False
    assert any("opencode binary" in e for e in result.errors)


# -- arm mapping -----------------------------------------------------------


def test_arm_has_octk() -> None:
    for arm in ("E", "F", "G", "H"):
        assert arm_has(arm, "octk") is True
    for arm in ("A", "B", "C", "D"):
        assert arm_has(arm, "octk") is False


def test_arm_has_ponytail() -> None:
    for arm in ("B", "D", "F", "H"):
        assert arm_has(arm, "ponytail") is True
    for arm in ("A", "C", "E", "G"):
        assert arm_has(arm, "ponytail") is False


def test_arm_has_graphify() -> None:
    for arm in ("C", "D", "G", "H"):
        assert arm_has(arm, "graphify") is True
    for arm in ("A", "B", "E", "F"):
        assert arm_has(arm, "graphify") is False


def test_arm_has_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        arm_has("A", "nope")


# -- worktree isolation -----------------------------------------------------


def _make_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_create_and_remove_worktree(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    wt = create_worktree(repo, "test-run-1")
    try:
        assert wt.exists()
        assert (wt / "README.md").exists()
        # writes in the worktree do not touch the source
        (wt / "marker.txt").write_text("x", encoding="utf-8")
        assert not (repo / "marker.txt").exists()
    finally:
        remove_worktree(repo, wt)
    assert not wt.exists()


def test_list_worktrees_includes_created(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path / "repo")
    wt = create_worktree(repo, "test-run-2")
    try:
        listed = list_worktrees(repo)
        assert wt in listed
    finally:
        remove_worktree(repo, wt)


# -- task loading ----------------------------------------------------------


def test_read_task_prompt_and_category() -> None:
    task_dir = Path(__file__).resolve().parents[1] / "benchmarks" / "tasks" / "simple_bug"
    prompt = read_task_prompt(task_dir)
    assert "tests/test_simple.py" in prompt
    assert read_task_category(task_dir) == "simple isolated bug"


def test_task_json_is_valid() -> None:
    task_dir = Path(__file__).resolve().parents[1] / "benchmarks" / "tasks" / "simple_bug"
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    assert data["name"] == "simple_bug"
    assert "oracle_test" in data


# -- report ----------------------------------------------------------------


def test_report_marks_invalid_runs(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    valid_m = RunManifest(
        arm="A", task="t", task_category="c", base_commit="abc",
        opencode_version="2.2.6", model_id="opencode-go/beam-free", effort="high",
        task_prompt_hash="a" * 64, acceptance_test_hash="b" * 64,
        randomization_seed=1, run_order=1, isolation_verified=True,
        transcript_path=str(transcript), ponytail_version=None, graphify_version=None,
        graphify_state="cold", ponytail_available=False, graphify_available=False,
        correctness={"acceptance_passed": True},
    )
    invalid_m = RunManifest(arm="B", task="t2")
    text = render_report([valid_m, invalid_m])
    assert "INVALID" in text
    assert "B" in text and "t2" in text
    assert "1 valid" in text.lower() or "1 valid" in text


def test_report_renders_aggregates(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    m = RunManifest(
        arm="E", task="t", task_category="c", base_commit="abc",
        opencode_version="2.2.6", model_id="opencode-go/beam-free", effort="high",
        task_prompt_hash="a" * 64, acceptance_test_hash="b" * 64,
        randomization_seed=1, run_order=1, isolation_verified=True,
        transcript_path=str(transcript), ponytail_version=None, graphify_version=None,
        graphify_state="cold", ponytail_available=False, graphify_available=False,
        correctness={"acceptance_passed": True}, duration_s=10.0, tokens_input=500,
    )
    text = render_report([m])
    assert "Arm E" in text
    assert "t" in text


def test_partition_validity(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    valid_m = RunManifest(
        arm="A", task="t", task_category="c", base_commit="abc",
        opencode_version="2.2.6", model_id="opencode-go/beam-free", effort="high",
        task_prompt_hash="a" * 64, acceptance_test_hash="b" * 64,
        randomization_seed=1, run_order=1, isolation_verified=True,
        transcript_path=str(transcript), ponytail_version=None, graphify_version=None,
        graphify_state="cold", ponytail_available=False, graphify_available=False,
        correctness={"acceptance_passed": True},
    )
    invalid_m = RunManifest()
    v, inv = partition_validity([valid_m, invalid_m])
    assert len(v) == 1
    assert len(inv) == 1


def test_load_manifests_from_directory(tmp_path: Path) -> None:
    d = tmp_path / "manifests"
    d.mkdir()
    m = RunManifest(arm="A", task="t", task_category="c", base_commit="abc")
    save_manifest(d / "run.json", m)
    loaded = load_manifests(d)
    assert len(loaded) == 1
