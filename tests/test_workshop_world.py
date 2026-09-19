"""Second-domain world tests (no stack needed): determinism and legality."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from world.workshop import RESOURCE_NODES, VALUES, WorkshopWorld


def _scripted(actions):
    seq = list(actions)

    def choose(state, legal, rng):
        if not seq:
            travels = [a for a in legal if a.startswith("travel:")]
            return travels[0] if travels else legal[0]
        action = seq.pop(0)
        assert action in legal, f"scripted action {action} illegal in {legal}"
        return action

    return choose


def test_same_seed_identical_trace():
    trace_actions = [
        "travel:grove", "gather:wood", "gather:wood", "travel:shop",
        "craft:plank", "travel:market", "sell:plank",
    ]
    w1 = WorkshopWorld(seed="workshop-0", max_steps=len(trace_actions))
    t1 = w1.run_episode(_scripted(trace_actions))
    w2 = WorkshopWorld(seed="workshop-0", max_steps=len(trace_actions))
    t2 = w2.run_episode(_scripted(trace_actions))
    assert [(s.action, s.object, s.outcome, s.score) for s in t1] == [
        (s.action, s.object, s.outcome, s.score) for s in t2
    ]
    # capacities are stable for the seed
    assert w1._capacity == w2._capacity


def test_gather_depletes_node():
    w = WorkshopWorld(seed="workshop-0")
    w.step("travel:grove")
    cap = w._capacity["grove"]
    for _ in range(cap):
        assert "gather:wood" in w.legal_actions()
        step = w.step("gather:wood")
        assert step.outcome == "concept_success"
    assert w.remaining("grove") == 0
    assert "gather:wood" not in w.legal_actions()
    step = w.step("gather:wood")
    assert step.outcome == "concept_failure"


def test_craft_requires_materials_and_cart_consumes_components():
    w = WorkshopWorld(seed="workshop-0")
    assert "craft:plank" not in w.legal_actions()
    w.step("travel:grove")
    w.step("gather:wood")
    w.step("gather:wood")
    w.step("travel:shop")
    assert "craft:plank" in w.legal_actions()
    w.step("craft:plank")
    assert w.state.inventory.get("plank") == 1
    assert "wood" not in w.state.inventory
    assert "craft:cart" not in w.legal_actions()  # no ingot/rope yet

    optional = w  # silence linters


def test_cart_cycle_scores_forty():
    w = WorkshopWorld(seed="workshop-0")
    cycle = [
        "travel:grove", "gather:wood", "gather:wood", "travel:shop",
        "craft:plank",
        "travel:pit", "gather:ore", "gather:ore", "travel:shop",
        "craft:ingot",
        "travel:fen", "gather:fiber", "gather:fiber", "gather:fiber", "travel:shop",
        "craft:rope",
        "craft:cart",
        "travel:market", "sell:cart",
    ]
    runner = WorkshopWorld(seed="workshop-0", max_steps=len(cycle))
    trace = runner.run_episode(_scripted(cycle))
    assert trace[-1].action == "sell" and trace[-1].score == VALUES["cart"]
    # state.score accumulates rewards; travel overhead lives in the step scores
    assert runner.state.score == VALUES["cart"]
    assert abs(sum(s.score for s in trace) - (VALUES["cart"] - 7 * 0.05)) < 1e-9


def test_sell_requires_inventory_and_market():
    w = WorkshopWorld(seed="workshop-0")
    w.step("travel:market")
    assert not any(a.startswith("sell:") for a in w.legal_actions())
    # traveling out and back with nothing yields no sells
    step = w.step("sell:plank")
    assert step.outcome == "concept_failure"


def test_resource_nodes_map_correctly():
    assert RESOURCE_NODES == {"grove": "wood", "pit": "ore", "fen": "fiber"}
