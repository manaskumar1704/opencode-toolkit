"""Capability Selector tests: ranking, native preference, dedupe, explanations."""

from __future__ import annotations

from octk.capabilities import record_from_dict
from octk.selector import select


def _record(
    cap_id: str,
    *,
    name: str,
    description: str,
    cap_type: str = "skill",
    activation: str = "enabled",
):
    return record_from_dict(
        {
            "id": cap_id,
            "type": cap_type,
            "name": name,
            "description": description,
            "activation": activation,
        },
        scope="project",
    )


def test_selects_by_term_overlap() -> None:
    records = [
        _record("skill:demo/review", name="review", description="Review a diff for bugs"),
        _record("skill:demo/deploy", name="deploy", description="Deploy to production"),
    ]

    result = select("review this pull request diff", records)

    assert result.selected
    assert result.selected[0].record.name == "review"
    assert "matched" in result.selected[0].reason


def test_prefers_native_over_octk_native_on_tie() -> None:
    native = _record(
        "skill:demo/search", name="search", description="Search the repository", cap_type="skill"
    )
    wrapper = _record(
        "octk_native:octk/search",
        name="search",
        description="Search the repository",
        cap_type="octk_native",
    )

    result = select("search the repository", [wrapper, native])

    assert result.selected[0].record.type == "skill"


def test_deduplicates_by_name() -> None:
    first = _record(
        "skill:alpha/review", name="review", description="Review code for issues"
    )
    second = _record(
        "skill:beta/review", name="review", description="Review code for issues"
    )

    result = select("review code", [first, second])

    assert len(result.selected) == 1
    assert result.skipped
    assert "duplicate name" in result.skipped[0].reason


def test_skips_unavailable_records() -> None:
    disabled = _record(
        "skill:demo/review",
        name="review",
        description="Review code",
        activation="disabled",
    )

    result = select("review code", [disabled])

    assert result.empty


def test_empty_task_selects_nothing() -> None:
    records = [_record("skill:demo/review", name="review", description="Review code")]
    assert select("", records).empty


def test_no_overlap_selects_nothing() -> None:
    records = [_record("skill:demo/deploy", name="deploy", description="Deploy to prod")]
    assert select("write a unit test", records).empty


def test_respects_limit() -> None:
    records = [
        _record(f"skill:demo/{n}", name=n, description="Search the repository")
        for n in ("alpha", "beta", "gamma")
    ]

    result = select("search repository", records, limit=2)

    assert len(result.selected) == 2
    assert len(result.skipped) == 1


def test_to_text_is_explainable() -> None:
    records = [_record("skill:demo/review", name="review", description="Review code")]
    text = select("review code", records).to_text()
    assert "Selected (1)" in text
    assert "review [skill]" in text
    assert "score=" in text
