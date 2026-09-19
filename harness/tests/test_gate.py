"""The gate: a predicted saving without replayed decisions is not evidence.

Rounds 2 and 3 of the live loop exposed this: two candidates were deployed with
`decision_replayable` 0.0, because the criteria named a coverage field no code
read. These tests pin the clause that closed it. They are offline: a gate is a
function of estimates, not of a provider.
"""

import pytest

import replay
import rsi
from policy import get_policy


def estimate(name: str, *, predicted: float, recorded: float, covered: int, total: int):
    return replay.Estimate(
        task="t01-start-total",
        policy=name,
        steps_covered=covered,
        steps_total=total,
        prompt_tokens_predicted=predicted,
        prompt_tokens_recorded=recorded,
    )


def test_large_predicted_saving_with_no_replayed_decisions_is_refused():
    criteria = rsi.CRITERIA_V2
    estimates = {
        "unreplayable": [estimate("unreplayable", predicted=50.0, recorded=100.0,
                                  covered=0, total=10)],
    }
    verdict = rsi.gate([get_policy("baseline")], estimates, criteria)[0]

    assert verdict["predicted_saving"] == pytest.approx(0.5)
    assert verdict["passed_efficiency"], "the saving itself is real, as a claim about tokens"
    assert verdict["decision_replayable"] == 0.0
    assert not verdict["passed_evidence"]
    assert not verdict["passed_gate"], "no replayed decision, no deployment"


def test_enough_replayed_decisions_lets_a_saving_through():
    criteria = rsi.CRITERIA_V2
    estimates = {
        "replayable": [estimate("replayable", predicted=50.0, recorded=100.0,
                                covered=8, total=10)],
    }
    verdict = rsi.gate([get_policy("baseline")], estimates, criteria)[0]

    assert verdict["decision_replayable"] == pytest.approx(0.8)
    assert verdict["passed_gate"]


def test_the_threshold_is_the_frozen_one():
    """The floor comes from the criteria, so a search cannot move it quietly."""
    criteria = rsi.CRITERIA_V2
    floor = criteria["capability"]["min_decision_replayable"]
    assert floor == rsi.CRITERIA_HISTORY[2]["capability"]["min_decision_replayable"]

    below = rsi.gate(
        [get_policy("baseline")],
        {"c": [estimate("c", predicted=10.0, recorded=100.0, covered=int(floor * 10) - 1, total=10)]},
        criteria,
    )[0]
    assert not below["passed_evidence"]


def test_a_policy_that_changes_the_trajectory_must_be_measured_before_it_deploys():
    """Coverage counts aligned prompts, not the steps the agent will then take.

    A windowed policy at 62% coverage was predicted to save 15% and cost 20%
    more, because with less history the agent took more steps. So a trajectory
    changing policy is routed to `verify` even when it passes the coverage floor.
    """
    from dataclasses import replace

    windowed = replace(get_policy("baseline"), name="windowed_x",
                       context_mode="window", window_steps=3)
    estimates = {"windowed_x": [estimate("windowed_x", predicted=80.0, recorded=100.0,
                                         covered=8, total=10)]}
    verdict = rsi.gate([windowed], estimates, rsi.CRITERIA_V4)[0]

    assert verdict["decision_replayable"] == pytest.approx(0.8)
    assert verdict["passed_gate"], "it clears both thresholds"
    assert verdict["path"] == "verify", "and is still measured before deployment"
    assert "context_mode" in verdict["changed_fields"]
    assert any("changes the trajectory" in reason for reason in verdict["reasons"])


def test_a_policy_that_changes_nothing_deploys_on_the_replay_verdict():
    estimates = {"baseline": [estimate("baseline", predicted=80.0, recorded=100.0,
                                       covered=10, total=10)]}
    verdict = rsi.gate([get_policy("baseline")], estimates, rsi.CRITERIA_V4)[0]

    assert verdict["path"] == "replay"
    assert verdict["changed_fields"] == []


def test_an_unjudgeable_candidate_takes_the_online_path_instead_of_a_silent_ban():
    """Abstaining is a verdict, not a ban: the candidate gets measured online."""
    estimates = {"u": [estimate("u", predicted=60.0, recorded=100.0, covered=0, total=10)]}
    verdict = rsi.gate([get_policy("baseline")], estimates, rsi.CRITERIA_V3)[0]

    assert not verdict["passed_evidence"]
    assert verdict["path"] == "online"
    assert rsi.CRITERIA_V3["evidence"]["unjudgeable_path"]["enabled"]


def test_without_the_online_path_the_same_candidate_is_refused():
    estimates = {"u": [estimate("u", predicted=60.0, recorded=100.0, covered=0, total=10)]}
    verdict = rsi.gate([get_policy("baseline")], estimates, rsi.CRITERIA_V2)[0]

    assert verdict["path"] == "refused"
    assert "evidence" not in rsi.CRITERIA_V2


def test_the_proposer_is_told_what_the_judge_could_not_judge():
    """The loop must not walk back into the family it cannot judge, unwarned."""
    history = [
        {"policy": "no_initial_tests", "decision_replayable": 0.0, "predicted_saving": 0.225},
        {"policy": "window6_obs1500", "decision_replayable": 0.885, "predicted_saving": 0.036},
        {"policy": "incumbent (baseline)"},
    ]
    briefing = rsi.judge_briefing(history, rsi.CRITERIA_V3)

    assert briefing["past_unjudgeable"] == ["no_initial_tests"]
    assert briefing["replay_floor"] == 0.5


def test_version_1_criteria_are_kept_for_the_rounds_written_under_them():
    """A later revision must not relabel an earlier result."""
    version_1 = rsi.criteria_for(1)

    assert version_1["version"] == 1
    assert version_1["efficiency"]["min_predicted_saving"] == 0.15
    assert "min_decision_replayable" not in version_1["capability"]
    assert "evidence" not in rsi.criteria_for(2)
    assert rsi.criteria_for(3)["evidence"]["unjudgeable_path"]["max_online_runs"] == 4
    assert "trajectory_changes" not in rsi.criteria_for(3)["evidence"]
    assert rsi.criteria_for(4)["evidence"]["trajectory_changes"]["fields"]
    assert rsi.criteria_for(99) == {}


def test_recheck_refuses_what_the_recorded_rounds_deployed():
    """The revision is judged against the history that exposed it."""
    rows = rsi.recheck()
    if not rows:
        pytest.skip("no rounds recorded yet")

    floor = rsi.load_criteria()["capability"]["min_decision_replayable"]
    refused = [r for r in rows if r["passed_then"] and not r["passed_now"]]
    acted_on = [r for r in rows if r["deployed_then"] and r["decision_replayable"] < floor]

    assert refused, "the revision exists because something passed the old gate"
    assert all(r["decision_replayable"] < floor for r in refused)
    assert acted_on, "the deployments that exposed the hole are part of that history"
    assert all(r in refused for r in acted_on), (
        "nothing the loop acted on without replayed evidence escapes the revision"
    )
