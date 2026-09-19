"""Offline replay-engine tests: no stack required.

Builds a synthetic experience tree (the same shape the bridge decodes from
the graph) and checks the judge:

  - the tree groups episodes and indexes transitions;
  - replaying a strategy that matches the recordings reproduces them exactly;
  - a diverging candidate either uses another recorded transition or is
    truncated as uncovered (never invents an outcome);
  - replay works with the world execution disabled (dreaming executes nothing).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from bridge import AttemptRecord
from replay.engine import ExperienceTree
from strategy import Strategy


def make_record(episode, index, location, carrying, dug, legal, action, obj, outcome, score, strategy_name):
    return AttemptRecord(
        subject="s",
        action=action,
        object=obj,
        outcome=outcome,
        score=score,
        episode=episode,
        step_index=index,
        state=json.dumps({"location": location, "carrying": carrying, "dug": dug, "score": 0.0, "steps": index}),
        legal="|".join(legal),
        strategy=strategy_name,
        note="",
    )


def campaign_tree() -> ExperienceTree:
    """Two recorded episodes of a tiny excursion (same shape as real records)."""
    records = []
    # episode A: camp -> beach -> dig -> deliver at the beach
    steps_a = [
        ("camp", "", {}, ["travel:beach", "travel:jungle"], "travel:beach", "beach", "concept_success", -0.1),
        ("beach", "", {}, ["dig:beach", "travel:camp"], "dig:beach", "beach", "concept_success", 0.0),
        ("beach", "artefact_beach_0", {"beach": 1}, ["deliver:beach", "travel:camp"], "deliver:beach", "beach", "concept_success", 18.0),
    ]
    for i, (loc, carry, dug, legal, action, obj, outcome, score) in enumerate(steps_a):
        records.append(make_record("A", i, loc, carry, dug, legal, action, obj, outcome, score, "policy_a"))

    # episode B: camp -> beach -> dig -> carry the cargo back to camp
    steps_b = [
        ("camp", "", {}, ["travel:beach", "travel:jungle"], "travel:beach", "beach", "concept_success", -0.1),
        ("beach", "", {}, ["dig:beach", "travel:camp"], "dig:beach", "beach", "concept_success", 0.0),
        ("beach", "artefact_beach_0", {"beach": 1}, ["deliver:beach", "travel:camp"], "travel:camp", "camp", "concept_success", -0.1),
    ]
    for i, (loc, carry, dug, legal, action, obj, outcome, score) in enumerate(steps_b):
        records.append(make_record("B", i, loc, carry, dug, legal, action, obj, outcome, score, "policy_b"))

    return ExperienceTree.from_records(records)


class ScriptedStrategy(Strategy):
    """Returns a fixed action sequence (for exactness checks)."""

    def __init__(self, name, actions):
        super().__init__(name=name, site_priority=["beach"], dig_limit=1)
        self._actions = list(actions)
        self._i = 0

    def choose(self, obs, legal):
        action = self._actions[min(self._i, len(self._actions) - 1)]
        self._i += 1
        return action


def test_tree_construction():
    tree = campaign_tree()
    assert tree.episode_count == 2
    assert tree.step_count == 6
    assert tree.transition_count == 4  # travel/dig shared; deliver_beach and travel_camp distinct
    report = tree.verify_consistency()
    assert report["conflicts"] == []
    assert report["exact_episodes"] == 2


def test_replay_matching_strategy_is_exact():
    tree = campaign_tree()
    strategy = ScriptedStrategy("a-replay", [s.action for s in tree.episodes["A"]])
    result = tree.replay(strategy, max_episodes=1)
    recorded_a = sum(s.score for s in tree.episodes["A"])
    assert abs(result.estimated_score - recorded_a) < 1e-9
    assert result.uncovered_steps == 0
    assert result.rows[0].ended == "recorded-end"


def test_replay_uses_recorded_transition_on_divergence():
    tree = campaign_tree()
    # A candidate that carries the artefact back to camp instead of delivering:
    # that transition is recorded in episode B.
    strategy = ScriptedStrategy(
        "diverger", ["travel:beach", "dig:beach", "travel:camp", "travel:beach"]
    )
    result = tree.replay(strategy, max_episodes=1)
    # step 3 came from B's recording (score -0.1); B ended there -> recorded end
    assert result.rows[0].ended == "recorded-end"
    assert abs(result.estimated_score - (-0.1 + 0.0 - 0.1)) < 1e-9
    assert result.uncovered_steps == 0


def test_replay_truncates_uncovered_decisions():
    tree = campaign_tree()
    # dig:camp was never recorded (camp is not a dig site) — the judge must
    # truncate, not credit.
    strategy = ScriptedStrategy("bad", ["dig:camp", "travel:beach", "travel:beach"])
    result = tree.replay(strategy, max_episodes=1)
    assert result.rows[0].ended == "uncovered"
    assert result.uncovered_steps == 1
    assert result.estimated_score == 0.0


def test_replay_executes_nothing():
    """With world execution disabled, replay must still work: the judge reads
    recordings only."""
    import world

    tree = campaign_tree()
    strategy = ScriptedStrategy("a-replay", [s.action for s in tree.episodes["A"]])

    def boom(*args, **kwargs):
        raise AssertionError("the world was executed during a dream")

    original = world.ExpeditionWorld.step
    world.ExpeditionWorld.step = boom
    try:
        result = tree.replay(strategy, max_episodes=1)
        assert result.estimated_score > 0
        report = tree.verify_consistency()
        assert report["conflicts"] == []
    finally:
        world.ExpeditionWorld.step = original
