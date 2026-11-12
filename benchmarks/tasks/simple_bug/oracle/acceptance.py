"""Hidden acceptance oracle for the simple-bug task. Applied at evaluation time."""
from __future__ import annotations

from octk.simple import last_n


def test_last_n_basic() -> None:
    assert last_n([1, 2, 3, 4, 5], 2) == [4, 5]


def test_last_n_larger_than_list() -> None:
    assert last_n([1, 2], 5) == [1, 2]


def test_last_n_zero() -> None:
    assert last_n([1, 2, 3], 0) == []


def test_last_n_negative() -> None:
    assert last_n([1, 2, 3], -1) == []
