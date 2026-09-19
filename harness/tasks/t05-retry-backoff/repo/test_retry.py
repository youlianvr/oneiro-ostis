from retry import retry


def test_returns_first_successful_value():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("boom")
        return "ok"

    assert retry(flaky, attempts=3, sleep=lambda _: None) == "ok"
    assert len(calls) == 2


def test_raises_after_attempts_exhausted():
    import pytest

    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry(always_fails, attempts=2, sleep=lambda _: None)
