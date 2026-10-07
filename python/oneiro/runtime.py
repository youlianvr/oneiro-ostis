"""Application lifecycle and prerequisites, not a fake substitute agent."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import socket
import time
import uuid
from typing import Any

from oneiro import __version__
from oneiro import config
from oneiro.ownership import FileLease
from oneiro.graph_worker import GraphWorker
from oneiro.query import GraphQueryError


class Runtime:
    def __init__(self, graph: GraphWorker | None = None) -> None:
        self.instance_id = uuid.uuid4().hex
        self.started_at: float | None = None
        self._lease: FileLease | None = None
        self._probe_lock = asyncio.Lock()
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._graph = graph

    async def start(self) -> None:
        if self._lease is not None:
            raise RuntimeError("Runtime already started")
        lease = FileLease(config.data_root() / "runtime.lock")
        lease.acquire()
        self._lease = lease
        try:
            if self._graph is None:
                host, port = str(config.value("graph.host")), int(config.value("graph.port"))
                self._graph = GraphWorker(f"ws://{host}:{port}/ws_json", "product",
                                          config.data_root() / "graph-writer.lock")
        except BaseException:
            lease.release()
            self._lease = None
            raise
        self.started_at = time.time()

    async def close(self) -> None:
        if self._graph is not None:
            await self._graph.close()
            self._graph = None
        if self._lease is not None:
            self._lease.release()
            self._lease = None
        self.started_at = None

    async def memory_page(self, *, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        if self._graph is None:
            raise GraphQueryError("store_closed", "runtime is not started")
        return await self._graph.call("page", cursor=cursor, limit=limit)

    async def memory_entity(self, record_id: str) -> dict[str, Any] | None:
        if self._graph is None:
            raise GraphQueryError("store_closed", "runtime is not started")
        return await self._graph.call("entity", record_id=record_id)

    async def status(self, *, refresh: bool = False) -> dict[str, Any]:
        async with self._probe_lock:
            if self._cached is None or refresh or time.monotonic() - self._cached_at > 5:
                self._cached = await asyncio.to_thread(self._inspect)
                self._cached_at = time.monotonic()
            return {**self._cached, "instance_id": self.instance_id,
                    "running": self._lease is not None, "version": __version__}

    @staticmethod
    def _inspect() -> dict[str, Any]:
        # A TCP probe proves reachability only. It does not validate vocabulary,
        # graph persistence, provider authorization, model tools or vision.
        host = str(config.value("graph.host"))
        port = int(config.value("graph.port"))
        try:
            with socket.create_connection((host, port), timeout=0.5):
                reachable = True
        except OSError:
            reachable = False
        dependencies = {name: importlib.util.find_spec(name) is not None
                        for name in ("sc_client", "sc_kpm", "websocket")}
        configured = bool(config.value("llm.api_key"))
        return {
            "ready": False,
            "phase": "foundation",
            "memory": {"required": "OSTIS", "tcp_reachable": reachable,
                       "verified": False, "fallback": None},
            "model": {"configured": configured, "verified": False,
                      "reason": "Run a real model capability check after adapter integration"},
            "dependencies": dependencies,
            "docker_cli": bool(shutil.which("docker")),
            "runtime_connected": False,
            "blocked": ["Agent runtime and typed OSTIS adapter are not integrated"
                        ] + ([] if reachable else ["OSTIS server is unreachable"]),
            "settings_error": config.describe()["error"],
            "autostart": False,
            "pid": os.getpid(),
        }
