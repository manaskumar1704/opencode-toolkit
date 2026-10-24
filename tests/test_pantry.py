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
