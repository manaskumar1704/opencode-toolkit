from pathlib import Path


def test_answer_names_pantry():
    answer = Path("ANSWER.md").read_text(encoding="utf-8").strip()
    assert answer == "octk/pantry.py"
