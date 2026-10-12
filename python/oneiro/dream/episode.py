"""One recorded turn, read back from the graph. Read-only.

The graph stores, for a turn: the owner's message, every tool call with the result
the model was given back, the decision, the state and the final reply. It does
**not** store the assembled prompt, its size, or per-step token counts, so this
module reports those as *not recorded* (``Episode.unrecorded``) instead of zeroes
that would read like a measurement.

A turn is addressed by its reply record's ID (``reply-<client_id>``); every `Action`
of that turn is named ``act-<reply record id>-<step>``, which is how the actions are
found. That prefix is used rather than the ``run_id`` field on purpose: a call that
did not run (refused, or waiting on the owner) is stored without a ``run_id``
(measured 2026-10-12), so `agent.turn_steps` — which filters on ``run_id`` — returns
a turn without its refusals. A judge that cannot see a refusal cannot see that
behaviour, so this reader keeps them and says so.

The model-facing text of a step (``Step.observation``) is produced by the live
turn's own rule, `agent.Step.to_message`, so a replay cannot disagree with what the
turn actually said.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from oneiro import agent, recall
from oneiro.records import EffectOutcome, State

TURN_PREFIX = "reply-"
ACTION_PREFIX = "act-"
MESSAGE_PREFIX = "msg-"
MESSAGE_KIND = "conversation_message"
ACTION_KIND = "action"

#: What one stored turn does not carry. Named so a reader can tell "measured as zero"
#: apart from "never recorded": a judge must treat neither as evidence.
UNRECORDED: tuple[str, ...] = (
    "the assembled prompt and its size",
    "per-step token counts",
    "the tool catalogue as it was offered at turn time",
)


class EpisodeError(ValueError):
    """A turn that cannot be read back: missing, or not a recorded turn."""


def turn_parts(turn_id: str) -> tuple[str, str]:
    """The client ID and the owner-message ID a reply ID implies."""
    if not isinstance(turn_id, str) or not turn_id.startswith(TURN_PREFIX) \
            or not turn_id[len(TURN_PREFIX):]:
        raise EpisodeError(f"{turn_id!r} is not a turn ID; a turn is named reply-<client_id>")
    client = turn_id[len(TURN_PREFIX):]
    return client, MESSAGE_PREFIX + client


def action_prefix(turn_id: str) -> str:
    """The ID prefix every Action of this turn carries."""
    return ACTION_PREFIX + turn_id + "-"


def stop_reason(record: dict[str, Any]) -> str:
    """Why the turn ended, from its record's state alone.

    ``stopped`` is the step limit or a failed turn; ``answered`` is a reply in words.
    An unknown state is reported as ``open`` rather than guessed into a terminal one.
    """
    state = str(record.get("state", ""))
    if state == State.UNCERTAIN.value:
        return "uncertain"
    if state == State.WAITING.value:
        return "waiting"
    if state == State.CANCELLED.value:
        return "cancelled"
    if state == State.FAILED.value:
        return "stopped"
    if state == State.COMPLETED.value:
        return "answered"
    return "open"


def _state_of(value: str) -> State | None:
    try:
        return State(value)
    except ValueError:
        return None


def _outcome_of(value: str) -> EffectOutcome:
    try:
        return EffectOutcome(value)
    except ValueError:
        return EffectOutcome.NONE


def _index(row: dict[str, Any], turn_id: str) -> int:
    """The step number: from the ``step:N`` label, else from the action's own name."""
    found = agent.step_index(row.get("labels", ()))
    if found is not None:
        return found
    tail = str(row.get("id", "")).removeprefix(action_prefix(turn_id))
    try:
        return int(tail)
    except ValueError:
        return 0


@dataclass(frozen=True)
class Step:
    """One tool call of a turn, as it was recorded: the call, its result and its outcome."""

    index: int
    tool: str
    arguments: dict[str, Any]
    decision: str
    reason: str
    ok: bool
    result: str          # the tool's own output, or the refusal text
    observation: str     # what the model was told back, by the live turn's own rule
    state: str
    outcome: str
    effect: str
    may_retry: bool
    action_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "tool": self.tool, "arguments": dict(self.arguments),
                "decision": self.decision, "reason": self.reason, "ok": self.ok,
                "result": self.result, "observation": self.observation, "state": self.state,
                "outcome": self.outcome, "effect": self.effect, "may_retry": self.may_retry,
                "action_id": self.action_id}


@dataclass(frozen=True)
class Episode:
    """A recorded turn: what was asked, what was called, what came back, how it ended."""

    turn_id: str
    conversation_id: str
    request: str
    role: str
    reply: str
    steps: tuple[Step, ...]
    tools: tuple[str, ...]
    stop_reason: str
    unrecorded: tuple[str, ...] = UNRECORDED

    @property
    def calls(self) -> int:
        """How many tool calls the turn recorded, refused ones included."""
        return len(self.steps)

    @property
    def refusals(self) -> tuple[Step, ...]:
        """The calls that did not run: refused, or waiting on the owner."""
        return tuple(step for step in self.steps if step.decision != "allow")

    def to_dict(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "conversation_id": self.conversation_id,
                "request": self.request, "role": self.role, "reply": self.reply,
                "steps": [step.to_dict() for step in self.steps], "tools": list(self.tools),
                "stop_reason": self.stop_reason, "unrecorded": list(self.unrecorded)}


def _step(row: dict[str, Any], turn_id: str) -> Step:
    """One Action row as a Step, with the model-facing text rebuilt by the live rule."""
    decision = str(row.get("decision") or "allow")
    reason, result = agent._stored_parts(decision, str(row.get("result", "")))
    effect = row.get("effect") or {}
    kind = str(effect.get("kind", ""))
    outcome = str(effect.get("outcome", EffectOutcome.NONE.value))
    state = str(row.get("state", ""))
    parsed_state = _state_of(state)
    parsed_outcome = _outcome_of(outcome)
    index = _index(row, turn_id)
    ok = decision == "allow" and parsed_state is State.COMPLETED
    view = agent.Step(index=index, tool=str(row.get("tool", "")),
                      arguments=dict(row.get("arguments") or {}), decision=decision,
                      reason=reason, ok=ok, result=result, action_id=str(row.get("id", "")),
                      state=state, effect=kind, outcome=outcome,
                      may_retry=agent.may_retry(kind, parsed_outcome, parsed_state)
                      if parsed_state is not None else False)
    return Step(index=index, tool=view.tool, arguments=view.arguments, decision=decision,
                reason=reason, ok=ok, result=result, observation=view.to_message(),
                state=state, outcome=outcome, effect=kind, may_retry=view.may_retry,
                action_id=view.action_id)


async def _actions(owner: Any, turn_id: str) -> list[dict[str, Any]]:
    prefix = action_prefix(turn_id)
    found = await recall.scan(owner, lambda row: row.get("kind") == ACTION_KIND
                              and str(row.get("id", "")).startswith(prefix))
    return sorted(found.rows, key=lambda row: _index(row, turn_id))


async def read(owner: Any, turn_id: str) -> Episode:
    """Read one recorded turn back. Raises `EpisodeError` when it is not on record.

    The reply must be on record: a turn whose provider failed before answering has no
    reply row, and is reported as unrecorded rather than half-read.
    """
    turn_parts(turn_id)
    reply = await owner.memory_entity(turn_id)
    if reply is None:
        raise EpisodeError(f"no reply is recorded for turn {turn_id}")
    if reply.get("kind") != MESSAGE_KIND:
        raise EpisodeError(f"{turn_id} is a {reply.get('kind')!r}, not a recorded turn")
    _, user_id = turn_parts(turn_id)
    user = await owner.memory_entity(user_id)
    if user is None:
        raise EpisodeError(f"the owner's message {user_id} of turn {turn_id} is not recorded")
    steps = tuple(_step(row, turn_id) for row in await _actions(owner, turn_id))
    return Episode(turn_id=turn_id, conversation_id=str(reply.get("conversation_id", "")),
                   request=str(user.get("text", "")), role=str(reply.get("role", "")),
                   reply=str(reply.get("text", "")), steps=steps,
                   tools=tuple(sorted({step.tool for step in steps})),
                   stop_reason=stop_reason(reply))


async def recent_turns(owner: Any, *, limit: int = 20) -> list[str]:
    """The newest recorded turns' IDs, newest first. Reads; writes nothing."""
    found = await recall.scan(owner, lambda row: row.get("kind") == MESSAGE_KIND
                              and str(row.get("id", "")).startswith(TURN_PREFIX), want=limit)
    return [str(row["id"]) for row in found.rows]
