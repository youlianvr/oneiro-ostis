"""Online episode runner: strategy acts in the world, OSTIS records everything.

Every step is recorded through the bridge — the C++ agent creates the attempt,
the bridge attaches the trajectory fields (episode, step index, the world state
BEFORE the action, the legal actions BEFORE the action, the producing strategy,
the world note). The dream engine later replays over exactly this recording.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from strategy import Observation, Strategy
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

    @property
    def deliveries(self) -> int:
        return sum(1 for s in self.steps if s.action == "deliver" and s.outcome == "concept_success")

    @property
    def digs(self) -> int:
        return sum(1 for s in self.steps if s.action == "dig" and s.outcome == "concept_success")

    def summary(self) -> str:
        return (
            f"{self.strategy_name}: score={self.total_score:.1f} "
            f"steps={len(self.steps)} digs={self.digs} deliveries={self.deliveries}"
        )


def observation_of(state) -> Observation:
    """Snapshot of the world state as the policy sees it."""
    return Observation(
        location=state.location,
        carrying=state.carrying,
        dug_count=dict(state.dug_count),
    )


def state_snapshot(state) -> dict:
    """Serialisable state snapshot stored on the attempt node (nrel_state)."""
    return {
        "location": state.location,
        "carrying": state.carrying,
        "dug": dict(state.dug_count),
        "score": round(state.score, 6),
        "steps": state.steps_used,
    }


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
    """Run one deterministic episode with `strategy`; record every step to OSTIS.

    The world state and legal actions are captured BEFORE each action, so the
    recording is a complete trajectory the dream engine can replay.
    """
    world = ExpeditionWorld(seed=world_seed, max_steps=max_steps)
    world.reset()
    if hasattr(strategy, "reset"):
        strategy.reset()

    if episode_id is None:
        episode_id = f"ep-{subject}-{int(time.time() * 1000)}"
    result = EpisodeResult(
        episode_id=episode_id,
        strategy_name=strategy.name,
        world_seed=world_seed,
        max_steps=max_steps,
    )

    ts = int(time.time())
    while world.state.steps_used < world.max_steps:
        state_before = state_snapshot(world.state)
        legal_before = world.legal_actions()
        if not legal_before:
            break
        action = strategy.choose(observation_of(world.state), legal_before)
        step = world.step(action)
        result.steps.append(step)
        result.total_score += step.score

        if record:
            bridge.record_attempt(
                subject,
                step.action,
                step.object,
                step.outcome,
                source="source_direct",
                kind="expedition",
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


def episode_id_for(prefix: str, strategy_name: str) -> str:
    return f"{prefix}-{strategy_name}-{int(time.time() * 1000)}"
