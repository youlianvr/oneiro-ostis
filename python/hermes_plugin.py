"""Hermes plugin adapter for Oneiro organization events.

Hermes remains the runtime and learning shell. This adapter only translates
verified lifecycle hooks into append-only Oneiro records. It does not import or
modify Hermes state databases, credentials, or memory providers.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional

from bridge import OneiroBridge


class OneiroHermesAdapter:
    """Translate one Hermes session into Oneiro lifecycle events."""

    def __init__(
        self,
        bridge_factory: Callable[[], OneiroBridge] = OneiroBridge,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._bridge_factory = bridge_factory
        self._session_id_factory = session_id_factory or (
            lambda: f"hermes_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        )
        self.bridge: Optional[OneiroBridge] = None
        self.session_id: Optional[str] = None

    def on_session_start(self, **kwargs: Any) -> None:
        self.bridge = self._bridge_factory()
        self.bridge.connect()
        self.session_id = self._session_id_factory()
        self.bridge.start_life_session(
            self.session_id,
            goals=[{"text": "continue the organization's current work", "origin": "runtime"}],
            self_state={"role": "hermes_runtime", "origin": "runtime"},
        )
        self._record("heartbeat_start", "runtime", {"kwargs": _safe_payload(kwargs)})

    def post_tool_call(self, **kwargs: Any) -> None:
        if self.bridge is None or self.session_id is None:
            return
        tool_name = str(kwargs.get("tool_name", "unknown"))
        self._record("tool_call", "worker", {
            "tool": tool_name,
            "result": _safe_payload(kwargs.get("result")),
        })

    def on_session_end(self, **kwargs: Any) -> None:
        if self.bridge is None or self.session_id is None:
            return
        self._record("heartbeat_end", "runtime", {"reason": _safe_payload(kwargs)})
        self.bridge.finish_life_session(
            self._session(),
            self_state={"last_reason": _safe_payload(kwargs), "origin": "runtime"},
        )
        self.bridge.close()
        self.bridge = None

    def on_session_finalize(self, **kwargs: Any) -> None:
        """Use the same durable boundary for Hermes' finalize hook."""
        self.on_session_end(**kwargs)

    def _record(self, kind: str, role: str, payload: dict) -> None:
        if self.bridge is None or self.session_id is None:
            return
        self.bridge.record_organization_event(
            session_id=self.session_id,
            role=role,
            kind=kind,
            payload=payload,
            origin="hermes",
        )

    def _session(self):
        latest = self.bridge.load_latest_life_session() if self.bridge is not None else None
        if latest is None or latest.session_id != self.session_id:
            raise RuntimeError("Oneiro session was not persisted before Hermes end hook")
        return latest


def _safe_payload(value: Any) -> Any:
    """Keep hook evidence JSON-shaped and bounded by the adapter caller."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_payload(item) for item in value]
    return str(value)


_adapter: Optional[OneiroHermesAdapter] = None


def register(ctx) -> None:
    """Hermes plugin entrypoint for the verified local hook API."""
    global _adapter
    _adapter = OneiroHermesAdapter()
    ctx.register_hook("on_session_start", _adapter.on_session_start)
    ctx.register_hook("post_tool_call", _adapter.post_tool_call)
    ctx.register_hook("on_session_end", _adapter.on_session_end)
    ctx.register_hook("on_session_finalize", _adapter.on_session_finalize)
