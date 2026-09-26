"""Answer `platform` from memory, before anything can reach a hung WMI service.

On this machine the Windows questions that Python's `platform` module answers
through WMI never return: `platform.system()` (the console's WSGI server calls
it while importing), `platform.processor()`, `platform.win32_ver()` and the
virtualenv bootstrap that pip runs all stop dead instead of failing. Nothing
on screen says why - the process just stands there.

This file exists twice over: it is copied into the console virtualenv's
`site-packages` by `scripts/install.py`, where CPython imports it at startup as
`sitecustomize`, and `scripts/oneiro-app.py` loads it by path to protect the
console process itself. `seed()` is the whole fix.

Two traps are worth naming, both measured here:

  * `platform.uname_result` is not a plain namedtuple: iterating it (its
    `__len__` does) reaches `uname_result.processor`, a cached property that
    asks the CPU through WMI. Constructing it by keyword goes through `_make`,
    which iterates too - so even *building* the cache hangs. The seeded object
    below is the same five-field namedtuple with `processor` already known,
    built positionally, and nothing is lazy.
  * `platform.win32_ver()` reaches WMI by itself and is patched for the same
    reason. The values come from `sys.getwindowsversion()` and the environment,
    which is what the platform module falls back to on machines where the
    query is not supported at all.
"""

from __future__ import annotations

import os
import platform
import socket
import sys


def seed() -> None:
    """Fill platform's Windows answers from facts already in memory."""
    if sys.platform != "win32" or getattr(platform, "_uname_cache", None):
        return

    windows = sys.getwindowsversion()
    base = platform.uname_result.__mro__[1]      # the five-field namedtuple

    class _SeededUname(base):
        """A uname_result whose processor is known instead of lazily asked."""

        __slots__ = ()
        processor = os.environ.get("PROCESSOR_IDENTIFIER") or ""

    platform._uname_cache = _SeededUname(
        "Windows",
        socket.gethostname(),
        str(windows.major),
        f"{windows.major}.{windows.minor}.{windows.build}",
        os.environ.get("PROCESSOR_ARCHITECTURE") or "AMD64",
    )

    def win32_ver(release: str = "", version: str = "", csd: str = "", ptype: str = ""):
        """What `platform.win32_ver` would answer, without the WMI round trip."""
        return (str(windows.major), f"{windows.major}.{windows.minor}.{windows.build}", csd, ptype)

    platform.win32_ver = win32_ver


if __name__ == "sitecustomize" or __name__ == "oneiro_wmi_seed":
    seed()
