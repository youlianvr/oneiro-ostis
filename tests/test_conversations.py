"""Conversations: many threads of messages, each kept and listed from the graph."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, Model, csrf_of, isolate, make_app, post


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def _say(client: TestClient, conversation: str, text: str, client_id: str):
    return post(client, "/api/message", {"text": text, "client_id": client_id,
                                         "conversation_id": conversation}, csrf_of(client))


def test_each_conversation_lists_only_its_own_messages_in_order(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "alpha-conv", "plan the trip", "client-conv-0001")
        _say(client, "beta-conv", "buy milk", "client-conv-0002")
        _say(client, "alpha-conv", "add the hotel", "client-conv-0003")
        listing = client.get("/api/conversations").json()
        alpha = client.get("/api/conversations/alpha-conv/messages").json()
        beta = client.get("/api/conversations/beta-conv/messages").json()
    summaries = {item["conversation_id"]: item for item in listing["conversations"]}
    assert summaries["alpha-conv"]["title"] == "add the hotel"  # newest owner text
    assert summaries["alpha-conv"]["messages"] == 4
    assert summaries["beta-conv"]["messages"] == 2
    assert [m["text"] for m in alpha["messages"]] == [
        "plan the trip", "answer:plan the trip", "add the hotel", "answer:add the hotel"]
    assert [m["text"] for m in beta["messages"]] == ["buy milk", "answer:buy milk"]
    assert alpha["complete"] is True


def test_a_new_conversation_id_is_fresh_and_unused(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)
        first = client.post("/api/conversations", headers={"X-Oneiro-CSRF": token}).json()
        second = client.post("/api/conversations", headers={"X-Oneiro-CSRF": token}).json()
        assert first["conversation_id"] != second["conversation_id"]
        empty = client.get(f"/api/conversations/{first['conversation_id']}/messages").json()
        assert empty["messages"] == []
        _say(client, first["conversation_id"], "hello there", "client-conv-0004")
        listing = client.get("/api/conversations").json()
    assert first["conversation_id"] in {c["conversation_id"] for c in listing["conversations"]}


def test_history_survives_a_restart(tmp_path, monkeypatch):
    Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        _say(client, "gamma-conv", "remember this", "client-conv-0005")
    with TestClient(make_app(tmp_path, links)) as client:
        history = client.get("/api/conversations/gamma-conv/messages").json()
        listing = client.get("/api/conversations").json()
    assert [m["text"] for m in history["messages"]] == ["remember this", "answer:remember this"]
    assert [c["conversation_id"] for c in listing["conversations"]] == ["gamma-conv"]


def test_a_limit_returns_the_newest_messages_and_says_the_rest_is_older(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        for number in range(3):
            _say(client, "delta-conv", f"message {number}", f"client-conv-010{number}")
        limited = client.get("/api/conversations/delta-conv/messages?limit=2").json()
    assert [m["text"] for m in limited["messages"]] == ["message 2", "answer:message 2"]
    assert limited["complete"] is False


def test_the_same_client_id_cannot_move_to_another_conversation(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "one-conv", "shared text", "client-conv-0020")
        moved = _say(client, "two-conv", "shared text", "client-conv-0020")
    assert moved.status_code == 409


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "semi;colon", ""])
def test_a_malformed_conversation_id_is_refused(tmp_path, monkeypatch, bad):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        response = post(client, "/api/message", {"text": "hi", "client_id": "client-conv-0030",
                                                 "conversation_id": bad}, csrf_of(client))
        assert response.status_code == 400
        assert client.get(f"/api/conversations/{bad}/messages").status_code in (400, 404)
