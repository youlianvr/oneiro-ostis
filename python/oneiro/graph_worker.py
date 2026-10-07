"""One graph lane in an owned process; stalled sockets cannot freeze HTTP.

Only this process connects sc-client. Queue admission is finite, and each call
has a hard deadline including worker startup. Killing a stuck graph worker does
not kill the server; its graph-owned pending publication is recovered by the
next worker. An interrupted write is uncertain, never reported as absent.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import multiprocessing
import time
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from oneiro.query import GraphQueryError
from oneiro.records import decode
from oneiro.store import MAX_LINK_BYTES
from oneiro.checkpoints import SnapshotBinding, DurabilityGate, snapshot, verify_binding


def _serve(connection: Any, url: str, stream: str, lease: str, scan_limit: int) -> None:
    # All imports and connect happen under the parent's process deadline.
    client = None
    store = None
    try:
        client = importlib.import_module("sc_client.client")
        from oneiro.sc_graph import ScLinkGraph
        from oneiro.store import RecordStore
        client.connect(url)
        store = RecordStore(ScLinkGraph(), stream, Path(lease), scan_limit=scan_limit)
        store.__enter__()
        connection.send({"ready": True})
        while True:
            request = connection.recv()
            if request is None:
                break
            operation, arguments = request
            try:
                result: Any
                if operation == "page":
                    result = asdict(store.page(**arguments))
                elif operation == "entity":
                    record = store.entity(arguments["record_id"])
                    result = record.to_dict() if record is not None else None
                elif operation == "checkpoint":
                    sequence = store.page(limit=1).candidates
                    result = {**store.graph.checkpoint(), "sequence": sequence, "stream": stream}
                elif operation == "append":
                    publication = store.append(decode(arguments["record"]), arguments["operation_id"],
                                               expected_revision=arguments.get("expected_revision", 0))
                    result = {"entry": publication.entry, "address": publication.address,
                              "sequence": publication.sequence, "revision": publication.revision,
                              "record": publication.record.to_dict(), "duplicate": publication.duplicate,
                              "durable": publication.durable}
                else:
                    raise GraphQueryError("bad_operation", "unsupported graph worker operation")
                connection.send({"result": result})
            except GraphQueryError as exc:
                connection.send({"error": exc.code, "reason": exc.reason})
            except (ValueError, TypeError, KeyError):
                connection.send({"error": "invalid_record", "reason": "record or request fails its contract"})
    except (EOFError, BrokenPipeError):
        pass  # parent closed its owned IPC channel
    except GraphQueryError as exc:
        connection.send({"error": exc.code, "reason": exc.reason})
    except ImportError:
        connection.send({"error": "client_missing", "reason": "install the locked graph extra"})
    except Exception:
        # Do not leak model/account data in arbitrary dependency exception text.
        connection.send({"error": "graph_worker_failed", "reason": "graph worker could not complete"})
    finally:
        if store is not None:
            store.close()
        if client is not None:
            client.disconnect()
        connection.close()


class GraphWorker:
    def __init__(self, url: str, stream: str, lease_path: Path,
                 *, timeout: float = 10.0, capacity: int = 16, scan_limit: int = 2000,
                 snapshot_binding: SnapshotBinding | None = None) -> None:
        if timeout <= 0 or type(capacity) is not int or capacity < 1:
            raise ValueError("positive timeout and capacity required")
        self.url, self.stream, self.lease_path = url, stream, lease_path
        self.timeout, self.capacity, self.scan_limit = timeout, capacity, scan_limit
        self.snapshot_binding = snapshot_binding
        self.durability = DurabilityGate(snapshot_binding.max_loss_seconds if snapshot_binding else 300)
        self._context = multiprocessing.get_context("spawn")
        self._process: Any = None
        self._connection: Any = None
        self._lane = asyncio.Lock()
        self._admitted = 0
        self._closing = False

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process is not None else None

    def _stop(self) -> None:
        process, connection = self._process, self._connection
        self._process = self._connection = None
        self.durability.fail("graph_worker_restarted")
        if connection is not None:
            connection.close()
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            if process.is_alive():
                raise GraphQueryError("worker_stop_failed", "owned graph worker is still running")
            process.close()

    def _start(self) -> None:
        parent, child = self._context.Pipe()
        process = self._context.Process(target=_serve,
            args=(child, self.url, self.stream, str(self.lease_path), self.scan_limit), daemon=True)
        self._connection, self._process = parent, process
        try:
            process.start()
        except BaseException:
            parent.close()
            self._connection = self._process = None
            raise
        finally:
            child.close()

    async def _receive(self, deadline: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        while loop.time() < deadline:
            if self._connection.poll():
                # poll can mean only a frame header arrived. recv must not
                # synchronously wait for its remaining body on the HTTP loop.
                try:
                    return await asyncio.wait_for(
                        asyncio.to_thread(self._connection.recv), timeout=max(0.001, deadline - loop.time()))
                except TimeoutError:
                    raise GraphQueryError("graph_timeout", "graph response frame stalled") from None
            if not self._process.is_alive():
                raise GraphQueryError("graph_worker_failed", "owned graph worker exited")
            await asyncio.sleep(0.01)
        raise GraphQueryError("graph_timeout", "graph deadline exceeded; write outcome may be uncertain")

    @staticmethod
    def _result(response: dict[str, Any]) -> Any:
        if "error" in response:
            raise GraphQueryError(response["error"], response["reason"])
        return response.get("result")

    async def call(self, operation: str, **arguments: Any) -> Any:
        if operation == "checkpoint":
            return await self.checkpoint()
        return await self._call(operation, arguments)

    async def _call(self, operation: str, arguments: dict[str, Any],
                    binding: SnapshotBinding | None = None) -> Any:
        if self._closing:
            raise GraphQueryError("store_closed", "graph lane is closed")
        if self._admitted >= self.capacity:
            raise GraphQueryError("graph_busy", "graph lane admission bound reached")
        # Refuse oversized local IPC before serialization into a pipe. This
        # bounds dispatch even when a caller bypasses the HTTP body validator.
        try:
            request_size = len(json.dumps(arguments, allow_nan=False).encode("utf-8"))
        except (ValueError, TypeError):
            raise GraphQueryError("invalid_record", "request is not finite JSON") from None
        if request_size > MAX_LINK_BYTES:
            raise GraphQueryError("record_too_large", "graph IPC request exceeds its bound")
        self._admitted += 1
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        acquired = False
        try:
            try:
                await asyncio.wait_for(self._lane.acquire(), timeout=self.timeout)
                acquired = True
            except TimeoutError:
                raise GraphQueryError("graph_busy", "graph lane queue deadline exceeded") from None
            if self._closing:
                raise GraphQueryError("store_closed", "graph lane is closed")
            if binding is not None:
                await asyncio.to_thread(verify_binding, binding, self.url)
            if self._process is None:
                self._start()
                startup = await self._receive(deadline)
                self._result(startup)
                if startup.get("ready") is not True:
                    raise GraphQueryError("graph_worker_failed", "worker did not become ready")
            # Writes may contain up to one bounded record; callers validate HTTP
            # buffering. Pipe send runs off the event loop too.
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise GraphQueryError("graph_timeout", "graph deadline exceeded before dispatch")
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self._connection.send, (operation, arguments)), timeout=remaining)
            except TimeoutError:
                raise GraphQueryError("graph_timeout", "graph dispatch timed out; write outcome unknown") from None
            response = await self._receive(deadline)
            result = self._result(response)
            if binding is not None:
                # Host-side copy subprocess is owned here, never orphaned if
                # the graph worker is terminated. Keep the writer lane held.
                cancelled = threading.Event()
                copy = asyncio.create_task(asyncio.to_thread(snapshot, binding, lambda: result, cancelled))
                try:
                    result = await asyncio.wait_for(asyncio.shield(copy), timeout=max(0.001, deadline - loop.time()))
                except (TimeoutError, asyncio.CancelledError):
                    cancelled.set()
                    # snapshot checks cancellation and reaps its exact docker
                    # subprocess; wait for cleanup before releasing the lane.
                    try:
                        await asyncio.shield(copy)
                    except GraphQueryError:
                        pass
                    raise
            return result
        except (EOFError, OSError):
            if acquired:
                await asyncio.to_thread(self._stop)
            raise GraphQueryError("server_unreachable", "graph worker IPC interrupted; write outcome unknown") from None
        except (GraphQueryError, TimeoutError, asyncio.CancelledError):
            # Only the request holding the lane may stop its process. Never stop
            # another call's worker just because a queued request expired.
            if acquired:
                await asyncio.to_thread(self._stop)
            raise
        finally:
            if acquired:
                self._lane.release()
            self._admitted -= 1

    async def checkpoint(self) -> dict[str, Any]:
        if self.snapshot_binding is None:
            self.durability.fail("snapshot_binding")
            raise GraphQueryError("snapshot_binding", "verified snapshot supervisor is not configured")
        started = time.monotonic()
        try:
            report = await self._call("checkpoint", {}, self.snapshot_binding)
            report["cycle_seconds"] = time.monotonic() - started
            self.durability.confirmed(report, started)
            return report
        except GraphQueryError as exc:
            self.durability.fail(exc.code)
            raise
        except (TimeoutError, asyncio.CancelledError):
            self.durability.fail("checkpoint_interrupted")
            raise

    async def close(self) -> None:
        self._closing = True
        async with self._lane:
            await asyncio.to_thread(self._stop)
