from __future__ import annotations

import asyncio
import multiprocessing
import time

import pytest
from fastapi.testclient import TestClient

from oneiro.graph_worker import GraphWorker
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
