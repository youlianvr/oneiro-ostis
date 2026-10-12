"""The judge: rebuilding a turn from its records, and the boundary that keeps it offline.

Every episode here is produced by the production loop over the real `RecordStore` with
only the provider stubbed, so the judge is measured against turns the product actually
wrote. The last test is the one the plan's acceptance names: the world's step functions
are replaced by functions that raise, and the judge must still answer.
"""
from __future__ import annotations

import asyncio

import pytest

from chat_fakes import GraphStub, MemoryLinks, Model, isolate
from oneiro import agent, models, recall, tools
from oneiro.chat import ModelReply
from oneiro.dream import episode, replay
from oneiro.dream.policy import BASE, TurnPolicy, get_policy
from oneiro.records import ConversationMessage, CuratedFact, Provenance, State
from oneiro.runtime import Runtime

CONVERSATION = "dream-replay"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def record_turn(owner, model, text, client, **kwargs):
    return asyncio.run(agent.run_turn(owner, text, client, CONVERSATION, call=model._call, **kwargs))


def a_turn(tmp_path, monkeypatch, *, client, reads=2, links=None, owner=None,
           text="read it twice"):
    """A real recorded turn with `reads` tool calls, then one answering call."""
    note = tmp_path / "notes.txt"
    note.write_text("the plan is to keep it small", encoding="utf-8")
    replies = [Model.tool("read_file", {"path": str(note)}, f"call-{i}")
               for i in range(1, reads + 1)]
    replies.append(ModelReply("Done."))
    model = Model(monkeypatch, replies=replies)
    owner = owner if owner is not None else owner_for(tmp_path, links or MemoryLinks())
    record_turn(owner, model, text, client)
    return owner, asyncio.run(episode.read(owner, "reply-" + client))


def seed_history(owner, conversation: str, count: int) -> None:
    """Earlier messages, some of them the manager's own — as a real conversation has."""
    for number in range(count):
        role = "owner" if number % 2 == 0 else "manager"
        record = ConversationMessage(id=f"seed-{number:02d}", conversation_id=conversation,
                                     role=role, text=f"earlier message {number}",
                                     provenance=Provenance.OWNER_INSTRUCTION
                                     if role == "owner" else Provenance.MODEL_CLAIM,
                                     state=State.COMPLETED)
        asyncio.run(owner.publish(record.to_dict(), record.id))


def test_a_turn_in_a_conversation_with_a_prelude_still_verifies(tmp_path, monkeypatch):
    """The history block's own assistant messages are not this turn's calls."""
    owner = owner_for(tmp_path, MemoryLinks())
    seed_history(owner, CONVERSATION, 4)
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-9", reads=1, owner=owner)

    context = asyncio.run(replay.read_context(owner, turn))
    proof = replay.verify_reconstruction(turn, context)

    assert len(context.history) == 4, "the prelude was read"
    assert proof.rows_match is True and proof.first_mismatch is None
    assert replay.estimate(turn, BASE, context).coverage == 1.0


def test_the_recorded_policy_covers_every_step_it_was_asked(tmp_path, monkeypatch):
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-1", reads=2)
    context = asyncio.run(replay.read_context(owner, turn))

    estimate = replay.estimate(turn, BASE, context)

    # Two calls and the answering call: the answer is a decision like any other.
    assert turn.calls == 2
    assert estimate.steps_total == replay.judged_steps(turn) == 3
    assert estimate.steps_covered == 3
    assert estimate.coverage == 1.0
    assert estimate.truncated is False and estimate.truncated_at is None


def test_verify_reconstruction_proves_the_round_trip_against_the_turn_that_ran(tmp_path, monkeypatch):
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-2", reads=2)
    context = asyncio.run(replay.read_context(owner, turn))

    proof = replay.verify_reconstruction(turn, context)

    assert proof.rows_match is True and proof.first_mismatch is None
    assert proof.steps == 2 and proof.coverage == 1.0
    assert "per-step token counts" in proof.not_recorded
    assert "the model's own tool-call IDs (rebuilt from the step number)" in proof.not_recorded


def test_a_candidate_that_clips_an_observation_is_truncated_at_the_step_it_first_diverges(
        tmp_path, monkeypatch):
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-3", reads=3)
    context = asyncio.run(replay.read_context(owner, turn))
    seen: list[int] = []
    original = replay.assemble

    def counting(episode_, policy, index, context_=None):
        seen.append(index)
        return original(episode_, policy, index, context_)

    monkeypatch.setattr(replay, "assemble", counting)
    estimate = replay.estimate(turn, TurnPolicy(name="terse", observation_chars=5), context)

    # The first call has no earlier observation to clip, so it survives; the second
    # differs, and everything after it is not counted at all.
    assert estimate.truncated_at == 2
    assert estimate.steps_covered == 1
    assert estimate.coverage == pytest.approx(1 / 4)
    assert max(seen) == 2, "the walk stopped at the first divergence"
    assert estimate.clipped_observations == 3
    assert "not replayable" in " ".join(estimate.notes)


def test_a_candidate_that_only_moves_the_step_limit_changes_no_context(tmp_path, monkeypatch):
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-4", reads=2)
    context = asyncio.run(replay.read_context(owner, turn))

    estimate = replay.estimate(turn, get_policy("long_turn"), context)

    assert estimate.coverage == 1.0 and estimate.truncated_at is None
    assert any("what replay cannot see is when this limit would stop the turn" in note
               for note in estimate.notes), "the limit's effect is outside the recording"


def test_dropping_the_facts_block_diverges_at_the_first_question(tmp_path, monkeypatch):
    links = MemoryLinks()
    owner = owner_for(tmp_path, links)
    fact = CuratedFact(id="fact-1", text="the plan is to keep it small",
                       provenance=Provenance.OWNER_INSTRUCTION, state=State.COMPLETED)
    asyncio.run(owner.publish(fact.to_dict(), fact.id))
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-5", reads=1, owner=owner)
    context = asyncio.run(replay.read_context(owner, turn))

    assert context.facts == ("the plan is to keep it small",)
    assert replay.estimate(turn, BASE, context).coverage == 1.0

    blind = replay.estimate(turn, get_policy("blind"), context)

    assert blind.steps_covered == 0 and blind.coverage == 0.0 and blind.truncated_at == 1


def test_dropping_the_history_diverges_when_the_conversation_has_one(tmp_path, monkeypatch):
    owner = owner_for(tmp_path, MemoryLinks())
    first = Model(monkeypatch, replies=[ModelReply("First answer.")])
    record_turn(owner, first, "first question", "c-rec-6a")
    second = Model(monkeypatch, replies=[ModelReply("Second answer.")])
    record_turn(owner, second, "second question", "c-rec-6b")
    turn = asyncio.run(episode.read(owner, "reply-c-rec-6b"))
    context = asyncio.run(replay.read_context(owner, turn))

    assert [message["content"] for message in context.history] == ["first question",
                                                                   "First answer."]
    assert replay.estimate(turn, BASE, context).coverage == 1.0

    without = replay.estimate(turn, get_policy("no_history"), context)

    assert without.truncated_at == 1 and without.coverage == 0.0
    assert any("read now, not as they were sent" in note for note in without.notes)


def test_the_judge_never_executes_the_world(tmp_path, monkeypatch):
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-7", reads=2)

    def explode(*_args, **_kwargs):
        raise AssertionError("the judge executed the world")

    monkeypatch.setattr(agent, "run_turn", explode)
    monkeypatch.setattr(agent, "default_registry", explode)
    monkeypatch.setattr(agent, "_run_tool", explode)
    monkeypatch.setattr(models, "registry", explode)
    monkeypatch.setattr(tools, "build_registry", explode)

    context = asyncio.run(replay.read_context(owner, turn))
    for policy in (BASE, get_policy("windowed"), get_policy("terse_observations")):
        estimate = replay.estimate(turn, policy, context)
        assert estimate.steps_total >= 1
    assert replay.verify_reconstruction(turn, context).rows_match is True


def test_replay_writes_nothing(tmp_path, monkeypatch):
    owner, turn = a_turn(tmp_path, monkeypatch, client="c-rec-8", reads=1)
    before = len(asyncio.run(owner.memory_page(limit=500))["items"])

    context = asyncio.run(replay.read_context(owner, turn))
    replay.estimate(turn, get_policy("windowed"), context)
    replay.verify_reconstruction(turn, context)

    assert len(asyncio.run(owner.memory_page(limit=500))["items"]) == before, "the judge is read-only"


def test_the_facts_preamble_is_the_same_sentence_the_live_turn_sends(tmp_path, monkeypatch):
    owner = owner_for(tmp_path, MemoryLinks())
    fact = CuratedFact(id="fact-2", text="keep it small",
                       provenance=Provenance.OWNER_INSTRUCTION, state=State.COMPLETED)
    asyncio.run(owner.publish(fact.to_dict(), fact.id))

    messages, report = asyncio.run(recall.reply_context(owner, "no-such-conversation",
                                                        exclude_id="none", history_limit=10,
                                                        char_budget=6000))

    assert report["facts"] == 1
    assert messages[0]["content"] == replay.facts_block(("keep it small",))
