"""Tiny module with one bug: the running total ignores the starting balance."""


def running_total(start, deltas):
    """Sum `deltas` on top of `start`."""
    total = start
    for d in deltas:
        total += d
    return total
