"""The entrypoint must never clear the knowledge base by accident.

These tests run the real `scripts/docker_entrypoint.sh` with stub binaries, so
they exercise the branch that decided to wipe a live graph on 2026-10-02. A
rebuild must take two explicit signals, and a routine start must leave the
storage alone.

Paths are handed to bash in POSIX form and the parent environment is passed
through in full: Git Bash fails to start from a stripped environment, which
looks like a test failure but is not one.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "scripts" / "docker_entrypoint.sh"
CONFIRMATION = "I_UNDERSTAND_THE_GRAPH_WILL_BE_CLEARED"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required")

# Git ships two bash binaries. `usr\bin\bash.exe` is the bare variant and does
# not translate Windows paths for its own arguments, so a script path handed to
# it arrives with its separators eaten. `bin\bash.exe` is the MSYS launcher and
# does translate, so the test prefers it.
_GIT_BASH = (r"C:\Program Files\Git\bin\bash.exe",
             r"C:\Program Files (x86)\Git\bin\bash.exe")


def _bash() -> str:
    for candidate in _GIT_BASH:
        if os.path.exists(candidate):
            return candidate
    found = shutil.which("bash")
    if found is None:
        raise RuntimeError("bash is required to run the entrypoint")
    return found


def _stubs(tmp_path: Path) -> tuple[Path, Path]:
    """A BINARY_PATH whose sc-builder and sc-machine record that they ran."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = (tmp_path / "calls.log").as_posix()
    for name in ("sc-builder", "sc-machine"):
        script = binaries / name
        script.write_text(
            f'#!/usr/bin/env bash\necho "{name} $*" >> "{log}"\nexit 0\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
    return binaries, tmp_path / "calls.log"


def _run(tmp_path: Path, binaries: Path, storage: Path, **env: str) -> subprocess.CompletedProcess:
    # build_kb refuses a KB path that does not exist, so a real file stands in
    # for the knowledge-base source list.
    sources = tmp_path / "repo.path"
    sources.write_text("ontology/experience.scs\n", encoding="utf-8")
    environment = dict(os.environ)
    environment.update({
        "BINARY_PATH": binaries.as_posix(),
        "CONFIG_PATH": "oneiro.ini",
        "KB_PATH": sources.as_posix(),
        "KB_STORAGE": storage.as_posix(),
        "EXTENSIONS_PATH": "",
        "REBUILD_KB": "0",
        "CONFIRM_KB_CLEAR": "",
    })
    environment.update(env)
    return subprocess.run([_bash(), str(ENTRYPOINT), "run"], capture_output=True,
                          text=True, env=environment, timeout=30)


def _existing_graph(tmp_path: Path) -> Path:
    storage = tmp_path / "kb.bin"
    storage.mkdir()
    (storage / "segments.scdb").write_bytes(b"existing graph")
    return storage


def test_rebuild_without_confirmation_refuses_and_starts_nothing(tmp_path):
    """The exact condition that wiped the graph on 2026-10-02."""
    binaries, log = _stubs(tmp_path)

    result = _run(tmp_path, binaries, _existing_graph(tmp_path), REBUILD_KB="1")

    assert result.returncode == 3, result.stderr
    assert "REFUSING TO CLEAR THE KNOWLEDGE BASE" in result.stderr
    assert CONFIRMATION in result.stderr, "the refusal must say how to really do it"
    assert not log.exists(), "neither sc-builder nor sc-machine may run"


def test_rebuild_with_confirmation_is_allowed(tmp_path):
    binaries, log = _stubs(tmp_path)

    result = _run(tmp_path, binaries, _existing_graph(tmp_path),
                  REBUILD_KB="1", CONFIRM_KB_CLEAR=CONFIRMATION)

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8")
    assert "sc-builder" in calls and "--clear" in calls, "a confirmed rebuild still clears"


def test_wrong_confirmation_phrase_is_refused(tmp_path):
    binaries, log = _stubs(tmp_path)

    result = _run(tmp_path, binaries, _existing_graph(tmp_path),
                  REBUILD_KB="1", CONFIRM_KB_CLEAR="yes")

    assert result.returncode == 3
    assert not log.exists()


def test_existing_graph_starts_without_rebuilding(tmp_path):
    binaries, log = _stubs(tmp_path)

    result = _run(tmp_path, binaries, _existing_graph(tmp_path), REBUILD_KB="0")

    assert result.returncode == 0, result.stderr
    assert "Existing graph found" in result.stdout
    assert "without rebuilding" in result.stdout
    calls = log.read_text(encoding="utf-8")
    assert "sc-machine" in calls
    assert "sc-builder" not in calls, "an existing graph must never be rebuilt on start"


def test_first_run_builds_without_clearing(tmp_path):
    """An empty volume is built once, and that build must not pass --clear."""
    binaries, log = _stubs(tmp_path)
    storage = tmp_path / "kb.bin"
    storage.mkdir()

    result = _run(tmp_path, binaries, storage, REBUILD_KB="0")

    assert result.returncode == 0, result.stderr
    assert "building from sources for the first time" in result.stdout
    calls = log.read_text(encoding="utf-8")
    assert "sc-builder" in calls
    assert "--clear" not in calls, "a first-run build has nothing to clear"


def test_graph_survives_two_routine_starts(tmp_path):
    """Two consecutive routine starts must not rebuild in between."""
    binaries, log = _stubs(tmp_path)
    storage = _existing_graph(tmp_path)

    for _ in range(2):
        assert _run(tmp_path, binaries, storage, REBUILD_KB="0").returncode == 0
    assert log.read_text(encoding="utf-8").count("sc-builder") == 0
