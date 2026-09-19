"""Stage-4 replay exactness test (requires the live oneiro-ostis stack).

Checks, against real recordings made through the C++ agents:

  - the experience tree decodes episodes and trajectories correctly;
  - recordings are consistent (deterministic world ⇒ no conflicting outcomes
    for the same signature+action);
  - replaying a strategy that follows a recorded episode reproduces its
    recorded scores exactly;
  - replaying with world execution disabled gives IDENTICAL estimates —
    dreaming executes nothing.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from bridge import OneiroBridge
from episode import run_episode
from replay.engine import ExperienceTree
from strategy import strategy_survey, strategy_weak_incumbent

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))


@pytest.fixture(scope="module")
def bridge():
    b = OneiroBridge(HOST, PORT)
    b.connect()
    yield b
    b.close()


@pytest.fixture(scope="module")
def recorded(bridge):
    """Two real recorded episodes: a weak day and a survey day."""
    subject = f"exactness_{int(time.time())}"
    weak = strategy_weak_incumbent()
    survey = strategy_survey()
    r_weak = run_episode(bridge, subject, weak, episode_id=f"{subject}-weak", max_steps=30)
    r_survey = run_episode(bridge, subject, survey, episode_id=f"{subject}-survey", max_steps=30)
    records = bridge.retrieve_attempts(subject)
    tree = ExperienceTree.from_records(records)
    return {"subject": subject, "weak": weak, "survey": survey, "tree": tree,
            "r_weak": r_weak, "r_survey": r_survey}


def test_tree_decodes_both_episodes(recorded):
    tree = recorded["tree"]
    assert tree.episode_count == 2
    assert tree.step_count == recorded["r_weak"].recorded + recorded["r_survey"].recorded
    report = tree.verify_consistency()
    assert report["conflicts"] == [], f"conflicting recordings: {report['conflicts']}"
    assert report["exact_episodes"] == 2


def test_replay_reproduces_own_recorded_episode_exactly(recorded):
    tree = recorded["tree"]
    # Replaying the weak strategy: its own episode must come out exactly.
    # Tolerance note: scores are stored in the KB as float32 sc-links, so the
    # replay sum equals the in-memory float64 sum up to float32 precision.
    result = tree.replay(recorded["weak"])
    rows = {row.episode: row for row in result.rows}
    own = rows[f"{recorded['subject']}-weak"]
    assert abs(own.score - recorded["r_weak"].total_score) < 1e-4
    assert own.covered == recorded["r_weak"].recorded
    assert own.uncovered == 0
    assert own.ended == "recorded-end"


def test_replay_executes_nothing_but_gives_identical_estimates(recorded):
    import world as world_mod

    tree = recorded["tree"]
    before = tree.replay(recorded["weak"]).estimated_score

    def boom(*args, **kwargs):
        raise AssertionError("the world was executed during a dream")

    original = world_mod.ExpeditionWorld.step
    world_mod.ExpeditionWorld.step = boom
    try:
        after = tree.replay(recorded["weak"]).estimated_score
        survey_after = tree.replay(recorded["survey"]).estimated_score
    finally:
        world_mod.ExpeditionWorld.step = original

    assert before == after
    assert survey_after != 0.0


def test_diverging_candidate_is_judged_from_recordings(recorded):
    """The survey strategy over the weak episode's initial state: where it
    diverges, the judge uses recorded transitions (or truncates)."""
    tree = recorded["tree"]
    result = tree.replay(recorded["survey"])
    rows = {row.episode: row for row in result.rows}
    own = rows[f"{recorded['subject']}-survey"]
    assert abs(own.score - recorded["r_survey"].total_score) < 1e-4  # float32 links
    assert own.uncovered == 0
    # over the other episode it either follows recordings or truncates — never invents
    other = rows[f"{recorded['subject']}-weak"]
    assert other.ended in ("recorded-end", "uncovered", "step-cap")
