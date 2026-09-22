"""What the script must do. Says nothing about how it must be written.

Two platform facts are handled here so the test measures the script and not
the shell it happens to land in: the interpreter is resolved with
``shutil.which`` (the same lookup the harness uses, which finds the Git/MSYS
bash rather than the WSL launcher Windows keeps in System32), and every path
handed to it is relative to this repository, because an absolute Windows path
does not survive the trip through an argument on either bash.
"""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent
SCRIPT = "tools/summarize.sh"
SAMPLES = "tools/samples"
BASH = shutil.which("bash") or "bash"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, SCRIPT, *args], cwd=REPO,
                          capture_output=True, text=True)


def test_one_line_per_file():
    done = run([SAMPLES])
    assert done.returncode == 0, done.stderr
    assert sorted(done.stdout.splitlines()) == ["a.txt: 2 lines", "b.txt: 3 lines"]


def test_refuses_a_missing_directory():
    done = run(["tools/nowhere"])
    assert done.returncode != 0
    assert (done.stdout + done.stderr).strip() != ""


def test_refuses_without_an_argument():
    done = run([])
    assert done.returncode != 0
    assert (done.stdout + done.stderr).strip() != ""
