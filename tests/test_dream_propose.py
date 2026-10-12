"""The proposer: a bounded search, one knob per neighbour, ordered by what records can say.

The turns here are real production turns over the real store, recorded through
`agent.run_turn`, and judged only from those records — the same path the proposer takes
outside a test.
"""
from __future__ import annotations

import asyncio

import pytest

from chat_fakes import GraphStub, MemoryLinks, Model, isolate
from oneiro import agent
from oneiro.chat import ModelReply
from oneiro.dream import episode, replay
from oneiro.dream.policy import BASE, KNOBS, VARIANTS
from oneiro.dream.propose import candidates, neighbours, propose
from oneiro.records import ConversationMessage, Provenance, State
from oneiro.runtime import Runtime

CONVERSATION = "dream-propose"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def seed_history(owner: Runtime, conversation: str, count: int) -> None:
    """Older messages in the conversation, so a window candidate has something to window."""
    for number in range(count):
        role = "owner" if number % 2 == 0 else "manager"
        record = ConversationMessage(id=f"seed-{number:02d}", conversation_id=conversation,
                                     role=role, text=f"earlier message {number} with some words",
                                     provenance=Provenance.OWNER_INSTRUCTION
                                     if role == "owner" else Provenance.MODEL_CLAIM,
                                     state=State.COMPLETED)
        asyncio.run(owner.publish(record.to_dict(), record.id))


def a_turn(tmp_path, monkeypatch, *, client, history=0):
    """One recorded turn, and the context read back for it."""
    note = tmp_path / "notes.txt"
    note.write_text("keep it small", encoding="utf-8")
    model = Model(monkeypatch, replies=[Model.tool("read_file", {"path": str(note)}, "call-1"),
                                        ModelReply("Small it is.")])
    owner = owner_for(tmp_path, MemoryLinks())
    if history:
        seed_history(owner, CONVERSATION, history)
    asyncio.run(agent.run_turn(owner, "read it", client, CONVERSATION, call=model._call))
    turn = asyncio.run(episode.read(owner, "reply-" + client))
    return turn, asyncio.run(replay.read_context(owner, turn))


def test_candidates_are_deduplicated_and_each_neighbour_changes_one_knob():
    found = candidates(BASE)
    shapes = [tuple(getattr(policy, knob) for knob in KNOBS) for policy in found]

    assert len(shapes) == len(set(shapes)), "no candidate is offered twice"
    assert any(policy.name == BASE.name for policy in found)
    for policy in neighbours(BASE):
        assert len(policy.changed_fields(BASE)) == 1


def test_the_recorded_policy_is_the_floor_and_ranks_first(tmp_path, monkeypatch):
    turn, context = a_turn(tmp_path, monkeypatch, client="c-pr-1", history=6)

    found = propose([turn], {turn.turn_id: context})

    assert found[0].policy == BASE.name
    assert found[0].coverage == 1.0 and found[0].changed == ()
    assert found[0].replayable is True


def test_a_window_the_turn_had_nothing_to_use_is_still_replayable(tmp_path, monkeypatch):
    turn, context = a_turn(tmp_path, monkeypatch, client="c-pr-2", history=0)

    found = {item.policy: item for item in propose([turn], {turn.turn_id: context})}

    assert found["no_history"].coverage == 1.0
    assert found["no_history"].replayable is True


def test_a_candidate_that_changes_what_was_shown_is_not_replayable(tmp_path, monkeypatch):
    turn, context = a_turn(tmp_path, monkeypatch, client="c-pr-3", history=6)

    found = {item.policy: item for item in propose([turn], {turn.turn_id: context})}

    assert found["windowed"].coverage == 0.0
    assert found["windowed"].replayable is False
    assert any("not replayable" in note for note in found["windowed"].notes)


def test_a_minimum_coverage_drops_what_the_records_cannot_speak_about(tmp_path, monkeypatch):
    turn, context = a_turn(tmp_path, monkeypatch, client="c-pr-4", history=6)

    found = propose([turn], {turn.turn_id: context}, minimum_coverage=1.0)

    assert [item.policy for item in found][0] == BASE.name
    assert all(item.coverage >= 1.0 for item in found)
    assert "windowed" not in {item.policy for item in found}
    assert VARIANTS["windowed"].name == "windowed"
