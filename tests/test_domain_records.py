"""The domain contracts: records, their states, and the retry rule.

These tests pin the decisions that everything above them depends on — that an
uncertain effect is never retried blindly, that a terminal record does not
quietly reopen, and that provenance decides whether a claim may be cited.
"""
from __future__ import annotations

import json

import pytest

from oneiro.events import Event, sequence, read_events
from oneiro.records import (
    Action, ConversationMessage, Decision, Effect, EffectOutcome, Experiment,
    Experience, Note, Provenance, RecordError, Release, State, Task, decode,
    decode_many,
)


def test_a_task_carries_provenance_and_an_explicit_state():
    task = Task(title="Bring up OSTIS", provenance=Provenance.OWNER_INSTRUCTION)
    assert task.state is State.QUEUED
    assert task.state.is_open and not task.state.is_terminal
    assert task.provenance is Provenance.OWNER_INSTRUCTION


def test_state_changes_are_immutable_and_stamped():
    task = Task(title="x")
    running = task.with_state(State.RUNNING)
    assert task.state is State.QUEUED, "the original record must not change"
    assert running.state is State.RUNNING and running.updated_at >= task.updated_at


def test_a_terminal_record_does_not_reopen():
    done = Task(title="x").with_state(State.COMPLETED)
    with pytest.raises(RecordError, match="cannot become"):
        done.with_state(State.RUNNING)


def test_every_record_kind_round_trips_through_json():
    records = [
        ConversationMessage(conversation_id="c1", role="owner", text="hello"),
        Task(title="do a thing", blocked_by=("t0",)),
        Action(run_id="r1", tool="file.write", effect=Effect("file.write", "/tmp/x",
                                                            EffectOutcome.SUCCEEDED)),
        Decision(question="which port", chosen="9899", alternatives=("9900",)),
        Note(topic="graph", body="OSTIS is required", sources=("s1",)),
        Experience(summary="worked", lesson="snapshot first"),
        Experiment(name="e1", hypothesis="faster", repeats=1),
        Release(version="0.2.0", checks={"unit": True, "smoke": True}),
    ]
    for record in records:
        again = decode(json.loads(record.to_json()))
        assert again == record, record.KIND
        assert again.KIND == record.KIND


def test_an_unknown_kind_or_version_is_refused():
    good = Task(title="x").to_dict()
    wrong_kind = dict(good, kind="nonsense")
    with pytest.raises(RecordError, match="unknown record kind"):
        decode(wrong_kind)
    with pytest.raises(RecordError, match="schema version"):
        decode(dict(good, schema_version=99))
    with pytest.raises(RecordError, match="missing"):
        decode({"kind": "task"})


def test_uncertain_effects_are_never_retried_blindly():
    """The rule that stops a restart from sending a second email."""
    uncertain = Action(run_id="r", tool="mail.send",
                       effect=Effect("mail.send", "owner", EffectOutcome.UNCERTAIN))
    assert uncertain.may_retry() is False
    assert uncertain.requires_inspection() is True

    failed = Action(run_id="r", tool="mail.send",
                    effect=Effect("mail.send", "owner", EffectOutcome.FAILED))
    assert failed.may_retry() is True, "an effect known not to have happened may be retried"

    read_only = Action(run_id="r", tool="fs.read", effect=Effect())
    assert read_only.may_retry() is False, "reads are not effects; replay is a decision"


def test_only_verified_provenance_may_be_cited():
    guess = Note(topic="t", body="b", provenance=Provenance.MODEL_CLAIM)
    seen = Note(topic="t", body="b", provenance=Provenance.OBSERVATION)
    assert guess.is_citable is False
    assert seen.is_citable is True
    assert Provenance.VERIFIED_TOOL_OUTCOME.is_verified


def test_an_experiment_cannot_conclude_below_three_repeats():
    frozen = Experiment(name="e", hypothesis="h", frozen_before_run=True, repeats=2)
    assert frozen.has_enough_repeats() is False
    assert frozen.may_conclude() is False
    assert frozen.with_repeats(3).may_conclude() is True
    assert Experiment(name="e", hypothesis="h", repeats=9, frozen_before_run=False
                      ).may_conclude() is False, "unfrozen criteria cannot conclude"


def test_a_release_needs_all_checks_to_pass():
    release = Release(version="1", checks={"unit": True, "smoke": False})
    assert release.checks_passed() is False
    assert release.with_state(State.COMPLETED).checks_passed() is False


def test_records_reject_empty_meaningful_fields():
    with pytest.raises(RecordError, match="title"):
        Task(title="   ")
    with pytest.raises(RecordError, match="question and chosen"):
        Decision(question="q")
    with pytest.raises(RecordError, match="role"):
        ConversationMessage(conversation_id="c", role="owner", text="  ")


def test_decode_many_reads_a_store_and_names_the_bad_line():
    text = "\n".join([Task(title="a").to_json(), Task(title="b").to_json()])
    assert len(decode_many(text)) == 2
    with pytest.raises(RecordError, match="line 2"):
        decode_many(Task(title="a").to_json() + "\n{not json}")


# ------------------------------------------------------------------ envelopes

def test_events_chain_by_causation_and_share_a_correlation():
    records = [Task(title="a"), Task(title="b"), Task(title="c")]
    events = sequence(records, correlation_id="work-1", channel="web")
    assert [e.causation_id for e in events] == ["", events[0].id, events[1].id]
    assert {e.correlation_id for e in events} == {"work-1"}


def test_an_event_without_a_correlation_is_refused():
    with pytest.raises(RecordError, match="correlation_id"):
        Event(event="task.created", record=Task(title="a"), correlation_id="")


def test_an_unknown_event_name_is_refused():
    with pytest.raises(RecordError, match="unknown event"):
        Event(event="task.exploded", record=Task(title="a"), correlation_id="c")


def test_an_event_digest_detects_editing():
    event = sequence([Task(title="a")], correlation_id="c")[0]
    assert Event.from_dict(event.to_dict()) == event
    tampered = event.to_dict()
    tampered["correlation_id"] = "other"
    with pytest.raises(RecordError, match="digest"):
        Event.from_dict(tampered)


def test_a_torn_last_line_is_reported_not_fatal():
    events = sequence([Task(title="a"), Task(title="b")], correlation_id="c")
    text = "\n".join(e.to_json() for e in events)
    good, skipped = read_events(text)
    assert len(good) == 2 and skipped == 0
    torn, skipped_tail = read_events(text + "\n" + events[0].to_json()[:40])
    assert len(torn) == 2, "a crash mid-append must not lose durable records"
    assert skipped_tail == 1