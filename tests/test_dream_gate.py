"""The gate: rules frozen before the run, three repeats, one way through, and an undo.

The records are the graph's own `Experiment` and `Release`, and the last test writes a
promotion and its rollback through the real `RecordStore`, so the rollback path is a
revision in the graph rather than a claim in a docstring.
"""
from __future__ import annotations

import asyncio

import pytest

from chat_fakes import GraphStub, MemoryLinks, isolate
from oneiro.dream.gate import (Criteria, Evidence, GateError, gate, open_experiment, promote,
                               publish_release, record_experiment, record_repeats, rollback)
from oneiro.records import RecordError, Release, State
from oneiro.runtime import Runtime

CRITERIA = Criteria()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def an_experiment(**overrides):
    arguments = {"name": "dream-windowed-1",
                 "hypothesis": "a smaller history window spends fewer tokens",
                 "control": "recorded", "candidate": "windowed", "criteria": CRITERIA}
    arguments.update(overrides)
    return open_experiment(**arguments)


def evidence(**overrides) -> Evidence:
    arguments = {"policy": "windowed", "coverage": 0.9, "saving": 0.2, "repeats": 3,
                 "regressions": 0}
    arguments.update(overrides)
    return Evidence(**arguments)


def test_an_experiment_is_frozen_before_the_run_and_needs_three_repeats():
    experiment = an_experiment()

    assert experiment.frozen_before_run is True
    assert experiment.min_repeats == 3 and experiment.repeats == 0
    assert experiment.has_enough_repeats() is False
    assert experiment.may_conclude() is False

    grown = record_repeats(experiment, 3)

    assert grown.has_enough_repeats() is True and grown.may_conclude() is True
    assert gate(grown, CRITERIA, evidence()).checks["enough_repeats"] is True
    assert gate(experiment, CRITERIA, evidence(repeats=2)).checks["enough_repeats"] is False


def test_a_repeat_count_never_goes_down():
    grown = record_repeats(an_experiment(), 3)

    with pytest.raises(RecordError):
        record_repeats(grown, 2)


def test_a_verdict_names_the_check_that_failed():
    experiment = record_repeats(an_experiment(), 3)

    verdict = gate(experiment, CRITERIA, evidence(coverage=0.2))

    assert verdict.passed is False
    assert verdict.checks["coverage"] is False
    assert verdict.checks["saving"] is True
    assert any("below the floor" in reason for reason in verdict.reasons)


def test_a_candidate_is_promoted_only_on_evidence():
    experiment = record_repeats(an_experiment(), 3)

    with pytest.raises(GateError) as refused:
        promote(experiment, CRITERIA, evidence(saving=0.01), version="0.2.0")

    assert "saving" in str(refused.value)
    promoted = promote(experiment, CRITERIA, evidence(), version="0.2.0")
    assert promoted.promoted is True and promoted.checks_passed() is True
    assert promoted.version == "0.2.0"


def test_evidence_about_another_candidate_cannot_carry_this_one():
    experiment = record_repeats(an_experiment(), 3)

    with pytest.raises(GateError) as refused:
        promote(experiment, CRITERIA, evidence(policy="blind"), version="0.2.0")

    assert "blind" in str(refused.value) and "windowed" in str(refused.value)


def test_an_experiment_without_repeats_cannot_conclude():
    experiment = an_experiment()

    with pytest.raises(GateError) as refused:
        promote(experiment, CRITERIA, evidence(repeats=3), version="0.2.0")

    assert "cannot conclude" in str(refused.value)


def test_a_promotion_needs_a_control_that_differs():
    with pytest.raises(GateError):
        an_experiment(candidate="recorded")


def test_a_rollback_is_a_new_revision_and_the_promoted_one_stays():
    experiment = record_repeats(an_experiment(), 3)
    promoted = promote(experiment, CRITERIA, evidence(), version="0.2.0")

    undone = rollback(promoted, reason="regression on the later turns")

    assert undone.id == promoted.id and undone.version == promoted.version
    assert undone.promoted is False and undone.rolled_back is True
    assert promoted.promoted is True and promoted.rolled_back is False
    assert "rollback:regression on the later turns" in undone.labels
    with pytest.raises(GateError) as refused:
        rollback(undone, reason="twice")
    assert "already rolled back" in str(refused.value)


def test_a_release_that_was_never_promoted_has_nothing_to_roll_back():
    never = Release(version="0.3.0", artifact="windowed", promoted=False,
                    state=State.COMPLETED)

    with pytest.raises(GateError) as refused:
        rollback(never, reason="because")

    assert "never promoted" in str(refused.value)


def test_a_promotion_and_its_rollback_land_in_the_graph_as_two_revisions(tmp_path, monkeypatch):
    owner = Runtime(graph=GraphStub(MemoryLinks(), tmp_path / "graph-writer.lock"))
    experiment = record_repeats(an_experiment(), 3)
    asyncio.run(record_experiment(owner, experiment))
    promoted = promote(experiment, CRITERIA, evidence(), version="0.2.0")

    first = asyncio.run(publish_release(owner, promoted))
    undone = rollback(promoted, reason="measured again")
    second = asyncio.run(publish_release(owner, undone, expected_revision=first["revision"]))

    assert (first["revision"], second["revision"]) == (1, 2)
    stored = asyncio.run(owner.memory_entity(promoted.id))
    assert stored["promoted"] is False and stored["rolled_back"] is True
    assert stored["version"] == "0.2.0"
    kept = asyncio.run(owner.memory_entity(experiment.id))
    assert kept["frozen_before_run"] is True and kept["candidate"] == "windowed"
