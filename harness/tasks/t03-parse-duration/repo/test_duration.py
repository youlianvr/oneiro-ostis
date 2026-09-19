from duration import parse_duration


def test_seconds():
    assert parse_duration("45s") == 45


def test_hours_only():
    assert parse_duration("2h") == 7200


def test_hours_and_minutes():
    assert parse_duration("1h30m") == 5400
