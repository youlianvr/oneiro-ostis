"""The screen before a run is spent: two blocks, and flags that only inform.

The rule these tests hold to is the one that makes the screen usable: it blocks
what provably cannot work or cannot be attributed, and it lets everything else
through with a note. A screen that refused a candidate for raising temperature or
for leaning on one task would be deciding by opinion what the online measurement
decides by fact — and it would have refused the edit this search actually
deployed, which moved two fields at once.
"""

from dataclasses import replace

import critic
import pytest
import replay
import rsi
from policy import HarnessPolicy, get_policy

BASE = HarnessPolicy()
CRITERIA = {"critic": {"min_max_steps": 3, "max_single_task_share": 0.9}}


def estimate(task: str, *, predicted: float, recorded: float):
    return replay.Estimate(task=task, policy="candidate",
                           prompt_tokens_predicted=predicted,
                           prompt_tokens_recorded=recorded)


def screen(candidate: HarnessPolicy, *, budget: int = 11, verdict: dict | None = None,
           estimates: list | None = None) -> dict:
    return critic.screen(candidate, BASE, verdict, estimates or [], CRITERIA, budget)


def test_a_policy_the_agent_cannot_work_in_is_blocked():
    for broken in (replace(BASE, max_steps=2),
                   replace(BASE, observation_chars=0),
                   replace(BASE, read_lines=0),
                   replace(BASE, context_mode="window", window_steps=0)):
        row = screen(broken)
        assert row["blocked"], f"{broken} should not be run"
        assert row["reasons"]


def test_an_edit_that_bundles_more_than_the_budget_is_blocked_and_told_to_split():
    bundled = replace(BASE, include_initial_tests=False, context_mode="window",
                      window_steps=6, observation_chars=600, read_lines=60)

    row = screen(bundled, budget=2)

    assert row["blocked"]
    assert any("split it" in reason for reason in row["reasons"])
    assert len(row["fields_changed"]) == 5


def test_the_deployed_edit_is_not_blocked_by_the_budget_that_was_set_after_it():
    """Two fields, and the second one only works with the first."""
    deployed = replace(BASE, include_initial_tests=False, observation_chars=1500)

    row = screen(deployed, budget=2)

    assert not row["blocked"]
    assert sorted(row["fields_changed"]) == ["include_initial_tests", "observation_chars"]


def test_a_saving_that_sits_in_one_task_is_flagged_and_not_refused():
    estimates = [estimate("t01", predicted=40.0, recorded=100.0),
                 estimate("t02", predicted=98.0, recorded=100.0),
                 estimate("t03", predicted=99.0, recorded=100.0)]

    row = screen(replace(BASE, observation_chars=800), estimates=estimates)

    assert not row["blocked"], "the measurement decides this, not the screen"
    claim = row["flags"][0]
    assert claim["task"] == "t01"
    assert claim["share"] > 0.9
    assert "sits in t01" in claim["note"]


def test_a_saving_spread_over_the_tasks_is_not_flagged():
    estimates = [estimate("t01", predicted=80.0, recorded=100.0),
                 estimate("t02", predicted=80.0, recorded=100.0),
                 estimate("t03", predicted=80.0, recorded=100.0)]

    row = screen(replace(BASE, observation_chars=800), estimates=estimates)

    assert row["flags"] == []


def test_raising_temperature_and_turning_a_dead_knob_are_flagged():
    noisy = screen(replace(BASE, temperature=0.8))
    dead = screen(replace(BASE, window_steps=4))

    assert any(flag["kind"] == "temperature_raised" for flag in noisy["flags"])
    assert any(flag["kind"] == "dead_knob" for flag in dead["flags"])
    assert not noisy["blocked"] and not dead["blocked"]


def test_the_incumbent_under_another_name_is_flagged_as_no_change():
    row = screen(replace(BASE, name="baseline_again"))

    assert not row["blocked"]
    assert row["fields_changed"] == []
    assert any(flag["kind"] == "no_change" for flag in row["flags"])


def test_a_round_is_reported_when_it_ignores_a_stall():
    """Stalling is a fact about the search, and the round has to answer it or say so."""
    candidate = replace(BASE, name="more_window", observation_chars=800)
    verdicts = [{"policy": "more_window", "predicted_saving": 0.2, "path": "online"}]
    state = {"round_budget": 4, "stalled": True, "untouched_components": ["control"]}

    data = critic.screen_round([candidate], BASE, verdicts,
                               {"more_window": [estimate("t01", predicted=80.0,
                                                         recorded=100.0)]},
                               CRITERIA, state)

    assert data["stalled"] is True
    assert data["stall_answered"] is False
    assert data["into_untouched"] == []

    into_control = replace(BASE, name="shorter_budget", max_steps=8)
    data = critic.screen_round([into_control], BASE,
                               [{"policy": "shorter_budget", "predicted_saving": 0.2,
                                 "path": "online"}],
                               {"shorter_budget": []}, CRITERIA, state)

    assert data["stall_answered"] is True
    assert data["into_untouched"] == ["shorter_budget"]


def test_the_budget_the_screen_uses_is_the_one_the_round_will_use():
    state = rsi.edits.state([], rsi.load_criteria(), round_index=1)
    data = critic.screen_round([get_policy("baseline")], get_policy("baseline"), [],
                               {}, rsi.load_criteria(), state)

    assert data["budget"] == state["round_budget"]
    assert pytest.approx(data["budget"]) == len(rsi.edits.FIELD_COMPONENT)
