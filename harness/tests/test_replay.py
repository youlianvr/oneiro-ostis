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
    """The longest recording made by the reference policy.

    The judge's contract is relative to the policy that was recorded: replaying
    a wider policy over an episode whose own history was trimmed legitimately
    predicts more characters, not fewer. So these tests stand on a baseline
    recording, where the recorded prompt is the unconstrained one.
    """
    records = [r for r in replay.load_records()
               if (r.get("policy") or {}).get("name") == "baseline"]
    if not records:
        pytest.skip("no baseline recording on disk yet")
    return max(records, key=lambda r: len(r.get("steps") or []))


# A recording is reproducible against the state it captured, and two things
# outside the recording can move under it. The skill catalog is a live file: it
# is part of the system prompt of a catalog policy, and one recorded run
# predates a change in it, which is worth 291 characters. Clipped tool output
# is the other: the live run kept up to four characters more than the clip
# rebuilds. Both are bounded and named here instead of being papered over with
# a tolerance nobody reads, and the share of recordings that replay character
# for character is asserted as measured, not hoped for.
CATALOG_STEP_DRIFT_LIMIT = 400
PLAIN_STEP_DRIFT_LIMIT = 4
EXACT_RECORDING_SHARE = 0.9


def step_drift(record: dict) -> int:
    """Largest single-step difference between the rebuild and the recording."""
    check = replay.verify_reconstruction(record)
    recorded = [s.get("prompt_chars", 0) for s in record["steps"]]
    return max((abs(b - a) for a, b in zip(check["rebuilt"], recorded)), default=0)


def test_most_recordings_replay_character_for_character():
    records = replay.load_records()
    exact = [r for r in records if replay.verify_reconstruction(r)["chars_match"]]
    share = len(exact) / len(records)
    assert share >= EXACT_RECORDING_SHARE, (
        f"only {len(exact)} of {len(records)} recordings reproduce prompt sizes exactly"
    )


def test_every_difference_between_replay_and_recording_is_bounded():
    offenders = []
    for record in replay.load_records():
        catalog = bool((record.get("policy") or {}).get("include_skill_catalog"))
        limit = CATALOG_STEP_DRIFT_LIMIT if catalog else PLAIN_STEP_DRIFT_LIMIT
        drift = step_drift(record)
        if drift > limit:
            offenders.append((record.get("label"), drift, limit))
    assert not offenders, offenders


def test_an_exact_recording_replays_to_the_same_character_count():
    record = next(r for r in replay.load_records()
                  if (r.get("policy") or {}).get("name") == "baseline"
                  and replay.verify_reconstruction(r)["chars_match"])
    policy = HarnessPolicy.from_descriptor(record["policy"])
    estimate = replay.estimate(record, policy)

    assert estimate.decision_replayable == 1.0
    assert estimate.prompt_chars_predicted == estimate.prompt_chars_recorded
    assert estimate.steps_covered == estimate.steps_total
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


def test_truncating_observations_lowers_the_prompt_against_the_recorded_policy():
    """Clipping can only remove characters, never add them."""
    record = newest_record()
    recorded = HarnessPolicy.from_descriptor(record["policy"])
    reference = replay.estimate(record, recorded)
    terse = replay.estimate(record, get_policy("terse"))

    assert terse.truncation_saved_chars >= 0
    assert terse.prompt_chars_predicted <= reference.prompt_chars_predicted


def test_the_judge_never_calls_the_model(monkeypatch):
    record = newest_record()

    def explode(*args, **kwargs):
        raise AssertionError("the replay judge must not call the provider")

    monkeypatch.setattr(agent.Provider, "chat", explode)
    estimate = replay.estimate(record, get_policy("windowed"))
    assert estimate.steps_total > 0
