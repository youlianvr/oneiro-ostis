"""The records every other layer agrees on.

One schema, one owner, one version. Conversation, tasks, runs, actions,
decisions, notes, experience, experiments and releases are all records here, so
the web channel, Telegram and the runtime cannot drift into separate truths about
what was asked, what was decided and what actually happened.

Three decisions are load-bearing, and everything else follows from them.

**Provenance is not decoration.** A sentence the owner typed, a sentence a model
produced, something an observer saw and the result of a tool call are four
different kinds of claim. Mixing them is how an assistant ends up treating its
own guess as a fact, so `Provenance` is carried on every record and is not
optional anywhere.

**A state is explicit, and `uncertain` is a real one.** Work that was interrupted
mid-effect has an unknown outcome. `State.UNCERTAIN` exists so that situation has
a name, because the alternative is reporting success for something that never
happened.

**An uncertain effect is never retried by default.** `Action.may_retry()` is the
single place that decides, and it refuses for uncertain effects. This is the rule
that prevents a restart from sending a second email, spending a second payment or
re-running a non-idempotent command whose first run may have succeeded.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, TypeVar

SCHEMA_VERSION = 1


def new_id() -> str:
    """A random stable identifier; publication sequence defines insertion order."""
    return uuid.uuid4().hex


def now() -> str:
    """An ISO-8601 UTC instant, second-resolution, always with the offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Provenance(str, Enum):
    """Where a claim came from. Determines how much weight it may carry."""

    OWNER_INSTRUCTION = "owner_instruction"
    MODEL_CLAIM = "model_claim"
    OBSERVATION = "observation"
    VERIFIED_TOOL_OUTCOME = "verified_tool_outcome"
    SYSTEM = "system"

    @property
    def is_verified(self) -> bool:
        """Only an observation or a tool outcome is evidence of what happened."""
        return self in (Provenance.OBSERVATION, Provenance.VERIFIED_TOOL_OUTCOME)


class State(str, Enum):
    """Lifecycle states. `UNCERTAIN` means the outcome is genuinely unknown."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    UNCERTAIN = "uncertain"

    @property
    def is_terminal(self) -> bool:
        return self in (State.COMPLETED, State.FAILED, State.CANCELLED)

    @property
    def is_open(self) -> bool:
        """Open work must survive a restart and must not be declared finished."""
        return self in (State.QUEUED, State.RUNNING, State.WAITING, State.UNCERTAIN)


class EffectOutcome(str, Enum):
    """What is known about an action that changes something outside the process."""

    NONE = "none"                    # the action only read
    SUCCEEDED = "succeeded"          # observed to have happened
    FAILED = "failed"                # observed not to have happened
    UNCERTAIN = "uncertain"          # may or may not have happened

    @property
    def permits_blind_retry(self) -> bool:
        """Only an effect known *not* to have happened may simply be tried again."""
        return self is EffectOutcome.FAILED


class RecordError(ValueError):
    """A record that cannot exist: a bad state transition or a missing field."""


@dataclass(frozen=True)
class Record:
    """Fields every record has. Subclasses add meaning, never replace this."""

    KIND: ClassVar[str] = "record"

    id: str = field(default_factory=new_id)
    schema_version: int = SCHEMA_VERSION
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)
    provenance: Provenance = Provenance.SYSTEM
    state: State = State.QUEUED
    labels: tuple[str, ...] = ()

    def with_state(self, state: State, **changes: Any) -> "Record":
        """A new record in a new state. Records are immutable, so history is real."""
        if state is self.state:
            return replace(self, updated_at=now(), **changes)
        if self.state.is_terminal and not changes.get("allow_reopen"):
            raise RecordError(
                f"{self.KIND} {self.id} is {self.state.value}; it cannot become "
                f"{state.value}. Write a new record that references it instead."
            )
        changes.pop("allow_reopen", None)
        return replace(self, state=state, updated_at=now(), **changes)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if isinstance(value, Enum):
                data[key] = value.value
            elif isinstance(value, tuple):
                data[key] = list(value)
            elif hasattr(value, "to_dict"):
                # A nested structure that knows how to describe itself, such as
                # Action.effect, serialises through its own contract.
                data[key] = value.to_dict()
            else:
                data[key] = value
        data["kind"] = self.KIND
        data["labels"] = list(self.labels)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        record = decode(data)
        if not isinstance(record, cls):
            raise RecordError(
                f"expected {cls.KIND}, got {record.KIND}"
            )
        return record


R = TypeVar("R", bound=Record)


@dataclass(frozen=True)
class ConversationMessage(Record):
    """One utterance in a conversation. Owner input or model output, never both."""

    KIND: ClassVar[str] = "conversation_message"

    conversation_id: str = ""
    role: str = ""                    # owner | manager | researcher | executor | system
    text: str = ""
    attachments: tuple[str, ...] = ()  # content addresses, never inline bytes

    def __post_init__(self) -> None:
        if not self.conversation_id:
            raise RecordError("conversation_id is required")
        if not self.role:
            raise RecordError("role is required")
        if not self.text.strip() and not self.attachments:
            raise RecordError("text or attachments are required")


@dataclass(frozen=True)
class Task(Record):
    """Something to be done. Shared truth: both channels read this same record."""

    KIND: ClassVar[str] = "task"

    title: str = ""
    detail: str = ""
    assigned_role: str = ""
    parent_id: str = ""
    blocked_by: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise RecordError("title is required")


@dataclass(frozen=True)
class Run(Record):
    """One attempt at a task. A task may have several runs; only one may win."""

    KIND: ClassVar[str] = "run"

    task_id: str = ""
    role: str = ""
    attempt: int = 1
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.task_id:
            raise RecordError("task_id is required")
        if self.attempt < 1:
            raise RecordError("attempt is 1-based")


@dataclass(frozen=True)
class Effect:
    """A change outside the process, and what is known about it."""

    kind: str = ""                    # what kind of effect, e.g. "file.write"
    target: str = ""                  # where it landed, an address or a path
    outcome: EffectOutcome = EffectOutcome.NONE
    observed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "target": self.target,
                "outcome": self.outcome.value, "observed_at": self.observed_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Effect":
        return cls(kind=str(data.get("kind", "")),
                   target=str(data.get("target", "")),
                   outcome=EffectOutcome(data.get("outcome", "none")),
                   observed_at=str(data.get("observed_at", "")))


@dataclass(frozen=True)
class Action(Record):
    """A tool call. `may_retry` is the whole point of this record."""

    KIND: ClassVar[str] = "action"

    run_id: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    effect: Effect = field(default_factory=Effect)
    result: str = ""
    decision: str = ""                 # allow | deny | ask; empty on older records

    def __post_init__(self) -> None:
        if not self.tool.strip():
            raise RecordError("tool is required")
        if self.decision and self.decision not in ("allow", "deny", "ask"):
            raise RecordError(f"unknown decision {self.decision!r}")

    def may_retry(self) -> bool:
        """Whether this action may simply be run again.

        False whenever the outcome is unknown. An uncertain effect is not
        permission to repeat it: the first attempt may have succeeded, and
        repeating it could send a second message or spend a second payment.
        Such work must be inspected before it is tried again.
        """
        return self.effect.outcome.permits_blind_retry

    def requires_inspection(self) -> bool:
        return self.effect.outcome is EffectOutcome.UNCERTAIN


@dataclass(frozen=True)
class Decision(Record):
    """A choice with its reason. Shared truth: both channels read this."""

    KIND: ClassVar[str] = "decision"

    question: str = ""
    chosen: str = ""
    alternatives: tuple[str, ...] = ()
    rationale: str = ""
    task_id: str = ""

    def __post_init__(self) -> None:
        if not self.question.strip() or not self.chosen.strip():
            raise RecordError("question and chosen are required")


@dataclass(frozen=True)
class Note(Record):
    """A retrieval-worthy finding. Provenance decides whether it may be trusted."""

    KIND: ClassVar[str] = "note"

    topic: str = ""
    body: str = ""
    sources: tuple[str, ...] = ()
    task_id: str = ""

    def __post_init__(self) -> None:
        if not self.topic.strip() or not self.body.strip():
            raise RecordError("topic and body are required")

    @property
    def is_citable(self) -> bool:
        """A model guess is a lead; only a verified claim may back an answer."""
        return self.provenance.is_verified


@dataclass(frozen=True)
class Experience(Record):
    """Something learned from a run, kept for the self-improvement cycle."""

    KIND: ClassVar[str] = "experience"

    summary: str = ""
    lesson: str = ""
    run_id: str = ""
    score: float | None = None
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise RecordError("summary is required")


@dataclass(frozen=True)
class Experiment(Record):
    """A candidate whose outcome is not yet known. Paired repeats are counted."""

    KIND: ClassVar[str] = "experiment"

    name: str = ""
    hypothesis: str = ""
    control: str = ""
    candidate: str = ""
    seeds: tuple[int, ...] = ()
    repeats: int = 0
    min_repeats: int = 3
    frozen_before_run: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.hypothesis.strip():
            raise RecordError("name and hypothesis are required")

    def has_enough_repeats(self) -> bool:
        """Whether the evidence count supports drawing a conclusion at all."""
        return self.repeats >= self.min_repeats

    def with_repeats(self, repeats: int) -> "Experiment":
        """A new experiment with more evidence recorded. Counts only go up."""
        if repeats < self.repeats:
            raise RecordError("repeats cannot be un-counted; record a new experiment")
        return replace(self, repeats=repeats, updated_at=now())

    def may_conclude(self) -> bool:
        """A conclusion needs frozen criteria and enough stochastic repeats."""
        return self.frozen_before_run and self.has_enough_repeats()


@dataclass(frozen=True)
class Release(Record):
    """A versioned release. Rollback must never erase newer owner data."""

    KIND: ClassVar[str] = "release"

    version: str = ""
    artifact: str = ""
    checks: dict[str, bool] = field(default_factory=dict)
    promoted: bool = False
    rolled_back: bool = False

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise RecordError("version is required")

    def checks_passed(self) -> bool:
        return bool(self.checks) and all(self.checks.values())


@dataclass(frozen=True)
class CuratedFact(Record):
    """A short fact the owner chose to keep, in force until it is removed.

    Only the owner writes these. A fact is therefore an owner instruction about
    the world, not an observation: it is stored with that provenance and is never
    presented as verified evidence. Active facts are COMPLETED; removal publishes
    a CANCELLED revision, so the history of the fact stays on record.
    """

    KIND: ClassVar[str] = "curated_fact"

    text: str = ""

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise RecordError("fact text is required")


@dataclass(frozen=True)
class Question(Record):
    """A question the assistant asked the owner, and the answer when it arrives.

    Asking is not blocking: the question is a record, so an unanswered one
    survives a restart and does not hold unrelated work. Until it is answered
    the assistant does not pretend to know the answer, and it never treats its
    own assumption as the owner's reply.
    """

    KIND: ClassVar[str] = "question"

    question: str = ""
    answer: str = ""
    task_id: str = ""
    conversation_id: str = ""

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise RecordError("question text is required")

    @property
    def answered(self) -> bool:
        return bool(self.answer.strip())

    def with_answer(self, answer: str) -> "Question":
        """A new revision carrying the owner's answer. The question is kept."""
        if not answer.strip():
            raise RecordError("an answer must not be empty")
        if self.answered:
            raise RecordError("this question already has an answer")
        return replace(self, answer=answer.strip(), updated_at=now())


@dataclass(frozen=True)
class Approval(Record):
    """The owner's decision about one exact action.

    An approval names the tool and the arguments it authorises. It is not a
    general licence: `covers` compares both, so an approval for one action can
    never release a different one, and a stale approval cannot release a new
    action even if the tool is the same.
    """

    KIND: ClassVar[str] = "approval"

    action_id: str = ""
    tool: str = ""
    arguments_digest: str = ""
    granted: bool = False
    reason: str = ""
    task_id: str = ""
    consumed_action_id: str = ""   # the action this grant has already released

    def __post_init__(self) -> None:
        if not self.action_id.strip() or not self.tool.strip():
            raise RecordError("action_id and tool are required")

    @property
    def available(self) -> bool:
        """Granted by the owner and not yet spent on an action.

        A grant is one-shot: releasing one call consumes it, so a refused or a
        completed grant is never silently reused for a later request.
        """
        return (self.granted and not self.consumed_action_id
                and self.provenance is Provenance.OWNER_INSTRUCTION)

    def covers(self, tool: str, arguments_digest: str) -> bool:
        """Whether this approval authorises exactly this call, and nothing else."""
        return self.available and self.tool == tool and self.arguments_digest == arguments_digest

    def consumed_by(self, action_id: str) -> "Approval":
        """The revision marking this grant as spent on one action."""
        if not action_id.strip():
            raise RecordError("action_id is required")
        if self.consumed_action_id:
            raise RecordError("this approval has already been consumed")
        return replace(self, consumed_action_id=action_id, updated_at=now())


@dataclass(frozen=True)
class Schedule(Record):
    """One standing instruction: run this task on this cron expression.

    The schedule is a record, not a line in a settings file, because the graph is
    the memory: it survives a restart, the owner can see what is on a schedule,
    and `last_fired_at` is what stops a process that starts again from firing the
    minute it already fired.
    """

    KIND: ClassVar[str] = "schedule"

    cron: str = ""
    task_title: str = ""
    task_detail: str = ""
    role: str = "executor"
    enabled: bool = True
    last_fired_at: str = ""
    last_task_id: str = ""

    def __post_init__(self) -> None:
        if not self.cron.strip() or not self.task_title.strip():
            raise RecordError("cron and task_title are required")


_KINDS: dict[str, type[Record]] = {
    cls.KIND: cls for cls in (
        Record, ConversationMessage, Task, Run, Action, Decision, Note,
        Experience, Experiment, Release, CuratedFact, Question, Approval,
        Schedule,
    )
}

#: Fields every persisted record must carry, whatever its kind.
REQUIRED = ("id", "kind", "schema_version", "created_at", "provenance", "state")


def decode(data: dict[str, Any]) -> Record:
    """Rebuild a record from its dictionary, refusing anything malformed.

    This is the only way into the schema, so a truncated file or a hand-edited
    store fails here rather than becoming a record with missing meaning.
    """
    if not isinstance(data, dict):
        raise RecordError(f"a record must be an object, got {type(data).__name__}")
    missing = [field_name for field_name in REQUIRED if field_name not in data]
    if missing:
        raise RecordError(f"record is missing {', '.join(missing)}")
    kind = data["kind"]
    if kind not in _KINDS:
        raise RecordError(f"unknown record kind {kind!r}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise RecordError(
            f"{kind} {data['id']} has schema version {data['schema_version']}; "
            f"this build reads version {SCHEMA_VERSION}"
        )
    cls = _KINDS[kind]
    fields = {f for f in cls.__dataclass_fields__ if f not in ("KIND",)}
    payload = {k: v for k, v in data.items() if k in fields}
    for name in ("provenance", "state"):
        try:
            payload[name] = Provenance(data[name]) if name == "provenance" else State(data[name])
        except ValueError as exc:
            raise RecordError(f"{kind} {data['id']}: {exc}") from None
    payload["labels"] = tuple(payload.get("labels", ()))
    if issubclass(cls, Action) and isinstance(payload.get("effect"), dict):
        payload["effect"] = Effect.from_dict(payload["effect"])
    if issubclass(cls, ConversationMessage):
        payload["attachments"] = tuple(payload.get("attachments", ()))
    if issubclass(cls, Task):
        payload["blocked_by"] = tuple(payload.get("blocked_by", ()))
    if issubclass(cls, Decision):
        payload["alternatives"] = tuple(payload.get("alternatives", ()))
    if issubclass(cls, Note):
        payload["sources"] = tuple(payload.get("sources", ()))
    if issubclass(cls, Experiment):
        payload["seeds"] = tuple(payload.get("seeds", ()))
    try:
        return cls(**payload)
    except TypeError as exc:
        raise RecordError(f"{kind} {data['id']}: {exc}") from None


def decode_many(text: str) -> list[Record]:
    """Every record in a JSON-lines store, in file order."""
    records = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(decode(json.loads(line)))
        except (ValueError, RecordError) as exc:
            raise RecordError(f"line {number}: {exc}") from None
    return records