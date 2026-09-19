"""Call a function again when it fails."""


def retry(fn, attempts=3, base_delay=1.0, sleep=None, fatal=()):
    """Call `fn()` up to `attempts` times, returning its value on success."""
    if sleep is None:
        import time

        sleep = time.sleep

    for _ in range(attempts):
        try:
            return fn()
        except Exception:
            continue
    raise RuntimeError("all attempts failed")
