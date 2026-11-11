"""Terminal-Bench 2.0 cohort tests: lock enforcement and command building."""

from __future__ import annotations

import json

import pytest

from benchmarks.external import (
    DATASET,
    DATASET_ALIAS,
    ExternalCohort,
    build_harbor_command,
    feasibility_checks,
    octk_config_content,
    preregistration,
    smoke_ladder,
)


def test_default_cohort_is_locked_to_the_internal_cohort() -> None:
    cohort = ExternalCohort()
    assert cohort.ok, cohort.validate()
    assert cohort.model_id == "opencode-go/beam-free"
    assert cohort.effort == "high"
    assert cohort.attempts == 5
    assert cohort.arm == "E"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("dataset", "swebench@1.0", "dataset must be"),
        ("model_id", "opencode/beam-free", "model must be"),
        ("effort", "medium", "effort must be"),
        ("arm", "H", "external arm must be"),
        ("attempts", 3, "attempts must be"),
        ("n_concurrent", 0, "n_concurrent must be"),
        ("task_limit", 0, "task_limit must be"),
    ],
)
def test_validate_rejects_cohort_drift(field: str, value: object, message: str) -> None:
    cohort = ExternalCohort(**{field: value})  # type: ignore[arg-type]
    errors = cohort.validate()
    assert any(message in error for error in errors)


def test_dataset_alias_is_accepted() -> None:
    assert ExternalCohort(dataset=DATASET).ok
    assert ExternalCohort(dataset=DATASET_ALIAS).ok


def test_harbor_command_contains_the_lock() -> None:
    command = build_harbor_command(ExternalCohort())
    assert command[:2] == ["harbor", "run"]
    assert "-d" in command
    assert command[command.index("-d") + 1] == DATASET_ALIAS
    assert command[command.index("-m") + 1] == "opencode-go/beam-free"
    assert command[command.index("-k") + 1] == "5"
    assert command[command.index("-a") + 1] == "opencode"


def test_harbor_command_rejects_invalid_cohort() -> None:
    with pytest.raises(ValueError, match="invalid external cohort"):
        build_harbor_command(ExternalCohort(effort="low"))


def test_octk_arm_injects_mcp_config_but_baseline_does_not() -> None:
    octk_command = build_harbor_command(ExternalCohort(arm="E"))
    baseline_command = build_harbor_command(ExternalCohort(arm="A"))
    assert "--ae" in octk_command
    assert "--ae" not in baseline_command


def test_octk_config_content_is_valid_and_points_at_octk_mcp() -> None:
    config = json.loads(octk_config_content())
    assert config["model"] == "opencode-go/beam-free"
    assert config["mcp"]["servers"]["octk"]["command"] == ["octk-mcp"]


def test_oracle_command_has_no_model() -> None:
    command = build_harbor_command(ExternalCohort(), oracle_only=True)
    assert command[command.index("-a") + 1] == "oracle"
    assert "-m" not in command
    assert "--ae" not in command


def test_smoke_ladder_is_ordered_and_includes_both_arms() -> None:
    ladder = smoke_ladder(ExternalCohort())
    assert [step["step"] for step in ladder] == [1, 2, 3, 4, 5]
    assert "oracle" in ladder[0]["command"]
    assert ladder[-1]["command"] == build_harbor_command(ExternalCohort())


def test_preregistration_records_the_lock_and_admits_unknowns() -> None:
    record = preregistration(ExternalCohort())
    assert record["dataset"] == DATASET_ALIAS
    assert record["model_id"] == "opencode-go/beam-free"
    assert record["effort"] == "high"
    assert record["attempts"] == 5
    assert record["cost_status"].startswith("UNKNOWN")
    assert record["dataset_version_hash"] == "FILL_AFTER_DOWNLOAD"


def test_feasibility_checks_report_without_installing() -> None:
    checks = feasibility_checks()
    assert set(checks) == {"docker", "uv", "harbor", "architecture", "opencode"}
    for check in checks.values():
        assert isinstance(check["ok"], bool)
        assert check["detail"]


def test_probe_cohort_relaxes_attempts_but_cannot_be_preregistered() -> None:
    probe = ExternalCohort(attempts=1, probe=True)
    assert probe.ok
    with pytest.raises(ValueError, match="probe cohorts"):
        preregistration(probe)
