"""Strategies for the workshop domain (second world).

Same contract as the island strategies — a descriptor that is JSON-serialisable,
executable against an observation, storable in the OSTIS graph — but over a
different domain: the free parameters are *what to produce* (target) and *in
which order to fetch raw materials*, which is exactly the sequencing/hoarding
decision the domain was built to expose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from world import bfs_next_hop
from world.workshop import LOCATIONS, RECIPES, RESOURCE_FOR, VALUES


# ---------- domain view ----------


@dataclass
class WorkshopObservation:
    location: str
    inventory: dict[str, int] = field(default_factory=dict)
    gathered: dict[str, int] = field(default_factory=dict)


def observation_of_snapshot(raw: dict) -> WorkshopObservation:
    """Build the policy's view from a recorded state snapshot."""
    return WorkshopObservation(
        location=str(raw.get("location", "")),
        inventory={str(k): int(v) for k, v in (raw.get("inventory") or {}).items()},
        gathered={str(k): int(v) for k, v in (raw.get("gathered") or {}).items()},
    )


def workshop_signature(raw: dict, full_action: str) -> tuple:
    """Outcome-sufficient signature for this domain.

    gather outcomes depend on the taken-count at the current node; craft and
    sell outcomes depend on the whole inventory; travel is uniform.
    """
    inv = raw.get("inventory") or {}
    gathered = raw.get("gathered") or {}
    return (
        str(raw.get("location", "")),
        tuple(sorted((str(k), int(v)) for k, v in inv.items())),
        int(gathered.get(raw.get("location", ""), 0)),
    )


# ---------- strategy ----------


@dataclass
class WorkshopStrategy:
    """Produce `target` repeatedly; fetch missing raw materials in `gather_order`.

    The policy may use world knowledge (recipes, map) — it never decides
    outcomes, only picks among the legal actions it is shown.
    """

    name: str
    target: str = "cart"
    gather_order: list[str] = field(default_factory=lambda: ["wood", "ore", "fiber"])
    _blocked: set = field(default_factory=set, repr=False, compare=False)

    def reset(self) -> None:
        """Per-episode memory: nodes observed depleted."""
        self._blocked = set()

    # ---------- descriptor ----------

    def descriptor(self) -> dict:
        return {"name": self.name, "target": self.target, "gather_order": list(self.gather_order)}

    @classmethod
    def from_descriptor(cls, d: dict) -> "WorkshopStrategy":
        errors = validate_workshop_descriptor(d)
        if errors:
            raise ValueError("invalid workshop descriptor: " + "; ".join(errors))
        return cls(
            name=str(d["name"]),
            target=str(d.get("target", "cart")),
            gather_order=[str(r) for r in d.get("gather_order", ["wood", "ore", "fiber"])],
        )

    # ---------- policy ----------

    def choose(self, obs: WorkshopObservation, legal: list[str]) -> str:
        legal_set = set(legal)
        cur = obs.location
        # A depleted node is discovered on arrival; recompute the plan then.
        for _ in range(3):
            action = self._decide(obs, legal_set, cur)
            if action is not None:
                return action
        travels = [a for a in legal if a.startswith("travel:")]
        return travels[0] if travels else legal[0]

    def _decide(self, obs: WorkshopObservation, legal_set: set, cur: str):
        inv = obs.inventory
        if inv.get(self.target, 0) > 0:
            if cur == "market" and f"sell:{self.target}" in legal_set:
                return f"sell:{self.target}"
            return self._towards(cur, "market", legal_set)

        plan = self._plan_step(obs)
        if plan is None:
            return self._salvage(obs, legal_set, cur)

        kind, item = plan[0], plan[1]
        if kind == "craft":
            if cur == "shop":
                return f"craft:{item}"
            return self._towards(cur, "shop", legal_set)

        # gather
        res, node = item, RESOURCE_FOR[item]
        if cur == node:
            if f"gather:{res}" in legal_set:
                return f"gather:{res}"
            self._blocked.add(node)
            return None  # recompute without this node
        return self._towards(cur, node, legal_set)

    def _plan_step(self, obs: WorkshopObservation):
        """Next productive step: craft the target, craft a component, or gather."""
        inv = obs.inventory
        target = self.target
        if all(inv.get(c, 0) >= n for c, n in RECIPES[target].items()):
            return ("craft", target)

        components_missing = [(c, n) for c, n in RECIPES[target].items() if inv.get(c, 0) < n]
        for c, n in components_missing:
            if c in RECIPES and all(inv.get(r, 0) >= v for r, v in RECIPES[c].items()):
                return ("craft", c)

        missing: dict[str, int] = {}
        for c, n in components_missing:
            recipe = RECIPES[c] if c in RECIPES else {c: n}
            for r, v in recipe.items():
                short = v - inv.get(r, 0)
                if short > 0:
                    missing[r] = max(missing.get(r, 0), short)
        if missing:
            candidates = [r for r in self.gather_order if r in missing and RESOURCE_FOR[r] not in self._blocked]
            candidates += [r for r in missing if RESOURCE_FOR[r] not in self._blocked]
            if candidates:
                return ("gather", candidates[0])
            return None  # every needed node is depleted
        return None

    def _salvage(self, obs: WorkshopObservation, legal_set: set, cur: str):
        """The target became impossible: craft the most valuable craftable
        item, sell anything sellable, otherwise gather anything available."""
        for item in sorted(VALUES, key=lambda i: -VALUES[i]):
            if f"craft:{item}" in legal_set:
                return f"craft:{item}"
        sellable = sorted((a for a in legal_set if a.startswith("sell:")), key=lambda a: -VALUES[a.split(":", 1)[1]])
        if obs.inventory:
            if cur == "market" and sellable:
                return sellable[0]
            move = self._towards(cur, "market", legal_set)
            if move is not None:
                return move
        for res in self.gather_order:
            if f"gather:{res}" in legal_set:
                return f"gather:{res}"
        return None

    @staticmethod
    def _towards(cur: str, dst: str, legal_set: set):
        hop = bfs_next_hop(cur, dst, LOCATIONS)
        if hop is None:
            return None
        action = f"travel:{hop}"
        return action if action in legal_set else None


def validate_workshop_descriptor(d: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(d, dict):
        return ["descriptor must be a JSON object"]
    if not isinstance(d.get("name"), str) or not d.get("name", "").strip():
        errors.append("name must be a non-empty string")
    if d.get("target") not in RECIPES:
        errors.append(f"target must be one of {sorted(RECIPES)}")
    order = d.get("gather_order", [])
    if not isinstance(order, list) or sorted(order) != sorted(RESOURCE_FOR):
        errors.append(f"gather_order must be a permutation of {sorted(RESOURCE_FOR)}")
    return errors


# ---------- baselines and candidates ----------

RESOURCES = ["wood", "ore", "fiber"]
ORDERS = [
    ["wood", "ore", "fiber"],
    ["fiber", "ore", "wood"],
    ["ore", "wood", "fiber"],
    ["wood", "fiber", "ore"],
    ["fiber", "wood", "ore"],
    ["ore", "fiber", "wood"],
]


def strategy_weak_incumbent_workshop() -> WorkshopStrategy:
    """First day: sell simple planks, fetch in a wasteful order."""
    return WorkshopStrategy(name="ws_weak_plank", target="plank", gather_order=["fiber", "ore", "wood"])


def strategy_survey_workshop() -> WorkshopStrategy:
    """Exploration walk: produce combos, natural order."""
    return WorkshopStrategy(name="ws_survey_cart", target="cart", gather_order=["wood", "ore", "fiber"])


def strategy_survey_workshop_alt() -> WorkshopStrategy:
    """Second exploration walk: another target and order (wider coverage)."""
    return WorkshopStrategy(name="ws_survey_rope", target="rope", gather_order=["fiber", "wood", "ore"])


class OfflineWorkshopGenerator:
    """Deterministic candidate sweep for the workshop domain (the dream's
    default proposal source; the island has its own generator in adapter_llm)."""

    name = "offline-workshop"

    def generate(self, context: dict, n: int) -> list[WorkshopStrategy]:
        incumbent = None
        inc_desc = (context or {}).get("incumbent")
        if isinstance(inc_desc, dict):
            try:
                incumbent = WorkshopStrategy.from_descriptor(inc_desc)
            except ValueError:
                incumbent = None
        return workshop_candidates(incumbent, limit=n or 24)


def workshop_candidates(incumbent: WorkshopStrategy | None = None, limit: int = 24) -> list[WorkshopStrategy]:
    """Deterministic sweep: target x gather order."""
    candidates: list[WorkshopStrategy] = []
    seen: set[str] = set()

    def add(s: WorkshopStrategy) -> None:
        if s.name not in seen and len(candidates) < limit:
            seen.add(s.name)
            candidates.append(s)

    if incumbent is not None:
        add(incumbent)
    add(strategy_survey_workshop())
    for target in ("cart", "rope", "ingot", "plank"):
        for order in ORDERS:
            add(WorkshopStrategy(name=f"ws_{target}_{order[0][0]}{order[1][0]}{order[2][0]}", target=target, gather_order=list(order)))
    return candidates
