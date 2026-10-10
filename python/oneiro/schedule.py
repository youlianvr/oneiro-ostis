"""The owner's schedules: cron-like standing instructions, held in the graph.

A schedule says "run this task on this expression". The expression is a plain
five-field cron line (`minute hour day month weekday`), with `*`, lists, ranges and
steps, and the shorthand names for the common cases. Only the well-known numeric
form is accepted: an expression the code cannot read exactly is refused with the
reason, never interpreted loosely, because a schedule that fires at a moment
nobody asked for is worse than one that does not fire.

The schedules are records rather than lines in a settings file. That buys three
things the owner can check: a schedule survives a restart together with the tasks
it made, `last_fired_at` is what stops a process that starts again from firing a
minute that already fired, and removing a schedule publishes a cancelled revision
instead of deleting anything.

One rule is the owner's own words: `initiative.level`. With `off` or `on_command`
a due schedule is named and left alone; `scheduled` adds the tasks put on a
schedule, and `proactive` adds what Oneiro notices by itself. Nothing here decides
that for itself.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable

from oneiro import recall, tasks
from oneiro.records import Schedule, State

SCHEDULE = Schedule.KIND
#: How often the background loop looks at the clock. Nothing here waits for a
#: whole interval to notice work: a tick is cheap and the level decides everything.
TICK_SECONDS = 60.0
#: How far ahead a next-fire search may look before the expression is called
#: impossible. A year covers every real calendar case and bounds the search.
HORIZON_DAYS = 366
MAX_TEXT_CHARS = 4000

FIELD_NAMES = ("minute", "hour", "day", "month", "weekday")
FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
SHORTHANDS = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
              "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *"}


class ScheduleError(ValueError):
    """An expression or a request that cannot be honoured, with a readable reason."""


def _number(text: str, low: int, high: int, *, weekday: bool) -> int:
    body = text.strip()
    if not body.lstrip("+").isdigit():
        raise ScheduleError(f"{body!r} is not a number")
    value = int(body)
    if weekday and value == 7:                 # cron lets both 0 and 7 mean Sunday
        value = 0
    if not low <= value <= high:
        raise ScheduleError(f"{value} is outside {low}..{high}")
    return value


def _field(text: str, low: int, high: int, *, weekday: bool) -> tuple[frozenset[int], bool]:
    """One field's allowed values, and whether it was left open with a bare `*`."""
    raw = text.strip()
    if not raw:
        raise ScheduleError("a field cannot be empty")
    values: set[int] = set()
    for item in raw.split(","):
        body, separator, raw_step = item.strip().partition("/")
        step = 1
        if separator:
            if not raw_step.isdigit() or int(raw_step) < 1:
                raise ScheduleError(f"{item.strip()!r}: a step must be a positive number")
            step = int(raw_step)
        body = body.strip()
        if body in ("", "*"):
            start, end = low, high
        elif "-" in body:
            first, _, last = body.partition("-")
            start = _number(first, low, high, weekday=weekday)
            end = _number(last, low, high, weekday=weekday)
            if end < start:
                raise ScheduleError(f"{item.strip()!r}: a range runs from the smaller value")
        else:
            start = end = _number(body, low, high, weekday=weekday)
        values.update(range(start, end + 1, step))
    if not values:                              # pragma: no cover - ranges always yield one
        raise ScheduleError(f"{raw!r} matches no value")
    return frozenset(values), raw == "*"


@dataclass(frozen=True)
class Cron:
    """A parsed expression: what it allows, and which fields it left open."""

    text: str
    values: tuple[frozenset[int], ...]
    opened: tuple[bool, ...]

    @classmethod
    def parse(cls, expression: str) -> "Cron":
        raw = str(expression or "").strip()
        if not raw:
            raise ScheduleError("a schedule needs an expression")
        spelled = SHORTHANDS.get(raw.lower(), raw)
        parts = spelled.split()
        if len(parts) != 5:
            raise ScheduleError(
                f"five fields are expected ({' '.join(FIELD_NAMES)}), got {len(parts)}")
        allowed: list[frozenset[int]] = []
        opened: list[bool] = []
        for index, part in enumerate(parts):
            low, high = FIELD_RANGES[index]
            try:
                values, is_open = _field(part, low, high, weekday=index == 4)
            except ScheduleError as exc:
                raise ScheduleError(f"{FIELD_NAMES[index]}: {exc}") from None
            allowed.append(values)
            opened.append(is_open)
        return cls(spelled, tuple(allowed), tuple(opened))

    def matches(self, moment: datetime) -> bool:
        """Whether this expression names this minute."""
        minute, hour, day, month, weekday = self.values
        weekday_value = (moment.weekday() + 1) % 7     # cron counts Sunday as 0
        if not self.opened[2] and not self.opened[4]:
            # The standard's rule: with both the day and the weekday restricted,
            # either matching is enough. Reading it as "both" would silently skip
            # the days the owner asked for.
            calendar = moment.day in day or weekday_value in weekday
        else:
            calendar = moment.day in day and weekday_value in weekday
        return (moment.minute in minute and moment.hour in hour
                and moment.month in month and calendar)

    def next_after(self, after: datetime) -> datetime:
        """The first minute this expression names, strictly after `after`."""
        moment = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
        limit = moment + timedelta(days=HORIZON_DAYS)
        while moment < limit:
            if self.matches(moment):
                return moment
            moment += timedelta(minutes=1)
        raise ScheduleError(f"{self.text!r} does not name a minute within {HORIZON_DAYS} days")

    def __str__(self) -> str:
        return self.text


# ---------- reading and writing the records ----------


def is_enabled(row: dict[str, Any]) -> bool:
    return bool(row.get("enabled", True)) and str(row.get("state") or "") != State.CANCELLED.value


def _moment(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def since(row: dict[str, Any]) -> datetime:
    """When this schedule's clock starts: the last firing, or its creation."""
    return _moment(row.get("last_fired_at")) or _moment(row.get("created_at")) or tasks.utcnow()


def next_at(row: dict[str, Any]) -> datetime | None:
    """The next local moment this schedule fires, or None if it cannot be read."""
    try:
        cron = Cron.parse(str(row.get("cron") or ""))
    except ScheduleError:
        return None
    try:
        return cron.next_after(since(row).astimezone())
    except ScheduleError:
        return None


def is_due(row: dict[str, Any], *, at: datetime) -> bool:
    moment = next_at(row)
    return moment is not None and moment <= at.astimezone()


async def current(owner: Any) -> dict[str, dict[str, Any]]:
    """The newest revision of every schedule, newest first."""
    found = await recall.scan(owner, lambda row: row.get("kind") == SCHEDULE)
    rows: dict[str, dict[str, Any]] = {}
    for row in found.rows:
        rows.setdefault(row["id"], row)
    return rows


def _item(row: dict[str, Any], *, at: datetime) -> dict[str, Any]:
    expression = str(row.get("cron") or "")
    try:
        readable = str(Cron.parse(expression))
        problem = ""
    except ScheduleError as exc:
        readable, problem = expression, str(exc)
    moment = next_at(row)
    return {"id": row["id"], "cron": expression, "readable_cron": readable,
            "problem": problem, "title": str(row.get("task_title") or ""),
            "detail": str(row.get("task_detail") or ""),
            "role": str(row.get("role") or "executor"),
            "enabled": is_enabled(row), "state": str(row.get("state") or ""),
            "last_fired_at": str(row.get("last_fired_at") or ""),
            "last_task_id": str(row.get("last_task_id") or ""),
            "next_at": moment.isoformat(timespec="minutes") if moment else "",
            "due_now": moment is not None and is_due(row, at=at),
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


async def listing(owner: Any, *, at: datetime | None = None) -> dict[str, Any]:
    """Every schedule as the owner reads it, with the level that governs it."""
    moment = at or tasks.utcnow()
    rows = await current(owner)
    level = tasks.level()
    items = [_item(row, at=moment)
             for row in sorted(rows.values(), key=lambda row: row["created_at"])]
    return {"schedules": items, "level": level, "fires": tasks.picks_up_work(level),
            "now": moment.astimezone().isoformat(timespec="minutes")}


async def add(owner: Any, *, title: str, cron: str, detail: str = "", role: str = "executor",
              client_id: str) -> dict[str, Any]:
    """One standing instruction, published once per client ID."""
    text = " ".join(str(title or "").split())
    if not text:
        raise ScheduleError("a schedule needs a title for the task it makes")
    if role not in tasks.ROLES:
        raise ScheduleError(f"a scheduled task runs as {' or '.join(tasks.ROLES)}, not {role!r}")
    readable = str(Cron.parse(cron))           # refused here if it cannot be read
    if not client_id or len(client_id) > 96:
        raise ScheduleError("a schedule needs a request id of at most 96 characters")
    schedule_id = "sched-" + client_id
    stored = await owner.memory_entity(schedule_id)
    if stored is not None:
        return {"schedule": stored, "duplicate": True}
    record = Schedule(id=schedule_id, cron=readable, task_title=text,
                      task_detail=str(detail or "").strip()[:MAX_TEXT_CHARS], role=role,
                      state=State.QUEUED)
    published = await owner.publish(record.to_dict(), schedule_id)
    return {"schedule": published["record"], "duplicate": published["duplicate"]}


async def remove(owner: Any, schedule_id: str, *, client_id: str) -> dict[str, Any]:
    """Call a schedule off. It is cancelled, never deleted: the history stays."""
    rows = await current(owner)
    row = rows.get(schedule_id)
    if row is None:
        raise ScheduleError("no schedule with that id is stored")
    if not is_enabled(row):
        return {"id": schedule_id, "removed": True, "duplicate": True}
    record = tasks.record_of(row)
    if not isinstance(record, Schedule):
        raise ScheduleError("that row is not a schedule")
    cancelled = record.with_state(State.CANCELLED, enabled=False)
    published = await owner.publish(cancelled.to_dict(), "schedule-remove-" + client_id,
                                    expected_revision=tasks.revision_of(row))
    return {"id": schedule_id, "removed": True, "duplicate": published["duplicate"]}


async def fire(owner: Any, row: dict[str, Any], *, at: datetime) -> dict[str, Any]:
    """Make the task this schedule is due for. Starting it is `tasks`'s business.

    Once per minute, and the minute is what makes it so. The task's request id,
    the mark on the schedule and the publication's operation ID are all made from
    the minute the firing belongs to, so two ticks inside one minute — a restarted
    process, a manual tick beside a background one — write the same records and
    the store answers the second with the first.
    """
    moment = at.astimezone().replace(second=0, microsecond=0)
    digest = hashlib.sha256(row["id"].encode("utf-8")).hexdigest()[:16]
    client_id = f"sched-{digest}-{moment:%Y%m%d%H%M}"
    created = await tasks.create(owner, title=str(row.get("task_title") or ""),
                                 detail=str(row.get("task_detail") or ""),
                                 role=str(row.get("role") or "executor"),
                                 labels=(f"schedule:{row['id']}",), client_id=client_id)
    task_id = created["task"]["id"]
    record = tasks.record_of(row)
    if not isinstance(record, Schedule):
        raise ScheduleError("that row is not a schedule")
    # The stamp is the minute, not the moment the tick happened to run: the whole
    # mark is then a function of the record and the minute, which is what lets a
    # recovery write the same thing the interrupted process would have.
    at_minute = moment.isoformat(timespec="seconds")
    marked = replace(record, last_fired_at=at_minute, last_task_id=task_id,
                     updated_at=at_minute)
    await owner.publish(marked.to_dict(), f"fired-{row['id']}-{moment:%Y%m%d%H%M}",
                        expected_revision=tasks.revision_of(row))
    return {"schedule_id": row["id"], "task_id": task_id,
            "at": moment.isoformat(timespec="minutes"),
            "duplicate_task": created["duplicate"]}


async def tick(owner: Any, *, at: datetime | None = None,
               call: Callable[..., Any] | None = None) -> dict[str, Any]:
    """One look at the clock: fire what is due, then let tasks work.

    Nothing here happens quietly. Every outcome says either what it did or why it
    did nothing, and with `off` or `on_command` the due schedules are named and
    left alone rather than silently ignored.
    """
    moment = (at or tasks.utcnow()).astimezone()
    level = tasks.level()
    rows = await current(owner)
    due = sorted((row for row in rows.values() if is_enabled(row) and is_due(row, at=moment)),
                 key=lambda row: row["created_at"])
    report: dict[str, Any] = {"at": moment.isoformat(timespec="minutes"), "level": level,
                              "fired": [], "due": [], "worked": None, "why": "nothing is due"}
    if not due:
        return report
    if not tasks.picks_up_work(level):
        # Named, with the reason: the owner set this schedule and is entitled to
        # know it is being held back rather than forgotten.
        report["due"] = [{"id": row["id"], "title": str(row.get("task_title") or ""),
                          "cron": str(row.get("cron") or "")} for row in due]
        report["why"] = (f"initiative is {level}: a schedule does not fire until you "
                          f"set it to scheduled")
        return report
    for row in due:
        report["fired"].append(await fire(owner, row, at=moment))
    report["worked"] = await tasks.tick(owner, call=call)
    report["why"] = report["worked"].get("why") or ""
    return report


async def loop(owner: Any, *, interval: float = TICK_SECONDS,
               call: Callable[..., Any] | None = None,
               on_error: Callable[[Exception], None] | None = None) -> None:
    """Look at the clock until the caller cancels this task.

    A tick that fails is reported through `on_error` and the loop keeps its place:
    a scheduler that dies on one bad record stops every future schedule, which is
    a worse failure than a tick that did nothing. Cancellation is the one way out.
    """
    while True:
        try:
            await tick(owner, call=call)
        except asyncio.CancelledError:
            raise
        except Exception as exc:            # reported, never swallowed in silence
            if on_error is not None:
                on_error(exc)
        await asyncio.sleep(interval)
