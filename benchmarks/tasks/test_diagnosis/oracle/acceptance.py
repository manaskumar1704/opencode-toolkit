from octk.diag_source import parse_pairs


def test_blank_lines_ignored():
    assert parse_pairs("a=1\n\nb=2") == {"a": "1", "b": "2"}


def test_single_pair():
    assert parse_pairs("x=9") == {"x": "9"}
