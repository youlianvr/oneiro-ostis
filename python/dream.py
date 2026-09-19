"""The dream cycle: propose strategies, judge them by exact replay, deploy the winner.

Flow (while the agent sleeps):
  1. load the recorded experience tree from the OSTIS graph;
  2. ask a candidate generator (offline sweep or LLM adapter) for strategies;
  3. judge every candidate by replaying it over the tree (replay.engine);
  4. the winner is persisted into the graph and returned for deployment.

Nothing here executes the world. The judge is the recording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from adapter_llm import make_generator
from replay.engine import ExperienceTree, ReplayResult
from strategy import Strategy


@dataclass
class DreamResult:
    """Outcome of one dream: what was proposed, what won, what the graph got."""

    round_index: int
    winner: Strategy
    incumbent: Optional[Strategy]
    results: list[tuple[Strategy, ReplayResult]] = field(default_factory=list)
    tree_summary: dict = field(default_factory=dict)
    consistency: dict = field(default_factory=dict)
    generator: str = "offline"
    saved: int = 0

    @property
    def winner_result(self) -> ReplayResult:
        for candidate, result in self.results:
            if candidate.name == self.winner.name:
                return result
        raise KeyError(self.winner.name)

    @property
    def improved(self) -> bool:
        """Did the dream find a strategy better than the incumbent (by replay)?"""
        if self.incumbent is None:
            return True
        inc = next((r for c, r in self.results if c.name == self.incumbent.name), None)
        return inc is None or self.winner_result.estimated_score > inc.estimated_score


def select_winner(results: list[tuple[Strategy, ReplayResult]]) -> tuple[Strategy, ReplayResult]:
    """Argmax by replay score; ties broken by coverage, then name (deterministic)."""
    return max(
        results,
        key=lambda pair: (
            pair[1].estimated_score,
            pair[1].coverage,
            -len(pair[0].name),
            pair[0].name,
        ),
    )


def dream(
    bridge,
    subject: str,
    *,
    round_index: int,
    incumbent: Optional[Strategy] = None,
    generator=None,
    limit: int = 24,
    save: bool = True,
) -> DreamResult:
    """Run one dream cycle over the recordings of `subject`."""
    records = bridge.retrieve_attempts(subject)
    tree = ExperienceTree.from_records(records)
    if tree.episode_count == 0:
        raise RuntimeError(
            f"no recorded trajectories for subject {subject!r}: nothing to dream about "
            f"(recorded {len(records)} attempts, none with episode/step/state fields)"
        )

    gen = generator or make_generator()
    context = {
        "round_index": round_index,
        "tree": tree.to_summary(),
        "incumbent": incumbent.descriptor() if incumbent is not None else None,
    }
    candidates = gen.generate(context, limit)
    if incumbent is not None and all(c.name != incumbent.name for c in candidates):
        candidates.insert(0, incumbent)
    if not candidates:
        raise RuntimeError("candidate generator returned nothing")

    results = [(c, tree.replay(c)) for c in candidates]
    winner, _ = select_winner(results)
    consistency = tree.verify_consistency()

    saved = 0
    if save:
        for candidate, result in results:
            bridge.save_strategy(
                candidate.name,
                candidate.descriptor(),
                replay_score=result.estimated_score,
                derived_from=(incumbent.name if incumbent is not None and candidate.name != incumbent.name else None),
                dream_round=round_index,
            )
            saved += 1

    return DreamResult(
        round_index=round_index,
        winner=winner,
        incumbent=incumbent,
        results=results,
        tree_summary=tree.to_summary(),
        consistency=consistency,
        generator=getattr(gen, "name", "offline"),
        saved=saved,
    )


def dream_table(dream_result: DreamResult) -> str:
    """Markdown table of the dream's proposals and their replay scores."""
    from replay.engine import REPLAY_HEADER

    lines = [REPLAY_HEADER]
    ranked = sorted(dream_result.results, key=lambda p: p[1].estimated_score, reverse=True)
    for candidate, result in ranked:
        marker = " **WINNER**" if candidate.name == dream_result.winner.name else ""
        lines.append(result.as_row().rstrip() + marker)
    return "\n".join(lines)
