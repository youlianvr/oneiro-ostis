"""Native memory: OSTIS is the durable truth, never a silent local fallback."""
from __future__ import annotations

import copy
import threading
import time
import uuid

ROLES = ("manager", "researcher", "executor")
SESSION = "oneiro-native-life"


class MemoryUnavailable(RuntimeError):
    pass


class EventMemory:
    def append(self, kind: str, actor: str, data: dict, *, origin: str = "runtime") -> dict:
        raise NotImplementedError

    def events(self) -> list[dict]:
        raise NotImplementedError

    def latest(self, kind: str) -> dict[str, dict]:
        result = {}
        for event in self.events():
            if event["kind"] == kind:
                result[event["data"]["id"]] = copy.deepcopy(event["data"])
        return result

    def notes(self, role: str | None = None, query: str = "", limit: int = 40) -> list[dict]:
        return [e for e in self.events() if e["kind"] == "note"
                and (not role or e["actor"] == role)
                and query.casefold() in str(e["data"]).casefold()][-limit:]


class GraphMemory(EventMemory):
    """Serialises calls to the existing process-global sc-client connection."""
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.lock = threading.RLock()
        self.connected = bridge is not None
        self.cache = None
        self.cache_at = 0.0

    def _connect(self):
        if not self.connected:
            from bridge import OneiroBridge
            self.bridge = OneiroBridge()
            self.bridge.connect()
            self.connected = True

    def append(self, kind, actor, data, *, origin="runtime"):
        with self.lock:
            try:
                self._connect()
                event = {"id": uuid.uuid4().hex, "at": time.time_ns(), "kind": kind,
                         "actor": actor, "origin": origin, "data": copy.deepcopy(data)}
                self.bridge.record_native_event(event, session_id=SESSION)
                if self.cache is not None:
                    self.cache.append(copy.deepcopy(event))
                return event
            except Exception as exc:
                raise MemoryUnavailable("OSTIS could not persist the native event") from exc

    def events(self):
        with self.lock:
            try:
                self._connect()
                if self.cache is None or time.monotonic() - self.cache_at > 5:
                    rows = self.bridge.load_native_events(session_id=SESSION)
                    events = [copy.deepcopy(row.payload) for row in rows if row.payload.get("id")]
                    self.cache = sorted(events, key=lambda e: (e["at"], e["id"]))
                    self.cache_at = time.monotonic()
                return copy.deepcopy(self.cache)
            except Exception as exc:
                raise MemoryUnavailable("OSTIS could not read native memory") from exc

    def close(self):
        with self.lock:
            if self.bridge:
                self.bridge.close()
            self.connected = False


class TestMemory(EventMemory):
    """Explicit test double; never selected by the launcher or a settings switch."""
    __test__ = False

    def __init__(self):
        self.rows = []
        self.lock = threading.RLock()

    def append(self, kind, actor, data, *, origin="runtime"):
        with self.lock:
            event = {"id": uuid.uuid4().hex, "at": time.time_ns(), "kind": kind,
                     "actor": actor, "origin": origin, "data": copy.deepcopy(data)}
            self.rows.append(event)
            return copy.deepcopy(event)

    def events(self):
        with self.lock:
            return copy.deepcopy(self.rows)
