"""Search over stored messages. "No match" is claimed only when the whole history was read."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, Model, csrf_of, isolate, make_app, post
from oneiro import recall


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def _say(client: TestClient, text: str, client_id: str, conversation: str = "main"):
    return post(client, "/api/message", {"text": text, "client_id": client_id,
                                         "conversation_id": conversation}, csrf_of(client))


def _search(client: TestClient, query: str):
    return client.get("/api/search", params={"q": query})


def test_a_word_finds_the_message_and_its_conversation(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "the quick brown fox", "client-srch-0001", "fox-conv")
        _say(client, "something else", "client-srch-0002", "other-conv")
        found = _search(client, "brown").json()
    owner_hits = [hit for hit in found["results"] if hit["role"] == "owner"]
    assert [hit["conversation_id"] for hit in owner_hits] == ["fox-conv"]
    assert "brown" in owner_hits[0]["snippet"]
    assert found["complete"] is True
    assert "matching messages in all" in found["note"]


def test_matching_is_case_insensitive_and_needs_every_word(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "The Quick Brown Fox", "client-srch-0003")
        both = _search(client, "brown FOX").json()
        missing = _search(client, "brown cat").json()
    assert any(hit["role"] == "owner" for hit in both["results"])
    assert all(hit["role"] != "owner" for hit in missing["results"])


def test_a_complete_miss_is_stated_as_no_match_in_all_records(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "ordinary words", "client-srch-0004")
        found = _search(client, "nonexistentterm").json()
    assert found["results"] == []
    assert found["complete"] is True
    assert found["note"].startswith("No match in all 2 stored records")


def test_a_bounded_miss_is_never_reported_as_no_match(tmp_path, monkeypatch):
    # Five messages, pages of two, a read bound of three: the answer covers only
    # part of the history, so the note must say so instead of claiming a full miss.
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "needle in the oldest message", "client-srch-0005")
        for number in range(2):
            _say(client, f"filler {number}", f"client-srch-006{number}")
        monkeypatch.setattr(recall, "PAGE", 2)
        monkeypatch.setattr(recall, "MAX_SCANNED", 3)
        found = _search(client, "nonexistentterm").json()
    assert found["results"] == []
    assert found["complete"] is False
    assert "did not cover the whole history" in found["note"]
    assert "No match in all" not in found["note"]


def test_a_match_beyond_the_read_bound_is_not_claimed_absent(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _say(client, "needle in the oldest message", "client-srch-0007")
        for number in range(2):
            _say(client, f"filler {number}", f"client-srch-008{number}")
        monkeypatch.setattr(recall, "PAGE", 2)
        monkeypatch.setattr(recall, "MAX_SCANNED", 3)
        found = _search(client, "needle").json()
    assert found["results"] == []
    assert found["complete"] is False


def test_search_finds_messages_after_a_restart(tmp_path, monkeypatch):
    Model(monkeypatch)
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        _say(client, "remember the lighthouse", "client-srch-0009", "lamp-conv")
    with TestClient(make_app(tmp_path, links)) as client:
        found = _search(client, "lighthouse").json()
    assert [hit["conversation_id"] for hit in found["results"] if hit["role"] == "owner"] == ["lamp-conv"]


@pytest.mark.parametrize("query", [None, "", "   ", "a" * 201, " ".join(["w"] * 7)])
def test_a_bad_query_is_refused(tmp_path, monkeypatch, query):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        params = {} if query is None else {"q": query}
        assert client.get("/api/search", params=params).status_code == 400
