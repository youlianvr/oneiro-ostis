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
   the estimate and is refused however large the predicted saving. Capability
   is never claimed here, because the judge abstains on the model's decisions;
   capability is only ever settled online.
5. **Deploy and measure** — the winner runs online on the search set and then
   on the held-out tasks it has never influenced. Held-out numbers are the
   only ones that may be quoted as results.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

import agent
import replay
import runner
from policy import HarnessPolicy, get_policy

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

CRITERIA_HISTORY = {1: CRITERIA_V1, 2: CRITERIA_V2}
DEFAULT_CRITERIA = CRITERIA_V2


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


def proposer_context(records: list[dict], history: list[dict], criteria: dict,
                     trace_budget: int = 7000) -> dict:
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


# ---------- gate ----------


def gate(candidates: list[HarnessPolicy], estimates: dict[str, list[replay.Estimate]],
         criteria: dict) -> list[dict]:
    """Deployable = predicted real saving *and* enough replayed decisions to back it.

    Capability is never claimed here: the judge abstains on the model's actual
    choices, so only the online run may speak about them.
    """
    minimum = criteria["efficiency"]["min_predicted_saving"]
    floor = criteria["capability"].get("min_decision_replayable", 0.0)
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
            "reasons": [
                f"predicted saving {saving:.1%} vs required {minimum:.0%}",
                f"decisions replayed {replayable:.0%} vs required {floor:.0%}",
            ] + [note for e in rows for note in e.notes][:2],
        })
    verdicts.sort(key=lambda v: v["predicted_saving"], reverse=True)
    return verdicts


# ---------- online measurement ----------


def measure(policy: HarnessPolicy, tasks: list[str], model: str, label: str) -> list[dict]:
    """Run the policy online and record the outcome of every task."""
    results = []
    for task in tasks:
        record = agent.run_task(task, model=model, label=label, policy=policy)
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
    solved = sum(1 for r in results if r["solved"])
    return {
        "tasks": len(results),
        "solved": solved,
        "prompt_tokens": sum(r["prompt_tokens"] for r in results),
        "mean_wall_seconds": round(sum(r["wall_seconds"] for r in results) / max(1, len(results)), 1),
    }


def incumbent_results(tasks: list[str]) -> list[dict]:
    """The best recorded baseline run per task, from the corpora already on disk."""
    records = {}
    for record in replay.load_records("base"):
        task = record["task"]
        if task not in tasks:
            continue
        if task not in records or (record.get("solved") and not records[task].get("solved")):
            records[task] = record
    return [{
        "task": task,
        "solved": bool(record.get("solved")),
        "steps": len(record.get("steps") or []),
        "tool_calls": record.get("tool_calls", 0),
        "prompt_tokens": (record.get("tokens") or {}).get("input", 0),
        "total_tokens": (record.get("tokens") or {}).get("total", 0),
        "wall_seconds": record.get("wall_seconds", 0),
        "stop_reason": record.get("stop_reason", "recorded"),
        "scratch": record.get("_path", ""),
    } for task, record in sorted(records.items())]


# ---------- one round ----------


def round_path(index: int) -> Path:
    return RSI_DIR / f"round-{index:02d}.json"


def load_rounds() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(RSI_DIR.glob("round-*.json"))]


def run_round(index: int, model: str = agent.DEFAULT_MODEL) -> dict:
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

    context = proposer_context(search_records, history, criteria)
    RSI_DIR.mkdir(parents=True, exist_ok=True)
    candidates, notes = propose(context, model)
    if not candidates:
        candidates, retry_notes = propose(context, model)  # one retry, then give up honestly
        notes = notes + [f"retry: {n}" for n in retry_notes]

    if not candidates:
        payload = {"round": index, "criteria_version": criteria["version"],
                   "criteria": criteria, "proposed": [], "notes": notes, "deployed": None,
                   "replay_verification": [replay.verify_reconstruction(r) for r in search_records]}
        round_path(index).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    estimates = replay.judge(search_records, candidates)
    verdicts = gate(candidates, estimates, criteria)
    passed = [v for v in verdicts if v["passed_gate"]]
    winner = next((c for c in candidates if c.name == passed[0]["policy"]), None) if passed else None

    payload = {
        "round": index,
        "criteria_version": criteria["version"],
        "criteria": criteria,
        "replay_verification": [replay.verify_reconstruction(r) for r in search_records],
        "proposed": [c.descriptor() for c in candidates],
        "notes": notes,
        "verdicts": verdicts,
        "deployed": None,
    }

    if winner is None:
        payload["outcome"] = "no candidate passed the efficiency gate; nothing deployed"
    else:
        search_results = measure(winner, search, model, f"rsi-r{index}-search")
        held_out_results = measure(winner, held_out, model, f"rsi-r{index}-heldout")
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
    shared = sorted(set(before) & set(after))
    solved_before = sum(1 for t in shared if before[t]["solved"])
    solved_after = sum(1 for t in shared if after[t]["solved"])
    tokens_before = sum(before[t]["prompt_tokens"] for t in shared)
    tokens_after = sum(after[t]["prompt_tokens"] for t in shared)
    return {
        "tasks": len(shared),
        "solved_before": solved_before,
        "solved_after": solved_after,
        "tasks_lost": sum(1 for t in shared if before[t]["solved"] and not after[t]["solved"]),
        "tasks_gained": sum(1 for t in shared if after[t]["solved"] and not before[t]["solved"]),
        "prompt_tokens_before": tokens_before,
        "prompt_tokens_after": tokens_after,
        "token_delta": (tokens_after - tokens_before) / tokens_before if tokens_before else 0.0,
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


def show() -> None:
    rounds = load_rounds()
    if not rounds:
        print("no rounds yet")
        return
    print("| round | candidates | passed gate | deployed | held-out solved | held-out tokens | "
          "transferred | outcome |")
    print("|---|---|---|---|---|---|---|---|")
    for payload in rounds:
        deployed = payload.get("deployed")
        held = deployed["online_held_out"] if deployed else None
        general = payload.get("generalisation")
        print(f"| {payload['round']} | {len(payload.get('proposed') or [])} | "
              f"{sum(1 for v in payload.get('verdicts') or [] if v['passed_gate'])} | "
              f"{(deployed or {}).get('policy', {}).get('name', '-') if deployed else '-'} | "
              f"{held['solved']}/{held['tasks']} | {held['prompt_tokens'] if held else '-'} | "
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
    parser.add_argument("--model", default=agent.DEFAULT_MODEL)
    args = parser.parse_args()

    if args.init:
        criteria = freeze_criteria(args.force)
        print(f"criteria frozen: {CRITERIA_PATH}")
        print(json.dumps(criteria, indent=2))
    elif args.round:
        payload = run_round(args.round, args.model)
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
