"""Pantry tests: glance, equip, traversal rejection, error messages."""

from __future__ import annotations

import pytest


def test_glance_includes_index_and_skills_line(tmp_root) -> None:
    skills = tmp_root / ".toolkit" / "skills"
    (skills / "mystyle.md").write_text(
        "---\ndescription: My styling rules\n---\nbody", encoding="utf-8"
    )
    from octk.pantry import glance

    result = glance(tmp_root)
    assert "Current task:" in result.text
    assert "Skills: mystyle (My styling rules)" in result.text
    assert "Specs: architecture, acceptance, user_flow" in result.text or "Specs:" in result.text
    assert result.pruned_chars == len(result.text)


def test_glance_raw_exceeds_pruned_with_large_specs(tmp_root) -> None:
    specs = tmp_root / ".toolkit" / "specs"
    (specs / "big.md").write_text("# big\n" + "x" * 40000, encoding="utf-8")
    from octk.pantry import glance

    result = glance(tmp_root)
    assert result.raw_chars > result.pruned_chars


@pytest.mark.parametrize("bad", ["../x", "a/b", "../../etc/passwd"])
def test_equip_rejects_traversal(tmp_root, bad: str) -> None:
    from octk.pantry import NameError, equip_spec

    with pytest.raises(NameError):
        equip_spec(tmp_root, bad)


def test_equip_missing_lists_available(tmp_root) -> None:
    from octk.pantry import NameError, equip_spec

    with pytest.raises(NameError) as excinfo:
        equip_spec(tmp_root, "nonexistent")
    assert "architecture" in str(excinfo.value)


def test_equip_spec_roundtrip(tmp_root) -> None:
    from octk.pantry import equip_spec

    assert "HLD" in equip_spec(tmp_root, "architecture")


def test_equip_skill_invalid_name(tmp_root) -> None:
    from octk.pantry import NameError, equip_skill

    with pytest.raises(NameError):
        equip_skill(tmp_root, "bad name!")


def test_glance_prefers_registry_description(tmp_root, monkeypatch) -> None:
    from octk.capabilities import record_from_dict, sync_discovered
    from octk.pantry import glance

    monkeypatch.setenv("OCTK_USER_CONFIG", str(tmp_root / "userconfig"))
    skills = tmp_root / ".toolkit" / "skills"
    (skills / "mystyle.md").write_text("# File heading\nbody", encoding="utf-8")
    record = record_from_dict(
        {
            "id": "octk_native:octk/skill-mystyle",
            "type": "octk_native",
            "name": "mystyle",
            "description": "From registry",
            "provenance": "octk_provided",
        },
        scope="project",
    )
    sync_discovered(tmp_root, [record])

    result = glance(tmp_root)

    assert "mystyle (From registry)" in result.text


def test_glance_bounded_read_ignores_far_description(tmp_root) -> None:
    from octk.pantry import glance

    skills = tmp_root / ".toolkit" / "skills"
    body = "x" * 5000 + "\ndescription: too late\n"
    (skills / "late.md").write_text(body, encoding="utf-8")

    result = glance(tmp_root)

    assert "too late" not in result.text
