"""Offline tests for the verified Hermes hook adapter."""

from dataclasses import dataclass

from hermes_plugin import OneiroHermesAdapter, register


@dataclass
class FakeSession:
    session_id: str


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.session = None

    def connect(self):
        self.calls.append(("connect",))

    def close(self):
        self.calls.append(("close",))

    def start_life_session(self, session_id, **kwargs):
        self.session = FakeSession(session_id)
        self.calls.append(("start", session_id, kwargs))
        return self.session

    def record_organization_event(self, **kwargs):
        self.calls.append(("event", kwargs))

    def load_latest_life_session(self):
        return self.session

    def finish_life_session(self, session, **kwargs):
        self.calls.append(("finish", session.session_id, kwargs))


def test_hooks_write_runtime_events_and_close_session():
    bridge = FakeBridge()
    adapter = OneiroHermesAdapter(
        bridge_factory=lambda: bridge,
        session_id_factory=lambda: "hermes-test",
    )

    adapter.on_session_start(source="test")
    adapter.post_tool_call(tool_name="pytest", result={"ok": True})
    adapter.on_session_end(reason="test complete")

    assert bridge.calls[0] == ("connect",)
    event_kinds = [call[1]["kind"] for call in bridge.calls if call[0] == "event"]
    assert event_kinds == ["heartbeat_start", "tool_call", "heartbeat_end"]
    assert any(call[0] == "finish" for call in bridge.calls)
    assert bridge.calls[-1] == ("close",)


def test_register_uses_only_verified_hermes_hooks():
    class Context:
        def __init__(self):
            self.hooks = {}

        def register_hook(self, name, callback):
            self.hooks[name] = callback

    context = Context()
    register(context)
    assert set(context.hooks) == {
        "on_session_start",
        "post_tool_call",
        "on_session_end",
        "on_session_finalize",
    }
