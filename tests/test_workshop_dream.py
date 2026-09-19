"""Second-domain dream test (requires the live oneiro-ostis stack).

Proves the dream machinery is not island-specific: the crafting world differs
structurally (inventory instead of carrying, recipes instead of sites), the
recorded trajectories live in the same graph schema, and the judge replays
them under the workshop's own signature and observation builder.

Day 1: the weak incumbent (planks, wasteful order). Exploration: two survey
walks. Dream: workshop sweep judged by exact replay. Day 2: measured winner —
must beat the incumbent on the same deterministic world.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from bridge import OneiroBridge
from dream import dream
from loop_workshop import run_workshop_episode
from replay.engine import ExperienceTree
from strategy_workshop import (
    OfflineWorkshopGenerator,
    observation_of_snapshot,
    strategy_survey_workshop,
    strategy_weak_incumbent_workshop,
    workshop_signature,
)

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))


@pytest.fixture(scope="module")
def bridge():
    b = OneiroBridge(HOST, PORT)
    b.connect()
    yield b
    b.close()


def test_workshop_dream_transfers_and_improves(bridge):
    subject = f"wsdream_{int(time.time())}"
    weak = strategy_weak_incumbent_workshop()

    day1 = run_workshop_episode(bridge, subject, weak, episode_id=f"{subject}-d1", max_steps=40)
    bridge.mark_strategy_online_score(weak.name, day1.total_score)

    run_workshop_episode(
        bridge, subject, strategy_survey_workshop(), episode_id=f"{subject}-explore1", max_steps=40
    )

    result = dream(
        bridge,
        subject,
        round_index=1,
        incumbent=weak,
        generator=OfflineWorkshopGenerator(),
        limit=24,
        signature=workshop_signature,
        observe=observation_of_snapshot,
    )
    assert result.tree_summary["episodes"] == 2
    assert result.consistency["conflicts"] == [], "workshop recordings conflicted"

    incumbent_result = next(r for c, r in result.results if c.name == weak.name)
    assert result.winner_result.estimated_score >= incumbent_result.estimated_score - 1e-9

    day2 = run_workshop_episode(bridge, subject, result.winner, episode_id=f"{subject}-d2", max_steps=40)
    bridge.mark_strategy_online_score(result.winner.name, day2.total_score)

    print(f"\nworkshop day1 ({day1.strategy_name}): {day1.total_score:.2f} [{day1.summary()}]")
    print(f"workshop day2 ({day2.strategy_name}): {day2.total_score:.2f} [{day2.summary()}]")
    print(f"dream winner replay: {result.winner_result.estimated_score:.1f} "
          f"coverage {result.winner_result.coverage:.2f}")

    assert day2.total_score > day1.total_score, (
        "the workshop dream found no improvement — document as an honest zero"
    )

    # exactness under the workshop signature: replaying the survey strategy
    # reproduces its own recorded episode (float32 tolerance, like the island)
    records = bridge.retrieve_attempts(subject)
    tree = ExperienceTree.from_records(records, signature_fn=workshop_signature)
    survey_result = tree.replay(strategy_survey_workshop(), observe=observation_of_snapshot)
    rows = {row.episode: row for row in survey_result.rows}
    assert rows[f"{subject}-explore1"].uncovered == 0
    assert rows[f"{subject}-explore1"].ended == "recorded-end"
