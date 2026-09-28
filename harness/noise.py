"""The noise floor: how large a measured difference has to be to be a difference.

Round 9 of this loop deployed a policy measured on one run per task. It read
-3.4% on the search set; with three runs per task the same policy read +4.0%.
Version 5 of the criteria answered that by demanding three runs, which reduces
the noise without saying how large a saving has to be before it is larger than
the noise. This module answers the second half.

The floor is a bootstrap interval of the difference itself. Both sides are runs
that already exist: the incumbent's recorded runs on one side, the runs the round
just made on the other. Drawing a measurement from each side repeatedly says how
far apart two measurements of *these two* policies land when the only thing
varying is which runs came up, and the rule is the strict reading — the whole
interval has to sit on the saving side of zero.

RRSI calibrates a delta from repeats of one policy (`calibrate.py`), which
answers "how much does this policy differ from itself". That is the right
question for a repeat measurement and the wrong one here: the decision compares
two different policies, and the spread of one policy against itself is not the
spread of that comparison. Using it would be wrong in both directions — a
low-variance candidate would be held to the incumbent's much wider spread, and a
noisy candidate would be let through by a quiet incumbent. The same-policy
question is still answerable, from `rsi.py --repeat-round`.
"""

from __future__ import annotations

import random
import statistics


def runs_by_task(records: list[dict], families: list[str],
                 tasks: list[str]) -> dict[str, list[int]]:
    """Prompt tokens per task for every run of the named policy families.

    A family is one policy with its repeats: `base`, `reference-baseline`,
    `reference-baseline-r2` are four runs of the hand-written baseline, and they
    are four measurements of one thing rather than four policies.
    """
    runs: dict[str, list[int]] = {}
    for record in records:
        label = record.get("label") or ""
        family = label.rpartition("-r")[0] if label.rpartition("-r")[2].isdigit() else label
        if family not in families or record["task"] not in tasks:
            continue
        runs.setdefault(record["task"], []).append((record.get("tokens") or {}).get("input", 0))
    return runs


def _quantile(sorted_values: list[float], probability: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = probability * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return sorted_values[low] * (1 - weight) + sorted_values[high] * weight


def bootstrap_interval(before: dict[str, list[int]], after: dict[str, list[int]],
                       alpha: float = 0.05, resamples: int = 2000,
                       seed: int = 20260925) -> dict:
    """The interval the measured difference has to clear, from both sides' runs.

    Each draw is a measurement rather than a single run: per task it averages as
    many runs as the sparser side actually has, and the two sides are summed and
    divided the way `compare()` divides them.

    Both sides need at least two runs per task, and this is not a convenience.
    With one run on a side the mean of that side is a single fixed value, the
    bootstrap cannot estimate its spread at all, and every resample then measures
    only the *other* side's noise — which makes the other side's spread look like
    a difference. A wall clock reading taken once is not a measurement of a
    clock's precision, and the same holds here.
    """
    tasks = sorted(task for task in set(before) & set(after)
                   if len(before[task]) >= 2 and len(after[task]) >= 2)
    runs = {t: {"before": len(before[t]), "after": len(after[t])}
            for t in sorted(set(before) & set(after))}
    if not tasks:
        return {"measured": False, "conclusion": "unmeasured", "alpha": alpha,
                "resamples": 0, "tasks": 0, "runs_per_task": runs,
                "note": "no task has two runs on both sides: a side measured once has "
                        "no spread to estimate, and the interval would report the "
                        "other side's noise as a difference"}
    if len(tasks) < 2:
        return {"measured": False, "conclusion": "unmeasured", "alpha": alpha,
                "resamples": 0, "tasks": len(tasks), "runs_per_task": runs,
                "note": "only one task has runs on both sides, too few for an "
                        "interval to rest on"}

    rng = random.Random(seed)
    sides = {task: (max(1, len(before[task])), max(1, len(after[task]))) for task in tasks}
    deltas = []
    for _ in range(resamples):
        total_before = total_after = 0.0
        for task in tasks:
            runs_before, runs_after = sides[task]
            total_before += statistics.mean(rng.choices(before[task], k=runs_before))
            total_after += statistics.mean(rng.choices(after[task], k=runs_after))
        deltas.append((total_after - total_before) / total_before if total_before else 0.0)
    deltas.sort()
    low = _quantile(deltas, alpha / 2)
    high = _quantile(deltas, 1 - alpha / 2)
    point = ((sum(statistics.mean(after[t]) for t in tasks)
              - sum(statistics.mean(before[t]) for t in tasks))
             / sum(statistics.mean(before[t]) for t in tasks))
    conclusion = "saving" if high < 0 else "cost" if low > 0 else "unclear"
    return {
        "measured": True,
        "conclusion": conclusion,
        "point": round(point, 4),
        "low": round(low, 4),
        "high": round(high, 4),
        "alpha": alpha,
        "resamples": resamples,
        "tasks": len(tasks),
        "runs_per_task": {t: {"before": len(before[t]), "after": len(after[t])}
                          for t in tasks},
        "note": f"{conclusion} at alpha {alpha}: 95% of the resampled differences fall "
                f"between {low:+.1%} and {high:+.1%}",
    }


def verdict(floor: dict) -> dict:
    """What the interval says about the measurement the round already made."""
    if not floor.get("measured"):
        return {"beyond_noise": None, "conclusion": "unmeasured", "floor": None,
                "note": floor.get("note", "no interval was drawn")}
    conclusion = floor["conclusion"]
    note = (f"measured {floor['point']:+.1%}, interval "
            f"[{floor['low']:+.1%}, {floor['high']:+.1%}] at alpha {floor['alpha']}")
    if conclusion == "unclear":
        note += (": the interval straddles zero, so this is not a change. Saving and "
                 "cost of the same size are both inside the spread of these runs")
    return {
        "beyond_noise": conclusion != "unclear",
        "conclusion": conclusion,
        "floor": floor,
        "note": note,
    }


def render(floor: dict, source: str | None = None) -> str:
    if not floor.get("measured"):
        return f"No interval drawn: {floor.get('note')}."
    runs = ", ".join(f"{task} {counts['before']}v{counts['after']}"
                     for task, counts in sorted(floor["runs_per_task"].items()))
    return "\n".join([
        f"Bootstrap interval of the measured difference, {floor['resamples']} resamples, "
        f"incumbent runs from {source or 'the recorded baseline'}:",
        "",
        "| quantity | value |", "|---|---|",
        f"| point estimate | {floor['point']:+.1%} |",
        f"| interval at alpha {floor['alpha']} | [{floor['low']:+.1%}, {floor['high']:+.1%}] |",
        f"| conclusion | {floor['conclusion']} |",
        f"| tasks | {floor['tasks']} |",
        f"| runs per task (incumbent v candidate) | {runs} |",
        "",
        "A difference whose whole interval does not sit on one side of zero is the "
        "spread of these runs, not a change, and is not reported as one.",
    ])
