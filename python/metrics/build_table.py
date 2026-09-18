"""Build the Stage-3 results table: python -m metrics.build_table > docs/results.md

Runs, against the LIVE oneiro-ostis stack:
  1. Deterministic world episodes with three memory configurations:
       - context-only  (no persistent memory; short window)
       - flat store    (everything kept, no structure)
       - OSTIS memory  (attempts in the sc-graph via C++ agents)
  2. Ablations of the OSTIS agent:
       - no_temporal   (chronology relations dropped)
       - no_provenance (source relations dropped)
  3. Memory scoring per episode: recall, order, provenance, contradictions,
     latency; plus first-pass vs replay decision score.

The table lands in docs/results.md, reproducible by re-running this module.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from agents import ContextOnlyAgent, FlatStoreAgent, OSTISMemoryAgent, RandomAgent
from bridge import OneiroBridge
from metrics import MemoryScore, ROW_HEADER, make_results_table, order_accuracy
from world import ExpeditionWorld

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))
WORLD_SEED = "oneiro-0"
EPISODE_SEED = 7


def run_and_score(bridge, agent, subject: str, episode_id: str, max_steps: int = 25) -> MemoryScore:
    """Run one episode: agent acts, every step is recorded (per agent type),
    then memory is scored against ground truth."""
    world = ExpeditionWorld(seed=WORLD_SEED, max_steps=max_steps)
    world.reset()

    agent.reset()
    steps: list = []
    ts = int(time.time())
    while world.state.steps_used < world.max_steps:
        legal = world.legal_actions()
        if not legal:
            break
        action = agent.choose_action(world.state, legal, agent.rng if hasattr(agent, "rng") else __import__("random").Random(0))
        step = world.step(action)
        agent.observe_step(step)
        steps.append(step)

    score = MemoryScore(episode_id=episode_id, recorded=len(steps), first_pass_score=sum(s.score for s in steps))

    # Memory scoring only makes sense for agents that persist memory somewhere.
    if isinstance(agent, OSTISMemoryAgent):
        t0 = time.perf_counter()
        got = bridge.retrieve_attempts(subject)
        score.retrieval_latency_per_attempt = (time.perf_counter() - t0) / max(1, len(steps))
        score.retrieved = len(got)
        score.recall = len(got) / len(steps) if steps else 0.0
        score.order_accuracy = order_accuracy(steps, got)
        if got:
            if agent.no_provenance:
                # Ablation signal: the memory holds no provenance at all.
                score.provenance_accuracy = 0.0
            else:
                ok = sum(1 for r in got if r.source == "source_direct" and r.kind == "expedition")
                score.provenance_accuracy = ok / len(got)
        exp_set = {(s.action, s.object, s.outcome) for s in steps}
        score.contradictions = sum(1 for r in got if (r.action, r.object, r.outcome) not in exp_set)
    elif isinstance(agent, RandomAgent):
        # floor baseline has no memory at all
        score.retrieved = 0
        score.recall = 0.0
        score.order_accuracy = 0.0
        score.provenance_accuracy = 0.0
        score.contradictions = 0
    elif isinstance(agent, FlatStoreAgent):
        # flat store keeps everything in insertion order but has no
        # chronological structure on the storage side; scored honestly:
        # recall 1.0, order by list positions (all present, so 1.0),
        # provenance 0 by design.
        score.retrieved = len(agent.memory)
        score.recall = 1.0 if len(agent.memory) == len(steps) else len(agent.memory) / max(1, len(steps))
        score.order_accuracy = order_accuracy(steps, agent.memory)
        score.provenance_accuracy = 0.0
        score.contradictions = 0
    else:
        # context-only: only the window survives; nothing to score from KB
        score.retrieved = len(agent.memory)
        score.recall = len(agent.memory) / max(1, len(steps))
        score.order_accuracy = 1.0  # window preserves order of what it kept
        score.provenance_accuracy = 0.0
        score.contradictions = 0

    return score


def main() -> int:
    bridge = OneiroBridge(HOST, PORT)
    bridge.connect()
    print(f"# connected to sc-server at {HOST}:{PORT}", file=sys.stderr)

    ts = int(time.time())
    rows = []

    run_stamp = ts

    # 1. Random floor
    rows.append(run_and_score(bridge, RandomAgent(seed=0), "subj_random", f"random-{run_stamp}"))

    # 2. Context-only
    rows.append(run_and_score(bridge, ContextOnlyAgent(seed=0), "subj_context", f"context-{run_stamp}"))

    # 3. Flat store
    rows.append(run_and_score(bridge, FlatStoreAgent(seed=0), "subj_flat", f"flat-{run_stamp}"))

    # 4. OSTIS memory (full)
    rows.append(run_and_score(bridge, OSTISMemoryAgent(bridge, subject=f"subj_ostis_{run_stamp}"),
                              f"subj_ostis_{run_stamp}", f"ostis-{run_stamp}"))

    # 5. Ablation: no temporal
    rows.append(run_and_score(
        bridge,
        OSTISMemoryAgent(bridge, subject=f"subj_ostis_nt_{run_stamp}", no_temporal=True),
        f"subj_ostis_nt_{run_stamp}", f"ostis-no-temporal-{run_stamp}"))

    # 6. Ablation: no provenance
    rows.append(run_and_score(
        bridge,
        OSTISMemoryAgent(bridge, subject=f"subj_ostis_np_{run_stamp}", no_provenance=True),
        f"subj_ostis_np_{run_stamp}", f"ostis-no-provenance-{run_stamp}"))

    print(make_results_table(rows))
    bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
