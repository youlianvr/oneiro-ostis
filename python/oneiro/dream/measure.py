"""The live leg: each task run at least three times under a candidate, spread shown.

Nothing here is estimated. A measurement is made of real turns through
`models.registry()` — the provider list the settings declare, and the model a role
resolves to after a real capability probe. No model name is written into this file,
so a measurement cannot be tied to whichever model happened to answer today.

Four rules, each of which exists because of a measurement that went wrong before:

* **Three repeats per task.** One run is not a measurement: the recorded noise floor
  of this machinery is tens of percent, so a single sample lands on either side of a
  threshold by accident. `run_report` shows the spread, not just the mean, so a number
  that is mostly spread can be seen as such.
* **A knob the live turn cannot apply is refused by name.** The turn reads
  `chat.history_messages`, `chat.context_chars` and `agent.max_turns` from the
  settings; there is no switch yet for the facts block or a tool-observation limit. A
  candidate that changes those is refused rather than measured as though it had been
  applied — a measurement of a policy that was never in force is worse than no number.
* **The demo is its own subject.** Records go to a stream of its own and settings and
  leases live under a root of its own, seeded from the owner's configuration with every
  secret left where it belongs, so a measurement cannot touch the owner's records, the
  owner's settings file, or the work the lead agent is doing.
* **A measurement that was cut short is resumed, not bought again.** The payload written
  by `--save` holds every run already observed; `reuse=` keeps the ones that came back,
  re-reads each verdict from that run's own record (the rule a run is scored by may have
  changed since it ran), and runs only the repeats that failed. Measured 2026-10-12: a
  product defect killed four of eighteen runs, and a repeat that already produced a
  number must not be paid for twice to replace the four that did not. A resume that
  cannot read what it holds stops and says so, instead of treating its own unreadable
  evidence as missing and buying it again — measured 2026-10-12: that mistake dropped
  fourteen recorded runs and bought nine of them a second time, three of which then died.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from oneiro import agent, config, models, settings_registry
from oneiro.dream import episode
from oneiro.dream.policy import BASE, TurnPolicy
from oneiro.graph_worker import GraphWorker
from oneiro.query import GraphQueryError
from oneiro.records import ConversationMessage, Provenance, State

#: The stream the demo's own records live in. Named explicitly and never the stream
#: the owner's work is in, so a measurement cannot be mistaken for a real run.
DEMO_STREAM = "dream"
DEFAULT_REPEATS = 3
#: How long one graph call of the demo's own may take. The product's lane default is ten
#: seconds, which is right for a page view and too tight here: a measurement runs beside
#: everything else the owner is doing, and on 2026-10-12 a single busy moment killed a
#: whole measurement (measured: `graph_timeout` raised while seeding a repeat's history,
#: which aborted every task behind it). The deadline is the demo's own, the product's
#: numbers are untouched.
LANE_TIMEOUT = 30.0
#: How many earlier messages a measured turn is given, so a window candidate has
#: something to window. Written as records, so no model call is spent on the prelude.
PRELUDE: tuple[tuple[str, str], ...] = (
    ("owner", "what should we do about the release checklist?"),
    ("manager", "I would keep the checklist in the repository and read it at the start."),
    ("owner", "and the notes from last week?"),
    ("manager", "They are in NOTES.md, which is where I would look first."),
    ("owner", "good, keep everything small."),
    ("manager", "Understood: small files, read on demand."),
)

#: The knobs the live turn reads from the settings, and the setting each names.
SETTING_OF: dict[str, str] = {
    "history_messages": "chat.history_messages",
    "context_chars": "chat.context_chars",
    "max_turns": "agent.max_turns",
}
APPLICABLE: tuple[str, ...] = tuple(SETTING_OF)


class MeasureError(RuntimeError):
    """A measurement that cannot be made honestly: an unappliable knob, no tasks."""


@dataclass(frozen=True)
class Task:
    """One small task: a request, the files it needs, and what a correct answer holds.

    `request` may name the fake workspace as ``{workspace}``; it is filled with the
    absolute path the fixtures were written to. A read is **not** rooted at the working
    folder — only a write is, and `tools.readable` resolves a relative path against the
    process working directory — so a fixture the model has to find is named absolutely.
    Measured 2026-10-12: a request saying "Read NOTES.md" had the model read the project
    checkout instead, and the turn was recorded as a failure to find a file that was in
    fact written. The task must not depend on the process working directory.

    `answers` is what an answer may say and still be right. It is a deliberately coarse
    check — the answer counts as solved when any of these appears in the reply — and it is
    plural because one measured run answered "keep **things** small" for a note that says
    "keep it small": a correct answer, scored wrong by a single expected string.
    """

    name: str
    request: str
    files: dict[str, str]
    answers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.request.strip() or not self.answers:
            raise MeasureError("a task needs a name, a request and the answers it accepts")
        if not all(str(answer).strip() for answer in self.answers):
            raise MeasureError(f"task {self.name!r} has an empty accepted answer")
        if not self.files:
            raise MeasureError(f"task {self.name!r} has no files to work from")

    def request_for(self, workspace: Path) -> str:
        """The request with every ``{workspace}`` replaced by this run's absolute path."""
        return self.request.replace("{workspace}", Path(workspace).as_posix())

    def solved_by(self, reply: str) -> bool:
        """Whether a reply is one of the answers this task accepts."""
        text = reply.casefold()
        return any(answer.casefold() in text for answer in self.answers)


#: The answers accepted for each task, named here rather than inline so the rule a
#: measurement is scored by is visible in one place.
ANSWERS: dict[str, tuple[str, ...]] = {
    "note-summary": ("keep it small", "keep things small"),
    "count-lines": ("7",),
    "find-file": ("beta.txt",),
}


TASKS: tuple[Task, ...] = (
    Task(name="note-summary",
         request=("Read {workspace}/NOTES.md with your read_file tool and answer in one "
                  "short sentence what it says."),
         files={"NOTES.md": "the plan is to keep it small\n"},
         answers=ANSWERS["note-summary"]),
    Task(name="count-lines",
         request=("How many lines does {workspace}/LINES.txt have? Read it with your "
                  "read_file tool and answer with the number only."),
         files={"LINES.txt": "".join(f"line {number}\n" for number in range(1, 8))},
         answers=ANSWERS["count-lines"]),
    Task(name="find-file",
         request=("Which file in {workspace} contains the word zebra? Use your list_files "
                  "and read_file tools and answer with the file name only."),
         files={"alpha.txt": "nothing to see here\n", "beta.txt": "a zebra lives here\n",
                "gamma.txt": "still nothing\n"},
         answers=ANSWERS["find-file"]),
)


class DemoOwner:
    """The product's own graph worker, on a stream of the demo's own.

    `agent.run_turn` needs somewhere to record what happened; this is that place, and
    it is the same worker the rest of the product writes through, not a second store.
    """

    def __init__(self, worker: GraphWorker) -> None:
        self._worker = worker

    @property
    def stream(self) -> str:
        return self._worker.stream

    @property
    def timeout(self) -> float:
        """The graph deadline this subject's lane was opened with."""
        return self._worker.timeout

    async def publish(self, record: dict[str, Any], operation_id: str, *,
                      expected_revision: int = 0) -> dict[str, Any]:
        return await self._worker.call("append", record=record, operation_id=operation_id,
                                       expected_revision=expected_revision)

    async def memory_entity(self, record_id: str) -> dict[str, Any] | None:
        return await self._worker.call("entity", record_id=record_id)

    async def memory_page(self, *, cursor: str | None = None,
                          limit: int | None = None) -> dict[str, Any]:
        return await self._worker.call("page", cursor=cursor, limit=limit)

    async def close(self) -> None:
        await self._worker.close()


def owner_for(data_root: Path, *, stream: str = DEMO_STREAM,
              timeout: float = LANE_TIMEOUT) -> DemoOwner:
    """A demo subject over the graph the settings declare, writing to its own stream."""
    host = str(config.value("graph.host"))
    port = int(config.value("graph.port"))
    worker = GraphWorker(f"ws://{host}:{port}/ws_json", stream,
                         Path(data_root) / "graph-writer.lock", timeout=timeout)
    return DemoOwner(worker)


def unappliable(policy: TurnPolicy, recorded: TurnPolicy = BASE) -> tuple[str, ...]:
    """The knobs this candidate changed that the live turn cannot be told to read."""
    return tuple(knob for knob in policy.changed_fields(recorded) if knob not in SETTING_OF)


def apply_policy(policy: TurnPolicy, recorded: TurnPolicy = BASE) -> dict[str, Any]:
    """Put the candidate's knobs into the settings the turn reads. Refuses the rest."""
    blocked = unappliable(policy, recorded)
    if blocked:
        raise MeasureError(
            f"the live turn cannot be told to change {', '.join(blocked)} yet; it reads "
            f"{', '.join(APPLICABLE)} from the settings, so this candidate cannot be "
            f"measured honestly")
    patch = {SETTING_OF[knob]: getattr(policy, knob)
             for knob in policy.changed_fields(recorded)}
    return config.save(patch) if patch else {}




@dataclass(frozen=True)
class Run:
    """One real turn: what it cost, what it did, and whether that answered the task.

    ``session`` names the measurement this turn was recorded in. A resumed measurement
    mixes two of them, and every number has to be able to say which one it came from.
    """

    repeat: int
    tokens_in: int
    tokens_out: int
    calls: int
    steps: int
    seconds: float
    solved: bool
    served: tuple[str, ...]
    error: str = ""
    session: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"repeat": self.repeat, "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out, "calls": self.calls, "steps": self.steps,
                "seconds": round(self.seconds, 3), "solved": self.solved,
                "served": list(self.served), "error": self.error, "session": self.session}

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "Run":
        """One run read back from a stored payload, so a measurement can be resumed."""
        return cls(repeat=int(row["repeat"]), tokens_in=int(row["tokens_in"]),
                   tokens_out=int(row["tokens_out"]), calls=int(row["calls"]),
                   steps=int(row["steps"]), seconds=float(row["seconds"]),
                   solved=bool(row["solved"]),
                   served=tuple(str(item) for item in row.get("served", ())),
                   error=str(row.get("error", "")), session=str(row.get("session", "")))


@dataclass(frozen=True)
class TaskResult:
    """Every repeat of one task under one candidate."""

    task: str
    policy: str
    runs: tuple[Run, ...]

    @property
    def measured(self) -> tuple[Run, ...]:
        """The repeats that came back. A refused call is not a measurement of a cost."""
        return tuple(run for run in self.runs if not run.error)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(run.error for run in self.runs if run.error)

    @property
    def mean_tokens_in(self) -> float:
        measured = self.measured
        return sum(run.tokens_in for run in measured) / len(measured) if measured else 0.0

    @property
    def spread(self) -> float | None:
        """(max − min) / mean over the repeats, or None when it cannot be told apart.

        A side measured once has no spread to estimate, so it is reported as unknown
        rather than as zero.
        """
        measured = self.measured
        if len(measured) < 2 or self.mean_tokens_in <= 0:
            return None
        values = [run.tokens_in for run in measured]
        return (max(values) - min(values)) / self.mean_tokens_in

    @property
    def solved(self) -> int:
        return sum(1 for run in self.measured if run.solved)

    def to_dict(self) -> dict[str, Any]:
        return {"task": self.task, "policy": self.policy,
                "runs": [run.to_dict() for run in self.runs],
                "repeats": len(self.runs), "measured": len(self.measured),
                "mean_tokens_in": round(self.mean_tokens_in, 1),
                "spread": None if self.spread is None else round(self.spread, 3),
                "solved": self.solved, "errors": list(self.errors)}

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "TaskResult":
        """One task's runs read back from a stored payload."""
        try:
            runs = tuple(Run.from_dict(item) for item in row["runs"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MeasureError(f"a stored run is not readable: {exc!r}") from None
        return cls(task=str(row["task"]), policy=str(row.get("policy", "")), runs=runs)


def missing_repeats(result: TaskResult, repeats: int = DEFAULT_REPEATS) -> tuple[int, ...]:
    """The repeat numbers this task still owes: nothing recorded, or recorded as an error.

    A run that came back with an error has no cost to compare and no verdict to keep, so
    the repeat is owed again. That is what a resumed measurement runs, and nothing else.
    """
    answered = {run.repeat for run in result.runs if not run.error}
    return tuple(number for number in range(1, repeats + 1) if number not in answered)


@dataclass(frozen=True)
class Measurement:
    """One candidate, every task, every repeat, with the ledger that paid for it."""

    policy: str
    repeats: int
    tasks: tuple[TaskResult, ...]
    session: str = ""
    notes: tuple[str, ...] = ()

    @property
    def mean_tokens_in(self) -> float:
        measured = [task for task in self.tasks if task.measured]
        return (sum(task.mean_tokens_in for task in measured) / len(measured)
                if measured else 0.0)

    @property
    def worst_spread(self) -> float | None:
        spreads = [task.spread for task in self.tasks if task.spread is not None]
        return max(spreads) if spreads else None

    @property
    def solved(self) -> int:
        return sum(task.solved for task in self.tasks)

    @property
    def runs(self) -> int:
        return sum(len(task.runs) for task in self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "repeats": self.repeats, "session": self.session,
                "tasks": [task.to_dict() for task in self.tasks],
                "mean_tokens_in": round(self.mean_tokens_in, 1),
                "worst_spread": None if self.worst_spread is None else round(self.worst_spread, 3),
                "solved": self.solved, "runs": self.runs, "notes": list(self.notes)}

    def task_result(self, name: str) -> TaskResult | None:
        """One task's runs, or None when this measurement does not hold that task."""
        for result in self.tasks:
            if result.task == name:
                return result
        return None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Measurement":
        """A measurement read back from a stored payload, so its runs can be resumed.

        What it holds is what it was given: the cost of a run is what the provider billed
        for it at the time and cannot be read back from anywhere else, so a payload is the
        record of a measurement and is refused only when it is not one.
        """
        if not isinstance(payload, dict) or "policy" not in payload or "tasks" not in payload:
            raise MeasureError("a stored measurement needs a policy and its tasks")
        if not isinstance(payload["tasks"], list):
            raise MeasureError("a stored measurement's tasks must be a list")
        return cls(policy=str(payload["policy"]),
                   repeats=int(payload.get("repeats", DEFAULT_REPEATS)),
                   tasks=tuple(TaskResult.from_dict(row) for row in payload["tasks"]),
                   session=str(payload.get("session", "")),
                   notes=tuple(str(note) for note in payload.get("notes", ())))


def write_fixtures(workspace: Path, task: Task) -> None:
    """Put one task's files in the fake workspace, where `request_for` points the model."""
    workspace.mkdir(parents=True, exist_ok=True)
    for name, body in task.files.items():
        (workspace / name).write_text(body, encoding="utf-8")


async def seed_history(owner: DemoOwner, conversation: str, *, session: str) -> None:
    """Give a conversation a fixed prelude of earlier messages, written as records."""
    for number, (role, text) in enumerate(PRELUDE):
        record = ConversationMessage(id=f"{session}-seed-{conversation}-{number}".replace("_", "-"),
                                     conversation_id=conversation, role=role, text=text,
                                     provenance=Provenance.OWNER_INSTRUCTION
                                     if role == "owner" else Provenance.MODEL_CLAIM,
                                     state=State.COMPLETED)
        await owner.publish(record.to_dict(), record.id)


async def run_once(owner: DemoOwner, task: Task, repeat: int, request: str, *,
                   conversation: str, session: str) -> Run:
    """One real turn, with the ledger read around it so the cost is the real one.

    Seeding the conversation's prelude is inside the same guard as the turn, because a
    failure anywhere here is one repeat that did not happen: it belongs in that repeat's
    `error`, not in a traceback that takes the other tasks down with it.
    """
    ledger = models.registry()
    before = ledger.report()
    started = time.monotonic()
    client = f"{session}-{task.name}-r{repeat}".replace("_", "-")
    result: dict[str, Any] | None = None
    error = ""
    try:
        await seed_history(owner, conversation, session=session)
        result = await agent.run_turn(owner, request, client, conversation)
    except Exception as exc:                      # a refused turn is recorded as such
        error = f"{type(exc).__name__}: {exc}"
    seconds = time.monotonic() - started
    after = ledger.report()
    fresh = after["entries"][len(before["entries"]):]
    reply = str(result["reply"]["text"]) if result else ""
    return Run(repeat=repeat,
               tokens_in=after["totals"]["tokens_in"] - before["totals"]["tokens_in"],
               tokens_out=after["totals"]["tokens_out"] - before["totals"]["tokens_out"],
               calls=len(fresh), steps=len(result["steps"]) if result else 0,
               seconds=seconds,
               solved=bool(result) and task.solved_by(reply),
               served=tuple(sorted({str(entry["served"]) for entry in fresh
                                    if entry.get("served")})),
               error=error, session=session)


#: How many times one record is asked for before a resume gives up.
#: The graph aborts the first calls of a newly opened lane (measured 2026-10-12 on this
#: machine: `server_unreachable: resolve_keynodes failed`, about nine seconds each), and
#: a burst of those must not cost a run that was already measured. Measured 2026-10-12:
#: a single un-retried read did exactly that — nine recorded runs were bought again.
RECORD_ATTEMPTS = 3
RECORD_PAUSE = 2.0


async def record_verdict(owner: Any, task: Task, run: Run, *, session: str) -> Run | None:
    """One recorded run with its verdict re-read from its own turn.

    The cost of a run is what the provider billed for it and is carried over untouched;
    the verdict is taken from the record rather than from a stored flag, because the rule
    a run is scored by may have changed since it ran.

    There are two ways this does not come back, and they are not the same thing:

    * **the record is not there** — the payload names a turn this graph never wrote —
      returns None, and that repeat is run again rather than carried on a claim;
    * **the graph will not answer** — raises `MeasureError` after a few attempts, because
      a resume that cannot read its own payload must stop rather than buy again the
      turns it already paid for.
    """
    client = f"{session}-{task.name}-r{run.repeat}".replace("_", "-")
    turn_id = f"reply-{client}"
    failure: GraphQueryError | None = None
    for attempt in range(RECORD_ATTEMPTS):
        try:
            turn = await episode.read(owner, turn_id)
        except episode.EpisodeError:
            return None
        except GraphQueryError as exc:
            failure = exc
            if attempt + 1 < RECORD_ATTEMPTS:
                await asyncio.sleep(RECORD_PAUSE)
            continue
        return replace(run, solved=task.solved_by(turn.reply), session=session)
    raise MeasureError(f"the record of {turn_id} cannot be read, so this measurement "
                       f"cannot be resumed: {failure}") from None


async def kept_runs(owner: Any, task: Task, reuse: "Measurement | None") -> tuple[Run, ...]:
    """The runs a payload already holds for this task: the repeats that need no buying.

    A run recorded as an error is not kept, and neither is one whose turn is not on the
    record at all — those repeats are run. A record the graph simply would not serve is
    not the same thing, and stops the measurement instead (`record_verdict`).
    """
    if reuse is None:
        return ()
    stored = reuse.task_result(task.name)
    if stored is None:
        return ()
    kept: list[Run] = []
    for run in stored.runs:
        if run.error:
            continue
        scored = await record_verdict(owner, task, run, session=run.session or reuse.session)
        if scored is not None:
            kept.append(scored)
    return tuple(kept)


async def measure(policy: TurnPolicy, *, workspace: Path, repeats: int = DEFAULT_REPEATS,
                  tasks: tuple[Task, ...] = TASKS, recorded: TurnPolicy = BASE,
                  owner: DemoOwner, session: str = "",
                  reuse: Measurement | None = None) -> Measurement:
    """Run every task `repeats` times under one candidate and collect what happened.

    Every repeat gets its own conversation, seeded with the same prelude, so the
    difference between two policies is the policy and not what a previous repeat left
    in the history.

    `reuse` is a measurement this one continues: its runs are kept as they were observed
    and only the repeats it is missing are run, so a measurement cut short by a failed
    turn is completed instead of bought a second time. It is refused when it does not
    hold this candidate's runs, and it stops with a named error when the record of a run
    it holds cannot be read — an unreadable payload is not a missing one.
    """
    if repeats < DEFAULT_REPEATS:
        raise MeasureError(f"a measurement needs at least {DEFAULT_REPEATS} repeats per "
                           f"task; {repeats} were asked for")
    if not tasks:
        raise MeasureError("a measurement needs at least one task")
    if reuse is not None and reuse.policy != policy.name:
        raise MeasureError(
            f"a resumed measurement must stay on the candidate it measured: the payload "
            f"holds {reuse.policy!r} and this run is {policy.name!r}, so its runs are not "
            f"this candidate's runs")
    apply_policy(policy, recorded)
    session = session or uuid.uuid4().hex[:8]
    results: list[TaskResult] = []
    for task in tasks:
        write_fixtures(Path(workspace), task)
        request = task.request_for(workspace)
        runs = list(await kept_runs(owner, task, reuse))
        owed = missing_repeats(TaskResult(task=task.name, policy=policy.name,
                                          runs=tuple(runs)), repeats)
        for repeat in owed:
            conversation = f"{session}-{task.name}-r{repeat}".replace("_", "-")
            runs.append(await run_once(owner, task, repeat, request,
                                       conversation=conversation, session=session))
        runs.sort(key=lambda run: run.repeat)
        results.append(TaskResult(task=task.name, policy=policy.name, runs=tuple(runs)))
    notes = ("cost is the provider's own token counts for the calls this process made; "
             "each repeat runs in a conversation of its own, seeded with the same prelude",
             "one measurement is not a conclusion: the spread below is what a difference "
             "has to clear")
    return Measurement(policy=policy.name, repeats=repeats, tasks=tuple(results),
                       session=session, notes=notes)


async def measure_tasks(policy: TurnPolicy, *, data_root: Path, repeats: int = DEFAULT_REPEATS,
                        stream: str = DEMO_STREAM, tasks: tuple[Task, ...] = TASKS,
                        recorded: TurnPolicy = BASE, session: str = "",
                        reuse: Measurement | None = None) -> Measurement:
    """The whole leg: a demo subject of its own, opened, measured, closed."""
    owner = owner_for(data_root, stream=stream)
    try:
        return await measure(policy, workspace=Path(data_root) / "workspace", repeats=repeats,
                             tasks=tasks, recorded=recorded, owner=owner, session=session,
                             reuse=reuse)
    finally:
        await owner.close()


def compare(control: Measurement, candidate: Measurement) -> dict[str, Any]:
    """What the two measurements say about each other, and what they do not.

    The saving is the candidate's mean against the control's, and it is reported
    beside the spread: a difference smaller than the spread is not a saving, it is
    noise, and the caller is given both numbers so it can say which it has.
    """
    base = control.mean_tokens_in
    saving = (base - candidate.mean_tokens_in) / base if base else 0.0
    worst = max([value for value in (control.worst_spread, candidate.worst_spread)
                 if value is not None], default=None)
    return {"control": control.policy, "candidate": candidate.policy,
            "control_tokens_in": round(base, 1),
            "candidate_tokens_in": round(candidate.mean_tokens_in, 1),
            "saving": round(saving, 4), "worst_spread": None if worst is None else round(worst, 3),
            "beyond_noise": bool(worst is not None and abs(saving) > worst),
            "solved": {"control": control.solved, "candidate": candidate.solved},
            "runs": {"control": control.runs, "candidate": candidate.runs}}


def demo_root() -> Path:
    """A fresh root for one measurement, beside nothing the owner uses."""
    return Path(tempfile.mkdtemp(prefix="oneiro-dream-"))


def point_at_root(root: Path, workspace: Path) -> tuple[Path, Path]:
    """Point this process at a root of the demo's own; returns `(settings file, data root)`."""
    root = Path(root)
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    os.environ["ONEIRO_SETTINGS_FILE"] = str(root / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(runtime)
    return root / "settings.json", runtime


def seed_settings(root: Path, workspace: Path) -> Path:
    """Seed the demo's own settings file from the owner's configuration, minus every secret.

    The owner's values are read **before** the root is switched, because a snapshot
    taken afterwards would be of an empty file and would lose, among other things, the
    address of the graph. Secrets are dropped rather than copied: a key resolves from
    the owner's keys file as it always does and is never written anywhere new.
    """
    owner = config.snapshot()
    workspace = Path(workspace)
    settings, _ = point_at_root(Path(root), workspace)
    patch = {setting.key: owner[setting.key]
             for setting in settings_registry.SETTINGS
             if setting.kind != "secret" and not setting.readonly}
    patch["tools.workspace"] = str(workspace)
    config.save(patch)
    return settings
