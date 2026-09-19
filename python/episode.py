"""Online episode runner: strategy acts in the world, OSTIS records everything.

Every step is recorded through the bridge — the C++ agent creates the attempt,
the bridge attaches the trajectory fields (episode, step index, the world state
BEFORE the action, the legal actions BEFORE the action, the producing strategy,
the world note). The dream engine later replays over exactly this recording.

`run_episode_on` is domain-agnostic: it drives any world that exposes the same
small protocol (reset / legal_actions / step / state.snapshot / max_steps).
The historical `run_episode` is the island convenience wrapper.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from strategy import Observation, Strategy, observation_of_snapshot
from world import ExpeditionWorld, Step


@dataclass
class EpisodeResult:
    """Outcome of one online episode (and what was recorded for it)."""

    episode_id: str
    strategy_name: str
    world_seed: str
    max_steps: int
    steps: list[Step] = field(default_factory=list)
    recorded: int = 0
    total_score: float = 0.0
    domain: str = "island"
    action_counts: Counter = field(default_factory=Counter)  # successful actions by verb

    @property
    def deliveries(self) -> int:
        return self.action_counts.get("deliver", 0)

    @property
    def digs(self) -> int:
        return self.action_counts.get("dig", 0)

    def counts(self, *verbs: str) -> str:
        return " ".join(f"{v}={self.action_counts.get(v, 0)}" for v in verbs)

    def summary(self) -> str:
        if self.domain == "expedition":
            return (
                f"{self.strategy_name}: score={self.total_score:.1f} "
                f"steps={len(self.steps)} digs={self.digs} deliveries={self.deliveries}"
            )
        return (
            f"{self.strategy_name}: score={self.total_score:.1f} steps={len(self.steps)} "
            + self.counts("gather", "craft", "sell")
        )


def observation_of(state) -> Observation:
    """Island snapshot of the world state as the policy sees it."""
    return observation_of_snapshot(state.snapshot())


def state_snapshot(state) -> dict:
    """Serialisable state snapshot stored on the attempt node (nrel_state)."""
    return state.snapshot()


def run_episode_on(
    world,
    bridge,
    subject: str,
    strategy,
    *,
    episode_id: str | None = None,
    record: bool = True,
    observe=None,
    domain: str = "island",
) -> EpisodeResult:
    """Run one deterministic episode on any protocol-compliant world;
    record every step to OSTIS (state and legal actions BEFORE each action)."""
    observe = observe or observation_of_snapshot
    world.reset()
    if hasattr(strategy, "reset"):
        strategy.reset()

    if episode_id is None:
        episode_id = f"ep-{subject}-{int(time.time() * 1000)}"
    result = EpisodeResult(
        episode_id=episode_id,
        strategy_name=strategy.name,
        world_seed=getattr(world, "seed", ""),
        max_steps=world.max_steps,
        domain=domain,
    )

    ts = int(time.time())
    while world.state.steps_used < world.max_steps:
        state_before = world.state.snapshot()
        legal_before = world.legal_actions()
        if not legal_before:
            break
        action = strategy.choose(observe(state_before), legal_before)
        step = world.step(action)
        result.steps.append(step)
        result.total_score += step.score
        if step.outcome == "concept_success":
            result.action_counts[step.action] += 1

        if record:
            bridge.record_attempt(
                subject,
                step.action,
                step.object,
                step.outcome,
                source="source_direct",
                kind=domain,
                score=step.score,
                timestamp=ts + len(result.steps),
                episode=episode_id,
                step_index=len(result.steps) - 1,
                state=state_before,
                legal=legal_before,
                strategy=strategy.name,
                note=step.note,
            )
            result.recorded += 1
    return result


def run_episode(
    bridge,
    subject: str,
    strategy: Strategy,
    *,
    world_seed: str = "oneiro-0",
    episode_id: str | None = None,
    max_steps: int = 40,
    record: bool = True,
) -> EpisodeResult:
    """Island episode: build the expedition world and run it (stage-3..6 API)."""
    world = ExpeditionWorld(seed=world_seed, max_steps=max_steps)
    return run_episode_on(
        world,
        bridge,
        subject,
        strategy,
        episode_id=episode_id,
        record=record,
        observe=observation_of_snapshot,
        domain="expedition",
    )


def episode_id_for(prefix: str, strategy_name: str) -> str:
    return f"{prefix}-{strategy_name}-{int(time.time() * 1000)}"
