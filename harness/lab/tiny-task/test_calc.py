from calc import running_total


def test_total_includes_start():
    assert running_total(100, [5, -3]) == 102


def test_total_without_deltas_is_start():
    assert running_total(7, []) == 7
