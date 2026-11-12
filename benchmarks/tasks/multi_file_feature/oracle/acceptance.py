from octk.multi_report import summary
from octk.multi_stats import median


def test_median_odd():
    assert median([1, 2, 3]) == 2


def test_median_even():
    assert median([1, 2, 3, 4]) == 2.5


def test_summary_includes_median():
    assert summary([1, 2, 3]) == {"n": 3, "mean": 2.0, "median": 2}
