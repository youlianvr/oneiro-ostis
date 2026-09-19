"""Second domain: a deterministic workshop economy.

Why a second world exists: the dream machinery (recorded trajectories in the
OSTIS graph -> exact replay judge -> deployed winner) must not be a story
about one island. This domain is structurally different from the expedition:

  - no carrying constraint; an inventory holds many stacks at once;
  - actions build on each other: gather -> craft components -> craft a combo
    item -> sell. Sequencing and hoarding decide the score;
  - three resource nodes feed recipes, so the *order* of trips matters;
  - the combo item (cart) is worth 2.2x the sum of its components — the
    interesting discovery for the dream is to hoard for combos instead of
    selling components one by one.

Everything is deterministic from a seed: node capacities and (there are no
random values besides capacities; values are fixed constants) — the same seed
always produces the same trace, process-stable.

Map:            shop <-> grove (wood)
                shop <-> pit   (ore)
                shop <-> fen   (fiber)
                shop <-> market

Actions:        travel:<location>          -0.05, one step
                gather:<resource>          +1 unit at the matching node
                craft:<item>               consumes recipe materials at shop
                sell:<item>                +value at market

Recipes:        plank  = 2 wood            value 6
                ingot  = 2 ore             value 8
                rope   = 3 fiber           value 9
                cart   = plank+ingot+rope  value 40
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from world import _noise

LOCATIONS: dict[str, list[str]] = {
    "shop": ["grove", "pit", "fen", "market"],
    "grove": ["shop"],
    "pit": ["shop"],
    "fen": ["shop"],
    "market": ["shop"],
}

RESOURCE_NODES: dict[str, str] = {"grove": "wood", "pit": "ore", "fen": "fiber"}
RESOURCE_FOR: dict[str, str] = {v: k for k, v in RESOURCE_NODES.items()}

RECIPES: dict[str, dict[str, int]] = {
    "plank": {"wood": 2},
    "ingot": {"ore": 2},
    "rope": {"fiber": 3},
    "cart": {"plank": 1, "ingot": 1, "rope": 1},
}
VALUES: dict[str, float] = {"plank": 6.0, "ingot": 8.0, "rope": 9.0, "cart": 40.0}
CRAFTABLE: list[str] = ["plank", "ingot", "rope", "cart"]
SELLABLE: list[str] = ["plank", "ingot", "rope", "cart"]

TRAVEL_COST = 0.05
STEP_BUDGET = 40


def _node_code(node: str) -> int:
    digest = hashlib.sha256(node.encode()).digest()
    return int.from_bytes(digest[:4], "big") % 1000


@dataclass
class WorkshopState:
    """Full observable state of one workshop episode.

    Score semantics (same as the island world): training wheels for display —
    `score` accumulates rewards only (sells); the travel overhead is carried
    by the individual Step scores, and an episode's total is the sum of them.
    """

    location: str = "shop"
    inventory: dict[str, int] = field(default_factory=dict)
    gathered: dict[str, int] = field(default_factory=dict)   # node -> units taken
    score: float = 0.0
    steps_used: int = 0

    def snapshot(self) -> dict:
        return {
            "location": self.location,
            "inventory": dict(self.inventory),
            "gathered": dict(self.gathered),
            "score": round(self.score, 6),
            "steps": self.steps_used,
        }


class WorkshopWorld:
    """Deterministic crafting-economy world."""

    def __init__(self, seed: str = "workshop-0", max_steps: int = STEP_BUDGET):
        self.seed = seed
        self.max_steps = max_steps
        self.reset()

    def reset(self) -> WorkshopState:
        self.state = WorkshopState()
        self._capacity: dict[str, int] = {}
        for node in RESOURCE_NODES:
            # 3..6 units per node, fixed by the seed
            self._capacity[node] = 3 + int(_noise(self.seed + ":cap", _node_code(node)) * 10) % 4
        return self.state

    # ---------- queries ----------

    def remaining(self, node: str) -> int:
        return max(0, self._capacity.get(node, 0) - self.state.gathered.get(node, 0))

    def can_craft(self, item: str) -> bool:
        recipe = RECIPES.get(item, {})
        return all(self.state.inventory.get(k, 0) >= v for k, v in recipe.items())

    def legal_actions(self, state: WorkshopState | None = None) -> list[str]:
        s = state or self.state
        acts: list[str] = []
        resource = RESOURCE_NODES.get(s.location)
        if resource is not None and self.remaining(s.location) > 0:
            acts.append(f"gather:{resource}")
        if s.location == "shop":
            for item in CRAFTABLE:
                if self.can_craft(item):
                    acts.append(f"craft:{item}")
        if s.location == "market":
            for item in SELLABLE:
                if s.inventory.get(item, 0) > 0:
                    acts.append(f"sell:{item}")
        acts.extend(f"travel:{loc}" for loc in LOCATIONS.get(s.location, []))
        return acts

    # ---------- execution ----------

    def step(self, action: str, state: WorkshopState | None = None):
        from world import Step

        s = state or self.state
        if s.steps_used >= self.max_steps:
            return Step(action.partition(":")[0], action.partition(":")[2], "concept_failure", 0.0, "budget exhausted")

        name, _, arg = action.partition(":")

        if name == "travel" and arg in LOCATIONS.get(s.location, []):
            s.location = arg
            s.steps_used += 1
            return Step("travel", arg, "concept_success", -TRAVEL_COST, f"at {arg}")

        if name == "gather" and RESOURCE_NODES.get(s.location) == arg:
            if self.remaining(s.location) <= 0:
                s.steps_used += 1
                return Step("gather", arg, "concept_failure", 0.0, "node depleted")
            s.gathered[s.location] = s.gathered.get(s.location, 0) + 1
            s.inventory[arg] = s.inventory.get(arg, 0) + 1
            s.steps_used += 1
            return Step("gather", arg, "concept_success", 0.0, f"{arg} +1 (have {s.inventory[arg]})")

        if name == "craft" and s.location == "shop" and self.can_craft(arg):
            for k, v in RECIPES[arg].items():
                s.inventory[k] -= v
                if s.inventory[k] <= 0:
                    del s.inventory[k]
            s.inventory[arg] = s.inventory.get(arg, 0) + 1
            s.steps_used += 1
            return Step("craft", arg, "concept_success", 0.0, f"crafted {arg}")

        if name == "sell" and s.location == "market" and s.inventory.get(arg, 0) > 0:
            s.inventory[arg] -= 1
            if s.inventory[arg] <= 0:
                del s.inventory[arg]
            gain = VALUES[arg]
            s.score += gain
            s.steps_used += 1
            return Step("sell", arg, "concept_success", gain, f"sold {arg} for {gain:.0f}")

        s.steps_used += 1
        return Step(name, arg, "concept_failure", 0.0, "illegal action")

    # ---------- full episodes ----------

    def run_episode(self, choose_action, seed: int = 0) -> list:
        import random

        from world import Step

        self.reset()
        rng = random.Random(seed)
        trace: list[Step] = []
        while self.state.steps_used < self.max_steps:
            acts = self.legal_actions()
            if not acts:
                break
            action = choose_action(self.state, acts, rng)
            trace.append(self.step(action))
        return trace
