import pytest

from calc import running_total


def test_zero_start():
    assert running_total(0, [1, 2, 3]) == 6


def test_negative_start():
    assert running_total(-10, [4]) == -6


def test_accepts_tuple():
    assert running_total(5, (1, 2)) == 8


def test_floats():
    assert running_total(0.5, [0.25]) == pytest.approx(0.75)
