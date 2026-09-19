from ranges import clamp


def test_clamps_low():
    assert clamp(-5, 0, 10) == 0


def test_keeps_value_inside():
    assert clamp(4, 0, 10) == 4


def test_clamps_high():
    assert clamp(99, 0, 10) == 10
