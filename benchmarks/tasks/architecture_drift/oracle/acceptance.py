import inspect

from octk.drift_target import build_user


def test_signature_matches_contract():
    assert list(inspect.signature(build_user).parameters) == ["name", "age"]


def test_output_matches_contract():
    assert build_user("a", 30) == {"name": "a", "age": 30}
