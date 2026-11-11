from pathlib import Path


def test_region_is_correct():
    answer = Path("ANSWER.md").read_text(encoding="utf-8").strip()
    assert answer == "eu-west-2"
