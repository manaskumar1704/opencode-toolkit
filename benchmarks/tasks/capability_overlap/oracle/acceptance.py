from pathlib import Path


def test_choice_is_the_broader_skill():
    answer = Path("CHOICE.md").read_text(encoding="utf-8").strip()
    assert answer == "code-review"
