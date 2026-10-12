"""The candidate: what one turn shows the model, and how long it may run.

This is the search space of the self-improvement core. A candidate is a program
over the knobs the agent turn actually reads, so it can be rewritten, judged from
records and deployed. `from_descriptor` refuses any field outside this list, which
is what keeps a search inside the layer it claims to change instead of leaking into
the turn's behaviour.

Each knob names the thing the live turn reads:

* ``history_messages`` — ``chat.history_messages``, how many earlier messages the
  reply context may carry;
* ``context_chars`` — ``chat.context_chars``, the character budget for those;
* ``max_turns`` — ``agent.max_turns``, the tool steps one turn may take;
* ``include_facts`` — whether the owner's curated facts are shown at all;
* ``observation_chars`` — how much of one tool result is shown back to the model,
  the live turn's ``MAX_RESULT``.

``name`` is a label, not a knob: two candidates that differ only in name are the
same program, so ``changed_fields`` never reports it. That is also why the gate can
call a rename free and a knob change an edit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

#: Every field a descriptor may carry, in the order one is printed.
FIELDS: tuple[str, ...] = (
    "name", "history_messages", "context_chars", "max_turns", "include_facts",
    "observation_chars",
)
#: The knobs, without the label. A verdict belongs to a change of these.
KNOBS: tuple[str, ...] = tuple(field for field in FIELDS if field != "name")

#: The shipped defaults, so ``TurnPolicy()`` is the policy the settings declare.
HISTORY_MESSAGES = 10
CONTEXT_CHARS = 6000
MAX_TURNS = 12
OBSERVATION_CHARS = 4000        # the live turn's MAX_RESULT


class PolicyError(ValueError):
    """A descriptor that cannot be a candidate: an unknown field or a bad value."""


@dataclass(frozen=True)
class TurnPolicy:
    """One candidate program. Immutable, so a judged candidate cannot shift under itself."""

    name: str = "recorded"
    history_messages: int = HISTORY_MESSAGES
    context_chars: int = CONTEXT_CHARS
    max_turns: int = MAX_TURNS
    include_facts: bool = True
    observation_chars: int = OBSERVATION_CHARS

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        """Refuse anything that is not a usable candidate, naming the field.

        A non-negative integer is required for every count; ``bool`` is not accepted
        where an integer is meant, because ``True`` would otherwise read as ``1`` and
        a window of one message would be a silent typo.
        """
        if not isinstance(self.name, str) or not self.name.strip():
            raise PolicyError("a candidate needs a non-empty name")
        for field in KNOBS:
            if field == "include_facts":
                continue
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise PolicyError(f"{field} must be a non-negative integer, got {value!r}")
        if not isinstance(self.include_facts, bool):
            raise PolicyError(f"include_facts must be true or false, got {self.include_facts!r}")

    def descriptor(self) -> dict[str, Any]:
        """The candidate as plain data: the form the graph stores and the judge reads."""
        return {field: getattr(self, field) for field in FIELDS}

    def to_json(self) -> str:
        return json.dumps(self.descriptor(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_descriptor(cls, data: dict[str, Any]) -> "TurnPolicy":
        """A candidate from stored data, refusing anything it does not recognise.

        A field the descriptor omits keeps its default, so a candidate may name only
        what it changes; a field it does not recognise is refused by name rather than
        dropped, because dropping it would run a different program than the one that
        was described.
        """
        if not isinstance(data, dict):
            raise PolicyError(f"a candidate descriptor must be an object, got {type(data).__name__}")
        unknown = sorted(set(data) - set(FIELDS))
        if unknown:
            raise PolicyError(
                f"unknown candidate fields: {', '.join(unknown)}; a candidate may only "
                f"change {', '.join(KNOBS)}")
        return cls(**{field: data[field] for field in FIELDS if field in data})

    def changed_fields(self, other: "TurnPolicy") -> tuple[str, ...]:
        """The knobs where this candidate differs from another, in field order."""
        return tuple(field for field in KNOBS if getattr(self, field) != getattr(other, field))


#: The policy the settings declare. It is the floor every candidate is measured against.
BASE = TurnPolicy()

#: Hand-written reference candidates. A judge's own proposals come later; these exist
#: so every round has a floor and an ablation to be read against, instead of a single
#: number that cannot be read at all.
VARIANTS: dict[str, TurnPolicy] = {
    "recorded": BASE,
    "blind": replace(BASE, name="blind", include_facts=False),
    "windowed": replace(BASE, name="windowed", history_messages=4),
    "no_history": replace(BASE, name="no_history", history_messages=0, context_chars=0),
    "tight_context": replace(BASE, name="tight_context", context_chars=2000),
    "long_turn": replace(BASE, name="long_turn", max_turns=20),
    "terse_observations": replace(BASE, name="terse_observations", observation_chars=800),
}


def get_policy(name: str) -> TurnPolicy:
    """One hand-written candidate by name, refused by name when it is not known."""
    if name not in VARIANTS:
        raise PolicyError(f"unknown candidate {name!r}; known: {sorted(VARIANTS)}")
    return VARIANTS[name]
