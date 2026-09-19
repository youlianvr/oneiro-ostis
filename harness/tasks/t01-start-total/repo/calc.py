"""A running total over a list of deltas."""


def running_total(start, deltas):
    """Return the sum of `deltas` on top of `start`."""
    total = 0
    for d in deltas:
        total += d
    return total
