"""The screen a candidate passes before a real run is spent on it.

RRSI puts its critic *before* the measurement: a domain denylist plus a model
review, so that a proposal locked to the evaluation set is refused while it is
still free. The equivalent risk here is narrower and can be stated exactly: the
harness has eleven fields, a candidate is a bundle of them, and a bundle whose
parts cannot be told apart produces a verdict that cannot be acted on. Eleven
rounds of this loop already produced one such bundle whose two halves were
useless apart and only worked together — the budget below is set so that a
two-field edit survives and a six-field one does not.

Two checks block, both because the policy provably cannot do what its own
numbers claim:

  not_workable  a field is set where the agent cannot function at all: no steps,
                no visibility of tool output, a history window of zero;
  over_budget   the edit moves more fields than the round budget allows, so a
                refusal or an acceptance would not say which part did it.

Everything else is a flag, recorded in the round and handed to the proposer, not
a veto. A candidate whose predicted saving comes from one task, a candidate that
raises temperature in a measurement that has to beat noise, a knob turned while
the mode that reads it is off: these are worth knowing and are not worth
refusing, because the online measurement is what decides them anyway.
"""

from __future__ import annotations

import edits
from policy import HarnessPolicy


def _workability(candidate: HarnessPolicy, rules: dict) -> list[str]:
    """Reasons this policy cannot run, as opposed to reasons it may be bad."""
    reasons = []
    floor = int(rules.get("min_max_steps", 3))
    if candidate.max_steps < floor:
        reasons.append(f"max_steps {candidate.max_steps} is below the floor {floor}: the "
                       "agent cannot finish a task in that many calls")
    if candidate.observation_chars == 0:
        reasons.append("observation_chars 0: the agent would never see any tool output")
    if candidate.read_lines < 1:
        reasons.append(f"read_lines {candidate.read_lines}: no read could return a line")
    if candidate.context_mode == "window" and candidate.window_steps < 1:
        reasons.append("context_mode 'window' with window_steps below 1: no history at all")
    return reasons


def _single_task_claim(estimates: list, rules: dict) -> dict | None:
    """Where a predicted saving comes from, when it comes from one task.

    The judge predicts a token count per task. A candidate whose whole predicted
    saving sits in one task is a claim about that task's shape, not about the
    harness, and the honest reading of it is a flag rather than a refusal — the
    round measures online anyway, and measurement is what settles it.
    """
    rows = [e for e in estimates if getattr(e, "prompt_tokens_recorded", 0)]
    tasks = {e.task for e in rows}
    if len(tasks) < 2:
        return None
    gains = {e.task: e.prompt_tokens_recorded - e.prompt_tokens_predicted for e in rows}
    positive = sum(gain for gain in gains.values() if gain > 0)
    if positive <= 0:
        return None
    best_task = max(gains, key=lambda task: gains[task])
    share = gains[best_task] / positive
    limit = float(rules.get("max_single_task_share", 0.9))
    if share <= limit:
        return None
    return {"task": best_task, "share": round(share, 3), "limit": limit,
            "tasks": len(rows),
            "note": f"{share:.0%} of the predicted saving sits in {best_task}"}


def screen(candidate: HarnessPolicy, base: HarnessPolicy, verdict: dict | None,
           estimates: list, criteria: dict, budget: int) -> dict:
    """One candidate's verdict from the screen: blocked, or flagged and let through."""
    rules = criteria.get("critic") or {}
    move = edits.change(base, candidate)
    reasons = _workability(candidate, rules)
    if len(move["fields"]) > budget:
        reasons.append(
            f"moves {len(move['fields'])} fields ({', '.join(sorted(move['fields']))}) and "
            f"this round allows {budget}: split it, so that an acceptance or a refusal "
            "says which part did it")

    flags = []
    claim = _single_task_claim(estimates, rules)
    if claim:
        flags.append(claim)
    if candidate.temperature > base.temperature:
        flags.append({"kind": "temperature_raised", "from": base.temperature,
                      "to": candidate.temperature,
                      "note": "a raised temperature widens the spread of the very "
                              "measurement that has to beat the noise floor"})
    if candidate.context_mode == "full" and candidate.window_steps != base.window_steps:
        flags.append({"kind": "dead_knob", "field": "window_steps",
                      "note": "window_steps is set while context_mode is 'full', which "
                              "never reads it"})
    if not move["components"]:
        flags.append({"kind": "no_change",
                      "note": "the candidate is the incumbent under another name"})

    return {
        "policy": candidate.name,
        "blocked": bool(reasons),
        "reasons": reasons,
        "flags": flags,
        "components": move["components"],
        "fields_changed": sorted(move["fields"]),
        "budget": budget,
        "predicted_saving": (verdict or {}).get("predicted_saving"),
        "decision_replayable": (verdict or {}).get("decision_replayable"),
    }


def screen_round(candidates: list[HarnessPolicy], base: HarnessPolicy,
                 verdicts: list[dict], estimates: dict[str, list],
                 criteria: dict, search_state: dict) -> dict:
    """Screen every candidate, and check the stall rule was answered.

    On stall the loop is expected to put at least one candidate into a component
    it has never touched. That expectation is reported rather than enforced: a
    search that is forbidden from returning to a promising component because a
    counter says so is a search that cannot use what it has learned.
    """
    budget = int(search_state.get("round_budget") or len(edits.FIELD_COMPONENT))
    by_name = {v["policy"]: v for v in verdicts}
    rows = [screen(candidate, base, by_name.get(candidate.name),
                   estimates.get(candidate.name) or [], criteria, budget)
            for candidate in candidates]
    blocked = [row["policy"] for row in rows if row["blocked"]]
    untouched = search_state.get("untouched_components") or []
    into_untouched = [row["policy"] for row in rows
                      if set(row["components"]) & set(untouched)]
    return {
        "budget": budget,
        "screened": rows,
        "blocked": blocked,
        "passed": [row["policy"] for row in rows if not row["blocked"]],
        "flags": [{"policy": row["policy"], **flag} for row in rows for flag in row["flags"]],
        "stalled": bool(search_state.get("stalled")),
        "stall_answered": (not search_state.get("stalled")) or bool(into_untouched),
        "into_untouched": into_untouched,
        "unstalled_components": untouched,
    }


def render(data: dict) -> str:
    lines = [f"Screen for this round (budget {data['budget']} fields per candidate):", "",
             "| candidate | blocked | why | flags |", "|---|---|---|---|"]
    for row in data["screened"]:
        why = "; ".join(row["reasons"]) or "-"
        flags = "; ".join(flag.get("note", flag.get("kind", "")) for flag in row["flags"]) or "-"
        lines.append(f"| {row['policy']} | {'yes' if row['blocked'] else 'no'} | {why} | "
                     f"{flags} |")
    if data["stalled"]:
        lines += ["", f"The search is stalled and this round "
                      f"{'did' if data['stall_answered'] else 'did not'} put a candidate into "
                      f"an untouched component "
                      f"({', '.join(data['unstalled_components']) or 'none left'})."]
    return "\n".join(lines)
