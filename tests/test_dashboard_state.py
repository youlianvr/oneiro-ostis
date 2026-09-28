"""The panel's first answer must never wait for the snapshot.

Reading the full snapshot cold takes minutes, and the old first request simply
sat in that read: the page showed «подключение» with an empty screen and no sign
of progress for as long as it lasted, which reads as a dead panel. These tests
pin the new contract at the route level, with the snapshot faked so nothing here
needs a live graph:

  * a cold request answers immediately with `building`, and the build really
    starts in the background - one build, however often the page polls;
  * once something is cached it is served as-is, stale included, while the
    fresh copy is built behind it: polling never waits;
  * a build that fails says so instead of pretending to make progress forever,
    and the failed attempt is not re-run on every poll.

The Flask test client is used on purpose: what is under test is the route's
behavior, not the socket.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
SERVER_PATH = PROJECT / "dashboard" / "server.py"

SNAPSHOT = {
    "subject": None, "strategies": [], "episodes": {}, "subjects": [],
    "consistency": {"episodes": 0, "steps": 0, "transitions": 0, "conflicts": 0},
    "job": {"running": False, "name": None},
    "benchmarks": {"memory": {"rows": []}, "series": {}, "harness": None},
}


@pytest.fixture()
def server(tmp_path, monkeypatch):
    """The real server module with its caches replaced: no live graph, no shared state.

    The settings file is pointed at tmp_path before the import, because the
    module reads the graph address at import time (python/config.py owns it) and
    a test must not depend on - or touch - the owner's settings.
    """
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    spec = importlib.util.spec_from_file_location("oneiro_dashboard_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_state_cache", {})
    monkeypatch.setattr(module, "_building", {})
    monkeypatch.setattr(module, "_build_error", {})
    return module


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_a_cold_request_answers_progress_and_builds_in_the_background(server, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_snapshot(subject):
        started.set()
        release.wait(5)
        return dict(SNAPSHOT, subject=subject)

    monkeypatch.setattr(server, "_snapshot", slow_snapshot)
    client = server.app.test_client()

    began = time.perf_counter()
    first = client.get("/api/state").get_json()
    took = time.perf_counter() - began

    assert took < 1.0                       # the answer did not wait for the graph
    assert first["building"] is True
    assert first["subjects"] == [] and first["strategies"] == []
    for key in ("episodes", "consistency", "job", "benchmarks"):
        assert key in first                  # complete shape: nothing to trip a renderer
    assert started.wait(2.0)                # the snapshot really is being read

    release.set()
    assert wait_until(lambda: "" in server._state_cache)
    second = client.get("/api/state").get_json()
    assert second.get("building") is not True
    assert second["subject"] is None


def test_polling_never_starts_a_second_build(server, monkeypatch):
    calls = {"n": 0}
    release = threading.Event()

    def snapshot(subject):
        calls["n"] += 1
        release.wait(5)
        return dict(SNAPSHOT)

    monkeypatch.setattr(server, "_snapshot", snapshot)
    client = server.app.test_client()
    client.get("/api/state")
    assert wait_until(lambda: calls["n"] == 1)

    for _ in range(5):
        assert client.get("/api/state").get_json()["building"] is True
    time.sleep(0.1)
    assert calls["n"] == 1                  # the page's 4-second poll costs nothing
    release.set()


def test_a_fresh_snapshot_is_served_without_touching_the_graph(server, monkeypatch):
    fresh = dict(SNAPSHOT, marker="fresh")
    with server._state_lock:
        server._state_cache[""] = (time.time(), fresh)

    def must_not_run(subject):
        raise AssertionError("a fresh snapshot must not be rebuilt")

    monkeypatch.setattr(server, "_snapshot", must_not_run)
    payload = server.app.test_client().get("/api/state").get_json()
    assert payload["marker"] == "fresh" and payload.get("building") is not True


def test_stale_data_is_served_while_the_fresh_copy_is_built(server, monkeypatch):
    stale = dict(SNAPSHOT, marker="stale", subjects=["a"])
    with server._state_lock:
        server._state_cache[""] = (time.time() - 3600.0, stale)

    release = threading.Event()

    def slow_snapshot(subject):
        release.wait(5)
        return dict(SNAPSHOT)

    monkeypatch.setattr(server, "_snapshot", slow_snapshot)
    client = server.app.test_client()

    began = time.perf_counter()
    payload = client.get("/api/state").get_json()
    took = time.perf_counter() - began

    assert took < 1.0
    assert payload["marker"] == "stale" and payload.get("building") is not True
    assert wait_until(lambda: server._building.get("") is True)   # refresh did start
    release.set()


def test_a_failed_build_is_reported_instead_of_spinning_forever(server, monkeypatch):
    attempts = {"n": 0}

    def broken(subject):
        attempts["n"] += 1
        raise RuntimeError("граф недоступен")

    monkeypatch.setattr(server, "_snapshot", broken)
    client = server.app.test_client()

    assert client.get("/api/state").get_json()["building"] is True
    assert wait_until(lambda: server._build_error.get(""))

    failed = client.get("/api/state").get_json()
    assert failed["building"] is False
    assert failed["error"] == "граф недоступен"

    time.sleep(0.05)
    assert client.get("/api/state").get_json()["error"] == "граф недоступен"
    time.sleep(0.05)
    assert attempts["n"] == 1               # within the pause, no new attempt


def test_after_the_pause_the_build_is_retried(server, monkeypatch):
    monkeypatch.setattr(server, "BUILD_RETRY_PAUSE", 0.2)
    outcomes = {"n": 0}

    def flaky(subject):
        outcomes["n"] += 1
        if outcomes["n"] == 1:
            raise RuntimeError("сеть не отвечает")
        return dict(SNAPSHOT, subjects=["a"])

    monkeypatch.setattr(server, "_snapshot", flaky)
    client = server.app.test_client()

    client.get("/api/state")
    assert wait_until(lambda: server._build_error.get(""))
    assert client.get("/api/state").get_json()["error"] == "сеть не отвечает"

    time.sleep(0.25)
    assert client.get("/api/state").get_json()["building"] is True
    assert wait_until(lambda: "" in server._state_cache)
