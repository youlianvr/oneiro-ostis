"""Tasks: what the owner wants done, one run at a time, and the states between.

A task and a run are records, so the graph is the memory and nothing important
lives only in this process. Four rules carry the weight:

**One attempt at a time, and never the same attempt twice.** A run is named from
the task and the attempt number, so a second run of one attempt would have to be
named differently, and `start` refuses while the newest attempt is still open.
Only one process writes at a time — the runtime lease is what guarantees that —
so the records and the name together leave no way to have two runs of one attempt.

**An attempt that did not report back is unknown, not retried.** This process
knows the run it is holding right now, and nothing else. Any stored run still
marked running is one that a restart or a crash interrupted, so whether it
changed anything is unknown: the task is reported UNCERTAIN and nothing starts it
again. Only the owner starts another attempt.

**A pause travels to dependents only.** A task whose `blocked_by` are unfinished
waits, and whatever waits on it waits with it. Unrelated work keeps going.

**A level that cannot be read cannot widen anything.** `initiative.level` decides
what may start without a word from the owner, and an unrecognised value means
`off`, because a typo in a settings file must never be the permissive case.

Delegation is the role on the task, `researcher` or `executor`. The turn a run
makes is offered exactly the tools that role may use — the same rule the policy
applies — so who does the work is a boundary rather than a label.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from oneiro import agent, config, recall
from oneiro.chat import ChatError
from oneiro.records import (ConversationMessage, Provenance, Run, State, Task, decode)
from oneiro.tools import Policy, Tool, for_role

TASK = Task.KIND
RUN = Run.KIND
MESSAGE = ConversationMessage.KIND

#: The roles that do work. `manager` owns the conversation, not a task.
ROLES = ("researcher", "executor")
#: Attempts one task may have before the process gives up and says so. More than
#: one because a single attempt is a lottery; not more than three because the
#: owner's word, not persistence, is what should carry a task further.
MAX_ATTEMPTS = 3
TITLE_CHARS = 200
DETAIL_CHARS = 4000
NOTES_CHARS = 2000

LEVELS = ("off", "on_command", "scheduled", "proactive")
#: A notification is a message with this label, so it appears in the conversation
#: it belongs to rather than on a page of its own. `HELD` marks the ones raised
#: inside the owner's quiet hours: stored either way, but not an interruption.
NOTICE = "notice"
HELD = "held"

#: The runs this process is holding right now. In memory on purpose: this is the
#: one fact a restart cannot recover, and pretending otherwise is how a process
#: repeats work it may already have done.
_HELD_RUNS: set[str] = set()
_HELD_LOCK = threading.Lock()


class TaskError(ValueError):
    """A task request that cannot be carried out, with a reason worth reading."""


@dataclass(frozen=True)
class Snapshot:
    """Everything the stored stream says about tasks, runs and open questions."""

    tasks: dict[str, dict[str, Any]]          # newest revision per task id
    runs: dict[str, list[dict[str, Any]]]     # newest revision per run, by task id
    scanned: int
    skipped: int
    complete: bool


@dataclass(frozen=True)
class View:
    """The task list as the owner reads it."""

    tasks: list[dict[str, Any]]
    scanned: int
    skipped: int
    complete: bool

    def to_dict(self) -> dict[str, Any]:
        return {"tasks": self.tasks, "scanned": self.scanned,
                "skipped": self.skipped, "complete": self.complete}


# ---------- the process's own facts ----------


def hold(run_id: str) -> None:
    """Mark an attempt as this process's responsibility, right now.

    Held from the moment `start` opens it until the attempt is written down, so a
    run that is still marked running means one of two things: this process is
    looking after it, or a process that is gone was. A restart leaves nothing
    held, and that is how the difference is known.
    """
    with _HELD_LOCK:
        _HELD_RUNS.add(run_id)


def release(run_id: str) -> None:
    with _HELD_LOCK:
        _HELD_RUNS.discard(run_id)


def is_held(run_id: str) -> bool:
    with _HELD_LOCK:
        return run_id in _HELD_RUNS


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- what the owner declared ----------


def level() -> str:
    """The declared initiative level. A value that cannot be read means `off`.

    Safe in the cautious direction on purpose: a settings file somebody edited by
    hand must not become the permissive case. `settings_error()` is what says so
    on a surface, so the fallback is never silent.
    """
    try:
        declared = str(config.value("initiative.level") or "").strip().lower()
    except ValueError:
        return "off"
    return declared if declared in LEVELS else "off"


def settings_error() -> str:
    """Why the level could not be read, in words, or an empty string."""
    try:
        config.value("initiative.level")
    except ValueError as exc:
        return str(exc)
    return ""


def picks_up_work(level_name: str) -> bool:
    """Whether the process may start work the owner did not just ask for.

    `off` and `on_command` both mean the owner's own word is what starts work;
    `scheduled` adds the tasks put on a schedule, and `proactive` adds what Oneiro
    notices by itself.
    """
    return level_name in ("scheduled", "proactive")


def speaks_up(level_name: str) -> bool:
    """Whether Oneiro may open a conversation about work of its own accord."""
    return level_name == "proactive"


def client_id_for(text: str, when: datetime) -> str:
    """A stable request id, so an identical ask in the same minute is one task."""
    digest = hashlib.sha256(f"{text}\n{when:%Y%m%d%H%M}".encode("utf-8")).hexdigest()[:24]
    return "cli-" + digest


# ---------- reading the records ----------


def record_of(row: dict[str, Any]) -> Any:
    """The typed record behind a stored row (`__` columns belong to the page)."""
    return decode({key: value for key, value in row.items() if not key.startswith("__")})


def revision_of(row: dict[str, Any]) -> int:
    return int(row.get("__revision__") or 0)


def state_of_row(row: dict[str, Any] | None) -> str:
    return str((row or {}).get("state") or State.QUEUED.value)


def _is_task_material(row: dict[str, Any]) -> bool:
    return row.get("kind") in (TASK, RUN)


async def snapshot(owner: Any) -> Snapshot:
    """One walk of the stored stream, filtered here because the graph serves pages.

    Rows arrive newest first, so the first row seen for an id is its current
    revision: a task's latest state, and one row per run rather than one per
    revision of that run.
    """
    found = await recall.scan(owner, _is_task_material)
    tasks: dict[str, dict[str, Any]] = {}
    runs: dict[str, dict[str, dict[str, Any]]] = {}
    for row in found.rows:
        kind = row.get("kind")
        if kind == TASK:
            tasks.setdefault(row["id"], row)
        elif kind == RUN:
            runs.setdefault(str(row.get("task_id") or ""), {}).setdefault(row["id"], row)
    return Snapshot(tasks,
                    {key: list(value.values()) for key, value in runs.items()},
                    found.scanned, found.skipped, found.complete)


def _attempt(row: dict[str, Any]) -> int:
    return int(row.get("attempt") or 1)


def _own_state(runs: list[dict[str, Any]]) -> tuple[str, str]:
    """What the task's own attempts say, before dependencies are considered."""
    if not runs:
        return State.QUEUED.value, "not started yet"
    latest = max(runs, key=_attempt)
    state = state_of_row(latest)
    if state == State.RUNNING.value:
        if is_held(latest["id"]):
            return State.RUNNING.value, "a run is in flight in this process"
        return (State.UNCERTAIN.value,
                "an attempt started and did not report back, so whether it changed "
                "anything is unknown; inspect it before trying again")
    if state == State.UNCERTAIN.value:
        return (State.UNCERTAIN.value,
                "an earlier attempt's outcome is unknown; only you can start another")
    if state == State.COMPLETED.value:
        return State.COMPLETED.value, "finished"
    if state == State.CANCELLED.value:
        return State.CANCELLED.value, "called off"
    attempts = len(runs)
    if attempts >= MAX_ATTEMPTS:
        return (State.FAILED.value,
                f"gave up after {attempts} attempts; nothing more is tried on its own")
    return State.QUEUED.value, f"ready for attempt {attempts + 1} of {MAX_ATTEMPTS}"


def states(snapshot: Snapshot) -> dict[str, tuple[str, str]]:
    """Each task's state now, and the sentence that says why.

    Two passes, so a dependency chain cannot recurse: first what a task's own
    attempts say, then whether something it waits for holds it back.

    `waiting` means one thing only: a dependency this task was told to wait for.
    Asking the owner is the conversation's tool, not a task's — a run works as
    `researcher` or `executor`, and neither role may ask — so no task can be held
    by an open question and none is reported as if it were.
    """
    own = {task_id: _own_state(snapshot.runs.get(task_id, []))
           for task_id in snapshot.tasks}
    settled = (State.COMPLETED.value, State.UNCERTAIN.value, State.RUNNING.value,
               State.CANCELLED.value)
    resolved: dict[str, tuple[str, str]] = {}
    for task_id, task in snapshot.tasks.items():
        state, why = own[task_id]
        if state in settled:
            resolved[task_id] = (state, why)
            continue
        missing = [str(blocked) for blocked in (task.get("blocked_by") or ())
                   if own.get(str(blocked), ("", ""))[0] != State.COMPLETED.value]
        if missing:
            names = ", ".join(str(snapshot.tasks.get(item, {}).get("title") or item)
                              for item in missing)
            resolved[task_id] = (State.WAITING.value, f"waiting for {names}")
            continue
        resolved[task_id] = (state, why)
    return resolved


def _run_out(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "attempt": _attempt(row), "role": str(row.get("role") or ""),
            "state": state_of_row(row), "notes": str(row.get("notes") or ""),
            "held_now": is_held(row["id"]), "started_at": row["created_at"],
            "updated_at": row["updated_at"]}


def _item(task_id: str, snapshot: Snapshot,
          resolved: dict[str, tuple[str, str]]) -> dict[str, Any]:
    task = snapshot.tasks[task_id]
    runs = sorted(snapshot.runs.get(task_id, ()), key=_attempt)
    state, why = resolved[task_id]
    return {"id": task_id, "title": str(task.get("title") or ""),
            "detail": str(task.get("detail") or ""),
            "role": str(task.get("assigned_role") or "executor"),
            "state": state, "why": why, "attempts": len(runs),
            "max_attempts": MAX_ATTEMPTS,
            "blocked_by": [str(item) for item in (task.get("blocked_by") or ())],
            "labels": [str(label) for label in (task.get("labels") or ())],
            "last_result": str(runs[-1].get("notes") or "") if runs else "",
            "created_at": task["created_at"], "updated_at": task["updated_at"],
            "runs": [_run_out(row) for row in reversed(runs)]}


def _ordered(snapshot: Snapshot) -> list[str]:
    """Oldest first, the way the owner asked for them.

    Timestamps have second resolution, so two tasks asked for in the same second
    are separated by the order the memory published them rather than by their
    random ids — which is what makes the list read in the order it was written.
    """
    return sorted(snapshot.tasks,
                  key=lambda tid: (snapshot.tasks[tid]["created_at"],
                                   int(snapshot.tasks[tid].get("__sequence__") or 0)))


async def view(owner: Any) -> View:
    snapshot_state = await snapshot(owner)
    resolved = states(snapshot_state)
    items = [_item(task_id, snapshot_state, resolved) for task_id in _ordered(snapshot_state)]
    return View(items, snapshot_state.scanned, snapshot_state.skipped,
                snapshot_state.complete)


async def history(owner: Any, task_id: str) -> dict[str, Any]:
    """One task with every attempt it made, newest first."""
    snapshot_state = await snapshot(owner)
    if task_id not in snapshot_state.tasks:
        raise TaskError("no task with that id is stored")
    resolved = states(snapshot_state)
    # A dependency outside the requested task still has to be nameable.
    names = {key: str(value.get("title") or key) for key, value in snapshot_state.tasks.items()}
    item = _item(task_id, snapshot_state, resolved)
    item["blocked_by_titles"] = [names.get(key, key) for key in item["blocked_by"]]
    return item


# ---------- writing the records ----------


async def create(owner: Any, *, title: str, detail: str = "", role: str = "executor",
                 blocked_by: tuple[str, ...] | list[str] = (), labels: tuple[str, ...] = (),
                 client_id: str) -> dict[str, Any]:
    """One task, published once per client ID, so a retried ask is not two tasks."""
    text = " ".join(str(title or "").split())
    if not text:
        raise TaskError("a task needs a title")
    if len(text) > TITLE_CHARS:
        raise TaskError(f"a title may be at most {TITLE_CHARS} characters")
    if role not in ROLES:
        raise TaskError(f"a task runs as {' or '.join(ROLES)}, not {role!r}")
    if not client_id or len(client_id) > 96:
        raise TaskError("a task needs a request id of at most 96 characters")
    task_id = "task-" + client_id
    stored = await owner.memory_entity(task_id)
    if stored is not None:
        return {"task": stored, "duplicate": True}
    blocked = tuple(str(item) for item in blocked_by)
    for item in blocked:
        if item == task_id:
            raise TaskError("a task cannot wait for itself")
        if await owner.memory_entity(item) is None:
            raise TaskError(f"nothing waits for {item}: no such task is stored")
    record = Task(id=task_id, title=text, detail=str(detail or "").strip()[:DETAIL_CHARS],
                  assigned_role=role, blocked_by=blocked, labels=tuple(labels),
                  provenance=Provenance.OWNER_INSTRUCTION, state=State.QUEUED)
    published = await owner.publish(record.to_dict(), task_id)
    return {"task": published["record"], "duplicate": published["duplicate"]}


async def start(owner: Any, task_id: str, *, retry: bool = False) -> dict[str, Any]:
    """Begin the next attempt of a task, or say why it cannot begin.

    Returning without starting is a normal answer, not an error: a task that is
    already running, waiting on something, or finished has a reason, and the
    reason is what the caller shows. `retry=True` is the owner's own decision to
    make another attempt after a failure or an unknown outcome; it still cannot
    begin work that is waiting on something.

    The refusal to start an open attempt is deliberate rather than an optimisation:
    an attempt whose outcome nobody wrote down must be looked at, and starting the
    next one on top of it is how the same effect happens twice.
    """
    snapshot_state = await snapshot(owner)
    task = snapshot_state.tasks.get(task_id)
    if task is None:
        raise TaskError("no task with that id is stored")
    runs = sorted(snapshot_state.runs.get(task_id, ()), key=_attempt)
    if runs and state_of_row(runs[-1]) == State.RUNNING.value:
        # An open attempt is never a second attempt, whatever asked.
        return {"run": runs[-1], "started": False,
                "why": "an attempt is already open; one attempt runs at a time"}
    state, why = states(snapshot_state)[task_id]
    if state in (State.WAITING.value, State.RUNNING.value):
        return {"run": None, "started": False, "why": f"this task is {state}: {why}"}
    if state != State.QUEUED.value and not retry:
        return {"run": None, "started": False, "why": f"this task is {state}: {why}"}
    attempt = (_attempt(runs[-1]) + 1) if runs else 1
    run_id = f"run-{task_id}-a{attempt}"
    record = Run(id=run_id, task_id=task_id, role=str(task.get("assigned_role") or "executor"),
                 attempt=attempt, state=State.RUNNING, provenance=Provenance.SYSTEM)
    # Held before it is written, so the attempt is this process's from the first
    # moment: between opening it and working it, nothing may read it as abandoned.
    hold(run_id)
    try:
        published = await owner.publish(record.to_dict(), run_id)
    except BaseException:
        release(run_id)
        raise
    stored = {**published["record"], "__revision__": published["revision"]}
    return {"run": stored, "started": not published["duplicate"],
            "why": "" if not published["duplicate"] else "this attempt is already open"}


async def finish(owner: Any, run: dict[str, Any], state: State, notes: str) -> dict[str, Any]:
    """Publish what became of one attempt. One revision, named by its outcome."""
    record = record_of(run)
    if not isinstance(record, Run):
        raise TaskError("that row is not a run")
    updated = record.with_state(state, notes=str(notes or "")[:NOTES_CHARS])
    published = await owner.publish(updated.to_dict(), f"{run['id']}-{state.value}",
                                    expected_revision=revision_of(run))
    return {**published["record"], "__revision__": published["revision"]}


def prompt_of(task: dict[str, Any]) -> str:
    """What the run is told to do: the owner's own words, then the detail."""
    title = " ".join(str(task.get("title") or "").split())
    detail = str(task.get("detail") or "").strip()
    return f"{title}\n\n{detail}" if detail else title


async def work(owner: Any, task: dict[str, Any], run: dict[str, Any], *,
               call: Callable[..., Any] | None = None,
               registry: dict[str, Tool] | None = None,
               policy: Policy | None = None) -> dict[str, Any]:
    """Run one attempt as its role and record what came of it, honestly.

    The run's own id is the turn's client ID, so the owner's instruction and the
    reply belong to one attempt: a second call for the same run replays the stored
    answer instead of asking the model again.
    """
    role = str(run.get("role") or task.get("assigned_role") or "executor")
    conversation = f"task-{task['id']}"
    if registry is None:
        # Only this role's tools are offered, so the model is not handed a
        # capability the record would then refuse.
        registry = for_role(agent.default_registry(owner, conversation), role)
    hold(run["id"])
    try:
        result = await agent.run_turn(
            owner, prompt_of(task), str(run["id"]), conversation, role=role,
            registry=registry, policy=policy, call=call)
    except ChatError as exc:
        # No reply is invented: the attempt failed and the reason is the record.
        stored = await finish(owner, run, State.FAILED, f"the model did not answer: {exc}")
        await notify(owner, conversation, _finished_notice(task, State.FAILED,
                                                           str(stored.get("notes") or "")))
        return {"run": stored, "state": State.FAILED.value, "text": "", "steps": []}
    finally:
        release(run["id"])
    reply = result["reply"]
    outcome = str(reply.get("state") or State.COMPLETED.value)
    text = str(reply.get("text") or "")
    if outcome == State.UNCERTAIN.value:
        state, notes = State.UNCERTAIN, text
    elif outcome in (State.FAILED.value, State.CANCELLED.value):
        state, notes = State.FAILED, text or "the turn ended without an answer"
    else:
        state, notes = State.COMPLETED, text
    stored = await finish(owner, run, state, notes)
    await notify(owner, conversation, _finished_notice(task, state, notes))
    return {"run": stored, "state": state.value, "text": text,
            "steps": result.get("steps") or [], "reply": reply}


async def tick(owner: Any, *, call: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Bring the records up to date, then start one ready task.

    One task per tick on purpose: the window, the chat and the scheduler share one
    process, and a tick that worked the whole list would hold it for as long as
    the list is long.
    """
    level_name = level()
    reconciled = await reconcile(owner)
    report: dict[str, Any] = {"level": level_name, "reconciled": reconciled,
                              "worked": None, "why": ""}
    if not picks_up_work(level_name):
        report["why"] = (f"initiative is {level_name}: only what you ask for starts "
                         f"by itself, so ready tasks are left alone")
        return report
    snapshot_state = await snapshot(owner)
    resolved = states(snapshot_state)
    ready = [task_id for task_id in _ordered(snapshot_state)
             if resolved[task_id][0] == State.QUEUED.value]
    if not ready:
        report["why"] = "no task is ready"
        return report
    task_id = ready[0]
    started = await start(owner, task_id)
    if not started["started"]:
        report["why"] = started["why"]
        return report
    outcome = await work(owner, snapshot_state.tasks[task_id], started["run"], call=call)
    report["worked"] = {**_item(task_id, snapshot_state, resolved),
                        "state": outcome["state"], "last_result": str(
                            (outcome["run"] or {}).get("notes") or "")}
    return report


async def reconcile(owner: Any) -> list[str]:
    """Write the honest outcome for attempts that stopped reporting.

    Called from a write path, never from a read: a stored run still marked
    running and not held by this process is one a restart interrupted, and the
    record should say so rather than let a reader guess.
    """
    snapshot_state = await snapshot(owner)
    written: list[str] = []
    for task_runs in snapshot_state.runs.values():
        for row in sorted(task_runs, key=_attempt):
            if state_of_row(row) == State.RUNNING.value and not is_held(row["id"]):
                await finish(owner, row, State.UNCERTAIN,
                             "this attempt started and never reported back; whether it "
                             "changed anything is unknown")
                written.append(row["id"])
    return written


# ---------- telling the owner ----------


def declared_quiet_hours() -> str:
    """The window as the owner wrote it, or an empty string if it cannot be read.

    An unreadable value is treated as "never quiet" and said out loud by
    `notices`, because a silence the owner did not ask for is worse than a notice
    during their evening — and an exception raised while a finished attempt was
    being written down would lose the notice entirely.
    """
    try:
        return str(config.value("initiative.quiet_hours") or "").strip()
    except ValueError:
        return ""


def quiet_window() -> tuple[int, int] | None:
    """The declared silent hours as minutes since midnight, or None.

    An empty value means never quiet. A value that cannot be read also means never
    quiet, and `notices` says which of the two it was.
    """
    raw = declared_quiet_hours()
    if not raw:
        return None
    start, separator, end = raw.partition("-")
    if not separator:
        return None
    try:
        first = _minutes(start.strip())
        last = _minutes(end.strip())
    except ValueError:
        return None
    return first, last


def _minutes(text: str) -> int:
    hours, separator, minutes = text.partition(":")
    if not separator or not hours.isdigit() or not minutes.isdigit():
        raise ValueError("a time reads as HH:MM")
    if not 0 <= int(hours) < 24 or not 0 <= int(minutes) < 60:
        raise ValueError("a time reads as HH:MM")
    return int(hours) * 60 + int(minutes)


def quiet_at(moment: datetime) -> bool:
    """Whether the owner asked for silence at this local moment."""
    window = quiet_window()
    if window is None:
        return False
    start, end = window
    at = moment.hour * 60 + moment.minute
    return start <= at < end if start <= end else (at >= start or at < end)


def _finished_notice(task: dict[str, Any], state: State, notes: str) -> str:
    title = str(task.get("title") or "the task")
    if state is State.COMPLETED:
        return f"Done: {title}\n{notes}".strip()[:NOTES_CHARS]
    if state is State.UNCERTAIN:
        return (f"{title}: an attempt stopped reporting. Whether it changed anything "
                f"is unknown, and it was not tried again.")
    return f"{title} did not finish: {notes}".strip()[:NOTES_CHARS]


async def notify(owner: Any, conversation_id: str, text: str, *,
                 at: datetime | None = None) -> dict[str, Any]:
    """Say one thing in a conversation, and hold it when quiet hours are on.

    Held is not hidden: the message is stored either way, because the memory is
    the truth, and the label is what tells the window not to interrupt the owner.

    The whole record is a function of the conversation, the words and the minute,
    so the same words in the same minute are one notice rather than a second one.
    That is what lets a retried attempt say its piece without telling the owner
    the same thing twice, and it is also what keeps the write idempotent: an
    identical operation ID with a different timestamp would be refused by the
    store rather than stored twice.
    """
    moment = (at or utcnow()).astimezone().replace(second=0, microsecond=0)
    held = quiet_at(moment)
    labels = (NOTICE, HELD) if held else (NOTICE,)
    digest = hashlib.sha256(
        f"{conversation_id}\n{text}\n{moment:%Y%m%d%H%M}".encode("utf-8")).hexdigest()[:24]
    stamp = moment.isoformat(timespec="seconds")
    record = ConversationMessage(id="notice-" + digest, conversation_id=conversation_id,
                                 role="system", text=text, labels=labels,
                                 created_at=stamp, updated_at=stamp,
                                 provenance=Provenance.SYSTEM, state=State.COMPLETED)
    published = await owner.publish(record.to_dict(), record.id)
    return {"record": published["record"], "held": held, "duplicate": published["duplicate"]}


async def notices(owner: Any, *, limit: int = 50) -> dict[str, Any]:
    """What Oneiro said on its own, newest first, held ones named as held."""
    window = quiet_window()
    declared = declared_quiet_hours()
    found = await recall.scan(
        owner,
        lambda row: (row.get("kind") == MESSAGE and NOTICE in (row.get("labels") or ())),
        want=limit)
    rows = []
    for row in found.rows:
        labels = list(row.get("labels") or ())
        held = HELD in labels
        rows.append({"id": row["id"], "conversation_id": row.get("conversation_id") or "",
                     "text": str(row.get("text") or ""), "at": row["updated_at"],
                     "held": held,
                     "why": (f"held: quiet hours are {declared}" if held and window
                             else ("held" if held else ""))})
    return {"notices": rows, "quiet_hours": declared, "scanned": found.scanned,
            "skipped": found.skipped, "complete": found.complete}


async def suggestions(owner: Any) -> dict[str, Any]:
    """Unfinished work that may come back to the owner, or why it may not.

    Only `proactive` speaks first, and only while suggestions are switched on.
    Anything else returns the reason rather than a fabricated shortlist.
    """
    level_name = level()
    if not speaks_up(level_name):
        return {"suggestions": [], "level": level_name,
                "why": f"initiative is {level_name}: Oneiro does not speak up first"}
    if not bool(config.value("initiative.suggestions")):
        return {"suggestions": [], "level": level_name,
                "why": "suggestions from memory and unfinished tasks are switched off"}
    snapshot_state = await snapshot(owner)
    resolved = states(snapshot_state)
    unfinished = (State.QUEUED.value, State.WAITING.value, State.UNCERTAIN.value)
    rows = [_item(task_id, snapshot_state, resolved)
            for task_id in _ordered(snapshot_state)
            if resolved[task_id][0] in unfinished]
    return {"suggestions": rows, "level": level_name, "why": ""}


def ready(item: dict[str, Any]) -> bool:
    """Whether a task may start now, by its derived state alone."""
    return item["state"] == State.QUEUED.value


async def run_now(owner: Any, task_id: str, *, retry: bool = False,
                  call: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Start an attempt because the owner asked for it, and run it here."""
    snapshot_state = await snapshot(owner)
    task = snapshot_state.tasks.get(task_id)
    if task is None:
        raise TaskError("no task with that id is stored")
    started = await start(owner, task_id, retry=retry)
    if not started["started"]:
        return {**started, "state": "", "text": "", "steps": []}
    return await work(owner, task, started["run"], call=call)
