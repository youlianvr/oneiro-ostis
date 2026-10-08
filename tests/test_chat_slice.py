"""The chat slice: one owner message, one model reply, no duplicates after restart.

The graph is the real RecordStore over an in-memory link graph (see chat_fakes),
so the idempotency under test is the production path. The model is a stub at
the `chat_reply` seam in most tests and a real local HTTP provider for the
transport tests.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chat_fakes import SECRET, MemoryLinks, Model, csrf_of, isolate, make_app, post, stored_page
from oneiro.chat import MAX_REPLY_BYTES, ChatError, chat_reply


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_one_round_trip_stores_both_messages_and_returns_them(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        response = post(client, "/api/message",
                        {"text": "hello owner", "client_id": "client-0001-aaaa"}, csrf_of(client))
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["text"] == "hello owner"
    assert body["user"]["role"] == "owner"
    assert body["reply"]["text"] == "answer:hello owner"
    assert body["reply"]["role"] == "manager"
    assert model.calls == ["hello owner"]


def test_resending_the_same_client_id_returns_the_stored_reply_without_a_model_call(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        token = csrf_of(client)
        first = post(client, "/api/message", {"text": "once", "client_id": "client-0002-bbbb"}, token).json()
        second = post(client, "/api/message", {"text": "once", "client_id": "client-0002-bbbb"}, token).json()
    assert second["user"] == first["user"]
    assert second["reply"] == first["reply"]
    # The retry returns the stored reply: no model call, so no context was built.
    assert second["context"] is None
    assert model.calls == ["once"]


def test_a_restart_does_not_duplicate_messages(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        post(client, "/api/message", {"text": "survive restart", "client_id": "client-0003-cccc"},
             csrf_of(client))
    # A new app instance over the same stored graph: the process restarted.
    with TestClient(make_app(tmp_path, links)) as client:
        again = post(client, "/api/message",
                     {"text": "survive restart", "client_id": "client-0003-cccc"}, csrf_of(client))
        assert again.status_code == 200
        page = stored_page(client)
    texts = sorted(item["text"] for item in page["items"])
    assert texts == ["answer:survive restart", "survive restart"]
    assert model.calls == ["survive restart"]


def test_a_model_outage_is_503_and_keeps_the_owner_message(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    model.failure = "the provider is unreachable (URLError)"
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        token = csrf_of(client)
        down = post(client, "/api/message", {"text": "keep me", "client_id": "client-0004-dddd"}, token)
        assert down.status_code == 503
        assert "unreachable" in down.json()["error"]
        assert SECRET not in down.text
        # The model comes back; the same client_id completes with one copy of each.
        model.failure = None
        up = post(client, "/api/message", {"text": "keep me", "client_id": "client-0004-dddd"}, token)
    assert up.status_code == 200
    assert up.json()["reply"]["text"] == "answer:keep me"
    assert model.calls == ["keep me", "keep me"]


def test_a_client_id_reused_for_different_text_is_a_conflict(tmp_path, monkeypatch):
    Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        token = csrf_of(client)
        post(client, "/api/message", {"text": "first text", "client_id": "client-0005-eeee"}, token)
        clash = post(client, "/api/message", {"text": "other text", "client_id": "client-0005-eeee"}, token)
    assert clash.status_code == 409


@pytest.mark.parametrize("body", [
    "not json",
    {"text": "   ", "client_id": "client-0006-ffff"},
    {"text": "x" * 4001, "client_id": "client-0006-ffff"},
    {"text": "ok", "client_id": "short"},
    {"text": "ok"},
])
def test_malformed_requests_are_refused_before_any_graph_write(tmp_path, monkeypatch, body):
    model = Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        raw = body if isinstance(body, str) else json.dumps(body)
        response = client.post("/api/message", content=raw,
                               headers={"X-Oneiro-CSRF": csrf_of(client),
                                        "Content-Type": "application/json"})
    assert response.status_code == 400
    assert links.links == {}
    assert model.calls == []


def test_a_foreign_origin_is_refused(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        response = client.post("/api/message", json={"text": "hi", "client_id": "client-0007-gggg"},
                               headers={"X-Oneiro-CSRF": csrf_of(client),
                                        "Origin": "http://evil.example"})
    assert response.status_code == 403


class _Provider(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        mode = self.server.mode  # type: ignore[attr-defined]
        if mode == "ok":
            status, body = 200, json.dumps({"choices": [{"message": {"content": "  hi there  "}}]})
        elif mode == "unauthorized":
            status, body = 401, json.dumps({"error": f"bad key {SECRET}"})
        else:
            status, body = 200, "x" * (MAX_REPLY_BYTES + 10)
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def provider():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _base(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/v1"


def test_the_transport_returns_the_trimmed_assistant_text(provider):
    provider.mode = "ok"
    text = chat_reply([{"role": "user", "content": "hi"}], base_url=_base(provider),
                      api_key=SECRET, model="auto/coding")
    assert text == "hi there"


def test_a_provider_refusal_reports_the_status_but_never_the_key(provider):
    provider.mode = "unauthorized"
    with pytest.raises(ChatError) as caught:
        chat_reply([{"role": "user", "content": "hi"}], base_url=_base(provider),
                   api_key=SECRET, model="auto/coding")
    assert "HTTP 401" in str(caught.value)
    assert SECRET not in str(caught.value)


def test_an_oversized_reply_is_refused(provider):
    provider.mode = "huge"
    with pytest.raises(ChatError, match="size limit"):
        chat_reply([{"role": "user", "content": "hi"}], base_url=_base(provider),
                   api_key=SECRET, model="auto/coding")


def test_an_unreachable_provider_is_a_chat_error_not_a_crash():
    with pytest.raises(ChatError, match="unreachable"):
        chat_reply([{"role": "user", "content": "hi"}], base_url="http://127.0.0.1:9/v1",
                   api_key=SECRET, model="auto/coding", timeout=3)
