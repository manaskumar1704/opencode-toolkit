"""Shared fixtures: a per-test scaffolded toolkit root."""

from __future__ import annotations

from pathlib import Path

import pytest

from octk.scaffold import init_repo


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """Temp dir already scaffolded with init_repo."""
    init_repo(tmp_path)
    return tmp_path
