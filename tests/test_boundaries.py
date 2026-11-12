"""Architecture boundary tests.

Core modules must not reach into a specific harness. Only ``octk/adapters/``
is allowed to know OpenCode's layout, config schema, or module names.
"""

from __future__ import annotations

from pathlib import Path

import octk

PACKAGE = Path(octk.__file__).parent


def _core_files() -> list[Path]:
    """Core = top-level modules and runtime; adapters/providers are boundaries.

    ``providers/`` legitimately knows where a harness installs skills and
    plugins - that is provider detection, not core policy.
    """
    return [
        path
        for path in PACKAGE.rglob("*.py")
        if not {"adapters", "providers", "__pycache__"} & set(path.parts)
    ]


def test_only_adapters_import_the_opencode_module() -> None:
    offenders = [
        str(path.relative_to(PACKAGE))
        for path in _core_files()
        if "adapters.opencode" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_core_does_not_hardcode_harness_paths() -> None:
    offenders: list[str] = []
    for path in _core_files():
        text = path.read_text(encoding="utf-8")
        if '".opencode/' in text or "'.opencode/" in text:
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_core_does_not_import_a_model_provider() -> None:
    forbidden = ("import openai", "import anthropic", "from openai", "from anthropic")
    offenders: list[str] = []
    for path in _core_files():
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in forbidden):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_scaffold_gets_harness_files_from_the_adapter() -> None:
    text = (PACKAGE / "scaffold.py").read_text(encoding="utf-8")
    assert "scaffold_managed_files" in text
    assert "opencode" not in text.lower()


def test_doctor_delegates_the_permissions_gate() -> None:
    text = (PACKAGE / "doctor.py").read_text(encoding="utf-8")
    assert "permissions_gate" in text
    assert "opencode" not in text.lower()
