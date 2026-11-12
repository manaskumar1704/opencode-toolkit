"""Shared fixtures: a per-test scaffolded toolkit root."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from octk.scaffold import init_repo

# Make the top-level benchmarks/ package importable from tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True, scope="session")
def isolated_workspaces(tmp_path_factory: pytest.TempPathFactory):
    """Keep test workspaces out of ~/.cache/octk-bench.

    Two pytest runs (or a pytest run next to a live benchmark) would otherwise
    fight over the same ``bench-A-task-r1`` directory.
    """
    import os

    previous = os.environ.get("OCTK_BENCH_WORKSPACE")
    os.environ["OCTK_BENCH_WORKSPACE"] = str(
        tmp_path_factory.mktemp("octk-bench-workspaces")
    )
    yield
    if previous is None:
        os.environ.pop("OCTK_BENCH_WORKSPACE", None)
    else:
        os.environ["OCTK_BENCH_WORKSPACE"] = previous


@pytest.fixture(scope="session", autouse=True)
def _isolated_bench_workspaces(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Give every test process its own workspace root.

    Benchmark workspaces are named after (arm, task, rep). Without this, two
    concurrent test runs share ``~/.cache/octk-bench/bench-A-task-r1`` and one
    recreates it while the other is running the oracle.
    """
    os.environ["OCTK_BENCH_WORKSPACE"] = str(
        tmp_path_factory.mktemp("bench-workspaces")
    )


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """Temp dir already scaffolded with init_repo."""
    init_repo(tmp_path)
    return tmp_path
