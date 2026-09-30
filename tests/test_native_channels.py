"""Channel contracts: web and Telegram are adapters, not second brains.

Offline throughout: the web tests drive a real HTTP server on a free port with
stdlib urllib, and the Telegram tests hand in a scripted transport. What is
verified is the seam itself — authentication, CSRF, ownership, exact approvals,
and one-time delivery — never a mock of the service underneath.
"""
from __future__ import annotations

import json
import socket
import threading
import types
import urllib.error
import urllib.request

import pytest

from native.memory import TestMemory
from native.service import Oneiro
from native.telegram import Telegram
from native.web import NativeServer


class FakeModel:
    def __init__(self, script=()):
        self.script = list(script)
        self.roles = {}
        self.calls = []

    def reply(self, role, messages, tools=None, budget=None, temperature=None):
        if budget is not None:
            budget.charge(role)
        item = self.script.pop(0) if self.script else {"role": "assistant", "content": "ok"}
        self.calls.append(types.SimpleNamespace(served="fake"))
        return types.SimpleNamespace(message=item, usage={}, model="fake")


@pytest.fixture
def service(tmp_path):
    svc = Oneiro(TestMemory(), FakeModel(), now=lambda: 1_700_000_000.0)
    svc.update_settings({"workspace": str(tmp_path)})
    return svc


# --------------------------------------------------------------------- web

@pytest.fixture
def web(service):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = NativeServer(("127.0.0.1", port), service, access_token="secret-token-value")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def call(base, path, *, method="GET", body=None, cookie="", csrf=""):
    headers = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Oneiro-CSRF"] = csrf
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"{}"), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}"), exc.headers


def signed_in(base):
    status, data, headers = call(base, "/api/login", method="POST", body={})
    assert status == 200
    cookie = headers.get("Set-Cookie", "").split(";")[0]
    return cookie, data["csrf"]


def test_health_answers_without_a_session(web):
    base, _ = web
    status, data, _ = call(base, "/api/health")
    assert status == 200 and data["product"] == "Oneiro"


def test_api_is_closed_until_the_owner_signs_in(web):
    base, _ = web
    status, _, _ = call(base, "/api/state")
    assert status == 401


def test_local_sign_in_seats_a_session_and_requires_csrf_on_writes(web, service):
    base, _ = web
    cookie, csrf = signed_in(base)
    status, _, _ = call(base, "/api/message", method="POST", body={"text": "hi"}, cookie=cookie)
    assert status == 403  # a cookie alone never authorises a write
    status, _, _ = call(base, "/api/message", method="POST", body={"text": "hi"}, cookie=cookie, csrf=csrf)
    assert status == 202
    assert any(row["text"] == "hi" for row in service.messages())


def test_every_answer_is_meant_for_the_same_service(web, service):
    base, _ = web
    cookie, csrf = signed_in(base)
    call(base, "/api/message", method="POST", body={"text": "one"}, cookie=cookie, csrf=csrf)
    call(base, "/api/message", method="POST", body={"text": "two"}, cookie=cookie, csrf=csrf)
    status, state, _ = call(base, "/api/state", cookie=cookie)
    assert status == 200
    texts = [row["text"] for row in state["messages"]]
    assert texts == [row["text"] for row in service.messages()] and "two" in texts


def test_bad_requests_are_refused_with_a_reason(web):
    base, _ = web
    cookie, csrf = signed_in(base)
    status, data, _ = call(base, "/api/decision", method="POST", body={"id": "nope", "approved": True},
                           cookie=cookie, csrf=csrf)
    assert status == 400 and data["error"]
    status, _, _ = call(base, "/api/nothing", method="POST", body={}, cookie=cookie, csrf=csrf)
    assert status == 404


def test_remote_sign_in_needs_the_real_token(web):
    base, server = web
    server.local_only = False  # as if proxied: the token is the door now
    status, _, _ = call(base, "/api/login", method="POST", body={"token": "wrong"})
    assert status == 401
    status, data, headers = call(base, "/api/login", method="POST", body={"token": "secret-token-value"})
    assert status == 200 and data["csrf"]
    assert "HttpOnly" in headers.get("Set-Cookie", "")


# ---------------------------------------------------------------- telegram

OWNER = 4242


class FakeTransport:
    """Scripted Bot API: remembers what was sent, plays back queued updates."""

    def __init__(self):
        self.sent = []
        self.updates = []

    def __call__(self, method, payload):
        self.sent.append((method, dict(payload)))
        if method == "getUpdates":
            rows, self.updates = self.updates, []
            return rows
        return {"message_id": len(self.sent)}


def make_telegram(service, tmp_path):
    transport = FakeTransport()
    bot = Telegram(service, "test-token", OWNER, transport=transport)
    return bot, transport


def owner_message(update_id, text, **extra):
    return {"update_id": update_id,
            "message": {"message_id": update_id, "from": {"id": OWNER},
                        "chat": {"id": OWNER}, "text": text, **extra}}


def test_only_the_owners_words_become_work(service):
    bot, transport = make_telegram(service, None)
    transport.updates = [
        owner_message(1, "sort the tax folder"),
        {"update_id": 2, "message": {"message_id": 2, "from": {"id": 999},
                                     "chat": {"id": OWNER}, "text": "do my bidding"}},
    ]
    bot.poll()
    texts = [row["text"] for row in service.messages()]
    assert texts == ["sort the tax folder"]


def test_duplicate_updates_are_not_taken_twice(service):
    bot, transport = make_telegram(service, None)
    transport.updates = [owner_message(7, "once")]
    bot.poll()
    transport.updates = [owner_message(7, "once")]
    bot.poll()
    assert len(service.messages()) == 1


def test_owner_button_releases_exactly_one_action(service, tmp_path):
    (tmp_path / "gone.txt").write_text("x", encoding="utf-8")
    task = service.create_task("executor", "remove the scratch file")
    result = service.dispatch("delete_file", {"path": "gone.txt"},
                              {"role": "executor", "conversation": "owner", "task_id": task["id"]})
    approval_id = result["approval_required"]
    bot, transport = make_telegram(service, tmp_path)
    press = {"update_id": 3, "callback_query": {"id": "cb1", "from": {"id": OWNER},
             "message": {"chat": {"id": OWNER}}, "data": f"yes:{approval_id}"}}
    transport.updates = [press]
    bot.poll()
    assert not (tmp_path / "gone.txt").exists()
    transport.updates = [dict(press, update_id=4)]  # a stale press must do nothing
    bot.poll()
    assert service.memory.latest("approval")[approval_id]["status"] == "completed"


def test_words_never_release_an_action(service):
    result = service.dispatch("delete_file", {"path": "x"},
                              {"role": "executor", "conversation": "owner", "task_id": ""})
    approval_id = result["approval_required"]
    bot, transport = make_telegram(service, None)
    transport.updates = [owner_message(5, "да, делай")]
    bot.poll()
    assert service.memory.latest("approval")[approval_id]["status"] == "pending"


def test_manager_output_is_delivered_once(service):
    bot, transport = make_telegram(service, None)
    service.emit("message", "manager", {"id": "m1", "side": "manager", "conversation": "owner",
                 "text": "found three things", "channel": "native", "reply_to": "",
                 "at": 1, "status": "completed"}, origin="model")
    bot.flush()
    bot.flush()
    deliveries = [payload["text"] for method, payload in transport.sent if method == "sendMessage"]
    assert deliveries.count("found three things") == 1
