"""The replay judge: exact where the recording is, abstaining where it is not.

These tests run offline. They skip if no replayable episode has been recorded
yet, because the judge is a function of recordings, not of a live provider.
"""

from dataclasses import replace

import pytest

import agent
import replay
from policy import HarnessPolicy, get_policy


def newest_record() -> dict:
    records = replay.load_records()
    if not records:
        pytest.skip("no replayable records on disk yet")
    return max(records, key=lambda r: len(r.get("steps") or []))


def test_replaying_the_recorded_policy_reproduces_prompt_sizes():
    record = newest_record()
    check = replay.verify_reconstruction(record)
    assert check["chars_match"], (
        "replaying the recorded policy must reproduce the recorded prompt sizes "
        f"character for character (first mismatch at step {check['first_mismatch']})"
    )


def test_identical_policy_is_fully_replayable():
    record = newest_record()
    policy = HarnessPolicy.from_descriptor(record["policy"])
    estimate = replay.estimate(record, policy)

    assert estimate.decision_replayable == 1.0
    assert estimate.steps_covered == estimate.steps_total
    assert estimate.prompt_chars_predicted == estimate.prompt_chars_recorded
    # the token model is fitted out of sample, so it lands close, not exactly
    assert 0.8 < estimate.saving_ratio < 1.2
    assert estimate.dropped_observations == 0


def test_windowed_policy_drops_history_and_abstains_on_diverged_steps():
    record = newest_record()
    windowed = replace(get_policy("windowed"), name="w2", window_steps=2)
    estimate = replay.estimate(record, windowed)

    assert estimate.prompt_chars_predicted < estimate.prompt_chars_recorded
    assert estimate.saving_ratio < 1.0
    assert estimate.dropped_observations > 0
    assert estimate.decision_replayable < 1.0
    assert any("abstain" in note for note in estimate.notes)


def test_blind_policy_shrinks_the_system_prompt():
    record = newest_record()
    recorded = HarnessPolicy.from_descriptor(record["policy"])
    blind = get_policy("blind")

    recorded_system = len(replay.system_text(record, recorded))
    blind_system = len(replay.system_text(record, blind))
    assert blind_system < recorded_system


def test_truncating_observations_is_exact_and_computed():
    record = newest_record()
    terse = get_policy("terse")
    estimate = replay.estimate(record, terse)
    assert estimate.truncation_saved_chars >= 0
    assert estimate.prompt_chars_predicted <= estimate.prompt_chars_recorded


def test_the_judge_never_calls_the_model(monkeypatch):
    record = newest_record()

    def explode(*args, **kwargs):
        raise AssertionError("the replay judge must not call the provider")

    monkeypatch.setattr(agent.Provider, "chat", explode)
    estimate = replay.estimate(record, get_policy("windowed"))
    assert estimate.steps_total > 0
