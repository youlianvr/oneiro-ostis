"""Where candidates come from, and why the first ones are written by hand.

The search is over the turn-assembly layer. This proposer takes the recorded policy,
the hand-written variants and one-knob neighbours of each, judges them from the
records with `replay`, and returns them ordered by what the recording can actually
say about them.

An LLM proposer is deliberately absent. The recorded history of the previous loop is
that its proposals were the least defensible part of it — everything that survived
came from hand-written families — and a proposer whose candidates cannot be measured
yet would only add noise to a ledger that has none. It belongs behind the gate, after
the measurement can show what it is worth.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from oneiro.dream import replay
from oneiro.dream.episode import Episode
from oneiro.dream.policy import BASE, KNOBS, VARIANTS, TurnPolicy

#: The one-knob neighbours offered for every knob, so a candidate can be attributed to
#: a single change. Bundles are what made the previous loop's ledger unreadable.
ONE_KNOB: tuple[tuple[str, tuple[Any, ...]], ...] = (
    ("history_messages", (0, 4, 6)),
    ("context_chars", (2000, 4000)),
    ("max_turns", (6, 20)),
    ("include_facts", (False,)),
    ("observation_chars", (800, 1600)),
)


def neighbours(recorded: TurnPolicy = BASE) -> list[TurnPolicy]:
    """One candidate per value, each differing from the recorded policy in one knob."""
    found: list[TurnPolicy] = []
    for field, values in ONE_KNOB:
        for value in values:
            if getattr(recorded, field) == value:
                continue
            found.append(replace(recorded, name=f"{field}={value}", **{field: value}))
    return found


def candidates(recorded: TurnPolicy = BASE, *, variants: bool = True) -> list[TurnPolicy]:
    """Every candidate offered this round, deduplicated by what it actually changes."""
    offered = [recorded]
    if variants:
        offered.extend(VARIANTS.values())
    offered.extend(neighbours(recorded))
    unique: dict[tuple[Any, ...], TurnPolicy] = {}
    for policy in offered:
        unique.setdefault(tuple(getattr(policy, knob) for knob in KNOBS), policy)
    return list(unique.values())


@dataclass(frozen=True)
class Proposal:
    """One candidate with what the recordings could say about it."""

    policy: str
    changed: tuple[str, ...]
    descriptor: dict[str, Any]
    coverage: float
    turns_covered: int
    turns_total: int
    chars_shown: int
    notes: tuple[str, ...]

    @property
    def replayable(self) -> bool:
        """Whether every recorded turn was rebuilt unchanged.

        Anything less means the candidate changed what the model saw somewhere, and
        what the model then did is not in the recording.
        """
        return self.turns_total > 0 and self.turns_covered == self.turns_total

    def to_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "changed": list(self.changed),
                "descriptor": dict(self.descriptor), "coverage": self.coverage,
                "turns_covered": self.turns_covered, "turns_total": self.turns_total,
                "chars_shown": self.chars_shown, "replayable": self.replayable,
                "notes": list(self.notes)}


def propose(episodes: Iterable[Episode], contexts: dict[str, replay.Context] | None = None, *,
            recorded: TurnPolicy = BASE,
            minimum_coverage: float = 0.0) -> list[Proposal]:
    """Judge every candidate from the records and order them.

    Ordering is by coverage first, then by how few knobs were touched: a candidate the
    recording fully covers and that changes one knob is the one worth measuring, and a
    candidate that changes nothing at all is the floor every other number is read
    against.
    """
    turns = list(episodes)
    contexts = contexts or {}
    found: list[Proposal] = []
    for policy in candidates(recorded):
        estimates = [replay.estimate(turn, policy, contexts.get(turn.turn_id),
                                     recorded_policy=recorded)
                     for turn in turns]
        total = len(estimates)
        coverage = (sum(item.coverage for item in estimates) / total) if total else 0.0
        if coverage < minimum_coverage:
            continue
        found.append(Proposal(
            policy=policy.name, changed=policy.changed_fields(recorded),
            descriptor=policy.descriptor(), coverage=round(coverage, 4),
            turns_covered=sum(1 for item in estimates if not item.truncated),
            turns_total=total, chars_shown=sum(item.chars_shown for item in estimates),
            notes=tuple(sorted({note for item in estimates for note in item.notes}))))
    found.sort(key=lambda item: (-item.coverage, len(item.changed), item.policy))
    return found
