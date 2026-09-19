import pytest

from ranges import clamp


def test_inverted_bounds_raise():
    with pytest.raises(ValueError):
        clamp(5, 10, 0)


def test_bounds_are_inclusive():
    assert clamp(10, 0, 10) == 10
    assert clamp(0, 0, 10) == 0


def test_equal_bounds():
    assert clamp(3, 3, 3) == 3


def test_int_stays_int():
    result = clamp(2, 0, 10)
    assert isinstance(result, int)


def test_floats():
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(2.5, 0.0, 1.0) == 1.0
