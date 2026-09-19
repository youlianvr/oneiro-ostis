"""Publish the RSI search tree into the OSTIS knowledge graph.

    python harness/publish.py           # baseline + every round on disk
    python harness/publish.py --show    # print what the graph already holds

The search tree is not a log file. Every candidate policy becomes a node of
class `concept_harness` carrying its descriptor, the judge's predicted saving,
the gate verdict and the online measurement; every round becomes a node of
class `concept_harness_round` carrying the frozen criteria it ran under. The
loop's history is then read the same way the agent's experience is read, and
sc-web can be pointed at it.

Publishing is idempotent: a policy already in the graph is left alone, so a
later round only adds what is new.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Appended, not prepended: `python/replay/` is a package of the world simulator
# and would shadow `harness/replay.py`, the judge this script publishes from.
sys.path.append(str(ROOT / "python"))

import replay  # noqa: E402  (the judge, beside this file)
import rsi  # noqa: E402
from bridge import OneiroBridge  # noqa: E402
from policy import get_policy  # noqa: E402

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))
INCUMBENT = "baseline"


def replayability(records: list[dict], verification: list[dict]) -> dict:
    """How much of each recorded decision the judge could rebuild exactly."""
    exact = sum(1 for row in verification if row.get("chars_match"))
    steps = sum(row.get("steps", 0) for row in verification)
    return {
        "episodes": len(verification),
        "episodes_rebuilt_exactly": exact,
        "steps_rebuilt": steps,
        "steps_total": sum(len(r.get("steps") or []) for r in records),
    }


def round_record(payload: dict, criteria: dict) -> dict:
    """The round as the graph stores it: criteria, candidates, verdicts, outcome."""
    deployed = payload.get("deployed") or {}
    # the rules that actually applied: the round's own snapshot, or the recorded
    # version of the criteria for rounds written before snapshots existed
    frozen = (payload.get("criteria")
              or rsi.criteria_for(payload.get("criteria_version"))
              or criteria)
    return {
        "round": payload["round"],
        "criteria_version": payload.get("criteria_version"),
        "frozen": {
            "version": frozen.get("version"),
            "efficiency": frozen.get("efficiency"),
            "capability": frozen.get("capability"),
        },
        "proposed": [p.get("name") for p in payload.get("proposed") or []],
        "evidence": payload.get("evidence"),
        "correction": payload.get("correction"),
        "verdicts": [
            {
                "policy": v["policy"],
                "predicted_saving": v["predicted_saving"],
                "decision_replayable": v["decision_replayable"],
                "passed_efficiency": v["passed_efficiency"],
                "passed_gate": v.get("passed_gate", v["passed_efficiency"]),
                "path": v.get("path") or ("replay" if v.get("passed_gate") else "refused"),
                "changed_fields": v.get("changed_fields") or [],
            }
            for v in payload.get("verdicts") or []
        ],
        "online_ab": (payload.get("online_ab") or {}).get("comparison"),
        "deployed": deployed.get("policy", {}).get("name") if deployed else None,
        "online_search": deployed.get("online_search"),
        "online_held_out": deployed.get("online_held_out"),
        "generalisation": payload.get("generalisation"),
        "outcome": payload.get("outcome", "-"),
    }


def publish(bridge: OneiroBridge) -> dict:
    criteria = rsi.load_criteria()
    rounds = rsi.load_rounds()
    records = replay.load_records("base")

    existing = {row["name"] for row in bridge.load_harnesses()}
    existing_rounds = {str(row["round"]) for row in bridge.load_harness_rounds()}
    published: list[str] = []

    if INCUMBENT not in existing:
        bridge.save_harness(INCUMBENT, get_policy(INCUMBENT).descriptor(), round_index=0)
        published.append(INCUMBENT)

    round_names: list[str] = []
    for payload in rounds:
        index = payload["round"]
        verdicts = {v["policy"]: v for v in payload.get("verdicts") or []}
        winner = (payload.get("deployed") or {}).get("policy", {}).get("name")

        for descriptor in payload.get("proposed") or []:
            name = descriptor.get("name")
            if not name or name in existing:
                continue
            verdict = verdicts.get(name) or {}
            bridge.save_harness(
                name,
                descriptor,
                replay_saving=verdict.get("predicted_saving"),
                gate=verdict or None,
                online_result=(
                    payload["deployed"].get("comparison") if name == winner else None
                ),
                derived_from=INCUMBENT,
                round_index=index,
            )
            existing.add(name)
            published.append(name)

        if str(index) in existing_rounds:
            continue
        record = round_record(payload, criteria)
        record["replayability"] = replayability(records, payload.get("replay_verification") or [])
        round_names.append(bridge.save_harness_round(index, record))
        existing_rounds.add(str(index))

    return {
        "published_policies": published,
        "published_rounds": round_names,
        "graph_policies": len(bridge.load_harnesses()),
        "graph_rounds": len(bridge.load_harness_rounds()),
    }


def show(bridge: OneiroBridge) -> None:
    policies = bridge.load_harnesses()
    rounds = bridge.load_harness_rounds()
    print(f"policies in the graph: {len(policies)} · rounds: {len(rounds)}")
    print("| policy | round | replay saving | gate | online held-out |")
    print("|---|---|---|---|---|")
    for policy in sorted(policies, key=lambda p: (p.get("round_index") or 0, p["name"])):
        gate = policy.get("gate") or {}
        # stored as the before/after comparison of the run the gate let through
        held = (policy.get("online_result") or {}).get("held_out")
        saving = policy.get("replay_saving")
        round_index = policy.get("round_index")
        online = (f"{held['solved_after']}/{held['tasks']} · {held['token_delta']:+.1%} tok"
                  if held else "-")
        passed = gate.get("passed_gate", gate.get("passed_efficiency"))
        route = gate.get("path", "replay" if passed else "refused") if gate else "-"
        print(f"| {policy['name']} | {int(round_index) if round_index is not None else '-'} | "
              f"{f'{saving:+.1%}' if saving is not None else '-'} | "
              f"{'pass' if passed else 'reject' if gate else '-'} via {route} | "
              f"{online} |")
    for row in rounds:
        record = row.get("record") or {}
        replay = record.get("replayability") or {}
        print(f"round {row['round']}: proposed {record.get('proposed')} · "
              f"deployed {record.get('deployed')} · evidence {record.get('evidence') or '-'} · "
              f"rebuilt exactly {replay.get('episodes_rebuilt_exactly')}/{replay.get('episodes')} · "
              f"{record.get('outcome')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="publish the RSI search tree into the graph")
    parser.add_argument("--show", action="store_true", help="print what the graph holds")
    args = parser.parse_args()

    bridge = OneiroBridge(HOST, PORT)
    try:
        bridge.connect()
    except Exception as exc:
        print(f"sc-machine unreachable at {HOST}:{PORT}: {exc}")
        return 2

    try:
        if args.show:
            show(bridge)
        else:
            print(json.dumps(publish(bridge), indent=2, ensure_ascii=False))
            show(bridge)
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
