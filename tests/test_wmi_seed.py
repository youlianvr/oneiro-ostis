"""The WMI seed: prove it answers, and prove it answers fast.

On this machine `platform.system()`, `platform.processor()` and
`platform.win32_ver()` never return (the query goes to an unhealed WMI
service), and everything that touches them - the console's WSGI server while
importing, pip and ensurepip while installing - stops dead with nothing on
screen. `scripts/wmi-seed/sitecustomize.py` is the answer, and this test runs a
child interpreter with it on `PYTHONPATH` so the questions are asked the way a
child process asks them.

A hang fails the test through its timeout: a few seconds is a pass, thirty is
not. The questions are asked in one child, because the failure mode is a
process that never comes back, not a wrong value.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "scripts" / "wmi-seed"
ASK = (
    "import platform\n"
    "print('system:', platform.system())\n"
    "print('uname:', tuple(platform.uname()))\n"
    "print('processor:', platform.processor())\n"
    "print('win32_ver:', platform.win32_ver())\n"
)


def test_the_seed_answers_the_windows_questions_without_reaching_wmi():
    result = subprocess.run(
        [sys.executable, "-c", ASK],
        env={**os.environ, "PYTHONPATH": str(SEED_DIR)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "system:" in result.stdout
    assert "uname:" in result.stdout
    assert "processor:" in result.stdout
    assert "win32_ver:" in result.stdout


def test_the_seed_file_is_where_the_launcher_looks_for_it():
    """The one caller left loads it by path.

    There used to be a second caller: the retired CowAgent console install route
    (`scripts/install.py`) copied the seed into that virtualenv's `site-packages`.
    The route and `console/` were deleted on 2026-10-13, so this test now pins the
    caller that remains - but the seed itself stays, because the hang it answers is
    a property of this machine, not of the route that installed the console.
    """
    assert (SEED_DIR / "sitecustomize.py").is_file()
    launcher = (Path(__file__).resolve().parent.parent / "scripts" / "oneiro-app.py").read_text(
        encoding="utf-8")
    assert '"wmi-seed"' in launcher
