"""Reading one recorded turn back from the graph.

The turn is produced by the production loop (`agent.run_turn`) over the real
`RecordStore`, with only the provider stubbed — so the episode under test is what
the product actually writes, not a hand-built fixture that only looks like it.
"""
from __future__ import annotations

import asyncio

import pytest

from chat_fakes import GraphStub, MemoryLinks, Model, isolate
from oneiro import agent
from oneiro.chat import ModelReply
from oneiro.dream import episode
from oneiro.records import State
from oneiro.runtime import Runtime

CONVERSATION = "dream-chat"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    """A runtime over the in-memory graph, ready to publish but never `start()`ed."""
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def run(owner, model, text, client_id, **kwargs):
    return asyncio.run(agent.run_turn(owner, text, client_id, CONVERSATION,
                                      call=model._call, **kwargs))


def stored_rows(owner) -> list[dict]:
    return asyncio.run(owner.memory_page(limit=500))["items"]


def test_a_recorded_turn_reads_back_with_its_request_calls_and_observations(tmp_path, monkeypatch):
    note = tmp_path / "notes.txt"
    note.write_text("the plan is to keep it small", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(note)}, "call-1"),
        ModelReply("The note says to keep it small."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())
    run(owner, model, "what does the note say?", "client-ep-0001")

    turn = asyncio.run(episode.read(owner, "reply-client-ep-0001"))

    assert turn.request == "what does the note say?"
    assert turn.conversation_id == CONVERSATION
    assert turn.role == "manager"
    assert turn.reply == "The note says to keep it small."
    assert turn.stop_reason == "answered"
    assert [step.tool for step in turn.steps] == ["read_file"]
    assert turn.steps[0].decision == "allow"
    assert turn.steps[0].state == State.COMPLETED.value
    assert "the plan is to keep it small" in turn.steps[0].result
    # What the model was told back is the live turn's own sentence, not a paraphrase.
    assert turn.steps[0].observation == f"read_file returned: {turn.steps[0].result}"
    assert turn.tools == ("read_file",)
    # What the graph does not carry is named, not reported as a zero measurement.
    assert "per-step token counts" in turn.unrecorded


def test_reading_a_turn_writes_nothing(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("Nothing to look up.")])
    owner = owner_for(tmp_path, MemoryLinks())
    run(owner, model, "hello", "client-ep-0002")
    before = len(stored_rows(owner))

    asyncio.run(episode.read(owner, "reply-client-ep-0002"))

    assert len(stored_rows(owner)) == before, "the reader is read-only"


def test_a_turn_that_hit_the_step_limit_reads_as_stopped(tmp_path, monkeypatch):
    note = tmp_path / "loop.txt"
    note.write_text("again", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(note)}, "call-1"),
        Model.tool("read_file", {"path": str(note)}, "call-2"),
    ])
    owner = owner_for(tmp_path, MemoryLinks())
    run(owner, model, "read it twice", "client-ep-0003", max_steps=1)

    turn = asyncio.run(episode.read(owner, "reply-client-ep-0003"))

    assert turn.stop_reason == "stopped"
    assert turn.calls == 1


def test_a_refused_call_is_recorded_in_the_episode(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[
        Model.tool("run_sandbox", {"command": ["rm", "-rf", "/"]}, "call-1"),
        ModelReply("That tool does not exist."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())
    run(owner, model, "delete everything", "client-ep-0004")

    turn = asyncio.run(episode.read(owner, "reply-client-ep-0004"))

    # A refusal carries no run_id, so turn_steps would drop it; the episode keeps it.
    assert [step.tool for step in turn.steps] == ["run_sandbox"]
    assert turn.steps[0].decision == "deny"
    assert turn.steps[0].state == State.FAILED.value
    assert "no tool named run_sandbox" in turn.steps[0].reason
    assert "did not run" in turn.steps[0].observation
    assert turn.refusals == (turn.steps[0],)


def test_an_unrecorded_turn_is_named_instead_of_invented(tmp_path, monkeypatch):
    owner = owner_for(tmp_path, MemoryLinks())

    with pytest.raises(episode.EpisodeError) as refused:
        asyncio.run(episode.read(owner, "reply-client-never"))

    assert "no reply is recorded" in str(refused.value)


def test_something_that_is_not_a_turn_id_is_refused(tmp_path, monkeypatch):
    owner = owner_for(tmp_path, MemoryLinks())

    with pytest.raises(episode.EpisodeError):
        asyncio.run(episode.read(owner, "msg-client-ep-0001"))


def test_recent_turns_lists_the_newest_recorded_turn_first(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("first"), ModelReply("second")])
    owner = owner_for(tmp_path, MemoryLinks())
    run(owner, model, "one", "client-ep-0005")
    run(owner, model, "two", "client-ep-0006")

    turns = asyncio.run(episode.recent_turns(owner))

    assert turns == ["reply-client-ep-0006", "reply-client-ep-0005"]
