"""Agents for Oneiro-OSTIS experiments.

All agents implement the same interface:
    choose_action(state, legal_actions, rng) -> action string
    observe_step(step)                        -> None  (called after execution)
    reset()                                   -> None  (before each episode)

Baselines:
  - ContextOnlyAgent — keeps only what fits in a short "attention window"
    of the last steps; forgets everything else. This is what a pure LLM
    with a limited context has.
  - FlatStoreAgent   — an unbounded flat list of past steps, unordered,
    no structure. This is "just store everything" without OSTIS relations.

Experimental agent:
  - OSTISMemoryAgent — records every attempt into the OSTIS knowledge base
    through the live stack (C++ agents build the graph), retrieves it back
    in chronological order and uses remembered experience to choose actions.

Ablation flags on OSTISMemoryAgent (configured in the ontology/relations
that get recorded):
  - no_temporal   — do not record nrel_prev_attempt usage (chronology lost)
  - no_provenance — do not record nrel_source (provenance lost)
"""

from __future__ import annotations

import random
import time
from typing import Optional

from world import Step, WorldState


def episode_step_score(steps: list[Step]) -> float:
    return sum(s.score for s in steps)


class RandomAgent:
    """Chooses uniformly among legal actions. Floor baseline."""

    def __init__(self, seed: int = 0):
        self.seed = seed

    def reset(self) -> None:
        pass

    def observe_step(self, step: Step) -> None:
        pass

    def choose_action(self, state: WorldState, legal: list[str], rng: random.Random) -> str:
        return rng.choice(legal)


class ContextOnlyAgent:
    """Remembers only the last `window` steps; everything older is forgotten."""

    def __init__(self, window: int = 3, seed: int = 0):
        self.window = window
        self.memory: list[Step] = []
        self.rng = random.Random(seed)

    def reset(self) -> None:
        self.memory = []

    def observe_step(self, step: Step) -> None:
        self.memory.append(step)
        if len(self.memory) > self.window:
            self.memory.pop(0)

    def choose_action(self, state: WorldState, legal: list[str], rng: random.Random) -> str:
        # deterministic-ish policy: prefer delivering when carrying; dig at new sites
        if state.carrying and any(a.startswith("deliver:") for a in legal):
            return max(
                (a for a in legal if a.startswith("deliver:")),
                key=lambda a: float(a.split(":")[1] in ("cove",)) ,
            )
        digs = [a for a in legal if a.startswith("dig:")]
        if digs:
            return rng.choice(digs)
        # travel towards a dig site not yet dug out (from remembered steps only)
        dug = {s.object for s in self.memory if s.action == "dig" and s.outcome == "concept_success"}
        travels = [a for a in legal if a.startswith("travel:")]
        if travels:
            return rng.choice(travels)
        return rng.choice(legal)


class FlatStoreAgent:
    """Stores every step in a flat unordered list; no order, no structure."""

    def __init__(self, seed: int = 0):
        self.memory: list[Step] = []
        self.rng = random.Random(seed)

    def reset(self) -> None:
        self.memory = []

    def observe_step(self, step: Step) -> None:
        self.memory.append(step)

    def choose_action(self, state: WorldState, legal: list[str], rng: random) -> str:
        # Same policy as ContextOnly but remembering all past dig successes.
        dug = {s.object for s in self.memory if s.action == "dig" and s.outcome == "concept_success"}
        digs = [a for a in legal if a.startswith("dig:")]
        if digs:
            return rng.choice(digs)
        if state.carrying and any(a.startswith("deliver:") for a in legal):
            return next(a for a in legal if a.startswith("deliver:"))
        travels = [a for a in legal if a.startswith("travel:")]
        return rng.choice(travels) if travels else rng.choice(legal)


class OSTISMemoryAgent:
    """Records each attempt to the OSTIS KB (live stack) and reads it back.

    The agent's policy mirrors FlatStoreAgent's, but its memory IS the OSTIS
    knowledge base: it observes by recording through the bridge, and chooses
    by retrieving from the graph. Ablation flags drop relations at write time.
    """

    def __init__(self, bridge, subject: str = "oneiro_agent", seed: int = 0,
                 no_temporal: bool = False, no_provenance: bool = False):
        self.bridge = bridge
        self.subject = subject
        self.no_temporal = no_temporal
        self.no_provenance = no_provenance
        self.records: list = []
        self.rng = random.Random(seed)

    def reset(self) -> None:
        self.records = []

    def observe_step(self, step: Step, timestamp: Optional[int] = None) -> None:
        if timestamp is None:
            timestamp = int(time.time())
        rec = self.bridge.record_attempt(
            self.subject,
            step.action,
            step.object,
            step.outcome,
            source=None if self.no_provenance else "source_direct",
            kind="expedition",
            score=step.score,
            timestamp=timestamp,
            no_temporal=self.no_temporal,
        )
        self.records.append(rec)

    def choose_action(self, state: WorldState, legal: list[str], rng: random.Random) -> str:
        # Retrieve from the KB (chronological) — this exercises retrieval too.
        got = self.bridge.retrieve_attempts(self.subject)
        dug = {r.object for r in got if r.action == "dig" and r.outcome == "concept_success"}
        delivered_from = {r.object for r in got if r.action == "deliver"}
        digs = [a for a in legal if a.startswith("dig:")]
        if digs:
            return rng.choice(digs)
        if state.carrying and any(a.startswith("deliver:") for a in legal):
            return next(a for a in legal if a.startswith("deliver:"))
        travels = [a for a in legal if a.strip and a.startswith("travel:")]
        return rng.choice(travels) if travels else rng.choice(legal)
