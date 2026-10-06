from app.modules.reports.lib.score import percent, pooled, score


def test_score_averages_ratios_and_skips_empty_ones():
    assert score([('a', 1, 2), ('b', 3, 3), ('c', 0, 0)]) == 75


def test_score_is_zero_when_nothing_counts():
    assert score([('a', 0, 0)]) == 0


def test_pooled_adds_key_by_key():
    assert pooled([[('a', 1, 2)], [('a', 2, 2), ('b', 0, 1)]]) == [('a', 3, 4), ('b', 0, 1)]


def test_percent_of_nothing_is_none():
    assert percent(0, 0) is None
    assert percent(7, 10) == 70
