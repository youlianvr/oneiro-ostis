"""Curated memory: short owner facts with a hard size budget, through the HTTP surface.

Facts are a separate record kind from conversation messages. The budget is
checked against what was actually read; if the stored records cannot be read
completely, writes are refused rather than admitted against an unknown total.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, Model, csrf_of, isolate, make_app, post, stored_page
from oneiro import recall


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def _facts(client: TestClient) -> dict:
    response = client.get("/api/memory/facts")
    assert response.status_code == 200
    return response.json()


def _add(client: TestClient, text: str, client_id: str):
    return post(client, "/api/memory/facts", {"text": text, "client_id": client_id}, csrf_of(client))


def _edit(client: TestClient, fact_id: str, text: str, revision: int, client_id: str):
    return post(client, f"/api/memory/facts/{fact_id}/edit",
                {"text": text, "client_id": client_id, "revision": revision}, csrf_of(client))


def _remove(client: TestClient, fact_id: str, revision: int, client_id: str):
    return post(client, f"/api/memory/facts/{fact_id}/remove",
                {"client_id": client_id, "revision": revision}, csrf_of(client))


def test_a_fact_is_stored_listed_and_survives_a_restart(tmp_path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        added = _add(client, "The owner works in Russian.", "fact-client-0001")
        assert added.status_code == 200
        assert added.json()["fact"]["id"] == "fact-fact-client-0001"
    with TestClient(make_app(tmp_path, links)) as client:
        listing = _facts(client)
    assert [fact["text"] for fact in listing["facts"]] == ["The owner works in Russian."]
    assert listing["facts"][0]["revision"] == 1
    assert listing["used_chars"] == len("The owner works in Russian.")
    assert listing["limit_chars"] == 2000
    assert listing["complete"] is True


def test_a_retried_add_with_the_same_client_id_does_not_duplicate(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        first = _add(client, "One fact only.", "fact-client-0002")
        second = _add(client, "One fact only.", "fact-client-0002")
        listing = _facts(client)
    assert first.json()["duplicate"] is False
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert len(listing["facts"]) == 1


def test_the_budget_refuses_a_fact_that_would_exceed_it_and_writes_nothing(tmp_path):
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        assert _add(client, "a" * 1500, "fact-client-0003").status_code == 200
        assert _add(client, "b" * 500, "fact-client-0004").status_code == 200
        before = _facts(client)
        over = _add(client, "c", "fact-client-0005")
        after = _facts(client)
    assert over.status_code == 422
    assert "limited to 2000 characters" in over.json()["error"]
    assert over.json()["used_chars"] == 2000
    assert after["facts"] == before["facts"]
    assert after["used_chars"] == 2000


def test_a_single_fact_longer_than_the_whole_budget_is_a_bad_request(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        response = _add(client, "x" * 2001, "fact-client-0006")
        assert response.status_code == 400
        assert _facts(client)["facts"] == []


def test_an_edit_replaces_the_text_and_advances_the_revision(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        fact_id = _add(client, "Prefers short answers.", "fact-client-0007").json()["fact"]["id"]
        edited = _edit(client, fact_id, "Prefers short, direct answers.", 1, "fact-edit-0007")
        listing = _facts(client)
    assert edited.status_code == 200
    assert listing["facts"][0]["text"] == "Prefers short, direct answers."
    assert listing["facts"][0]["revision"] == 2
    assert listing["used_chars"] == len("Prefers short, direct answers.")


def test_an_edit_from_a_stale_revision_is_a_conflict_and_changes_nothing(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        fact_id = _add(client, "Original.", "fact-client-0008").json()["fact"]["id"]
        assert _edit(client, fact_id, "First change.", 1, "fact-edit-0008").status_code == 200
        stale = _edit(client, fact_id, "Second change.", 1, "fact-edit-0009")
        listing = _facts(client)
    assert stale.status_code == 409
    assert listing["facts"][0]["text"] == "First change."


def test_a_retried_edit_with_the_same_client_id_is_not_applied_twice(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        fact_id = _add(client, "Start.", "fact-client-0010").json()["fact"]["id"]
        first = _edit(client, fact_id, "Changed once.", 1, "fact-edit-0010")
        retry = _edit(client, fact_id, "Changed once.", 1, "fact-edit-0010")
        listing = _facts(client)
    assert first.status_code == 200
    assert retry.status_code == 200 and retry.json()["duplicate"] is True
    assert listing["facts"][0]["revision"] == 2


def test_an_edit_that_would_exceed_the_budget_is_refused(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        small = _add(client, "s" * 10, "fact-client-0011").json()["fact"]["id"]
        _add(client, "b" * 1990, "fact-client-0012")
        over = _edit(client, small, "s" * 11, 1, "fact-edit-0011")
        listing = _facts(client)
    assert over.status_code == 422
    assert listing["facts"][0]["text"] == "s" * 10


def test_a_removed_fact_leaves_the_list_frees_its_budget_and_cannot_be_edited(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        fact_id = _add(client, "To be removed.", "fact-client-0013").json()["fact"]["id"]
        removed = _remove(client, fact_id, 1, "fact-del-0013")
        listing = _facts(client)
        late_edit = _edit(client, fact_id, "Too late.", 2, "fact-edit-0013")
        retry = _remove(client, fact_id, 1, "fact-del-0013")
    assert removed.status_code == 200
    assert listing["facts"] == [] and listing["used_chars"] == 0
    assert late_edit.status_code == 409
    assert retry.status_code == 200 and retry.json()["duplicate"] is True


def test_removing_an_unknown_fact_is_not_found(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        assert _remove(client, "fact-nothere-0001", 1, "fact-del-0014").status_code == 404
        assert _edit(client, "not-a-fact", "x", 1, "fact-edit-0014").status_code == 404


def test_facts_are_not_conversation_messages(tmp_path, monkeypatch):
    Model(monkeypatch)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        _add(client, "A fact about the owner.", "fact-client-0015")
        post(client, "/api/message", {"text": "hello", "client_id": "client-0015-chat"}, csrf_of(client))
        listing = _facts(client)
        page = stored_page(client)
    assert [fact["text"] for fact in listing["facts"]] == ["A fact about the owner."]
    kinds = sorted(item["kind"] for item in page["items"])
    assert kinds == ["conversation_message", "conversation_message", "curated_fact"]


def test_an_incomplete_read_refuses_the_write_instead_of_guessing_the_budget(tmp_path, monkeypatch):
    # Five facts written under the normal bound. Then the bound shrinks below the
    # stream, so the total cannot be read to its end: a write must be refused.
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        for number in range(5):
            assert _add(client, f"fact number {number}", f"fact-client-02{number:02d}").status_code == 200
        monkeypatch.setattr(recall, "PAGE", 2)
        monkeypatch.setattr(recall, "MAX_SCANNED", 3)
        listing = _facts(client)
        refused = _add(client, "one more", "fact-client-0299")
    assert listing["complete"] is False
    assert refused.status_code == 503
    assert "could not be fully read" in refused.json()["error"]
