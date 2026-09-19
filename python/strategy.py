"""Strategy descriptors for the Oneiro-OSTIS expedition world.

A Strategy is an executable policy over the deterministic world: given the
observation (location, carried artefact, dug counts) and the list of legal
actions, it returns exactly one action. Strategies are JSON-serialisable
descriptors, which is what makes the dream cycle possible:

  - stored in the OSTIS graph (concept_strategy nodes),
  - proposed by generators (deterministic offline sweep or an LLM adapter),
  - replayed by the dream engine against the recorded experience tree,
  - deployed into the next online round.

The policy may use world *topology* (the island map) to route; it never
decides outcomes — those come from the world in online rounds and from
recordings in replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from world import DELIVERY_MULTIPLIER, DIG_SITES, ISLAND


# ---------- topology helpers ----------


def bfs_next_hop(src: str, dst: str, graph: dict[str, list[str]] | None = None) -> Optional[str]:
    """First step of a shortest path src -> dst; None if unreachable."""
    graph = graph or ISLAND
    if src == dst:
        return None
    seen = {src}
    frontier = [(src, None)]
    while frontier:
        node, first_hop = frontier.pop(0)
        for nb in graph.get(node, []):
            if nb in seen:
                continue
            hop = first_hop or nb
            if nb == dst:
                return hop
            seen.add(nb)
            frontier.append((nb, hop))
    return None


def distance(src: str, dst: str, graph: dict[str, list[str]] | None = None) -> int:
    """Shortest path length in edges; large number if unreachable."""
    graph = graph or ISLAND
    if src == dst:
        return 0
    seen = {src}
    frontier = [(src, 0)]
    while frontier:
        node, d = frontier.pop(0)
        for nb in graph.get(node, []):
            if nb in seen:
                continue
            if nb == dst:
                return d + 1
            seen.add(nb)
            frontier.append((nb, d + 1))
    return 10**6


# ---------- strategy ----------


@dataclass
class Observation:
    """What the policy sees before choosing: the world as recorded."""

    location: str
    carrying: str = ""
    dug_count: dict[str, int] = field(default_factory=dict)


@dataclass
class Strategy:
    """A parameterised expedition policy.

    site_priority    — where to go next (first not-yet-done site)
    dig_limit        — max artefacts to take from one site per episode
    deliver_order    — delivery points best-first (cove 1.5x > beach 1.2x > camp 1.0x)
    """

    name: str
    site_priority: list[str]
    dig_limit: int = 2
    deliver_order: list[str] = field(default_factory=lambda: ["cove", "beach", "camp"])
    # per-episode working memory: sites observed to be empty (dig not legal)
    # though the dig limit had not been reached. Reset before every episode.
    _exhausted: set = field(default_factory=set, repr=False, compare=False)

    # ---------- executable policy ----------

    def reset(self) -> None:
        """Clear per-episode memory (called by runners before each episode)."""
        self._exhausted = set()

    def choose(self, obs: Observation, legal: list[str]) -> str:
        legal_set = set(legal)
        cur = obs.location

        if obs.carrying:
            # Deliver wherever the preference ranks best, else move toward the
            # best delivery point.
            delivers = [a for a in legal if a.startswith("deliver:")]
            if delivers:
                rank = {loc: i for i, loc in enumerate(self.deliver_order)}
                return min(delivers, key=lambda a: (rank.get(a.split(":", 1)[1], 99), a))
            for target in self.deliver_order:
                hop = bfs_next_hop(cur, target)
                if hop is not None and f"travel:{hop}" in legal_set:
                    return f"travel:{hop}"
            return legal[0]

        # Not carrying: dig here if this site is still on the plan.
        if f"dig:{cur}" in legal_set and obs.dug_count.get(cur, 0) < self.dig_limit:
            return f"dig:{cur}"
        if f"dig:{cur}" not in legal_set:
            # Standing here and cannot dig: the site is empty (or the limit is
            # reached). Remember it, or the plan would keep walking back to a
            # site that has nothing left.
            self._exhausted.add(cur)

        # Otherwise head for the first site in priority that still needs work.
        for site in self.site_priority:
            if site in self._exhausted:
                continue
            if obs.dug_count.get(site, 0) >= self.dig_limit:
                continue
            if site == cur:
                continue  # standing here and the dig above was not chosen
            hop = bfs_next_hop(cur, site)
            if hop is not None and f"travel:{hop}" in legal_set:
                return f"travel:{hop}"

        # Plan exhausted: keep gathering anything legal, else keep moving.
        digs = [a for a in legal if a.startswith("dig:")]
        if digs:
            return digs[0]
        travels = [a for a in legal if a.startswith("travel:")]
        return travels[0] if travels else legal[0]

    # ---------- descriptor ----------

    def descriptor(self) -> dict:
        return {
            "name": self.name,
            "site_priority": list(self.site_priority),
            "dig_limit": int(self.dig_limit),
            "deliver_order": list(self.deliver_order),
        }

    @classmethod
    def from_descriptor(cls, d: dict) -> "Strategy":
        errors = validate_descriptor(d)
        if errors:
            raise ValueError("invalid strategy descriptor: " + "; ".join(errors))
        return cls(
            name=str(d["name"]),
            site_priority=[str(s) for s in d["site_priority"]],
            dig_limit=int(d.get("dig_limit", 2)),
            deliver_order=[str(s) for s in d.get("deliver_order", ["cove", "beach", "camp"])],
        )


def validate_descriptor(d: dict) -> list[str]:
    """Return a list of schema violations (empty = valid)."""
    errors: list[str] = []
    if not isinstance(d, dict):
        return ["descriptor must be a JSON object"]
    name = d.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")
    sites = d.get("site_priority")
    if not isinstance(sites, list) or not sites or not all(isinstance(s, str) for s in sites):
        errors.append("site_priority must be a non-empty list of site names")
    else:
        unknown = [s for s in sites if s not in DIG_SITES]
        if unknown:
            errors.append(f"unknown sites in site_priority: {unknown}")
    limit = d.get("dig_limit", 2)
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 6):
        errors.append("dig_limit must be an integer in [1, 6]")
    order = d.get("deliver_order", ["cove", "beach", "camp"])
    if not isinstance(order, list) or not all(o in DELIVERY_MULTIPLIER for o in order):
        errors.append(f"deliver_order must be a subset of {sorted(DELIVERY_MULTIPLIER)}")
    return errors


# ---------- named baselines ----------


def nearest_first_order(start: str = "camp") -> list[str]:
    """All dig sites ordered by travel distance from the start camp."""
    return sorted(DIG_SITES, key=lambda s: (distance(start, s), s))


def strategy_survey() -> Strategy:
    """Dig every site to exhaustion, deliver at the best place available.

    Used as exploration: it covers the transition space broadly, which is
    what later dreams replay against.
    """
    return Strategy(
        name="survey",
        site_priority=nearest_first_order(),
        dig_limit=6,
        deliver_order=["cove", "beach", "camp"],
    )


def strategy_survey_reverse() -> Strategy:
    """Second exploration walk: farthest sites first (covers the other
    direction of the island's travel edges for the replay judge)."""
    return Strategy(
        name="survey_reverse",
        site_priority=list(reversed(nearest_first_order())),
        dig_limit=6,
        deliver_order=["cove", "beach", "camp"],
    )


def strategy_weak_incumbent() -> Strategy:
    """A plausible-but-mediocre first day: far sites first, one artefact per
    site, delivery wherever the cheapest multiplier is available first."""
    return Strategy(
        name="weak_wander",
        site_priority=["swamp", "peak", "cliff", "cave", "ruins", "jungle", "cove", "beach"],
        dig_limit=1,
        deliver_order=["camp", "beach", "cove"],
    )


# ---------- candidate generation (offline, deterministic) ----------

_FIXED_ORDERS: dict[str, list[str]] = {
    "nearest": nearest_first_order(),
    "farthest": list(reversed(nearest_first_order())),
    "alpha": sorted(DIG_SITES),
    "reverse_alpha": list(reversed(sorted(DIG_SITES))),
    "coastal": ["cove", "beach", "swamp", "cave", "peak", "cliff", "ruins", "jungle"],
}


def default_candidates(incumbent: Optional[Strategy] = None, limit: int = 24) -> list[Strategy]:
    """A deterministic sweep over (site order x dig limit x delivery order).

    No LLM and no world-internals are used here: orders are topology-based,
    limits and delivery preferences are the free parameters. The dream engine
    judges them; this generator only proposes.
    """
    candidates: list[Strategy] = []
    seen: set[str] = set()

    def add(s: Strategy) -> None:
        if s.name not in seen and len(candidates) < limit:
            seen.add(s.name)
            candidates.append(s)

    if incumbent is not None:
        add(incumbent)
    add(strategy_survey())

    for order_name, order in _FIXED_ORDERS.items():
        for dig_limit in (1, 2, 4):
            add(
                Strategy(
                    name=f"cand_{order_name}_d{dig_limit}",
                    site_priority=list(order),
                    dig_limit=dig_limit,
                    deliver_order=["cove", "beach", "camp"],
                )
            )

    # delivery-preference variants on the most promising looking orders
    for order_name in ("nearest", "coastal"):
        for deliver_order in (["beach", "cove", "camp"], ["cove", "camp", "beach"]):
            add(
                Strategy(
                    name=f"cand_{order_name}_dl_{''.join(o[0] for o in deliver_order)}",
                    site_priority=list(_FIXED_ORDERS[order_name]),
                    dig_limit=4,
                    deliver_order=list(deliver_order),
                )
            )
    return candidates
