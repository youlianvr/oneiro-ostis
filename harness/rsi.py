"""The recursive loop: propose, judge from recordings, gate, deploy, measure.

    python harness/rsi.py --init                    # freeze the criteria once
    python harness/rsi.py --round 1                 # propose, judge, gate, deploy, measure
    python harness/rsi.py --show                    # what the rounds established

Order of operations, and why it is this order:

1. **Freeze** — the acceptance criteria (capability tolerance, efficiency
   threshold, the held-out task list) are written to disk once, before any
   search happens. A later round cannot move them (SoL-Pi's discipline).
2. **Propose** — the model reads the *full* trajectories of past episodes plus
   every earlier candidate's estimate and online result, and writes a new
   policy (Meta-Harness: summaries lose the diagnostic signal).
3. **Judge** — `replay.py` recomputes what each candidate would have been
   shown, from recordings only. No agent run, no tokens.
4. **Gate** — a candidate is deployable when the judge predicts a real cost
   saving *and* was able to replay enough of its decisions to say so; a
   candidate whose prompts diverge from the recording has no evidence behind
   the estimate, so it takes the online path instead of being silently banned:
   it is measured online on the search set inside the round budget, and that
   measurement, not a replay estimate, is what its deployment rests on.
   Capability is never claimed by the judge, because it abstains on the model's
   decisions; capability is only ever settled online.
5. **Deploy and measure** — the winner runs online on the search set and then
   on the held-out tasks it has never influenced. Held-out numbers are the
   only ones that may be quoted as results.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import replace
from pathlib import Path

import agent
import replay
import runner
from policy import VARIANTS, HarnessPolicy, get_policy

LAB = Path(__file__).resolve().parent / "lab"
RSI_DIR = LAB / "rsi"
CRITERIA_PATH = RSI_DIR / "criteria.json"

SEARCH_TASKS = ["t01-start-total", "t02-clamp-bounds", "t03-parse-duration",
                "t05-retry-backoff"]
HELD_OUT_TASKS = ["t04-dedupe-order", "t06-csv-column-total"]

# The acceptance rules, versioned. Numbers a search may not quietly move: the
# revision below changed no threshold, it only made the evidence requirement
# real. Rounds record the criteria they ran under, so a later revision never
# relabels an earlier result.

CRITERIA_V1 = {
    "frozen_at": "2026-09-20",
    "version": 1,
    "search_tasks": SEARCH_TASKS,
    "held_out_tasks": HELD_OUT_TASKS,
    "efficiency": {
        "min_predicted_saving": 0.15,
        "note": "a candidate must be predicted to save at least 15% of prompt tokens",
    },
    "capability": {
        "max_tasks_lost": 1,
        "min_covered_steps": 0,
        "note": "online on the search set, a deployed candidate may lose at most one "
                "task against the incumbent; the judge cannot settle capability and "
                "does not pretend to",
    },
    "budget": {
        "online_runs_per_round": 8,
        "note": "measured runs per round, search plus held-out",
    },
}

CRITERIA_V2 = {
    **CRITERIA_V1,
    "version": 2,
    "capability": {
        "max_tasks_lost": 1,
        "min_decision_replayable": 0.5,
        "note": "online on the search set, a deployed candidate may lose at most one "
                "task against the incumbent; the judge cannot settle capability and "
                "does not pretend to",
    },
    "revision": {
        "from_version": 1,
        "reason": "version 1 named a coverage field that no code read, so the gate "
                  "could decide on a predicted saving while the judge had replayed "
                  "no step of the candidate at all",
        "evidence": "rounds 2 and 3 deployed candidates with decision_replayable "
                    "0.0: their prompt divergence meant zero covered steps, and the "
                    "saving was an extrapolation from the token model, not a replay",
        "unchanged": "min_predicted_saving 0.15, max_tasks_lost 1",
    },
}

CRITERIA_V3 = {
    **CRITERIA_V2,
    "version": 3,
    "evidence": {
        "unjudgeable_path": {
            "enabled": True,
            "max_online_runs": 4,
            "note": "when the judge cannot replay a candidate's decisions, the "
                    "candidate may be measured online on the search set inside the "
                    "round budget; its efficiency claim then rests on that "
                    "measurement and is labelled as such, never on a replay estimate",
        },
        "note": "a replay verdict needs the judge to have replayed at least half of "
                "the candidate's decisions; below that the judge abstains and the "
                "online path decides instead",
    },
    "revision": {
        "from_version": 2,
        "reason": "version 2 left the family that diverges at step 0 permanently "
                  "undeployable: the judge abstains on it, and abstention with no "
                  "alternative path turns into a silent ban rather than a verdict",
        "evidence": "round 4 proposed three candidates at +22..27% predicted saving, "
                    "all with 0% replayed decisions, and the round ended with nothing "
                    "measured at all",
        "unchanged": "min_predicted_saving 0.15, max_tasks_lost 1, "
                     "min_decision_replayable 0.5",
    },
}

CRITERIA_V4 = {
    **CRITERIA_V3,
    "version": 4,
    "evidence": {
        **CRITERIA_V3["evidence"],
        "trajectory_changes": {
            "fields": ["context_mode", "window_steps", "observation_chars", "read_lines",
                       "include_initial_tests", "include_file_list", "max_steps",
                       "verify_before_finish", "max_verify_nudges"],
            "note": "a policy that changes what the agent is shown or how long it may run "
                    "does not just change a prompt, it changes the trajectory. Replay "
                    "covers aligned steps, and a candidate like that produces fewer "
                    "aligned steps in reality than the estimate assumed, so the estimate "
                    "is an estimate about a trajectory that no longer exists",
            "requirement": "such a candidate is measured online on the search set before "
                           "it may be deployed, whatever its replay coverage",
        },
    },
    "revision": {
        "from_version": 3,
        "reason": "replay coverage measures how many of the recorded steps a candidate "
                  "would have sent, not how many steps it would then take. Measured: a "
                  "windowed candidate at 62% coverage was predicted to save 15% and cost "
                  "20% more, because the agent, with less history, took more steps on five "
                  "of six tasks (t02: 6 to 9 steps, t06: 6 to 10)",
        "evidence": "reference measurement stored under the label reference-window3; "
                    "the per-task step counts are in the recorded runs",
        "unchanged": "min_predicted_saving 0.15, max_tasks_lost 1, "
                     "min_decision_replayable 0.5",
    },
}

CRITERIA_HISTORY = {1: CRITERIA_V1, 2: CRITERIA_V2, 3: CRITERIA_V3, 4: CRITERIA_V4}
DEFAULT_CRITERIA = CRITERIA_V4

# The proposer is a different job from the agent under test: it reasons about
# trajectories rather than acting, so it may be a different model. The agent
# still runs on agent.DEFAULT_MODEL; changing this does not make old rounds
# incomparable, because every round records the model it was proposed with.
PROPOSER_MODEL = "zai-org/GLM-5.3-Flash"

# The provider's free tier admits paid accounts first, so any one model can be
# at capacity for minutes. The chain is the fallback order, and every switch is
# written into the round: a round proposed by a fallback model says so.
PROPOSER_MODELS = [
    "zai-org/GLM-5.3-Flash",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "MiniMaxAI/MiniMax-M2.7",
]


# ---------- criteria ----------


def freeze_criteria(force: bool = False) -> dict:
    RSI_DIR.mkdir(parents=True, exist_ok=True)
    if CRITERIA_PATH.exists() and not force:
        raise SystemExit(f"criteria already frozen at {CRITERIA_PATH}; refusing to rewrite")
    payload = json.loads(json.dumps(DEFAULT_CRITERIA))
    payload["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    CRITERIA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_criteria() -> dict:
    if not CRITERIA_PATH.exists():
        raise SystemExit("criteria are not frozen yet; run `python harness/rsi.py --init`")
    return json.loads(CRITERIA_PATH.read_text(encoding="utf-8"))


def criteria_for(version) -> dict:
    """The rules in force for a criteria version, for reading old rounds back.

    Rounds carry their own snapshot from version 2 on; this is the fallback.
    """
    try:
        return CRITERIA_HISTORY[int(version)]
    except (KeyError, TypeError, ValueError):
        return {}


# ---------- proposer ----------


PROPOSER_SYSTEM = """You improve the harness of a coding agent.

The harness decides what the model is shown: whether the file list is in the
system prompt, whether the failing test output is shown at the start, how much
of the earlier conversation is kept, how long tool output may be, how many
steps the loop may take, and whether a failing test sends the agent back in.

You will get a JSON object with four keys:
  base_policy     the policy in use now; your proposals are variations of it
  policy_fields   the exact fields allowed, with their types and ranges
  criteria        frozen acceptance rules (savings threshold, tolerance)
  episodes        full recorded trajectories: every tool call, its arguments,
                  and the observation the agent received, step by step
  past_candidates judged estimates and online measurements from earlier rounds
  past_deployments what the online runs actually measured: token change on the
                  search set, solved count and token change on the held-out set,
                  and whether the saving transferred. This is the only feedback
                  about reality; read it before proposing
  measured_references  the same measurements for hand-written policies, run as a
                  control. A policy that looks good to the judge and cost more
                  when run is the most useful thing here
  judge           how the judge decides, and which past candidates it could not
                  judge at all: read it before proposing, because a policy whose
                  prompts diverge from the recording at step 0 cannot be judged
                  and can only be measured online at the cost of real runs

Propose policies that make the agent cheaper (fewer prompt tokens) or more
reliable (more tasks solved) by acting on what the trajectories actually show:
files read twice without an edit in between, the same command run again, long
observations nobody needed afterwards, a step budget too small to recover from
a failing test.

Reply with ONLY a JSON array of 2 to 4 objects. Each object is a policy: it
must carry a unique short "name" and the same keys as base_policy, nothing
else. Never return the episodes or the criteria back. No prose, no markdown.

Example shape:
[{"name": "lean_window", "include_file_list": true, "include_initial_tests": false,
  "context_mode": "window", "window_steps": 6, "observation_chars": 800,
  "read_lines": 80, "max_steps": 12, "verify_before_finish": true,
  "max_verify_nudges": 1, "temperature": 0.2}]"""

POLICY_FIELDS = {
    "name": "string, unique and short",
    "include_file_list": "bool",
    "include_initial_tests": "bool",
    "context_mode": "'full' or 'window'",
    "window_steps": "int >= 1, blocks of history kept when context_mode='window'",
    "observation_chars": "int >= 0, tool output longer than this is clipped",
    "read_lines": "int >= 1, lines one read_file call may return",
    "max_steps": "int >= 1, model calls allowed per episode",
    "verify_before_finish": "bool, failing tests send the agent back in",
    "max_verify_nudges": "int >= 0",
    "temperature": "float 0..1",
}


def judge_briefing(history: list[dict], criteria: dict) -> dict:
    """What the judge can and cannot decide, told by its own recorded history.

    Without this the proposer keeps returning the same family: a policy that
    diverges from the recording at step 0 can never be judged, and knowing
    which families those were is the difference between searching and looping.
    """
    floor = criteria["capability"].get("min_decision_replayable", 0.0)
    unjudgeable = [row["policy"] for row in history
                   if row.get("decision_replayable") is not None
                   and row["decision_replayable"] < floor]
    return {
        "replay_floor": floor,
        "criterion": "the share of a candidate's decisions the judge must rebuild from "
                     "the recording before it may decide at all",
        "why_unjudgeable": "the candidate's prompts diverge from the recording. "
                           "Removing the initial test output changes the first message, "
                           "so no step aligns and nothing can be replayed",
        "past_unjudgeable": unjudgeable,
        "the_choice": "a candidate the judge can replay is decided for free and at once; "
                      "a candidate it cannot replay is measured online inside the round "
                      "budget, which costs real runs and is slower but is not refused. "
                      "Both are legitimate proposals; the second is worth it only when "
                      "the predicted saving is large",
    }


def deployment_history(rounds: list[dict]) -> list[dict]:
    """What the online runs measured, for the proposer to learn from.

    The judge's verdicts say what a candidate would have cost. Only these say
    what happened: whether the saving survived being run, and whether it held on
    tasks the policy never touched.
    """
    rows = []
    for payload in rounds:
        deployed = payload.get("deployed") or {}
        if not deployed:
            continue
        comparison = deployed.get("comparison") or {}
        general = payload.get("generalisation") or {}
        rows.append({
            "round": payload["round"],
            "policy": deployed.get("policy", {}).get("name"),
            "evidence": payload.get("evidence"),
            "search_token_delta": (comparison.get("search") or {}).get("token_delta"),
            "search_tasks_lost": (comparison.get("search") or {}).get("tasks_lost"),
            "held_out_solved": (deployed.get("online_held_out") or {}).get("solved"),
            "held_out_tasks": (deployed.get("online_held_out") or {}).get("tasks"),
            "held_out_token_delta": (comparison.get("held_out") or {}).get("token_delta"),
            "transferred": general.get("transferred"),
        })
    return rows


def proposer_context(records: list[dict], history: list[dict], criteria: dict,
                     trace_budget: int = 7000, deployments: list[dict] | None = None) -> dict:
    """Everything the proposer is allowed to see: full traces, not summaries."""
    traces = []
    for record in records:
        step_lines = []
        for action in (record.get("trajectory") or [])[:12]:
            args = json.dumps(action.get("args") or {}, ensure_ascii=False)[:200]
            observation = (action.get("observation") or "")[:600]
            step_lines.append(f"{action.get('tool')}({args}) -> {observation}")
        text = "\n".join(step_lines)[:trace_budget]
        traces.append({
            "task": record["task"],
            "prompt": record["user_prompt"][:300],
            "outcome": "solved" if record.get("solved") else "FAILED",
            "steps": len(record.get("steps") or []),
            "tool_calls": record.get("tool_calls", 0),
            "prompt_tokens": (record.get("tokens") or {}).get("input", 0),
            "trajectory": text,
        })
    return {
        "base_policy": get_policy("baseline").descriptor(),
        "policy_fields": POLICY_FIELDS,
        "criteria": {k: criteria[k] for k in ("efficiency", "capability", "budget")},
        "episodes": traces,
        "past_candidates": history,
        "past_deployments": deployments,
        "measured_references": reference_measurements(),
        "judge": judge_briefing(history, criteria),
    }


def propose(context: dict, model: str, count: int = 3) -> tuple[list[HarnessPolicy], list[str]]:
    """Ask the model for new policies; validate hard, drop what does not fit."""
    provider = agent.Provider(model, runner.api_key(), temperature=0.7)
    messages = [
        {"role": "system", "content": PROPOSER_SYSTEM},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)[:120000]},
    ]
    message, _ = provider.chat(messages, None)
    text = (message.get("content") or "").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        proposals = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"proposer returned unparseable JSON: {exc}"]
    if not isinstance(proposals, list):
        return [], ["proposer did not return an array"]

    policies: list[HarnessPolicy] = []
    notes: list[str] = []
    for proposal in proposals[:count]:
        try:
            policies.append(HarnessPolicy.from_descriptor(proposal))
        except (ValueError, TypeError) as exc:
            notes.append(f"dropped invalid proposal: {exc}")
    return policies, notes


def proposer_chain(preferred: str) -> list[str]:
    """The preferred proposer first, then every other model the provider offers."""
    return [preferred] + [m for m in PROPOSER_MODELS if m != preferred]


def propose_with_fallback(context: dict, models: list[str],
                          notes: list[str]) -> tuple[list[HarnessPolicy], list[str], str | None]:
    """Ask each model in turn; every refusal is recorded in the round.

    Losing a round to a capacity refusal would waste the recordings the round
    was built on, so the loop moves on to the next model instead of dying. The
    model that actually answered is what the round reports.
    """
    for model in models:
        try:
            candidates, model_notes = propose(context, model)
        except RuntimeError as exc:
            notes.append(f"{model}: provider refused ({str(exc)[:160]})")
            continue
        notes.extend(model_notes)
        if candidates:
            return candidates, notes, model
        notes.append(f"{model}: returned no valid candidate")
    return [], notes, None


# ---------- gate ----------


def gate(candidates: list[HarnessPolicy], estimates: dict[str, list[replay.Estimate]],
         criteria: dict) -> list[dict]:
    """Deployable = predicted real saving *and* enough replayed decisions to back it.

    Capability is never claimed here: the judge abstains on the model's actual
    choices, so only the online run may speak about them.
    """
    minimum = criteria["efficiency"]["min_predicted_saving"]
    floor = criteria["capability"].get("min_decision_replayable", 0.0)
    online_ok = bool(criteria.get("evidence", {}).get("unjudgeable_path", {}).get("enabled"))
    trajectory_fields = (criteria.get("evidence", {})
                         .get("trajectory_changes", {}).get("fields") or [])
    baseline = get_policy("baseline")
    by_name = {candidate.name: candidate for candidate in candidates}
    verdicts = []
    for name, rows in estimates.items():
        predicted = sum(e.prompt_tokens_predicted for e in rows)
        recorded = sum(e.prompt_tokens_recorded for e in rows)
        saving = 1 - (predicted / recorded) if recorded else 0.0
        covered = sum(e.steps_covered for e in rows)
        total = sum(e.steps_total for e in rows)
        replayable = covered / total if total else 0.0
        saving_ok = saving >= minimum
        evidence_ok = replayable >= floor
        candidate = by_name.get(name)
        changed = ([f for f in trajectory_fields
                    if getattr(candidate, f) != getattr(baseline, f)]
                   if candidate is not None else [])
        # A policy that changes what the agent sees or how long it may run does
        # not just change a prompt: the trajectory itself will differ, so a
        # replay verdict about it has to be checked against a real run.
        needs_verification = bool(saving_ok and evidence_ok and changed)
        path = ("verify" if needs_verification
                else "replay" if saving_ok and evidence_ok
                else "online" if saving_ok and online_ok
                else "refused")
        verdicts.append({
            "policy": name,
            "predicted_tokens": round(predicted, 1),
            "recorded_tokens": round(recorded, 1),
            "predicted_saving": round(saving, 4),
            "steps_covered": covered,
            "steps_total": total,
            "decision_replayable": round(replayable, 3),
            "passed_efficiency": saving_ok,
            "passed_evidence": evidence_ok,
            "passed_gate": saving_ok and evidence_ok,
            "path": path,
            "changed_fields": changed,
            "reasons": [
                f"predicted saving {saving:.1%} vs required {minimum:.0%}",
                f"decisions replayed {replayable:.0%} vs required {floor:.0%}",
                f"path: {path}",
            ] + ([f"changes the trajectory: {', '.join(changed)}"] if changed else []) \
              + [note for e in rows for note in e.notes][:2],
        })
    verdicts.sort(key=lambda v: v["predicted_saving"], reverse=True)
    return verdicts


# ---------- online measurement ----------


def measure(policy: HarnessPolicy, tasks: list[str], model: str, label: str) -> list[dict]:
    """Run the policy online and record the outcome of every task.

    A provider outage is recorded as unmeasured (`solved` stays None), never as
    a failure: an accounting where a refused request looks like a lost task
    would quietly make every policy look worse than it is.
    """
    results = []
    for task in tasks:
        try:
            record = agent.run_task(task, model=model, label=label, policy=policy)
        except RuntimeError as exc:
            results.append({
                "task": task, "solved": None, "steps": 0, "tool_calls": 0,
                "prompt_tokens": 0, "total_tokens": 0, "wall_seconds": 0.0,
                "stop_reason": "provider_refused", "error": str(exc)[:200], "scratch": "",
            })
            continue
        results.append({
            "task": task,
            "solved": bool(record["solved"]),
            "steps": len(record["steps"]),
            "tool_calls": record["tool_calls"],
            "prompt_tokens": record["tokens"]["input"],
            "total_tokens": record["tokens"]["total"],
            "wall_seconds": record["wall_seconds"],
            "stop_reason": record["stop_reason"],
            "scratch": record["scratch"],
        })
    return results


def summarise(results: list[dict]) -> dict:
    measured = [r for r in results if r["solved"] is not None]
    return {
        "tasks": len(results),
        "measured": len(measured),
        "unmeasured": len(results) - len(measured),
        "solved": sum(1 for r in measured if r["solved"]),
        "prompt_tokens": sum(r["prompt_tokens"] for r in measured),
        "mean_wall_seconds": round(sum(r["wall_seconds"] for r in measured)
                                  / max(1, len(measured)), 1),
    }


# The same rule the judge uses when it loads its corpus, so the judge's bar and
# the online bar are set by the same runs. Defined in replay.py, the module that
# owns recordings.
NORMAL_STOPS = replay.NORMAL_STOPS


def results_from_records(records: list[dict]) -> list[dict]:
    """Recorded episodes in the same shape `measure` returns, for comparison."""
    return [{
        "task": record["task"],
        "solved": bool(record.get("solved")),
        "steps": len(record.get("steps") or []),
        "tool_calls": record.get("tool_calls", 0),
        "prompt_tokens": (record.get("tokens") or {}).get("input", 0),
        "total_tokens": (record.get("tokens") or {}).get("total", 0),
        "wall_seconds": record.get("wall_seconds", 0),
        "stop_reason": record.get("stop_reason", "recorded"),
        "scratch": record.get("_path", ""),
    } for record in sorted(records, key=lambda r: r["task"])]


def incumbent_results(tasks: list[str]) -> list[dict]:
    """The recorded baseline per task: normal runs only, solved if any solved.

    Several runs of the same task exist. Averaging over the runs that terminated
    normally is the honest baseline: one lucky cheap run must not set the bar for
    every later policy.
    """
    by_task: dict[str, list[dict]] = {}
    for record in replay.load_records("base"):
        if record["task"] in tasks and record.get("stop_reason") in NORMAL_STOPS:
            by_task.setdefault(record["task"], []).append(record)

    results = []
    for task, group in sorted(by_task.items()):
        solved = [r for r in group if r.get("solved")]
        chosen = solved or group
        results.append({
            "task": task,
            "solved": bool(solved),
            "steps": int(statistics.mean(len(r.get("steps") or []) for r in chosen)),
            "tool_calls": int(statistics.mean(r.get("tool_calls", 0) for r in chosen)),
            "prompt_tokens": int(statistics.mean((r.get("tokens") or {}).get("input", 0)
                                                 for r in chosen)),
            "total_tokens": int(statistics.mean((r.get("tokens") or {}).get("total", 0)
                                                for r in chosen)),
            "wall_seconds": round(statistics.mean(r.get("wall_seconds", 0) for r in chosen), 1),
            "stop_reason": "recorded",
            "scratch": ",".join(r.get("_path", "") for r in chosen),
            "runs_averaged": len(chosen),
        })
    return results


# ---------- one round ----------


def round_path(index: int) -> Path:
    return RSI_DIR / f"round-{index:02d}.json"


def load_rounds() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(RSI_DIR.glob("round-*.json"))]


def first_by_path(verdicts: list[dict], candidates: list[HarnessPolicy], path: str):
    """The best candidate the gate sent down a given path (verdicts arrive sorted)."""
    for verdict in verdicts:
        if verdict["path"] == path:
            return next((c for c in candidates if c.name == verdict["policy"]), None)
    return None


def run_round(index: int, proposer_model: str = PROPOSER_MODEL,
              agent_model: str = agent.DEFAULT_MODEL) -> dict:
    criteria = load_criteria()
    search, held_out = criteria["search_tasks"], criteria["held_out_tasks"]
    records = replay.load_records("base")
    search_records = [r for r in records if r["task"] in search]
    if not search_records:
        raise SystemExit("no recorded search episodes; run the corpus first")

    previous = load_rounds()
    history: list[dict] = []
    for round_record in previous:
        history.extend(round_record.get("verdicts", []))
    history.append({
        "policy": "incumbent (baseline)",
        "online_search": summarise(incumbent_results(search)),
        "online_held_out": summarise(incumbent_results(held_out)),
        "status": "incumbent",
    })

    context = proposer_context(search_records, history, criteria,
                               deployments=deployment_history(previous))
    RSI_DIR.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    candidates, notes, answered_by = propose_with_fallback(
        context, proposer_chain(proposer_model), notes)
    proposer_model = answered_by

    if not candidates:
        payload = {"round": index, "criteria_version": criteria["version"],
                   "criteria": criteria, "proposed": [], "notes": notes, "deployed": None,
                   "evidence": "no model answered or none returned a valid candidate",
                   "proposer_model": proposer_model,
                   "agent_model": agent_model,
                   "replay_verification": [replay.verify_reconstruction(r) for r in search_records]}
        round_path(index).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    estimates = replay.judge(search_records, candidates)
    verdicts = gate(candidates, estimates, criteria)
    winner = first_by_path(verdicts, candidates, "replay")
    verify_candidate = first_by_path(verdicts, candidates, "verify")
    online_candidate = first_by_path(verdicts, candidates, "online")

    payload = {
        "round": index,
        "criteria_version": criteria["version"],
        "criteria": criteria,
        "replay_verification": [replay.verify_reconstruction(r) for r in search_records],
        "proposed": [c.descriptor() for c in candidates],
        "notes": notes,
        "verdicts": verdicts,
        "evidence": ("judged by replay over the recorded episodes" if winner
                     else "no candidate the judge could judge"),
        "proposer_model": proposer_model,
        "agent_model": agent_model,
        "deployed": None,
    }

    measured_before_deploy = False
    if winner is None and verify_candidate is not None:
        # Judged, but the judgement is about a trajectory this policy will not
        # produce: it changes what the agent is shown or how long it may run.
        winner, measured_before_deploy = verify_candidate, True
        payload["evidence"] = (
            "judged by replay, then measured online before deployment: the policy "
            "changes what the agent is shown, so its trajectory, not only its "
            "prompt, was in question")
    elif winner is None and online_candidate is not None:
        # The judge abstained on everything, so nothing here is decided by
        # prediction. The candidate is measured online inside the round budget
        # and the number that matters is the measurement, not the estimate.
        winner, measured_before_deploy = online_candidate, True
        payload["evidence"] = ("online measurement: the judge could not replay this "
                               "candidate's decisions, so its efficiency is what "
                               "running it actually cost")

    if winner is not None and measured_before_deploy:
        label = (f"rsi-r{index}-verify-search" if payload["evidence"].startswith("judged")
                 else f"rsi-r{index}-online-search")
        search_results = measure(winner, search, agent_model, label)
        online_comparison = compare(incumbent_results(search), search_results)
        tolerance = criteria["capability"]["max_tasks_lost"]
        payload["online_ab"] = {"results_search": search_results, "comparison": online_comparison}
        predicted = next(v["predicted_saving"] for v in verdicts if v["policy"] == winner.name)
        if online_comparison.get("unmeasured_tasks"):
            payload["deployed"] = None
            payload["outcome"] = (
                "online path: measurement incomplete. The provider refused "
                f"{len(online_comparison['unmeasured_tasks'])} of {len(search)} runs, so "
                "capability was not settled and nothing was deployed")
            round_path(index).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return payload
        if online_comparison["token_delta"] >= 0 or online_comparison["tasks_lost"] > tolerance:
            # The measurement contradicts the estimate, and the measurement wins.
            payload["deployed"] = None
            payload["outcome"] = (
                f"online path: measured and refused. Predicted {predicted:+.1%}, measured "
                f"{online_comparison['token_delta']:+.1%} prompt tokens on "
                f"{len(online_comparison['token_scope_tasks'])} comparable tasks, "
                f"{online_comparison['tasks_lost']} of {online_comparison['tasks']} tasks lost "
                f"(tolerance {tolerance}); held-out tasks were never touched")
            round_path(index).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return payload

    if winner is None:
        payload["outcome"] = "no candidate passed the efficiency gate; nothing deployed"
    else:
        # the online path already paid for the search-set run; reuse it rather
        # than spending the same budget twice on one candidate
        search_results = (payload["online_ab"]["results_search"]
                          if payload.get("online_ab") else
                          measure(winner, search, agent_model, f"rsi-r{index}-search"))
        held_out_results = measure(winner, held_out, agent_model, f"rsi-r{index}-heldout")
        payload["deployed"] = {
            "policy": winner.descriptor(),
            "online_search": summarise(search_results),
            "online_held_out": summarise(held_out_results),
            "results_search": search_results,
            "results_held_out": held_out_results,
            "comparison": {
                "search": compare(incumbent_results(search), search_results),
                "held_out": compare(incumbent_results(held_out), held_out_results),
            },
        }
        comparison = payload["deployed"]["comparison"]
        payload["generalisation"] = generalisation(comparison["search"], comparison["held_out"])
        tolerance = criteria["capability"]["max_tasks_lost"]
        lost = comparison["search"]["tasks_lost"]
        verdict = ("deployed and within capability tolerance"
                   if lost <= tolerance else
                   f"deployed but lost {lost} tasks (tolerance {tolerance})")
        if not payload["generalisation"]["transferred"]:
            verdict += "; the saving did not transfer to the held-out tasks"
        unmeasured = sum(1 for r in search_results + held_out_results if r["solved"] is None)
        if unmeasured:
            verdict += (f"; round incomplete: the provider refused {unmeasured} online runs "
                        "(recorded as unmeasured, not as failures)")
        if payload["evidence"].startswith("online"):
            verdict += "; deployed on its online measurement, not on a judged estimate"
        payload["outcome"] = verdict

    round_path(index).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def generalisation(search: dict, held_out: dict) -> dict:
    """Did what the gate measured on the search set hold on the held-out set?

    The gate may only look at the search set; this is the honest report of
    whether the saving survived the tasks the policy never influenced.
    """
    search_delta = search["token_delta"]
    held_delta = held_out["token_delta"]
    search_solved = search["solved_after"] - search["solved_before"]
    held_solved = held_out["solved_after"] - held_out["solved_before"]
    return {
        "search_token_delta": search_delta,
        "held_out_token_delta": held_delta,
        "search_solved_delta": search_solved,
        "held_out_solved_delta": held_solved,
        "transferred": search_delta <= 0 and held_delta <= 0 and held_solved >= 0,
    }


def compare(incumbent: list[dict], candidate: list[dict]) -> dict:
    before = {r["task"]: r for r in incumbent}
    after = {r["task"]: r for r in candidate}
    unmeasured = sorted(t for t in set(before) & set(after) if after[t]["solved"] is None)
    shared = sorted(t for t in set(before) & set(after)
                    if before[t]["solved"] is not None and after[t]["solved"] is not None)
    solved_before = sum(1 for t in shared if before[t]["solved"])
    solved_after = sum(1 for t in shared if after[t]["solved"])
    # Tokens are only comparable on work both sides finished. A task neither
    # solved burns steps until the budget ends, and counting that as a cost
    # increase would punish a policy for failing exactly as much as the baseline.
    comparable = [t for t in shared if before[t]["solved"] and after[t]["solved"]]
    tokens_before = sum(before[t]["prompt_tokens"] for t in comparable)
    tokens_after = sum(after[t]["prompt_tokens"] for t in comparable)
    return {
        "tasks": len(shared),
        "unmeasured_tasks": unmeasured,
        "token_scope_tasks": comparable,
        "unsolved_in_both": [t for t in shared
                             if not before[t]["solved"] and not after[t]["solved"]],
        "solved_before": solved_before,
        "solved_after": solved_after,
        "tasks_lost": sum(1 for t in shared if before[t]["solved"] and not after[t]["solved"]),
        "tasks_gained": sum(1 for t in shared if after[t]["solved"] and not before[t]["solved"]),
        "prompt_tokens_before": tokens_before,
        "prompt_tokens_after": tokens_after,
        "token_delta": ((tokens_after - tokens_before) / tokens_before
                        if tokens_before else 0.0),
    }


def recheck() -> list[dict]:
    """Re-apply the frozen criteria to the verdicts the rounds already recorded.

    Nothing is re-run and nothing is re-measured: this reads the numbers the
    judge produced and asks what the current rules would have decided, so a
    revision of the gate can be judged against the history that exposed it.
    """
    criteria = load_criteria()
    minimum = criteria["efficiency"]["min_predicted_saving"]
    floor = criteria["capability"].get("min_decision_replayable", 0.0)
    rows: list[dict] = []
    for payload in load_rounds():
        deployed = (payload.get("deployed") or {}).get("policy", {}).get("name")
        for verdict in payload.get("verdicts") or []:
            saving_ok = verdict["predicted_saving"] >= minimum
            evidence_ok = verdict["decision_replayable"] >= floor
            rows.append({
                "round": payload["round"],
                "policy": verdict["policy"],
                "criteria_version": payload.get("criteria_version"),
                "predicted_saving": verdict["predicted_saving"],
                "decision_replayable": verdict["decision_replayable"],
                # rounds written before the gate had an evidence clause only
                # recorded the efficiency verdict
                "passed_then": bool(verdict.get("passed_gate", verdict.get("passed_efficiency"))),
                "passed_now": saving_ok and evidence_ok,
                "deployed_then": deployed == verdict["policy"],
            })
    return rows


def ledger() -> dict:
    """What the loop spent online, against what judging every candidate online costs.

    The recordings are the asset: a candidate the judge can decide on costs no
    online run at all. That difference is the point of the design, so it is
    counted rather than asserted.
    """
    criteria = load_criteria()
    search_tasks = criteria["search_tasks"]
    rounds = load_rounds()

    floor = criteria["capability"].get("min_decision_replayable", 0.0)
    proposed = refused_free = measured_online = deployed = online_runs = 0
    unbacked = 0
    for payload in rounds:
        proposed += len(payload.get("proposed") or [])
        deployed_name = (payload.get("deployed") or {}).get("policy", {}).get("name")
        for verdict in payload.get("verdicts") or []:
            if verdict.get("path") == "online":
                measured_online += 1
            elif not verdict.get("passed_gate", verdict.get("passed_efficiency")):
                refused_free += 1
            if (verdict["policy"] == deployed_name
                    and verdict["decision_replayable"] < floor):
                unbacked += 1
        if payload.get("deployed"):
            deployed += 1
            online_runs += (payload["deployed"]["online_search"]["tasks"]
                            + payload["deployed"]["online_held_out"]["tasks"])
        elif payload.get("online_ab"):
            # measured online and refused: the runs were still spent
            online_runs += payload["online_ab"]["comparison"]["tasks"]

    sweep = proposed * len(search_tasks)
    return {
        "rounds": len(rounds),
        "criteria_version": criteria["version"],
        "candidates_proposed": proposed,
        "refused_from_recordings_alone": refused_free,
        "decided_online": measured_online,
        "deployed": deployed,
        "deployments_without_replayed_evidence": unbacked,
        "online_runs_spent": online_runs,
        "online_sweep_counterfactual": sweep,
        "runs_saved": sweep - online_runs,
        "note": "the counterfactual is what measuring every proposed candidate on the "
                "search set would have cost, one run per candidate per task",
    }


def render_ledger(rows: dict) -> str:
    factor = (rows["online_sweep_counterfactual"] / rows["online_runs_spent"]
              if rows["online_runs_spent"] else 0.0)
    lines = [f"Loop ledger over {rows['rounds']} rounds (criteria v{rows['criteria_version']}):", "",
             "| quantity | value |", "|---|---|",
             f"| candidates proposed | {rows['candidates_proposed']} |",
             f"| refused on recordings alone | {rows['refused_from_recordings_alone']} |",
             f"| decided online | {rows['decided_online']} |",
             f"| deployed | {rows['deployed']} |",
             f"| deployed without replayed evidence | {rows['deployments_without_replayed_evidence']} |",
             f"| online runs spent | {rows['online_runs_spent']} |",
             f"| online runs if every candidate were measured | "
             f"{rows['online_sweep_counterfactual']} |",
             f"| runs saved | {rows['runs_saved']} ({factor:.1f}x) |", "",
             f"{rows['note']}."]
    return "\n".join(lines)


def render_recheck(rows: list[dict], criteria: dict) -> str:
    floor = criteria["capability"].get("min_decision_replayable", 0.0)
    lines = [f"Criteria v{criteria['version']} (coverage floor {floor:.0%}) applied to recorded verdicts:", "",
             "| round | policy | predicted saving | decisions replayed | passed then | passed now | deployed then |",
             "|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append(
            f"| {row['round']} | {row['policy']} | {row['predicted_saving']:+.1%} | "
            f"{row['decision_replayable']:.0%} | {'yes' if row['passed_then'] else 'no'} | "
            f"{'yes' if row['passed_now'] else 'no'} | {'yes' if row['deployed_then'] else 'no'} |")
    flipped = [r for r in rows if r["passed_then"] and not r["passed_now"]]
    lines += ["", f"{len(flipped)} of {len(rows)} verdicts recorded under earlier rules "
                  f"would be refused under v{criteria['version']}."]
    return "\n".join(lines)


def replay_health() -> dict:
    """How well the judge rebuilds what it replays: the number behind its verdicts."""
    records = replay.load_records("base")
    checks = [replay.verify_reconstruction(record) for record in records]
    model = replay.cross_validate(records)
    return {
        "episodes": len(records),
        "rebuilt_exactly": sum(1 for check in checks if check.get("chars_match")),
        "steps": sum(check.get("steps", 0) for check in checks),
        "token_model_mean_error": round(model["mean_relative_error"], 4),
        "token_model_max_error": round(model["max_relative_error"], 4),
    }


def reference_table() -> list[dict]:
    """Judge the hand-written policies, so a round that finds nothing has a scale.

    Offline, free, no provider: this is the judge's own answer to "what could be
    saved by trimming what the agent sees and keeps", which is the honest way to
    read a proposal that came in at zero.
    """
    criteria = load_criteria()
    records = [r for r in replay.load_records("base") if r["task"] in criteria["search_tasks"]]
    if not records:
        return []
    policies = [get_policy(name) for name in sorted(VARIANTS)]
    estimates = replay.judge(records, policies)
    rows = []
    for verdict in gate(policies, estimates, criteria):
        rows.append({**verdict, "policy": verdict["policy"]})
    return rows


def render_reference(rows: list[dict]) -> str:
    if not rows:
        return "no replayable episodes on the search set yet"
    lines = ["Hand-written harness policies, judged from the recordings (no runs):", "",
             "| policy | predicted saving | decisions replayed | path |", "|---|---|---|---|"]
    for row in sorted(rows, key=lambda r: r["predicted_saving"], reverse=True):
        lines.append(f"| {row['policy']} | {row['predicted_saving']:+.1%} | "
                     f"{row['decision_replayable']:.0%} | {row['path']} |")
    return "\n".join(lines)


def measure_reference(name: str, agent_model: str) -> dict:
    """Measure a hand-written policy online, clearly labelled as a reference.

    Not a proposal, not gated: this is the control experiment, and the label on
    its runs says so.
    """
    criteria = load_criteria()
    search, held_out = criteria["search_tasks"], criteria["held_out_tasks"]
    policy = get_policy(name)
    label = f"reference-{name}"
    search_results = measure(policy, search, agent_model, label)
    held_out_results = measure(policy, held_out, agent_model, label)
    comparison = {"search": compare(incumbent_results(search), search_results),
                  "held_out": compare(incumbent_results(held_out), held_out_results)}
    return {
        "policy": policy.descriptor(),
        "label": label,
        "online_search": summarise(search_results),
        "online_held_out": summarise(held_out_results),
        "comparison": comparison,
        "generalisation": generalisation(comparison["search"], comparison["held_out"]),
    }


def recompare() -> list[dict]:
    """Recompute every recorded round's comparison from the runs it wrote.

    The first baseline this loop used picked, per task, the cheapest recording
    including runs that ended in an error; on a task the agent failed, that is a
    one step failure against which any real attempt looks wasteful. The originals
    stay in the round files, the corrected numbers are added beside them, and the
    reason is written down: a correction that erases what it corrects is not a
    correction.
    """
    criteria = load_criteria()
    rows = []
    for path in sorted(RSI_DIR.glob("round-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        deployed = payload.get("deployed") or {}
        if not deployed:
            continue
        index = payload["round"]
        rebuilt = {}
        for name, tasks in (("search", criteria["search_tasks"]),
                            ("held_out", criteria["held_out_tasks"])):
            labels = [f"rsi-r{index}-{name}", f"rsi-r{index}-online-search"] if name == "search" \
                else [f"rsi-r{index}-heldout"]
            records = [r for label in labels for r in replay.load_records(label)
                       if r["task"] in tasks]
            if not records:
                rebuilt = {}
                break
            rebuilt[name] = compare(incumbent_results(tasks), results_from_records(records))
        if not rebuilt:
            continue
        payload["comparison_corrected"] = rebuilt
        payload["generalisation_corrected"] = generalisation(rebuilt["search"], rebuilt["held_out"])
        payload["correction"] = (
            "the recorded comparison used the cheapest recorded run per task as the "
            "baseline, including runs that ended in an error; this one averages only "
            "runs that terminated normally, divided by solved, and compares tokens "
            "only on tasks both sides solved")
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        rows.append({"round": index, "policy": deployed.get("policy", {}).get("name"),
                     "before": deployed.get("comparison"),
                     "corrected": rebuilt,
                     "transferred": payload["generalisation_corrected"]["transferred"]})
    return rows


def compare_label(label: str) -> dict:
    """Recompute the comparison for a set of recorded runs, from the runs.

    The runs are the measurement; a stored comparison is a summary that can be
    recomputed, and when the baseline definition is corrected, recomputing beats
    re-running something already paid for.
    """
    criteria = load_criteria()
    search, held_out = criteria["search_tasks"], criteria["held_out_tasks"]
    records = replay.load_records(label)
    by_task = {r["task"]: r for r in records}
    search_records = [by_task[t] for t in search if t in by_task]
    held_records = [by_task[t] for t in held_out if t in by_task]
    comparison = {
        "search": compare(incumbent_results(search), results_from_records(search_records)),
        "held_out": compare(incumbent_results(held_out), results_from_records(held_records)),
    }
    return {"label": label, "runs": len(records), "comparison": comparison,
            "generalisation": generalisation(comparison["search"], comparison["held_out"])}


def reference_measurements() -> list[dict]:
    """Online measurements of hand-written policies, recomputed from their runs.

    These are the control experiment: what actually happened when a policy that
    the judge liked was run. The proposer is shown them, because they are facts
    about the world, and a search that cannot see the world's answer to a policy
    will keep proposing it.
    """
    criteria = load_criteria()
    records = [r for r in replay.load_records("base")
               if r["task"] in criteria["search_tasks"]]
    labels = sorted({(r.get("label") or "") for r in replay.load_records()
                     if (r.get("label") or "").startswith("reference-")})
    rows = []
    for label in labels:
        data = compare_label(label)
        search, held = data["comparison"]["search"], data["comparison"]["held_out"]
        name = label.replace("reference-", "")
        judge = None
        if name in VARIANTS and records:
            policy = get_policy(name)
            judge = gate([policy], replay.judge(records, [policy]), criteria)[0]
        rows.append({
            "policy": name,
            "label": label,
            "runs": data["runs"],
            "predicted_saving": (judge or {}).get("predicted_saving"),
            "decision_replayable": (judge or {}).get("decision_replayable"),
            "judge_path": (judge or {}).get("path"),
            "search_token_delta": search["token_delta"],
            "search_token_scope_tasks": len(search["token_scope_tasks"]),
            "search_tasks_lost": search["tasks_lost"],
            "held_out_token_delta": held["token_delta"],
            "transferred": data["generalisation"]["transferred"],
        })
    return rows


def state() -> dict:
    """The whole loop as JSON, so every report renders from the same source."""
    criteria = load_criteria()
    rounds = []
    for payload in load_rounds():
        deployed = payload.get("deployed") or {}
        verification = payload.get("replay_verification") or []
        rounds.append({
            "round": payload["round"],
            "criteria_version": payload.get("criteria_version"),
            "proposer_model": payload.get("proposer_model"),
            "agent_model": payload.get("agent_model"),
            "candidates": len(payload.get("proposed") or []),
            "proposed": [p.get("name") for p in payload.get("proposed") or []],
            "verdicts": [
                {
                    "policy": v["policy"],
                    "predicted_saving": v["predicted_saving"],
                    "decision_replayable": v["decision_replayable"],
                    "passed": bool(v.get("passed_gate", v.get("passed_efficiency"))),
                    # rounds written before the gate had an evidence clause are
                    # labelled with the rules they were actually decided under,
                    # not with today's verdict on them
                    "path": v.get("path") or (
                        "replay" if v.get("passed_gate") else
                        "gate-v1" if v.get("passed_efficiency") else "refused"),
                }
                for v in payload.get("verdicts") or []
            ],
            "deployed": deployed.get("policy", {}).get("name") if deployed else None,
            "evidence": payload.get("evidence"),
            "online_search": deployed.get("online_search"),
            "online_held_out": deployed.get("online_held_out"),
            "online_ab": (payload.get("online_ab") or {}).get("comparison"),
            "generalisation": payload.get("generalisation"),
            # present when the comparison was recomputed against the corrected
            # baseline; the stored one stays readable beside it
            "generalisation_corrected": payload.get("generalisation_corrected"),
            "comparison_corrected": payload.get("comparison_corrected"),
            "correction": payload.get("correction"),
            "outcome": payload.get("outcome"),
            "replay_episodes_rebuilt": sum(1 for c in verification if c.get("chars_match")),
            "replay_episodes": len(verification),
        })
    return {
        "criteria": criteria,
        "rounds": rounds,
        "recheck": recheck(),
        "references": reference_measurements(),
        "ledger": ledger(),
        "replayability": replay_health(),
        "incumbent": {
            "search": summarise(incumbent_results(criteria["search_tasks"])),
            "held_out": summarise(incumbent_results(criteria["held_out_tasks"])),
        },
    }


def show() -> None:
    rounds = load_rounds()
    if not rounds:
        print("no rounds yet")
        return
    print("| round | candidates | judged | deployed | evidence | held-out solved | held-out tokens | "
          "transferred | outcome |")
    print("|---|---|---|---|---|---|---|---|---|")
    for payload in rounds:
        deployed = payload.get("deployed")
        held = deployed["online_held_out"] if deployed else None
        general = payload.get("generalisation")
        judged = sum(1 for v in payload.get("verdicts") or []
                     if v.get("passed_gate", v.get("passed_efficiency")))
        name = (deployed or {}).get("policy", {}).get("name") if deployed else None
        verdict_for = next((v for v in payload.get("verdicts") or [] if v["policy"] == name), None)
        route = ((verdict_for or {}).get("path")
                 or ("none" if name else "-"))
        held_solved = f"{held['solved']}/{held['tasks']}" if held else "-"
        print(f"| {payload['round']} | {len(payload.get('proposed') or [])} | {judged} | "
              f"{(deployed or {}).get('policy', {}).get('name', '-') if deployed else '-'} | "
              f"{route} | {held_solved} | {held['prompt_tokens'] if held else '-'} | "
              f"{('yes' if general['transferred'] else 'no') if general else '-'} | "
              f"{payload.get('outcome', '-')} |")


def main() -> None:
    parser = argparse.ArgumentParser(description="Oneiro RSI loop over the harness policy")
    parser.add_argument("--init", action="store_true", help="freeze the criteria")
    parser.add_argument("--force", action="store_true", help="rewrite frozen criteria (never during a search)")
    parser.add_argument("--round", type=int, help="run one round with this index")
    parser.add_argument("--show", action="store_true", help="summarise the rounds")
    parser.add_argument("--recheck", action="store_true",
                        help="re-apply the frozen criteria to the recorded verdicts")
    parser.add_argument("--ledger", action="store_true",
                        help="what the loop spent online, against an online sweep")
    parser.add_argument("--state", action="store_true",
                        help="the whole loop as JSON for reports and the dashboard")
    parser.add_argument("--reference", action="store_true",
                        help="judge the hand-written policies from the recordings")
    parser.add_argument("--measure-reference", metavar="NAME",
                        help="measure a hand-written policy online, as a labelled control")
    parser.add_argument("--recompare", action="store_true",
                        help="recompute stored round comparisons from their runs")
    parser.add_argument("--compare-label", metavar="LABEL",
                        help="recompute the comparison for a label from its recorded runs")
    parser.add_argument("--model", default=PROPOSER_MODEL,
                        help="model that writes the candidate policies")
    parser.add_argument("--agent-model", default=agent.DEFAULT_MODEL,
                        help="model the agent under test runs on; the online "
                             "measurement must use the model the episodes were "
                             "recorded with")
    args = parser.parse_args()

    if args.init:
        criteria = freeze_criteria(args.force)
        print(f"criteria frozen: {CRITERIA_PATH}")
        print(json.dumps(criteria, indent=2))
    elif args.round:
        payload = run_round(args.round, args.model, args.agent_model)
        print(json.dumps({k: v for k, v in payload.items()
                          if k in ("round", "outcome", "notes")}, indent=2, ensure_ascii=False))
        for verdict in payload.get("verdicts") or []:
            print(f"  {verdict['policy']:<18} saving={verdict['predicted_saving']:+.1%} "
                  f"covered={verdict['steps_covered']}/{verdict['steps_total']} "
                  f"replayable={verdict['decision_replayable']:.0%} "
                  f"saving_ok={verdict['passed_efficiency']} "
                  f"evidence_ok={verdict['passed_evidence']} "
                  f"passed={verdict['passed_gate']}")
        if payload.get("deployed"):
            print(json.dumps(payload["deployed"]["comparison"], indent=2))
    elif args.state:
        print(json.dumps(state(), indent=2, ensure_ascii=False))
    elif args.reference:
        print(render_reference(reference_table()))
    elif args.compare_label:
        print(json.dumps(compare_label(args.compare_label), indent=2, ensure_ascii=False))
    elif args.recompare:
        rows = recompare()
        if not rows:
            print("no measured deployments to recompute")
        for row in rows:
            old, new = row["before"] or {}, row["corrected"]
            print(f"round {row['round']} · {row['policy']}")
            for side in ("search", "held_out"):
                o, n = (old.get(side) or {}), new[side]
                print(f"  {side:<9} tokens {o.get('token_delta', 0):+.1%} -> {n['token_delta']:+.1%} "
                      f"on {len(n['token_scope_tasks'])} comparable tasks · "
                      f"solved {n['solved_before']}->{n['solved_after']}")
            print(f"  transferred: {new['search']['token_delta'] <= 0 and new['held_out']['token_delta'] <= 0}")
    elif args.measure_reference:
        result = measure_reference(args.measure_reference, args.agent_model)
        print(json.dumps({k: v for k, v in result.items() if k != "policy"},
                         indent=2, ensure_ascii=False))
    elif args.ledger:
        if not load_rounds():
            print("no rounds recorded yet")
        else:
            print(render_ledger(ledger()))
    elif args.recheck:
        criteria = load_criteria()
        rows = recheck()
        if not rows:
            print("no verdicts recorded yet")
        else:
            print(render_recheck(rows, criteria))
    elif args.show:
        show()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
