"""Metrics for the Oneiro-OSTIS memory experiments.

The central function is ``score_episode``: it records an episode's attempts
into the OSTIS knowledge base through the live stack (the C++ agents do the
graph work), retrieves them back, and compares against ground truth:

  - recall        — how many of the recorded attempts come back
  - order         — adjacent-pair order agreement of the retrieved sequence
  - provenance    — source/kind fields survive (direct vs hearsay)
  - contradictions— retrieved records that differ from ground truth
  - latency       — record+retrieve wall time per attempt

Decision quality (replay) is measured separately: an agent that replays its
remembered experience should do at least as well as the first pass — and
strictly better when memory is used well.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from world import ExpeditionWorld, Step


@dataclass
class MemoryScore:
    """Result of scoring one episode's memory against ground truth."""

    episode_id: str
    recall: float = 0.0
    order_accuracy: float = 0.0
    provenance_accuracy: float = 0.0
    contradictions: int = 0
    retrieval_latency_per_attempt: float = 0.0

    recorded: int = 0
    retrieved: int = 0

    # filled when a replay is scored
    first_pass_score: float = 0.0
    memory_replay_score: Optional[float] = None

    def as_row(self) -> str:
        replay = "-" if self.memory_replay_score is None else f"{self.memory_replay_score:.1f}"
        return (
            f"| {self.episode_id} | {self.recorded} | {self.retrieved} "
            f"| {self.recall:.2f} | {self.order_accuracy:.2f} | {self.provenance_accuracy:.2f} "
            f"| {self.contradictions} | {self.retrieval_latency_per_attempt * 1000:.0f}ms "
            f"| {self.first_pass_score:.1f} | {replay} |"
        )


ROW_HEADER = (
    "| episode | recorded | retrieved | recall | order | provenance | contra | latency/attempt "
    "| first-pass | replay |\n"
    "|---|---|---|---|---|---|---|---|---|---|"
)


def order_accuracy(expected: list[Step], got: list) -> float:
    """Fraction of adjacent ground-truth pairs that appear in the same order
    in the retrieved sequence. Both sides are keyed by (action, object);
    first occurrence positions are used so repeated attempts are handled.
    """
    got_pairs = [(r.action, r.object) for r in got]
    exp_pairs = [(s.action, s.object) for s in expected]
    pos_in_got: dict = {}
    for i, p in enumerate(got_pairs):
        if p not in pos_in_got:
            pos_in_got[p] = i
    correct = comparable = 0
    for ea, eb in zip(exp_pairs, exp_pairs[1:]):
        if ea == eb:
            continue  # identical keys carry no order information
        if ea in pos_in_got and eb in pos_in_got:
            comparable += 1
            if pos_in_got[ea] < pos_in_got[eb]:
                correct += 1
    return correct / comparable if comparable else 0.0


def score_episode(
    bridge,
    subject: str,
    steps: list[Step],
    episode_id: str,
) -> MemoryScore:
    """Record steps into KB via bridge, retrieve back, compare with ground truth."""
    t0 = time.perf_counter()
    ts = int(time.time())
    for i, s in enumerate(steps):
        bridge.record_attempt(
            subject,
            s.action,
            s.object,
            s.outcome,
            source="source_direct",
            kind="expedition",
            score=s.score,
            timestamp=ts + i,
        )
    record_ms = (time.perf_counter() - t0) / max(1, len(steps))

    t0 = time.perf_counter()
    got = bridge.retrieve_attempts(subject)
    retrieval_ms = (time.perf_counter() - t0) / max(1, len(steps))

    score = MemoryScore(episode_id=episode_id, recorded=len(steps), retrieved=len(got))
    score.recall = len(got) / len(steps) if steps else 0.0
    score.order_accuracy = order_accuracy(steps, got)

    # provenance: source and kind survive on every retrieved attempt
    if got:
        ok = sum(1 for r in got if r.source == "source_direct" and r.kind == "expedition")
        score.provenance_accuracy = ok / len(got)

    # contradictions: retrieved records that differ from ground truth
    exp_set = {(s.action, s.object, s.outcome) for s in steps}
    for r in got:
        if (r.action, r.object, r.outcome) not in exp_set:
            score.contradictions += 1

    score.retrieval_latency_per_attempt = record_ms + retrieval_ms
    score.first_pass_score = sum(s.score for s in steps)
    return score


def make_results_table(rows: list[MemoryScore]) -> str:
    lines = [ROW_HEADER]
    lines.extend(r.as_row() for r in sorted(rows, key=lambda r: r.episode_id))
    return "\n".join(lines)
