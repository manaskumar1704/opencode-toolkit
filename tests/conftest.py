"""Shared fixtures: a per-test scaffolded toolkit root."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from octk.scaffold import init_repo

# Make the top-level benchmarks/ package importable from tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """Temp dir already scaffolded with init_repo."""
    init_repo(tmp_path)
    return tmp_path
