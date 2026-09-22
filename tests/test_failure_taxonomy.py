"""The labeller must name only what the record actually shows."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

from failure_taxonomy import (  # noqa: E402
    CATEGORIES,
    MODES,
    label_episode,
    label_judge_refusal,
    label_tool_trace,
    summarize,
)


def ids(labels) -> list[str]:
    return [label.mode.mode_id for label in labels]


def test_the_taxonomy_has_the_papers_shape():
    assert len(MODES) == 14
    assert {mode.category for mode in MODES} == set(CATEGORIES)
    assert len({mode.mode_id for mode in MODES}) == 14
    assert all(0 < mode.share < 1 for mode in MODES)
    assert abs(sum(mode.share for mode in MODES) - 1.0) < 0.01


def test_running_out_of_steps_is_a_termination_failure():
    labels = label_episode({"stop_reason": "max_steps", "solved": False, "tool_calls": 9})
    assert ids(labels) == ["FM-1.5"]


def test_many_steps_beside_the_ceiling_also_read_as_repetition():
    labels = label_episode({"stop_reason": "max_steps", "solved": False, "tool_calls": 14})
    assert ids(labels) == ["FM-1.5", "FM-1.3"]


def test_claiming_success_while_the_checks_fail_is_incorrect_verification():
    labels = label_episode({"stop_reason": "finished", "solved": False,
                            "final_text": "all three tests pass", "tool_calls": 5})
    assert ids(labels) == ["FM-3.3"]


def test_stopping_silently_without_result_is_premature_termination():
    labels = label_episode({"stop_reason": "finished", "solved": False,
                            "final_text": "", "tool_calls": 5})
    assert ids(labels) == ["FM-3.1"]


def test_a_solved_episode_carries_no_failure_label():
    assert label_episode({"stop_reason": "finished", "solved": True, "tool_calls": 6}) == []


def test_a_record_that_is_not_a_record_labels_nothing():
    assert label_episode(None) == []
    assert label_episode({"weird": object()}) == []


def test_repeating_the_same_call_three_times_is_repetition():
    steps = [{"name": "bash", "arguments": {"command": "pytest -q"}}] * 3
    assert ids(label_tool_trace(steps)) == ["FM-1.3"]


def test_two_identical_calls_are_not_a_failure():
    steps = [{"name": "bash", "arguments": {"command": "pytest -q"}}] * 2
    assert label_tool_trace(steps) == []


def test_the_judge_coverage_rule_is_incomplete_verification():
    label = label_judge_refusal("coverage: only 0 of 26 decisions were recovered")
    assert label is not None and label.mode.mode_id == "FM-3.2"


def test_a_candidate_measured_worse_is_incorrect_verification():
    label = label_judge_refusal("the candidate is worse on held-out tasks")
    assert label is not None and label.mode.mode_id == "FM-3.3"


def test_an_unrecognised_reason_stays_unlabelled():
    # A wrong label is worse than none: this is the whole point of the module.
    assert label_judge_refusal("the queue was busy") is None


def test_each_label_carries_its_citation_and_counts_by_category():
    labels = label_episode({"stop_reason": "max_steps", "solved": False, "tool_calls": 14})
    payload = labels[0].as_payload()
    assert "2503.13657" in payload["taxonomy"]
    assert payload["category"] in CATEGORIES
    counts = summarize(labels)
    assert counts["FC1 System Design Issues"] == 2
    assert counts["FC3 Task Verification"] == 0
