"""Stage-4 dream test (requires the live oneiro-ostis stack).

The full half-loop, on real recordings:

  1. day 1: a weak incumbent strategy acts; every step recorded;
  2. an exploration episode widens the recorded transition coverage;
  3. the dream proposes candidates, judges them by exact replay over the
     recordings, and persists the winner into the graph;
  4. day 2: the winner is deployed online; the measured score must beat the
     incumbent's measured score — that is the honest proof the dream worked.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from adapter_llm import OfflineStrategyGenerator
from bridge import OneiroBridge
from dream import dream, dream_table
from episode import run_episode
from strategy import strategy_survey, strategy_weak_incumbent

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))


@pytest.fixture(scope="module")
def bridge():
    b = OneiroBridge(HOST, PORT)
    b.connect()
    yield b
    b.close()


def test_dream_improves_the_next_online_round(bridge):
    subject = f"dream_{int(time.time())}"
    weak = strategy_weak_incumbent()

    # --- day 1: live with the incumbent, recorded to the graph
    day1 = run_episode(bridge, subject, weak, episode_id=f"{subject}-d1", max_steps=40)
    bridge.mark_strategy_online_score(weak.name, day1.total_score)

    # --- exploration: broad coverage for the judge
    run_episode(bridge, subject, strategy_survey(), episode_id=f"{subject}-explore", max_steps=40)

    # --- dream: propose, judge by replay, persist
    result = dream(
        bridge,
        subject,
        round_index=1,
        incumbent=weak,
        generator=OfflineStrategyGenerator(limit=24),
        limit=24,
    )
    assert result.tree_summary["episodes"] == 2
    assert result.consistency["conflicts"] == []
    assert result.saved == len(result.results)

    incumbent_result = next(r for c, r in result.results if c.name == weak.name)
    assert result.winner_result.estimated_score >= incumbent_result.estimated_score - 1e-9

    # --- day 2: deploy the winner and measure it online
    day2 = run_episode(bridge, subject, result.winner, episode_id=f"{subject}-d2", max_steps=40)
    bridge.mark_strategy_online_score(result.winner.name, day2.total_score)

    print("\n" + dream_table(result))
    print(f"\nday1 ({day1.strategy_name}): {day1.total_score:.1f}  [{day1.summary()}]")
    print(f"day2 ({day2.strategy_name}): {day2.total_score:.1f}  [{day2.summary()}]")

    assert day2.total_score >= day1.total_score - 1e-9
    assert day2.total_score > day1.total_score, (
        "the dream found no improvement over the incumbent — document as an honest zero"
    )

    # the winner is a first-class graph entity now
    saved = {s["name"]: s for s in bridge.load_strategies()}
    assert result.winner.name in saved
    assert saved[result.winner.name]["replay_score"] is not None
    assert saved[result.winner.name]["online_score"] is not None
