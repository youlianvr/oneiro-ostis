from dedupe import unique


def test_unhashable_items():
    items = [{"a": 1}, {"a": 1}, {"b": 2}]
    assert unique(items) == [{"a": 1}, {"b": 2}]


def test_empty():
    assert unique([]) == []


def test_mixed_types():
    assert unique([1, "1", 1.0, "1"]) == [1, "1", 1.0]


def test_returns_list():
    assert isinstance(unique((1, 2, 1)), list)
