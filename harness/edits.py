"""The edit ledger: what each candidate changed, why, and what it cost.

RRSI (Regularized Recursive Self-Improvement of Agent Harnesses, arXiv
2609.24972) regularises the *search trajectory* rather than the edit space, and
its unit of accounting is the edit: which component of the harness was changed,
what hypothesis the change tests, what the judge predicted, what a real run
measured, and whether the change was kept. Without that unit the history of a
search is an anonymous list of field values, and eleven rounds spent on one
component look exactly like eleven rounds spent exploring.

Eleven rounds of this loop already produced that picture the hard way: the only
edit that ever survived a measurement changed two fields of `context`, and
nothing in the round files makes that visible — a reader has to diff every
proposal against the baseline by hand to see it.

This module owns the ledger. Its rows live inside the round file that produced
them, under `edits`, so a round stays one self-contained record of what was
decided and why — the rule that already keeps a round's criteria beside its
verdicts applies to its edits too. A later round reads them from disk rather
than from a model's memory, which is what makes two questions answerable that
the verdicts alone cannot answer: which parts of the harness this search has
never touched, and which it has worn out.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from policy import HarnessPolicy


@dataclass(frozen=True)
class Proposal:
    """A candidate and the reason its proposer gave for it.

    Kept apart from `HarnessPolicy` on purpose: the policy is the search space
    and must stay comparable field by field, while the reason is provenance and
    would pollute every descriptor if it lived there.
    """

    policy: HarnessPolicy
    hypothesis: str = ""

# The three components of a harness policy, in the grouping `policy.py` already
# uses: what the model is shown, what is kept from earlier steps, and when the
# loop stops.
COMPONENT_FIELDS = {
    "context": ("include_file_list", "include_initial_tests", "include_skill_catalog"),
    "history": ("context_mode", "window_steps", "observation_chars", "read_lines"),
    "control": ("max_steps", "verify_before_finish", "max_verify_nudges", "temperature"),
}
COMPONENTS = tuple(COMPONENT_FIELDS)
FIELD_COMPONENT = {name: component for component, fields in COMPONENT_FIELDS.items()
                   for name in fields}

# What became of an edit. `deployed` is the only one that means the policy
# replaced the incumbent; everything else is a refusal, and the ledger says
# which kind, because "refused on the recordings for free" and "measured and
# found worse" are different facts about the world.
VERDICTS = ("deployed", "measured_worse", "measured_incomplete", "refused_by_gate",
            "critic_blocked", "not_deployed")


# ---------- one edit ----------


def change(base: HarnessPolicy, candidate: HarnessPolicy) -> dict:
    """Every field this candidate moves, and which components those fields are in."""
    fields = {}
    for name in FIELD_COMPONENT:
        before, after = getattr(base, name), getattr(candidate, name)
        if before != after:
            fields[name] = [before, after]
    components = [c for c in COMPONENTS if any(f in fields for f in COMPONENT_FIELDS[c])]
    return {"components": components, "fields": fields}


def describe(fields: dict) -> str:
    """A mechanical reading of the diff, for edits whose proposer gave no reason.

    The hypothesis is written by the model that made the edit. When there is
    none — every round recorded before the ledger existed — this stands in its
    place and is marked as derived, rather than left blank: a blank reason reads
    as "no reason" when the truth is "not recorded".
    """
    return "; ".join(f"{name}: {before!r} -> {after!r}"
                     for name, (before, after) in sorted(fields.items()))


def record(round_index: int, candidate: HarnessPolicy, base: HarnessPolicy, *,
           verdict: str, hypothesis: str = "", predicted_saving: float | None = None,
           decision_replayable: float | None = None, path: str | None = None,
           measured_saving: float | None = None, measured_scope: int | None = None,
           tasks_lost: int | None = None, reason: str = "",
           critic: dict | None = None) -> dict:
    """One ledger row. `accepted` means the edit became the incumbent."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}; known: {VERDICTS}")
    move = change(base, candidate)
    text = hypothesis.strip() or describe(move["fields"])
    return {
        "round": round_index,
        "candidate": candidate.name,
        "components": move["components"],
        "fields": move["fields"],
        "hypothesis": text,
        "hypothesis_source": "proposer" if hypothesis.strip() else "derived",
        "verdict": verdict,
        "accepted": verdict == "deployed",
        "predicted_saving": predicted_saving,
        "decision_replayable": decision_replayable,
        "path": path,
        "measured_saving": measured_saving,
        "measured_scope": measured_scope,
        "tasks_lost": tasks_lost,
        "reason": reason,
        "critic": critic,
    }


# ---------- the ledger ----------


def rows_for(payload: dict, base: HarnessPolicy | None = None) -> list[dict]:
    """One round's edit records: its own, or rebuilt from its verdicts."""
    return payload.get("edits") or backfill([payload], base=base)


def ledger(rounds: list[dict], base: HarnessPolicy | None = None) -> list[dict]:
    """Every edit the loop has recorded, oldest round first.

    Rounds written before the ledger existed are rebuilt from their verdicts, so
    the history starts at round one rather than at the day the ledger was added.
    A search that reports only the edits it happened to record is a search that
    quietly drops its own failures.
    """
    rows: list[dict] = []
    for payload in rounds:
        rows.extend(rows_for(payload, base=base))
    return rows


def backfill(rounds: list[dict], base: HarnessPolicy | None = None) -> list[dict]:
    """The ledger the eleven recorded rounds would have written.

    Their hypotheses were never asked for, so those rows are marked `derived`
    and say so. Their verdicts and numbers are read from the round files, not
    recomputed: a ledger that disagrees with the records it was built from would
    be a second source of truth, and this project has one.
    """
    base = base or HarnessPolicy()
    rows = []
    for payload in rounds:
        proposed = {p.get("name"): p for p in payload.get("proposed") or []}
        deployed = ((payload.get("deployed") or {}).get("policy") or {})
        deployed_name = deployed.get("name")
        online_ab = (payload.get("online_ab") or {}).get("comparison") or {}
        deployed_comparison = ((payload.get("deployed") or {}).get("comparison") or {})
        measured = {
            "delta": online_ab.get("token_delta"),
            "scope": len(online_ab.get("token_scope_tasks") or []),
            "lost": online_ab.get("tasks_lost"),
        }
        for verdict in payload.get("verdicts") or []:
            name = verdict["policy"]
            descriptor = proposed.get(name)
            if descriptor is None:
                continue
            try:
                candidate = HarnessPolicy.from_descriptor(descriptor)
            except (ValueError, TypeError):
                continue
            if name == deployed_name:
                search = (deployed_comparison.get("search") or {})
                outcome, measurement, scope, lost = (
                    "deployed", search.get("token_delta"),
                    len(search.get("token_scope_tasks") or []), search.get("tasks_lost"))
            elif online_ab and verdict.get("path") == "online":
                outcome = "measured_incomplete" if measured["delta"] is None else "measured_worse"
                measurement, scope, lost = measured["delta"], measured["scope"], measured["lost"]
            elif verdict.get("path") == "refused":
                outcome, measurement, scope, lost = "refused_by_gate", None, None, None
            else:
                outcome, measurement, scope, lost = "not_deployed", None, None, None
            rows.append(record(
                payload["round"], candidate, base,
                verdict=outcome,
                predicted_saving=verdict.get("predicted_saving"),
                decision_replayable=verdict.get("decision_replayable"),
                path=verdict.get("path"),
                measured_saving=measurement, measured_scope=scope, tasks_lost=lost,
                reason="; ".join(verdict.get("reasons") or [])[:400],
            ))
    return rows


# ---------- what the ledger says about the search ----------


def field_budget(round_index: int, criteria: dict, total: int) -> int:
    """How many fields one candidate may move this round (RRSI's annealed `b_t`).

    Early rounds are allowed a broad edit: the search is still finding out which
    part of the harness matters. The budget then anneals towards one field, so
    that a later verdict is attributable to a single change instead of to a
    bundle whose parts cannot be told apart. The floor is not zero: the one edit
    this search ever deployed moved two fields and only worked together, and a
    budget that forbids that would forbid the result.
    """
    rules = (criteria.get("search") or {}).get("edit_budget") or {}
    decay = float(rules.get("decay", 0.9))
    floor = int(rules.get("min_fields", 2))
    grown = math.ceil(total * (decay ** max(0, round_index - 1)))
    return max(floor, min(total, grown))


def state(records: list[dict], criteria: dict, round_index: int | None = None) -> dict:
    """The search state the proposer is told: what has been tried, and how it went.

    Only facts read off the ledger. Nothing here is a wall: a component that has
    been edited and refused is still a legitimate place to edit, it just has to
    argue with the refusals first, and the proposer is given them to argue with.
    """
    rules = criteria.get("search") or {}
    window = int(rules.get("stall_window", 5))
    worn_after = int(rules.get("pruned_after", 2))
    total_fields = len(FIELD_COMPONENT)

    per_component = {c: {"edits": 0, "accepted": 0, "refused": 0, "rounds": []}
                     for c in COMPONENTS}
    accepted_rounds = []
    for row in records:
        for component in row.get("components") or []:
            bucket = per_component[component]
            bucket["edits"] += 1
            bucket["accepted" if row.get("accepted") else "refused"] += 1
            bucket["rounds"].append(row["round"])
        if row.get("accepted"):
            accepted_rounds.append(row["round"])

    latest = round_index if round_index is not None else max(
        (row["round"] for row in records), default=0)
    last_accepted = max(accepted_rounds) if accepted_rounds else None
    stall_rounds = 0 if last_accepted is None else latest - last_accepted
    if last_accepted is None:
        stall_rounds = latest

    untouched = [c for c in COMPONENTS if per_component[c]["edits"] == 0]
    worn_out = [c for c in COMPONENTS
                if per_component[c]["edits"] >= worn_after and per_component[c]["accepted"] == 0]
    novel = [c for c in COMPONENTS if per_component[c]["accepted"] == 0]

    return {
        "round_budget": field_budget(latest + 1 if round_index is None else round_index,
                                     criteria, total_fields),
        "field_budget_note": "fields one candidate may move this round; it anneals by "
                             "round, so later edits stay attributable",
        "novelty": round(len(novel) / len(COMPONENTS), 3),
        "novelty_note": "share of the harness components no accepted edit has ever touched",
        "components": per_component,
        "untouched_components": untouched,
        "worn_out_components": worn_out,
        "worn_out_note": "edited at least twice and never once accepted. Not banned — an "
                         "edit here is allowed and has to say what is different this time",
        "last_accepted_round": last_accepted,
        "stall_rounds": stall_rounds,
        "stalled": stall_rounds >= window,
        "stall_window": window,
        "stall_note": "rounds since the last accepted edit; on stall the round is expected "
                      "to put at least one candidate into a component the search has never "
                      "touched",
        "past_edits": [
            {k: row.get(k) for k in ("round", "candidate", "components", "fields",
                                     "hypothesis", "verdict", "accepted",
                                     "predicted_saving", "measured_saving", "reason")}
            for row in records[-60:]
        ],
    }


def summary(records: list[dict]) -> dict:
    """Counts per component and per verdict, for the ledger view."""
    per_component = {c: {"edits": 0, "accepted": 0} for c in COMPONENTS}
    per_verdict = {v: 0 for v in VERDICTS}
    for row in records:
        per_verdict[row.get("verdict")] = per_verdict.get(row.get("verdict"), 0) + 1
        for component in row.get("components") or []:
            per_component[component]["edits"] += 1
            if row.get("accepted"):
                per_component[component]["accepted"] += 1
    return {
        "edits": len(records),
        "accepted": sum(1 for row in records if row.get("accepted")),
        "rounds": len({row["round"] for row in records}),
        "components": per_component,
        "verdicts": per_verdict,
        "untouched": [c for c in COMPONENTS if per_component[c]["edits"] == 0],
        "derived_hypotheses": sum(1 for row in records
                                  if row.get("hypothesis_source") == "derived"),
    }


def render(records: list[dict]) -> str:
    if not records:
        return "the ledger is empty; no round has recorded an edit yet"
    data = summary(records)
    lines = [f"The edit ledger over {data['rounds']} rounds: {data['edits']} edits, "
             f"{data['accepted']} accepted.", "", "| component | edits | accepted |",
             "|---|---|---|"]
    for component, bucket in data["components"].items():
        lines.append(f"| {component} | {bucket['edits']} | {bucket['accepted']} |")
    lines += ["", "| round | candidate | component | fields | predicted | measured | verdict |",
              "|---|---|---|---|---|---|---|"]
    for row in records[-40:]:
        fields = ", ".join(f"{k}={v[1]!r}" for k, v in row["fields"].items())
        predicted = ("-" if row.get("predicted_saving") is None
                     else f"{row['predicted_saving']:+.1%}")
        measured = ("-" if row.get("measured_saving") is None
                    else f"{row['measured_saving']:+.1%}")
        lines.append(f"| {row['round']} | {row['candidate']} | "
                     f"{', '.join(row['components'])} | {fields} | {predicted} | {measured} | "
                     f"{row['verdict']} |")
    if data["untouched"]:
        lines += ["", f"Never touched: {', '.join(data['untouched'])}."]
    if data["derived_hypotheses"]:
        lines += [f"{data['derived_hypotheses']} edits predate the ledger and carry a "
                  "derived reason rather than the proposer's own."]
    return "\n".join(lines)
