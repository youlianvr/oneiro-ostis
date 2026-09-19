"""The dream judge: exact replay over the recorded experience tree.

What this module does
---------------------
It loads every recorded attempt of a subject (episode, step index, the world
state before the action, the legal actions before the action, the outcome the
world actually produced) into an ExperienceTree, and then evaluates candidate
strategies by walking that tree:

  - at each step the candidate chooses among the RECORDED legal actions;
  - if the candidate picks the recorded action, the walk continues along that
    recorded trajectory and takes the recorded outcome;
  - if the candidate diverges, the walk looks up the transition
    (state signature, action) anywhere in the tree; if the transition was
    recorded, its recorded outcome is taken and the walk continues from that
    recording's successor state;
  - if no recording of that transition exists, the walk stops there and the
    episode is marked uncovered (pessimistic: no outcome is invented).

So every number the judge uses comes from a recording. Dreaming executes
nothing — the module deliberately has no access to the world object.

The signature is chosen to be outcome-sufficient for this world: (location,
carried artefact, artefacts already taken from the current site). Dig outcomes
depend only on the taken-count at the current site; deliver outcomes only on
the carried artefact and the delivery location (in the signature via location);
travel outcomes are uniform.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

from strategy import Observation, Strategy


# ---------- tree nodes ----------


@dataclass(frozen=True)
class TreeStep:
    """One recorded step: everything the world showed and produced."""

    episode: str
    index: int
    location: str
    carrying: str
    dug_count: tuple  # sorted tuple of (site, count)
    legal: tuple[str, ...]
    action: str
    object: str
    outcome: str
    score: float
    strategy: Optional[str] = None
    note: str = ""

    def dug_dict(self) -> dict[str, int]:
        return dict(self.dug_count)

    @property
    def full_action(self) -> str:
        """The qualified action string as the policy speaks it.

        The bridge records the world's Step: `action` is the verb and
        `object` is the target, so travel to the beach is recorded as
        ('travel', 'beach'). The policy chooses among qualified legal strings
        ('travel:beach'). This property bridges the two forms; records that
        already carry a qualified action pass through unchanged.
        """
        if ":" in self.action:
            return self.action
        if self.object:
            return f"{self.action}:{self.object}"
        return self.action

    def signature(self) -> tuple:
        return (self.location, self.carrying, dict(self.dug_count).get(self.location, 0))


def _signature_of(location: str, carrying: str, dug_count: dict[str, int]) -> tuple:
    return (location, carrying, dug_count.get(location, 0))


def _step_from_record(rec) -> Optional[TreeStep]:
    """Convert an AttemptRecord (bridge) into a TreeStep, or None if it has no
    trajectory fields (older recordings stay usable for memory metrics only)."""
    if rec.episode is None or rec.step_index is None or not rec.state:
        return None
    try:
        state = json.loads(rec.state)
    except ValueError:
        return None
    dug = state.get("dug") or {}
    legal = tuple((rec.legal or "").split("|")) if rec.legal else tuple()
    return TreeStep(
        episode=rec.episode,
        index=int(rec.step_index),
        location=str(state.get("location", "")),
        carrying=str(state.get("carrying", "")),
        dug_count=tuple(sorted((str(k), int(v)) for k, v in dug.items())),
        legal=legal,
        action=rec.action,
        object=rec.object,
        outcome=rec.outcome,
        score=float(rec.score or 0.0),
        strategy=rec.strategy,
        note=rec.note or "",
    )


# ---------- the tree ----------


class ExperienceTree:
    """All recorded trajectories of one subject, indexed for replay."""

    def __init__(self, episodes: dict[str, list[TreeStep]]):
        self.episodes = episodes
        self.index: dict[tuple, TreeStep] = {}
        self.support: Counter = Counter()
        self.successors: dict[tuple, Optional[TreeStep]] = {}
        self._build_index()

    # ---------- construction ----------

    @classmethod
    def from_records(cls, records: Iterable) -> "ExperienceTree":
        episodes: dict[str, list[TreeStep]] = {}
        for rec in records:
            step = _step_from_record(rec)
            if step is None:
                continue
            episodes.setdefault(step.episode, []).append(step)
        for ep in episodes.values():
            ep.sort(key=lambda s: s.index)
        return cls(episodes)

    def _build_index(self) -> None:
        for ep in self.episodes.values():
            for i, step in enumerate(ep):
                key = (step.signature(), step.full_action)
                self.support[key] += 1
                if key not in self.index:
                    self.index[key] = step
                    successor = ep[i + 1] if i + 1 < len(ep) else None
                    self.successors[key] = successor

    # ---------- properties ----------

    @property
    def episode_count(self) -> int:
        return len(self.episodes)

    @property
    def step_count(self) -> int:
        return sum(len(ep) for ep in self.episodes.values())

    @property
    def transition_count(self) -> int:
        return len(self.index)

    def to_summary(self) -> dict:
        """Compact description of the tree (context for candidate generators)."""
        sites: dict[str, dict] = {}
        for ep in self.episodes.values():
            for s in ep:
                if s.action == "dig" and s.outcome == "concept_success":
                    sites.setdefault(s.object, {"digs": 0})
                    sites[s.object]["digs"] += 1
        deliveries = Counter()
        for ep in self.episodes.values():
            for s in ep:
                if s.action == "deliver" and s.outcome == "concept_success":
                    deliveries[s.object] += 1
        return {
            "episodes": self.episode_count,
            "steps": self.step_count,
            "transitions": self.transition_count,
            "digs_per_site": {k: v["digs"] for k, v in sorted(sites.items())},
            "deliveries": dict(deliveries),
        }

    # ---------- consistency (exactness) ----------

    def verify_consistency(self) -> dict:
        """Every recording of the same (signature, action) must agree.

        The world is deterministic, so conflicting recorded outcomes would mean
        the tree — and therefore the judge — is lying. Also verifies that the
        index-driven walk can reproduce each recorded episode's scores when
        following recorded transitions (no invented outcomes, no truncation).
        """
        conflicts: list[dict] = []
        per_key: dict[tuple, set] = {}
        for ep in self.episodes.values():
            for s in ep:
                key = (s.signature(), s.full_action)
                outcome = (s.outcome, round(s.score, 9), s.object)
                seen = per_key.setdefault(key, set())
                if seen and outcome not in seen:
                    conflicts.append(
                        {
                            "signature": key[0],
                            "action": key[1],
                            "outcomes": sorted(map(str, seen)) + [str(outcome)],
                        }
                    )
                seen.add(outcome)

        exact_episodes = 0
        for ep_id, steps in self.episodes.items():
            total = 0.0
            ok = True
            for s in steps:
                entry = self.index.get((s.signature(), s.full_action))
                if entry is None:
                    ok = False
                    break
                total += entry.score
            if ok and abs(total - sum(s.score for s in steps)) < 1e-9:
                exact_episodes += 1
        return {
            "episodes": self.episode_count,
            "steps": self.step_count,
            "transitions": self.transition_count,
            "conflicts": conflicts,
            "exact_episodes": exact_episodes,
        }

    # ---------- the walk ----------

    def replay(self, strategy: Strategy, *, max_episodes: Optional[int] = None) -> "ReplayResult":
        """Evaluate `strategy` over the whole tree. Executes nothing."""
        result = ReplayResult(strategy=strategy.name)
        episodes = list(self.episodes.items())
        if max_episodes is not None:
            episodes = episodes[:max_episodes]

        for ep_id, steps in episodes:
            if not steps:
                continue
            # Per-episode policy memory (exhausted sites): fresh per episode,
            # exactly like an online run.
            if hasattr(strategy, "reset"):
                strategy.reset()
            row = ReplayEpisode(episode=ep_id)
            score = 0.0
            cur: Optional[TreeStep] = steps[0]
            follow_own = True
            own_index = 0
            steps_taken = 0
            cap = len(steps)

            while steps_taken < cap and cur is not None:
                obs = Observation(location=cur.location, carrying=cur.carrying, dug_count=cur.dug_dict())
                action = strategy.choose(obs, list(cur.legal))
                steps_taken += 1

                if follow_own and own_index < len(steps) and action == steps[own_index].full_action:
                    step = steps[own_index]
                    score += step.score
                    row.covered += 1
                    own_index += 1
                    if own_index >= len(steps):
                        row.ended = "recorded-end"
                        break
                    cur = steps[own_index]
                    continue

                # divergence: consult the global recordings
                follow_own = False
                key = (_signature_of(cur.location, cur.carrying, cur.dug_dict()), action)
                entry = self.index.get(key)
                if entry is None:
                    row.uncovered += 1
                    row.ended = "uncovered"
                    break
                score += entry.score
                row.covered += 1
                successor = self.successors.get(key)
                if successor is None:
                    row.ended = "recorded-end"
                    break
                cur = successor

            else:
                row.ended = row.ended or "step-cap"

            row.score = score
            result.rows.append(row)
            result.estimated_score += score
            result.covered_steps += row.covered
            result.uncovered_steps += row.uncovered

        result.episodes = len(result.rows)
        return result


@dataclass
class ReplayEpisode:
    """Per-episode replay detail."""

    episode: str
    score: float = 0.0
    covered: int = 0
    uncovered: int = 0
    ended: str = ""  # recorded-end | uncovered | step-cap


@dataclass
class ReplayResult:
    """What a candidate strategy would have done, according to the recordings."""

    strategy: str
    estimated_score: float = 0.0
    episodes: int = 0
    covered_steps: int = 0
    uncovered_steps: int = 0
    rows: list[ReplayEpisode] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        total = self.covered_steps + self.uncovered_steps
        return self.covered_steps / total if total else 0.0

    @property
    def mean_score(self) -> float:
        """Replay score per recorded episode (comparable across dreams)."""
        return self.estimated_score / self.episodes if self.episodes else 0.0

    @property
    def truncated_episodes(self) -> int:
        return sum(1 for r in self.rows if r.ended == "uncovered")

    def as_row(self) -> str:
        return (
            f"| {self.strategy} | {self.estimated_score:.1f} | {self.mean_score:.1f} | {self.episodes} "
            f"| {self.coverage:.2f} | {self.uncovered_steps} | {self.truncated_episodes} |"
        )


REPLAY_HEADER = (
    "| candidate | replay score | per episode | episodes | coverage | uncovered steps | truncated episodes |\n"
    "|---|---|---|---|---|---|---|"
)
