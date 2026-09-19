import pytest

from duration import parse_duration


def test_minutes_only():
    assert parse_duration("90m") == 5400


def test_all_three_units():
    assert parse_duration("1h2m3s") == 3723


def test_zero():
    assert parse_duration("0s") == 0


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_duration("soon")


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_duration("")
