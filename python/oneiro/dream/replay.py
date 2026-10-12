"""The judge: rebuild what a candidate would have shown, from records alone.

A candidate changes what one turn shows the model. To judge it without spending a
token, this module rebuilds, from a recorded `Episode` alone, the messages each
candidate would have sent at every step, and compares that against the messages the
recorded policy would have sent. Where the two are equal the recorded decision still
stands, so the step is *covered*; where they differ the model's decision at that step
is unknown, and the episode is **truncated there** rather than extrapolated. The
number this module returns is that ratio: covered steps over the steps the turn
recorded.

Three rules are load-bearing.

**Nothing here runs.** The world — a model call, a tool executing — is never imported
by this module, and a test replaces it with functions obliged to raise, so a hidden
execution fails loudly instead of quietly turning an estimate into a measurement.

**The recording is the floor, and its gaps are named.** The graph does not store the
sent prompt, its size, per-step tokens, the model's own tool-call IDs, the assistant's
text before a call, or the tool catalogue as it was offered; the history and facts
blocks are read *now* and may differ from what was actually sent. `NOT_RECORDED` names
all of it, and every report carries that list, so no number here reads as measured.

**A step is covered only when the two contexts are identical.** The history and facts
blocks are the same object in both reconstructions, so whatever they are, they cancel;
what a candidate changes is what the judge can see.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from oneiro import agent, config, recall
from oneiro.dream import episode as recorded
from oneiro.dream.policy import BASE, TurnPolicy

#: What no stored turn carries. Every report repeats it, because a number read as
#: "measured" when it is estimated is the one failure this whole package exists to avoid.
NOT_RECORDED: tuple[str, ...] = (
    "the assembled prompt and its size",
    "per-step token counts",
    "the history and facts blocks as they were sent (read now, not then)",
    "the model's own tool-call IDs (rebuilt from the step number)",
    "the assistant's text before a tool call",
    "the tool catalogue as it was offered",
)
#: The sentence `recall.reply_context` puts before the owner's facts. Kept here so a
#: candidate that drops the facts block is compared against the real one, and guarded
#: by a test that asserts the two are identical rather than hoping so.
FACTS_PREAMBLE = ("Facts the owner stated and asked you to keep in mind. They are the "
                  "owner's own statements, not verified observations:")


def facts_block(texts: tuple[str, ...]) -> str:
    """The system message that carries the owner's curated facts, text for text."""
    return FACTS_PREAMBLE + "\n" + "\n".join(f"- {text}" for text in texts)


@dataclass(frozen=True)
class Context:
    """The parts of a sent prompt the recording does not carry, read from the graph now.

    ``derived`` is True whenever the blocks were read after the turn rather than
    stored with it, so a report can say the reconstruction rests on them.
    """

    facts: tuple[str, ...] = ()
    history: tuple[dict[str, Any], ...] = ()
    derived: bool = False


def call_id(step: recorded.Step) -> str:
    """A stable ID for one tool call. The model's own ID is not recorded."""
    return f"step-{step.index}"


def _clip(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit] + f"\n... [{len(text) - limit} characters truncated]"
    return text


def observation_for(step: recorded.Step, limit: int) -> str:
    """What the model would be told back for this call under an observation limit.

    The limit is applied to the tool's result and the sentence rebuilt by the live
    turn's own rule, because that is where the live turn applies its own bound: the
    stored observation is already what `agent.MAX_RESULT` produced, so the recorded
    policy reproduces it exactly rather than clipping it a second time.
    """
    if not limit or len(step.result) <= limit:
        return step.observation
    view = agent.Step(index=step.index, tool=step.tool, arguments=step.arguments,
                      decision=step.decision, reason=step.reason, ok=step.ok,
                      result=_clip(step.result, limit), action_id=step.action_id,
                      state=step.state, effect=step.effect, outcome=step.outcome,
                      may_retry=step.may_retry)
    return view.to_message()


def _assistant_message(step: recorded.Step) -> dict[str, Any]:
    """The assistant turn that requested one call, in the shape the live loop sends."""
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": call_id(step), "type": "function",
                            "function": {"name": step.tool,
                                         "arguments": json.dumps(step.arguments,
                                                                 ensure_ascii=False)}}]}


def _windowed(history: tuple[dict[str, Any], ...], policy: TurnPolicy) -> list[dict[str, Any]]:
    """The history a policy would show: newest first within a budget, then in order.

    This is the assembly the candidate owns, so it is implemented here rather than
    taken from the live path; the rule is the one `recall.reply_context` uses, which
    is what makes a candidate that changes neither knob reproduce the recording.
    """
    if policy.history_messages <= 0:
        return []
    rows = list(history[-policy.history_messages:])
    kept: list[dict[str, Any]] = []
    used = 0
    for row in reversed(rows):
        content = str(row.get("content", ""))
        if used + len(content) > policy.context_chars:
            break
        used += len(content)
        kept.append(row)
    return list(reversed(kept))


def assemble(episode: recorded.Episode, policy: TurnPolicy, index: int,
             context: Context | None = None) -> list[dict[str, Any]]:
    """The messages `policy` would send when asking for step `index` (1-based).

    The recorded rows supply the request, every earlier call and every observation;
    the system prompt is this build's own constant; the facts and history blocks come
    from `context`. Nothing else is consulted, and nothing is executed.
    """
    if index < 1:
        raise ValueError("a step number is 1-based")
    context = context or Context()
    messages: list[dict[str, Any]] = [{"role": "system", "content": agent.SYSTEM_PROMPT}]
    if policy.include_facts and context.facts:
        messages.append({"role": "system", "content": facts_block(context.facts)})
    messages.extend(_windowed(context.history, policy))
    messages.append({"role": "user", "content": episode.request})
    for step in episode.steps[: index - 1]:
        messages.append(_assistant_message(step))
        messages.append({"role": "tool", "tool_call_id": call_id(step),
                         "content": observation_for(step, policy.observation_chars)})
    return messages


def composed_chars(messages: list[dict[str, Any]]) -> int:
    """Characters of text in an assembled context, its tool declarations excluded."""
    return sum(len(str(message.get("content") or "")) for message in messages)


def judged_steps(episode: recorded.Episode) -> int:
    """How many times the model was asked during this turn.

    A turn with N recorded calls that ended by answering was asked N+1 times: the last
    question produced the answer, and it is a decision like any other, so a candidate
    that changes the opening context is judged even on a turn that called no tool.
    A turn that ran out of steps was never asked again, so it has exactly N.
    """
    return len(episode.steps) + (1 if episode.stop_reason == "answered" else 0)


@dataclass(frozen=True)
class Estimate:
    """What replay can say about one candidate on one recorded turn."""

    turn_id: str
    policy: str
    steps_total: int
    steps_covered: int
    truncated_at: int | None
    chars_shown: int
    clipped_observations: int
    notes: tuple[str, ...] = ()

    @property
    def coverage(self) -> float:
        """Exact steps over recorded steps. A turn with no steps has nothing to truncate."""
        if self.steps_total == 0:
            return 1.0
        return self.steps_covered / self.steps_total

    @property
    def truncated(self) -> bool:
        return self.truncated_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "policy": self.policy, "steps_total": self.steps_total,
                "steps_covered": self.steps_covered, "coverage": round(self.coverage, 4),
                "truncated_at": self.truncated_at, "chars_shown": self.chars_shown,
                "clipped_observations": self.clipped_observations, "notes": list(self.notes)}


def estimate(episode: recorded.Episode, policy: TurnPolicy, context: Context | None = None, *,
             recorded_policy: TurnPolicy = BASE) -> Estimate:
    """Judge one candidate against one recorded turn, truncating at the first divergence.

    Steps are walked in order. The first step whose rebuilt context differs from the
    recorded policy's is where the recording stops being evidence: the walk stops
    there, and the steps after it are not counted at all, because on a different
    context the model would not have taken the recorded path.
    """
    total = judged_steps(episode)
    covered = 0
    truncated: int | None = None
    chars = 0
    for position in range(1, total + 1):
        candidate = assemble(episode, policy, position, context)
        if candidate != assemble(episode, recorded_policy, position, context):
            truncated = position
            break
        covered += 1
        chars += composed_chars(candidate)
    # Clipping is a property of the candidate over the whole turn, not of the walk, so
    # it counts every recorded call even the ones past the truncation point.
    clipped = sum(1 for step in episode.steps
                  if observation_for(step, policy.observation_chars) != step.observation)

    notes: list[str] = []
    if truncated is not None:
        notes.append(f"step {truncated} of {total} diverges from the recording, "
                     f"so the model's decision there is not replayable and nothing after it "
                     f"is counted")
    elif policy.changed_fields(recorded_policy) == ("max_turns",):
        notes.append("the context is unchanged at every recorded step; what replay cannot "
                     "see is when this limit would stop the turn")
    if context is not None and context.derived:
        notes.append("the history and facts blocks were read now, not as they were sent")
    if clipped:
        notes.append(f"{clipped} observation(s) would be clipped by this limit")
    return Estimate(turn_id=episode.turn_id, policy=policy.name,
                    steps_total=total, steps_covered=covered,
                    truncated_at=truncated, chars_shown=chars,
                    clipped_observations=clipped, notes=tuple(notes))


def judge(episodes: list[recorded.Episode], policies: list[TurnPolicy],
          contexts: dict[str, Context] | None = None, *,
          recorded_policy: TurnPolicy = BASE) -> dict[str, list[Estimate]]:
    """Every candidate against every recorded turn, keyed by candidate name."""
    contexts = contexts or {}
    return {policy.name: [estimate(turn, policy, contexts.get(turn.turn_id),
                                   recorded_policy=recorded_policy)
                          for turn in episodes]
            for policy in policies}


def _rows_match(episode: recorded.Episode, messages: list[dict[str, Any]],
                position: int) -> bool:
    """Whether the recorded parts of a rebuilt context still equal the stored rows.

    Only the messages **after the request** are this turn's own record: the history block
    above it carries assistant messages of its own, and counting those as this turn's
    calls made every turn with a prelude fail its own round trip (measured 2026-10-12:
    `rows_match=False` on all seven turns of both live measurements, whose conversations
    are seeded with three earlier exchanges).
    """
    start: int | None = None
    for index, message in enumerate(messages):
        if message["role"] == "user" and message.get("content") == episode.request:
            start = index
    if start is None:
        return False
    own = messages[start + 1:]
    preceding = episode.steps[: position - 1]
    if len(own) != 2 * len(preceding):
        return False
    for offset, stored in enumerate(preceding):
        assistant, tool = own[2 * offset], own[2 * offset + 1]
        if assistant["role"] != "assistant" or tool["role"] != "tool":
            return False
        call = assistant["tool_calls"][0]["function"]
        if (tool["content"] != stored.observation or call["name"] != stored.tool
                or json.loads(call["arguments"]) != stored.arguments):
            return False
    return True


@dataclass(frozen=True)
class Reconstruction:
    """The round-trip proof: the recorded policy rebuilds the turn that actually ran."""

    turn_id: str
    steps: int
    rows_match: bool
    first_mismatch: int | None
    coverage: float
    not_recorded: tuple[str, ...] = NOT_RECORDED

    def to_dict(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "steps": self.steps, "rows_match": self.rows_match,
                "first_mismatch": self.first_mismatch, "coverage": round(self.coverage, 4),
                "not_recorded": list(self.not_recorded)}


def verify_reconstruction(episode: recorded.Episode, context: Context | None = None, *,
                          policy: TurnPolicy = BASE) -> Reconstruction:
    """Prove the rebuild against the turn that ran, then report what it still cannot prove.

    Every rebuilt step must carry the recorded request, the recorded calls and the
    recorded observations byte for byte, and the recorded policy must cover every step.
    A failure here means the judge's model of the turn is wrong and every estimate below
    it is void, which is why this is a gate rather than a diagnostic.
    """
    mismatches = [position for position, _ in enumerate(episode.steps, start=1)
                  if not _rows_match(episode, assemble(episode, policy, position, context),
                                     position)]
    return Reconstruction(turn_id=episode.turn_id, steps=len(episode.steps),
                          rows_match=not mismatches,
                          first_mismatch=mismatches[0] if mismatches else None,
                          coverage=estimate(episode, policy, context).coverage)


async def read_context(owner: Any, episode: recorded.Episode, *,
                       recorded_policy: TurnPolicy = BASE) -> Context:
    """Read the facts and pre-turn history from the graph. Read-only, and clearly derived.

    History is limited to the messages that existed **before** the turn, so a turn is
    not shown its own answer. The blocks are still read now rather than as they were
    sent, which is why the result is marked derived and every report says so.
    """
    _, user_id = recorded.turn_parts(episode.turn_id)
    user = await owner.memory_entity(user_id)
    stamp = str((user or {}).get("created_at", ""))
    skipped = {user_id, episode.turn_id}
    found = await recall.scan(owner, lambda row: row.get("kind") == recorded.MESSAGE_KIND
                              and row.get("conversation_id") == episode.conversation_id
                              and str(row.get("id", "")) not in skipped
                              and str(row.get("created_at", "")) <= stamp)
    history = tuple({"role": "user" if row.get("role") == "owner" else "assistant",
                     "content": str(row.get("text", ""))}
                    for row in reversed(found.rows))
    try:
        facts = await recall.current_facts(owner)
    except Exception:                     # an unreadable fact set is not a reason to guess
        texts: tuple[str, ...] = ()
    else:
        texts = tuple(str(fact["text"]) for fact in facts.facts)
    return Context(facts=texts, history=history, derived=True)


def history_limit(policy: TurnPolicy = BASE) -> tuple[int, int]:
    """The window the settings declare: `(messages, characters)` for the recorded policy."""
    return policy.history_messages, policy.context_chars


def current_policy() -> TurnPolicy:
    """The recorded policy as the settings declare it now, falling back to `BASE`."""
    try:
        return TurnPolicy(name="recorded",
                          history_messages=int(config.value("chat.history_messages")),
                          context_chars=int(config.value("chat.context_chars")),
                          max_turns=int(config.value("agent.max_turns")),
                          observation_chars=agent.MAX_RESULT)
    except (ValueError, TypeError, KeyError):
        return BASE
