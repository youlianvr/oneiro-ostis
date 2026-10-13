from __future__ import annotations

import asyncio
import multiprocessing
import time

import pytest
from fastapi.testclient import TestClient

from oneiro.graph_worker import GraphWorker, page_budget
from oneiro.query import GraphQueryError
from oneiro.runtime import Runtime
from oneiro.web import create_app


def hung_child(connection):
    connection.send({"ready": True})
    connection.recv()
    time.sleep(60)


class HungWorker(GraphWorker):
    def _start(self):
        parent, child = self._context.Pipe()
        process = self._context.Process(target=hung_child, args=(child,), daemon=True)
        self._connection, self._process = parent, process
        process.start()
        self.last_process = process
        self.last_pid = process.pid
        child.close()


def test_timeout_stops_only_owned_worker_and_does_not_block_control(tmp_path):
    async def scenario():
        worker = HungWorker("unused", "test", tmp_path / "writer.lock", timeout=1.5)
        ticks = []

        async def control():
            for _ in range(10):
                await asyncio.sleep(0.03)
                ticks.append(time.monotonic())
        start = time.monotonic()
        task = asyncio.create_task(control())
        with pytest.raises(GraphQueryError, match="graph_timeout"):
            await worker.call("page")
        await task
        assert len(ticks) == 10
        assert time.monotonic() - start < 5
        assert worker.pid is None
        assert not worker.durability.status()["external_effects_allowed"]
        assert worker.last_pid not in [p.pid for p in multiprocessing.active_children()]
        await worker.close()
    asyncio.run(scenario())


def test_admission_is_bounded_and_cancelled_call_reaps_owned_process(tmp_path):
    async def scenario():
        worker = HungWorker("unused", "test", tmp_path / "writer.lock", timeout=5, capacity=1)
        task = asyncio.create_task(worker.call("page"))
        while worker.pid is None:
            await asyncio.sleep(0.01)
        with pytest.raises(GraphQueryError, match="graph_busy"):
            await worker.call("page")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker.pid is None and worker._admitted == 0
        assert worker.last_pid not in [p.pid for p in multiprocessing.active_children()]
        await worker.close()
        with pytest.raises(GraphQueryError, match="store_closed"):
            await worker.call("page")
    asyncio.run(scenario())


class FakeSave(GraphWorker):
    """A worker whose graph answers one native-Save report and nothing else.

    Used to assert what `save()` promises: the report is passed through and its own words say
    what was *not* established, without a live server and without a snapshot supervisor.
    """

    async def _call(self, operation, arguments, binding=None):
        assert operation == "checkpoint" and arguments == {}
        assert binding is None
        return {"saved": True, "seconds": 0.02, "crash_atomic": False,
                "action_address": 17, "sequence": 3, "stream": self.stream}


def test_a_save_reports_what_it_proved_and_never_claims_durability(tmp_path):
    async def scenario():
        worker = FakeSave("unused", "test", tmp_path / "writer.lock")
        before = worker.durability.status()
        report = await worker.save()
        assert report["saved"] is True
        assert report["durable"] is False
        assert "not claimed" in report["note"]
        # The effect gate is untouched: a save is not a checkpoint, and nothing here may
        # read as permission for an external effect later.
        assert worker.durability.status() == before
        await worker.close()
    asyncio.run(scenario())


def test_a_save_without_a_graph_is_an_error_not_a_claim(tmp_path):
    import socket

    async def scenario():
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            port = blocker.getsockname()[1]
            worker = GraphWorker(f"ws://127.0.0.1:{port}/ws_json", "test",
                                 tmp_path / "writer.lock", timeout=2)
            with pytest.raises(GraphQueryError) as error:
                await worker.save()
            assert error.value.code in ("graph_worker_failed", "graph_timeout",
                                        "server_unreachable")
            assert worker.pid is None
            await worker.close()
    asyncio.run(scenario())


def test_oversized_dispatch_never_starts_a_worker(tmp_path):
    async def scenario():
        worker = GraphWorker("unused", "test", tmp_path / "writer.lock")
        with pytest.raises(GraphQueryError, match="record_too_large"):
            await worker.call("append", record={"body": "x" * 140000})
        assert worker.pid is None and worker._admitted == 0
        await worker.close()
    asyncio.run(scenario())


def test_missing_server_is_an_error_not_an_empty_memory(tmp_path):
    import socket

    async def scenario():
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            port = blocker.getsockname()[1]
            worker = GraphWorker(f"ws://127.0.0.1:{port}/ws_json", "test",
                                 tmp_path / "writer.lock", timeout=2)
            with pytest.raises(GraphQueryError) as error:
                await worker.call("page", limit=5)
            assert error.value.code in ("graph_worker_failed", "graph_timeout")
            assert worker.pid is None
            await worker.close()
    asyncio.run(scenario())


class MemoryLane:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.failure = None

    async def call(self, operation, **arguments):
        self.calls.append((operation, arguments))
        if self.failure:
            raise GraphQueryError(self.failure, "test failure")
        if operation == "entity":
            return None
        return {"items": [{"id": "real-record"}], "cursor": None,
                "candidates": 1, "scanned": 1, "skipped": [], "truncated": False}

    async def close(self):
        self.closed = True


def test_request_consumer_uses_bounded_page_seam_and_reports_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    lane = MemoryLane()
    with TestClient(create_app(Runtime(lane))) as browser:
        response = browser.get("/api/memory/records?limit=3")
        assert response.status_code == 200
        assert response.json()["items"] == [{"id": "real-record"}]
        assert lane.calls == [("page", {"cursor": None, "limit": 3})]
        assert response.json()["order"] == "publication_newest_first"
        assert "access-control-allow-origin" not in response.headers
        for bad in ("0", "501", "1.5", "many"):
            assert browser.get(f"/api/memory/records?limit={bad}").status_code == 400
        assert len(lane.calls) == 1  # validation happens before graph dispatch
        assert browser.get("/api/memory/records/unknown").status_code == 404
        lane.failure = "server_unreachable"
        response = browser.get("/api/memory/records")
        assert response.status_code == 503
        assert response.json()["error"] == "server_unreachable"
        assert response.json()["fallback"] is None
        lane.failure = "bad_cursor"
        assert browser.get("/api/memory/records?cursor=bad").status_code == 400
    assert lane.closed


#: How long the first answer of a page read is held back. It has to outlast both the
#: spawn of the child and the page budget below: a spawned child imports this module and
#: its dependencies, which costs a couple of seconds on an idle machine.
#:
#: Measured 2026-10-13, and the reason these two numbers are what they are: with the
#: budget at 3.0 s the first full-suite run of the day failed here — under load the spawn
#: of the child outlasted the page budget, the read expired before anything was dispatched,
#: and `_fail_lane` took its `never_answered` path and stopped a worker that had only not
#: finished starting. The same test passed three times out of three on its own (9.6–10.8 s).
#: The behaviour under test is unchanged (a page deadline that expires after dispatch keeps
#: the worker and owes its answer); only the margin for a loaded machine is wider.
SLOW_FIRST_DELAY = 16.0

#: The page budget the first read runs out of: longer than a spawn, shorter than the answer.
SHORT_PAGE_BUDGET = 10.0


def slow_first_child(connection):
    connection.send({"ready": True})
    connection.recv()
    time.sleep(SLOW_FIRST_DELAY)
    connection.send({"result": {"which": 1}})
    connection.recv()
    connection.send({"result": {"which": 2}})


class SlowFirstWorker(GraphWorker):
    """A worker whose first answer arrives after the page's own budget has run out."""

    def _start(self):
        parent, child = self._context.Pipe()
        process = self._context.Process(target=slow_first_child, args=(child,), daemon=True)
        self._connection, self._process = parent, process
        process.start()
        self.last_pid = process.pid
        child.close()


def dead_child(connection):
    connection.send({"error": "graph_worker_failed", "reason": "the graph did not come up"})
    time.sleep(10)          # keep the pipe open: the parent reads the error, not EOF


class DeadWorker(GraphWorker):
    """A worker whose child never reaches the graph and says so."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = 0

    def _start(self):
        self.attempts += 1
        parent, child = self._context.Pipe()
        process = self._context.Process(target=dead_child, args=(child,), daemon=True)
        self._connection, self._process = parent, process
        process.start()
        child.close()


def test_a_page_read_that_runs_out_of_budget_keeps_the_worker(tmp_path):
    """A page's deadline must not kill a worker that would have answered.

    Measured 2026-10-11 with a silent graph: cancelling the page read reached the worker's
    stop path, so every page view respawned the worker and closed the durability gate.
    """
    async def scenario():
        worker = SlowFirstWorker("unused", "test", tmp_path / "writer.lock", timeout=15)
        with page_budget(SHORT_PAGE_BUDGET):
            with pytest.raises(GraphQueryError, match="graph_timeout"):
                await worker.call("page")
        assert worker.pid is not None, "a page read killed a worker that would have answered"
        # The abandoned answer is still owed, so the next request must consume it instead
        # of reading it as its own result.
        assert await worker.call("page") == {"which": 2}
        assert worker.pid is not None
        await worker.close()
    asyncio.run(scenario())


def test_a_target_that_never_came_up_is_remembered_and_costs_no_gate(tmp_path):
    """A graph that never comes up is one attempt, not one process per page view.

    Measured 2026-10-11: every /api/tasks view of a silent graph started a worker and
    closed the durability gate, though nothing had been written by it.
    """
    async def scenario():
        worker = DeadWorker("unused", "test", tmp_path / "writer.lock", timeout=10)
        before = worker.durability.status()
        for _ in range(3):
            with page_budget(10.0):
                with pytest.raises(GraphQueryError, match="graph_worker_failed"):
                    await worker.call("page")
        assert worker.attempts == 1, "a page view started a worker per view"
        assert worker.pid is None
        assert worker.durability.status()["failure"] == before["failure"], (
            "a page view closed the durability gate for a graph that never came up")
        await worker.close()
    asyncio.run(scenario())


def silent_child(connection):
    time.sleep(60)          # says nothing at all: neither ready nor an error


class SilentWorker(GraphWorker):
    """A worker whose child never speaks, which is the shape a closed port has."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = 0

    def _start(self):
        self.attempts += 1
        parent, child = self._context.Pipe()
        process = self._context.Process(target=silent_child, args=(child,), daemon=True)
        self._connection, self._process = parent, process
        process.start()
        child.close()


def test_a_closed_port_costs_one_attempt_for_the_window(tmp_path):
    """A target that never answers at all is remembered, however the failure arrives.

    Measured 2026-10-11 with a merely closed port: every page read ended in
    `graph_timeout` on the page budget, the per-target memo never armed (the code was not
    in `DOWN_CODES`), and four reads spawned four workers at 3.0 s each. A closed port
    fails as a timeout, which is the shape this child has.
    """
    async def scenario():
        worker = SilentWorker("unused", "test", tmp_path / "writer.lock", timeout=15)
        before = worker.durability.status()
        waits = []
        for _ in range(3):
            started = time.monotonic()
            with page_budget(SHORT_PAGE_BUDGET):
                with pytest.raises(GraphQueryError, match="graph_timeout"):
                    await worker.call("page")
            waits.append(time.monotonic() - started)
        assert worker.attempts == 1, f"a page view started a worker per view: {worker.attempts}"
        assert waits[0] >= SHORT_PAGE_BUDGET * 0.5, (
            f"the first read did not wait for its own budget: {waits[0]:.1f}s")
        assert max(waits[1:]) < 1.0, (
            f"a remembered target waited the budget again: {[round(w, 2) for w in waits]}")
        assert worker.durability.status()["failure"] == before["failure"], (
            "a page view closed the durability gate for a graph that never came up")
        await worker.close()
    asyncio.run(scenario())


def test_request_modules_do_not_import_legacy_full_log_loaders():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "python" / "oneiro"
    forbidden = {"load_organization_events", "load_life_sessions", "load_strategies",
                 "member_addresses", "load_harnesses", "load_memory_sessions"}
    for name in ("web.py", "runtime.py", "graph_worker.py", "store.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, (name, node.attr)
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "bridge", name
