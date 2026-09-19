import pytest

from retry import retry


def test_backoff_doubles_and_no_sleep_after_last_failure():
    delays = []

    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry(always_fails, attempts=3, base_delay=0.5, sleep=delays.append)

    assert delays == [0.5, 1.0]


def test_fatal_exception_is_not_retried():
    calls = []

    def fatally_broken():
        calls.append(1)
        raise KeyError("fatal")

    with pytest.raises(KeyError):
        retry(fatally_broken, attempts=5, sleep=lambda _: None, fatal=(KeyError,))

    assert len(calls) == 1


def test_single_attempt():
    delays = []

    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        retry(always_fails, attempts=1, base_delay=2.0, sleep=delays.append)

    assert delays == []


def test_returns_value_without_sleep():
    delays = []
    assert retry(lambda: 42, attempts=3, sleep=delays.append) == 42
    assert delays == []
