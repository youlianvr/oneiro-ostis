"""Parse short duration strings such as '1h30m' or '45s'."""

import re

UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Return the number of seconds described by `text`."""
    hours = re.match(r"^(\d+)h$", text)
    if hours:
        return int(hours.group(1)) * UNITS["h"]
    seconds = re.match(r"^(\d+)s$", text)
    if seconds:
        return int(seconds.group(1))
    raise ValueError(f"cannot parse duration: {text!r}")
