"""The recursive loop: online round -> record -> dream -> deploy -> repeat.

Each round:
  1. the agent lives one episode in the world with the currently deployed
     strategy; every step is recorded to the OSTIS graph;
  2. an exploration episode (survey strategy) runs; its trajectory widens the
     transition coverage the dream will judge against;
  3. the agent sleeps: the dream engine proposes candidates and replays them
     over ALL recordings, the best one is deployed for the next round;
  4. the measured online score of the deployed strategy is written back onto
     its strategy node.

Everything in `docs/rounds.md` comes from a real run of this module:

    python -m loop > docs/rounds.md
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

from bridge import OneiroBridge
from dream import DreamResult, dream, dream_table
from episode import EpisodeResult, episode_id_for, run_episode
from strategy import Strategy, strategy_survey, strategy_survey_reverse, strategy_weak_incumbent

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))
WORLD_SEED = "oneiro-0"


@dataclass
class RoundLog:
    round_index: int
    online: EpisodeResult
    exploration: list[EpisodeResult]
    dream_result: DreamResult | None
    deployed_next: Strategy


@dataclass
class LoopReport:
    subject: str
    world_seed: str
    rounds: list[RoundLog] = field(default_factory=list)

    # ---------- reporting ----------

    def table(self) -> str:
        lines = [
            "| round | strategy online | online score | digs | deliveries | dream winner | replay est. | coverage | tree steps |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for log in self.rounds:
            dr = log.dream_result
            winner = dr.winner.name if dr else "-"
            est = f"{dr.winner_result.estimated_score:.1f}" if dr else "-"
            cov = f"{dr.winner_result.coverage:.2f}" if dr else "-"
            tree_steps = dr.tree_summary.get("steps", "-") if dr else "-"
            lines.append(
                f"| {log.round_index} | {log.online.strategy_name} | {log.online.total_score:.1f} "
                f"| {log.online.digs} | {log.online.deliveries} | {winner} | {est} | {cov} | {tree_steps} |"
            )
        return "\n".join(lines)

    def curve(self) -> str:
        """ASCII bars of the measured online scores, one per round."""
        scores = [log.online.total_score for log in self.rounds]
        if not scores:
            return ""
        top = max(scores) or 1.0
        width = 40
        lines = ["```"]
        for log, score in zip(self.rounds, scores):
            bar = "#" * max(1, int(width * max(score, 0.0) / top))
            lines.append(f"r{log.round_index} {log.online.strategy_name:<16} {score:>7.1f} |{bar}")
        lines.append("```")
        return "\n".join(lines)


def run_loop(
    bridge,
    *,
    subject: str,
    rounds: int = 4,
    world_seed: str = WORLD_SEED,
    max_steps: int = 40,
    limit: int = 24,
    generator=None,
    exploration: bool = True,
) -> LoopReport:
    """Run the full recursive loop on the live stack."""
    strategy = strategy_weak_incumbent()
    report = LoopReport(subject=subject, world_seed=world_seed)

    for r in range(1, rounds + 1):
        online = run_episode(
            bridge,
            subject,
            strategy,
            world_seed=world_seed,
            episode_id=episode_id_for(f"r{r}-online", strategy.name),
            max_steps=max_steps,
        )
        # write the measured score onto the strategy node (deployment evidence)
        bridge.mark_strategy_online_score(strategy.name, online.total_score)

        exploration_episodes: list[EpisodeResult] = []
        if exploration:
            # Two exploration walks per round (nearest-first and farthest-first)
            # widen the transition coverage both directions of the island.
            for explore_strategy in (strategy_survey(), strategy_survey_reverse()):
                exploration_episodes.append(
                    run_episode(
                        bridge,
                        subject,
                        explore_strategy,
                        world_seed=world_seed,
                        episode_id=episode_id_for(f"r{r}-explore", explore_strategy.name),
                        max_steps=max_steps,
                    )
                )

        dream_result = dream(
            bridge,
            subject,
            round_index=r,
            incumbent=strategy,
            generator=generator,
            limit=limit,
        )
        report.rounds.append(
            RoundLog(
                round_index=r,
                online=online,
                exploration=exploration_episodes,
                dream_result=dream_result,
                deployed_next=dream_result.winner,
            )
        )
        strategy = dream_result.winner

    return report


def main() -> int:
    bridge = OneiroBridge(HOST, PORT)
    bridge.connect()
    subject = f"oneiro_loop_{int(__import__('time').time())}"

    report = run_loop(bridge, subject=subject, rounds=int(os.environ.get("ONEIRO_ROUNDS", "4")))

    print("# Oneiro-OSTIS — recursive loop rounds")
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
        print("## Last dream — proposals and replay verdicts")
        print()
        print(dream_table(last.dream_result))
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
