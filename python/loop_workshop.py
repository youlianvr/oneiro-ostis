"""Recursive loop on the SECOND domain (workshop): does the dream transfer?

The same machinery as `loop.py` — record trajectories, dream by exact replay
over the recordings, deploy the winner — but the world is the crafting
economy, the signature is the workshop's, and the candidates come from the
workshop sweep. Nothing about the judge or the graph schema is island-specific
except the two pluggable functions (signature, observation).

    PYTHONPATH=python python -m loop_workshop > docs/rounds-workshop.md
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

from bridge import OneiroBridge
from dream import DreamResult, dream
from episode import EpisodeResult, episode_id_for, run_episode_on
from strategy_workshop import (
    OfflineWorkshopGenerator,
    WorkshopStrategy,
    observation_of_snapshot,
    strategy_survey_workshop,
    strategy_survey_workshop_alt,
    strategy_weak_incumbent_workshop,
    workshop_signature,
)
from world.workshop import WorkshopWorld

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))
WORLD_SEED = "workshop-0"


def run_workshop_episode(
    bridge,
    subject: str,
    strategy: WorkshopStrategy,
    *,
    world_seed: str = WORLD_SEED,
    episode_id: str | None = None,
    max_steps: int = 40,
) -> EpisodeResult:
    world = WorkshopWorld(seed=world_seed, max_steps=max_steps)
    return run_episode_on(
        world,
        bridge,
        subject,
        strategy,
        episode_id=episode_id,
        observe=observation_of_snapshot,
        domain="workshop",
    )


@dataclass
class WorkshopRoundLog:
    round_index: int
    online: EpisodeResult
    exploration: list[EpisodeResult]
    dream_result: DreamResult | None


@dataclass
class WorkshopReport:
    subject: str
    world_seed: str
    rounds: list[WorkshopRoundLog] = field(default_factory=list)

    def table(self) -> str:
        lines = [
            "| round | strategy online | online score | gather/craft/sell | dream winner | replay est. | coverage | tree steps |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for log in self.rounds:
            dr = log.dream_result
            winner = dr.winner.name if dr else "-"
            est = f"{dr.winner_result.estimated_score:.1f}" if dr else "-"
            cov = f"{dr.winner_result.coverage:.2f}" if dr else "-"
            tree_steps = dr.tree_summary.get("steps", "-") if dr else "-"
            lines.append(
                f"| {log.round_index} | {log.online.strategy_name} | {log.online.total_score:.1f} "
                f"| {log.online.counts('gather', 'craft', 'sell')} | {winner} | {est} | {cov} | {tree_steps} |"
            )
        return "\n".join(lines)

    def curve(self) -> str:
        """ASCII bars: each round's best measured score (the dream's output is
        the winner for the next round, so the measured column is compared
        against the incumbent's frozen day-1 score)."""
        scores = [log.online.total_score for log in self.rounds]
        if not scores:
            return ""
        top = max(scores) or 1.0
        width = 40
        lines = ["```"]
        for log, score in zip(self.rounds, scores):
            bar = "#" * max(1, int(width * max(score, 0.0) / top))
            lines.append(f"r{log.round_index} {log.online.strategy_name:<24} {score:>7.2f} |{bar}")
        lines.append(f"day-1 incumbent: {scores[0]:.2f} (frozen baseline)")
        lines.append("```")
        return "\n".join(lines)


def run_workshop_loop(
    bridge,
    *,
    subject: str,
    rounds: int = 3,
    world_seed: str = WORLD_SEED,
    max_steps: int = 40,
    limit: int = 24,
    exploration: bool = True,
) -> WorkshopReport:
    strategy = strategy_weak_incumbent_workshop()
    report = WorkshopReport(subject=subject, world_seed=world_seed)

    for r in range(1, rounds + 1):
        online = run_workshop_episode(
            bridge,
            subject,
            strategy,
            world_seed=world_seed,
            episode_id=episode_id_for(f"w{r}-online", strategy.name),
            max_steps=max_steps,
        )
        bridge.mark_strategy_online_score(strategy.name, online.total_score)

        exploration_episodes: list[EpisodeResult] = []
        if exploration:
            for explore in (strategy_survey_workshop(), strategy_survey_workshop_alt()):
                exploration_episodes.append(
                    run_workshop_episode(
                        bridge,
                        subject,
                        explore,
                        world_seed=world_seed,
                        episode_id=episode_id_for(f"w{r}-explore", explore.name),
                        max_steps=max_steps,
                    )
                )

        dream_result = dream(
            bridge,
            subject,
            round_index=r,
            incumbent=strategy,
            generator=OfflineWorkshopGenerator(),
            limit=limit,
            signature=workshop_signature,
            observe=observation_of_snapshot,
        )
        report.rounds.append(
            WorkshopRoundLog(round_index=r, online=online, exploration=exploration_episodes, dream_result=dream_result)
        )
        strategy = dream_result.winner

    return report


def main() -> int:
    bridge = OneiroBridge(HOST, PORT)
    bridge.connect()
    subject = f"workshop_loop_{int(__import__('time').time())}"

    report = run_workshop_loop(bridge, subject=subject, rounds=int(os.environ.get("ONEIRO_ROUNDS", "3")))

    print("# Oneiro-OSTIS — recursive loop on the workshop domain (second world)")
    print()
    print(f"Subject: `{subject}` · world seed `{report.world_seed}` · all numbers from live runs")
    print()
    print(report.table())
    print()
    print("## Online score by round")
    print()
    print(report.curve())
    print()

    last = report.rounds[-1]
    if last.dream_result:
        from dream import dream_table

        print("## Last dream — proposals and replay verdicts (top rows)")
        print()
        table = dream_table(last.dream_result).splitlines()
        print("\n".join(table[:9]))
        print()
        consistency = last.dream_result.consistency
        print(
            f"Tree: {consistency['episodes']} episodes, {consistency['steps']} steps, "
            f"{consistency['transitions']} transitions, conflicts: {len(consistency['conflicts'])}"
        )
    bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
