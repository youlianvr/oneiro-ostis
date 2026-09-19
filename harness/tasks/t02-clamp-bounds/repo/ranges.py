"""Range helpers."""


def clamp(value, lo, hi):
    """Return `value` limited to the closed interval [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
