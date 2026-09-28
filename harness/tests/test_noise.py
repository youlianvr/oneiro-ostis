"""The interval: a difference has to clear its own measurement noise.

Round 9 is the reason this module exists. It deployed a policy that read -3.4%
from one run per task and +4.0% from three, and no rule in the loop could have
told those two numbers apart, because no rule asked how far apart two
measurements of the same thing can land. These tests hold the interval to that
job, including the case it must refuse to answer at all.
"""

import noise
import pytest


def test_a_policy_measured_against_itself_is_not_a_difference():
    """Both sides are runs of one policy: the honest answer is that nothing moved."""
    runs = {task: [100, 104, 96, 101] for task in ("t01", "t02", "t03")}
    floor = noise.bootstrap_interval(runs, {k: list(v) for k, v in runs.items()})

    assert floor["measured"]
    assert floor["conclusion"] == "unclear"
    assert floor["low"] < 0 < floor["high"]


def test_a_saving_larger_than_the_spread_is_a_saving():
    before = {task: [400, 410, 390, 405] for task in ("t01", "t02", "t03")}
    after = {task: [300, 305, 295, 302] for task in ("t01", "t02", "t03")}

    floor = noise.bootstrap_interval(before, after)

    assert floor["conclusion"] == "saving"
    assert floor["point"] == pytest.approx(-0.26, abs=0.02)
    assert floor["high"] < 0
    assert "saving" in floor["note"]


def test_a_cost_of_the_same_size_is_a_cost():
    before = {task: [300, 305, 295, 302] for task in ("t01", "t02")}
    after = {task: [400, 410, 390, 405] for task in ("t01", "t02")}

    floor = noise.bootstrap_interval(before, after)

    assert floor["conclusion"] == "cost"
    assert floor["low"] > 0


def test_a_side_measured_once_is_not_a_measurement():
    """One run has no spread to estimate, and would report the other side's noise."""
    before = {"t01": [100, 104, 96, 101], "t02": [200, 205, 195, 202]}
    after = {"t01": [100], "t02": [200]}

    floor = noise.bootstrap_interval(before, after)

    assert not floor["measured"]
    assert floor["conclusion"] == "unmeasured"
    assert "no spread to estimate" in floor["note"]
    assert floor["runs_per_task"]["t01"] == {"before": 4, "after": 1}


def test_one_task_is_not_enough_to_rest_an_interval_on():
    floor = noise.bootstrap_interval({"t01": [100, 104, 96]}, {"t01": [90, 91, 92]})

    assert not floor["measured"]
    assert "one task" in floor["note"]


def test_the_interval_is_not_decided_by_which_runs_came_up():
    """Same inputs, same answer: a floor that moved between runs would move verdicts."""
    before = {task: [400, 410, 390, 405, 398] for task in ("t01", "t02", "t03")}
    after = {task: [340, 350, 330, 345, 338] for task in ("t01", "t02", "t03")}

    first = noise.bootstrap_interval(before, after)
    second = noise.bootstrap_interval(before, after)

    assert first == second


def test_the_verdict_reads_the_interval_rather_than_the_point_estimate():
    before = {task: [400, 410, 390, 405] for task in ("t01", "t02", "t03")}
    inside = noise.bootstrap_interval(before, {t: [380, 430, 390, 400] for t in before})
    outside = noise.bootstrap_interval(before, {t: [250, 260, 240, 255] for t in before})

    unclear = noise.verdict(inside)
    saving = noise.verdict(outside)

    assert unclear["beyond_noise"] is False
    assert "straddles zero" in unclear["note"]
    assert saving["beyond_noise"] is True
    assert saving["conclusion"] == "saving"


def test_an_unmeasured_floor_says_so_instead_of_asserting_one():
    call = noise.verdict(noise.bootstrap_interval({}, {}))

    assert call["beyond_noise"] is None
    assert call["conclusion"] == "unmeasured"
    assert "no interval" in noise.render(noise.bootstrap_interval({}, {})).lower()


def test_runs_are_gathered_by_policy_family():
    records = [
        {"task": "t01", "label": "reference-baseline", "tokens": {"input": 100}},
        {"task": "t01", "label": "reference-baseline-r2", "tokens": {"input": 110}},
        {"task": "t01", "label": "reference-baseline-r3", "tokens": {"input": 120}},
        {"task": "t01", "label": "reference-terse-r1", "tokens": {"input": 90}},
        {"task": "t02", "label": "reference-baseline-r2", "tokens": {"input": 200}},
    ]

    runs = noise.runs_by_task(records, ["reference-baseline"], ["t01", "t02"])

    assert runs == {"t01": [100, 110, 120], "t02": [200]}


def test_the_real_control_against_the_real_baseline_is_not_a_difference():
    """The hand-written window3 policy was the judge's favourite. It was never a saving.

    Its own runs are on disk, three per task, and this is the measurement the
    rules of version 4 were revised over. If the interval ever calls this a
    saving, the interval is wrong.
    """
    import replay
    import rsi

    criteria = rsi.load_criteria()
    tasks = criteria["search_tasks"]
    records = replay.load_records()
    before = noise.runs_by_task(records,
                                list((criteria.get("noise") or {}).get("runs_from") or []),
                                tasks)
    after = noise.runs_by_task(records, ["reference-window3"], tasks)
    if not before or not after:
        pytest.skip("the control runs are not on disk")

    floor = noise.bootstrap_interval(before, after)

    assert floor["measured"]
    assert floor["conclusion"] == "unclear"
