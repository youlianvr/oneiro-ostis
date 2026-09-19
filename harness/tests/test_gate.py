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


def test_version_1_criteria_are_kept_for_the_rounds_written_under_them():
    """A later revision must not relabel an earlier result."""
    version_1 = rsi.criteria_for(1)

    assert version_1["version"] == 1
    assert version_1["efficiency"]["min_predicted_saving"] == 0.15
    assert "min_decision_replayable" not in version_1["capability"]
    assert rsi.criteria_for(99) == {}


def test_recheck_refuses_what_the_recorded_rounds_deployed():
    """The revision is judged against the history that exposed it."""
    rows = rsi.recheck()
    if not rows:
        pytest.skip("no rounds recorded yet")

    refused = [r for r in rows if r["passed_then"] and not r["passed_now"]]
    assert all(r["decision_replayable"] < 0.5 for r in refused)
    assert all(r["deployed_then"] for r in refused), (
        "the only verdicts the revision flips are ones the loop acted on"
    )
