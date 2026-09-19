"""Deterministic mini-world for Oneiro-OSTIS experiments.

Island expedition: the agent explores locations, gathers artefacts and
delivers them. Every action has a numeric outcome, and the world is fully
deterministic: the same seed always produces the same trace and the same
scores. Randomness is drawn only from ``random.Random(seed)`` — no hidden
state, no wall-clock time.

World rules (deterministic given the seed):
  - A fixed island graph of locations (travel between neighbours).
  - Each location hides artefacts with fixed values; ``dig`` at a location
    yields one artefact per call until the location is empty.
  - Artefact values have per-seed noise, but the noise stream is fixed, so
    runs with the same seed observe identical values.
  - ``deliver`` converts the carried artefact into score (delivery value
    depends on the destination camp).
  - Episode ends when the step budget is exhausted or the agent returns
    to the start camp with nothing carried.

The world is the ONLY source of outcomes: agents never decide scores,
they only choose actions and read results.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

# Fixed island topology: location -> neighbours.
ISLAND: dict[str, list[str]] = {
    "camp": ["beach", "jungle", "cliff"],
    "beach": ["camp", "cove"],
    "cove": ["beach", "swamp"],
    "jungle": ["camp", "ruins"],
    "ruins": ["jungle", "cave"],
    "cave": ["ruins", "swamp"],
    "cliff": ["camp", "peak"],
    "peak": ["cliff"],
    "swamp": ["cove", "cave"],
}

DIG_SITES = ["beach", "cove", "jungle", "ruins", "cave", "cliff", "peak", "swamp"]

DELIVERY_MULTIPLIER = {"camp": 1.0, "beach": 1.2, "cove": 1.5}
STEP_BUDGET = 40


@dataclass
class Step:
    """One executed world step (to be recorded as an attempt)."""

    action: str           # travel | dig | deliver
    object: str           # location name
    outcome: str          # concept_success | concept_failure
    score: float          # numeric outcome of this single step
    note: str = ""


@dataclass
class WorldState:
    """Full observable state of one episode."""

    location: str = "camp"
    carrying: str = ""            # artefact id currently carried, "" if none
    score: float = 0.0            # accumulated score
    steps_used: int = 0
    dug_out: set[str] = field(default_factory=set)   # (site) emptied entirely
    dug_count: dict[str, int] = field(default_factory=dict)  # site -> taken count
    rng_cursor: int = 0           # position in the deterministic noise stream


def _noise(seed: str, index: int) -> float:
    """Deterministic pseudo-random value in [1.0, 2.0) from seed+index.

    Uses a hash so every site's k-th artefact has the same value across
    all runs with the same world seed — independent of visit order.
    """
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    return 1.0 + (int.from_bytes(digest[:4], "big") % 1000) / 1000.0


def _site_code(site: str) -> int:
    """Process-independent site code.

    Python's built-in hash() for strings is randomized per process
    (PYTHONHASHSEED), which made artefact values differ between runs.
    sha256 gives the same code everywhere, forever.
    """
    digest = hashlib.sha256(site.encode()).digest()
    return int.from_bytes(digest[:4], "big") % 1000


class ExpeditionWorld:
    """Deterministic island-expedition world."""

    def __init__(self, seed: str = "oneiro-0", max_steps: int = STEP_BUDGET):
        self.seed = seed
        self.max_steps = max_steps
        self.reset()

    def reset(self) -> WorldState:
        self.state = WorldState()
        self._site_value_counters: dict[str, int] = {}
        for site in DIG_SITES:
            # artefact count per site is deterministic from the seed
            self._site_value_counters[site] = 2 + (int(_noise(self.seed + ":count", _site_code(site)) * 10) % 3)
        return self.state

    # ---------- legality ----------

    def legal_actions(self, state: WorldState | None = None) -> list[str]:
        s = state or self.state
        acts: list[str] = []
        if s.carrying:
            # Deliver where you stand (only at a delivery point), or move on.
            if s.location in DELIVERY_MULTIPLIER:
                acts.append(f"deliver:{s.location}")
            for loc in ISLAND[s.location]:
                acts.append(f"travel:{loc}")
        else:
            if s.location in DIG_SITES and self._remaining(s, s.location) > 0:
                acts.append(f"dig:{s.location}")
            for loc in ISLAND[s.location]:
                acts.append(f"travel:{loc}")
        return acts or [f"travel:{ISLAND[s.location][0]}"]

    def _remaining(self, state: WorldState, site: str) -> int:
        return max(0, self._site_value_counters.get(site, 0) - state.dug_count.get(site, 0))

    # ---------- execution ----------

    def step(self, action: str, state: WorldState | None = None) -> Step:
        """Execute one action; returns the Step (never raises on illegal input,
        illegal actions become concept_failure with score 0)."""
        s = state or self.state
        if s.steps_used >= self.max_steps:
            return Step(action, "", "concept_failure", 0.0, "budget exhausted")

        name, _, arg = action.partition(":")

        if name == "travel" and arg in ISLAND.get(s.location, []):
            s.location = arg
            s.steps_used += 1
            return Step("travel", arg, "concept_success", -0.1, f"at {arg}")

        if name == "dig" and arg == s.location and s.location in DIG_SITES:
            remaining = self._remaining(s, s.location)
            if remaining <= 0:
                s.steps_used += 1
                return Step("dig", arg, "concept_failure", 0.0, "site empty")
            idx = s.dug_count.get(s.location, 0)
            value = _noise(self.seed + ":val", _site_code(s.location) * 10 + idx) * 10.0
            s.dug_count[s.location] = idx + 1
            s.carrying = f"artefact_{s.location}_{idx}"
            s.steps_used += 1
            return Step("dig", arg, "concept_success", 0.0, f"found {s.carrying} worth {value:.1f}")

        if name == "deliver" and s.carrying and arg in DELIVERY_MULTIPLIER and arg == s.location:
            site = s.carrying.split("_")[1]
            idx = int(s.carrying.split("_")[2])
            value = _noise(self.seed + ":val", _site_code(site) * 10 + idx) * 10.0
            gain = value * DELIVERY_MULTIPLIER[arg]
            s.score += gain
            s.carrying = ""
            s.steps_used += 1
            return Step("deliver", arg, "concept_success", gain, f"delivered for {gain:.1f}")

        # anything illegal
        s.steps_used += 1
        return Step(name, arg, "concept_failure", 0.0, "illegal action")

    # ---------- full episodes ----------

    def run_episode(self, choose_action, seed: int = 0) -> list[Step]:
        """Run one episode; choose_action(state, legal_actions) -> action str.

        Returns the list of Steps. The world state is reset first; the seed
        parameter selects among deterministic action-noise variants given to
        the agent (the world itself stays deterministic for a fixed world seed).
        """
        self.reset()
        rng = random.Random(seed)
        trace: list[Step] = []
        while self.state.steps_used < self.max_steps:
            acts = self.legal_actions()
            if not acts:
                break
            action = choose_action(self.state, acts, rng)
            trace.append(self.step(action))
            if not self.state.carrying and self.state.steps_used >= self.max_steps:
                break
        return trace
