from pathlib import Path


def test_selector_fixed():
    text = Path("app/index.html").read_text(encoding="utf-8")
    assert 'getElementById("go")' in text
    assert 'getElementById("g0")' not in text
