"""The edit ledger: what a candidate changed, and what the search has worn out.

The ledger exists because eleven rounds of this loop could not answer a question
about themselves: which component of the harness had been edited, and which had
been edited and refused until it stopped being worth trying. These tests pin the
answers, and pin the rule that an old round without a ledger is still counted —
a history that starts the day the bookkeeping was added is a history with its
failures removed.
"""

from dataclasses import replace

import edits
import pytest
from policy import HarnessPolicy, get_policy

BASE = HarnessPolicy()


def _round(index: int, candidate: HarnessPolicy, *, verdict: str, accepted: bool = False,
           predicted: float = 0.2, hypothesis: str = "") -> dict:
    return edits.record(index, candidate, BASE, verdict=verdict, hypothesis=hypothesis,
                        predicted_saving=predicted)


def test_a_change_names_the_components_it_touches():
    move = edits.change(BASE, replace(BASE, observation_chars=800))

    assert move["components"] == ["history"]
    assert move["fields"] == {"observation_chars": [2000, 800]}

    both = edits.change(BASE, replace(BASE, include_initial_tests=False, max_steps=8))
    assert sorted(both["components"]) == ["context", "control"]
    assert edits.change(BASE, BASE) == {"components": [], "fields": {}}


def test_only_a_deployed_edit_is_accepted():
    deployed = _round(1, replace(BASE, max_steps=8), verdict="deployed")
    refused = _round(1, replace(BASE, read_lines=60), verdict="refused_by_gate")
    measured = _round(1, replace(BASE, read_lines=60), verdict="measured_worse")

    assert deployed["accepted"] is True
    assert refused["accepted"] is False
    assert measured["accepted"] is False


def test_an_unknown_verdict_is_refused_rather_than_stored():
    with pytest.raises(ValueError):
        edits.record(1, BASE, BASE, verdict="probably_fine")


def test_an_edit_without_a_reason_gets_a_derived_one_and_says_so():
    row = _round(1, replace(BASE, observation_chars=800), verdict="refused_by_gate")

    assert row["hypothesis_source"] == "derived"
    assert "observation_chars" in row["hypothesis"]

    stated = _round(1, replace(BASE, observation_chars=800), verdict="refused_by_gate",
                    hypothesis="history: shorter output, because the traces show it is unused")
    assert stated["hypothesis_source"] == "proposer"
    assert stated["hypothesis"].startswith("history:")


def test_the_budget_anneals_and_never_forbids_the_edit_that_worked():
    """The one edit this search ever deployed moved two fields and only worked as a pair."""
    criteria = {"search": {"edit_budget": {"decay": 0.9, "min_fields": 2}}}
    total = len(edits.FIELD_COMPONENT)

    budgets = [edits.field_budget(round_index, criteria, total) for round_index in range(1, 30)]

    assert budgets[0] == total, "the first round may move everything"
    assert budgets == sorted(budgets, reverse=True), "and the budget only shrinks"
    assert min(budgets) == 2, "and stops at the pair that worked, not at one field"


def test_the_search_state_says_what_was_never_touched_and_what_wore_out():
    control_once = _round(1, replace(BASE, max_steps=8), verdict="refused_by_gate")
    control_again = _round(2, replace(BASE, max_steps=9), verdict="refused_by_gate")
    kept = _round(3, replace(BASE, observation_chars=1500), verdict="deployed")
    criteria = {"search": {"stall_window": 5, "pruned_after": 2}}

    state = edits.state([control_once, control_again, kept], criteria, round_index=4)

    assert state["components"]["control"] == {"edits": 2, "accepted": 0, "refused": 2,
                                              "rounds": [1, 2]}
    assert state["worn_out_components"] == ["control"]
    assert state["untouched_components"] == ["context"], "context was never edited"
    assert state["last_accepted_round"] == 3
    assert state["stall_rounds"] == 1
    assert not state["stalled"]
    assert state["novelty"] == pytest.approx(2 / 3, abs=1e-3), (
        "two of three components have no accepted edit")


def test_a_stalled_search_is_named_rather_than_left_to_be_inferred():
    rows = [_round(index, replace(BASE, observation_chars=1000 + index),
                   verdict="refused_by_gate")
            for index in range(1, 8)]
    criteria = {"search": {"stall_window": 5, "pruned_after": 2}}

    state = edits.state(rows, criteria, round_index=8)

    assert state["stalled"] is True
    assert state["stall_rounds"] == 8
    assert state["last_accepted_round"] is None


def test_a_round_without_a_ledger_is_still_counted():
    """Eleven rounds predate this bookkeeping; dropping them would hide their failures."""
    payload = {
        "round": 11,
        "proposed": [{"name": "winner", "include_initial_tests": False,
                      "observation_chars": 1500},
                     {"name": "also_ran", "read_lines": 60}],
        "verdicts": [
            {"policy": "winner", "predicted_saving": 0.294, "decision_replayable": 0.72,
             "path": "online", "reasons": ["predicted saving 29.4% vs required 15%"]},
            {"policy": "also_ran", "predicted_saving": 0.02, "decision_replayable": 0.9,
             "path": "refused", "reasons": ["predicted saving 2.0% vs required 15%"]},
        ],
        "deployed": {"policy": {"name": "winner"},
                     "comparison": {"search": {"token_delta": -0.133, "tasks_lost": 0,
                                               "token_scope_tasks": ["t01", "t02"]}}},
    }

    rows = edits.backfill([payload])
    by_name = {row["candidate"]: row for row in rows}

    assert len(rows) == 2
    assert by_name["winner"]["verdict"] == "deployed"
    assert by_name["winner"]["measured_saving"] == pytest.approx(-0.133)
    assert by_name["winner"]["components"] == ["context", "history"]
    assert by_name["also_ran"]["verdict"] == "refused_by_gate"
    assert all(row["hypothesis_source"] == "derived" for row in rows)


def test_a_round_with_its_own_rows_is_not_rebuilt_over_them():
    payload = {"round": 1, "edits": [{"round": 1, "candidate": "kept", "components": [],
                                      "fields": {}, "hypothesis": "written down",
                                      "verdict": "refused_by_gate", "accepted": False}],
               "proposed": [], "verdicts": []}

    assert edits.rows_for(payload) == payload["edits"]
    assert edits.ledger([payload]) == payload["edits"]


def test_the_recorded_rounds_are_readable_as_a_ledger():
    """The real history, from disk: 29 edits over eleven rounds, four kept."""
    import rsi

    rows = edits.ledger(rsi.load_rounds())
    if not rows:
        pytest.skip("no rounds recorded yet")
    data = edits.summary(rows)

    assert data["rounds"] >= 11
    assert data["edits"] == len(rows)
    assert data["accepted"] <= data["edits"]
    assert set(data["components"]) == set(edits.COMPONENTS), "every component has a bucket"
    assert all(row["components"] for row in rows if row["fields"]), (
        "an edit that moves a field names the component that field belongs to")
    assert get_policy("baseline") is not None
