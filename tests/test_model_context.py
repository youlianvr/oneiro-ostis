"""What the model is given before a reply, and what the reply says about it.

The model stub records every message list it receives, so these tests check the
exact context the provider would see, through the same HTTP surface the owner uses.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, Model, csrf_of, isolate, make_app, post
from oneiro import agent, config
from oneiro.query import GraphQueryError
from oneiro.runtime import Runtime


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def rules(messages: list[dict]) -> list[dict]:
    """The behavioural preamble every turn starts with, checked and removed.

    It comes first so that the rules are in force before any stored text - the
    owner's facts, earlier messages - reaches the model as content.
    """
    assert messages[0] == {"role": "system", "content": agent.SYSTEM_PROMPT}
    return messages[1:]


def test_the_model_gets_the_facts_then_earlier_messages_oldest_first(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)
        post(client, "/api/memory/facts", {"text": "The owner prefers Russian.", "client_id": "fact-ctx-0001"}, token)
        post(client, "/api/message", {"text": "first", "client_id": "client-ctx-0001"}, token)
        second = post(client, "/api/message", {"text": "second", "client_id": "client-ctx-0002"}, token)
    first_call = rules(model.messages[0])
    assert "The owner prefers Russian." in first_call[0]["content"]
    assert first_call[0]["role"] == "system"
    assert first_call[1:] == [{"role": "user", "content": "first"}]
    later_call = rules(model.messages[-1])
    assert later_call == [
        {"role": "system", "content": later_call[0]["content"]},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer:first"},
        {"role": "user", "content": "second"},
    ]
    assert later_call[0]["content"] == first_call[0]["content"]
    assert second.json()["context"] == {"status": "complete", "facts": 1, "history": 2, "notes": []}


def test_the_character_limit_drops_the_oldest_messages_and_says_so(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    config.save({"chat.context_chars": 25})
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)
        for number in (1, 2, 3):
            post(client, "/api/message", {"text": f"message {number}",
                                          "client_id": f"client-budget-000{number}"}, token)
        last = post(client, "/api/message", {"text": "message 4", "client_id": "client-budget-0004"}, token)
    # Newest first under a 25-character budget: "answer:message 3" (16) and
    # "message 3" (9) fit exactly; "answer:message 2" would exceed it.
    assert rules(model.messages[-1]) == [
        {"role": "user", "content": "message 3"},
        {"role": "assistant", "content": "answer:message 3"},
        {"role": "user", "content": "message 4"},
    ]
    context = last.json()["context"]
    assert context["status"] == "limited"
    assert any("Older messages were left out" in note for note in context["notes"])


def test_the_history_setting_sends_only_the_newest_messages_and_says_so(tmp_path, monkeypatch):
    model = Model(monkeypatch)
    config.save({"chat.history_messages": 1})
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)
        post(client, "/api/message", {"text": "first", "client_id": "client-hist-0001"}, token)
        post(client, "/api/message", {"text": "second", "client_id": "client-hist-0002"}, token)
        third = post(client, "/api/message", {"text": "third", "client_id": "client-hist-0003"}, token)
    assert rules(model.messages[-1]) == [
        {"role": "assistant", "content": "answer:second"},
        {"role": "user", "content": "third"},
    ]
    context = third.json()["context"]
    assert context["status"] == "limited"
    assert "Only the newest 1 earlier messages are sent." in context["notes"]


def test_a_failed_memory_read_still_answers_and_names_what_was_missing(tmp_path, monkeypatch):
    model = Model(monkeypatch)

    async def unreadable(self, *, cursor=None, limit=None):
        raise GraphQueryError("server_unreachable", "graph is down")

    monkeypatch.setattr(Runtime, "memory_page", unreadable)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        response = post(client, "/api/message", {"text": "still answer", "client_id": "client-ctx-0009"},
                        csrf_of(client))
    assert response.status_code == 200
    assert response.json()["reply"]["text"] == "answer:still answer"
    assert rules(model.messages[-1]) == [{"role": "user", "content": "still answer"}]
    context = response.json()["context"]
    assert context["status"] == "memory_unavailable"
    assert any("graph is down" in note for note in context["notes"])
