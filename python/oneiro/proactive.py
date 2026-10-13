"""What Oneiro says first: the digest when the quiet hours end, one reminder after that.

Two moments, and neither is a clock of its own. `tick` is called by the scheduler's
own tick (`schedule.tick`), so one process, one timer and one place decide when a
proactive moment has arrived — a second timer would be a second answer to "when does
Oneiro speak", and the two would eventually disagree.

**The digest belongs to a quiet window, and one window gets one digest.** It is said
at the first tick at or after the window ends, and it names what finished inside that
window, what did not, and what is still open. A process that was not running when the
window ended says it at the next tick instead of dropping the morning, and the same
date never says it twice: the notice carries a key made from the window's end, so a
second ask reads the first answer back (`tasks.notice_id`).

**A reminder is said once per unfinished item, and only while nobody has answered it.**
An item is unfinished while its own state is `queued`, `waiting`, `uncertain` or
`failed` — the four states in which the owner's word, not persistence, is what carries
it further. It is reminded when it has stayed unfinished for `initiative.reminder_after`
minutes and no owner message has been written in that item's conversation since. Once
the item is finished, nothing more is said about it; the reminder that was already said
is never said again.

**Both are notices, and both respect the quiet hours.** They are published through
`tasks.notify`: the same record shape as a finished attempt's notice, in a conversation,
labelled `notice`, and labelled `held` inside the quiet window — stored either way,
because the memory is the truth, and the label is what tells the window not to
interrupt the owner. The digest is said in the owner's own conversation (`main`), so a
channel that carries that conversation carries the digest too; a reminder is said in the
item's own conversation, beside the notices about that item.

**Neither speaks up below `proactive`.** That is what the level means: `off` and
`on_command` let only the owner's word start anything, and `scheduled` adds the tasks
put on a schedule. Both here are Oneiro speaking first, so anything below `proactive`
is named as held back — with the reason — rather than silently skipped.

The notices are written in one language, as a finished attempt's notice always has
been; what a screen shows around them is localized in `i18n`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from oneiro import config, recall, tasks
from oneiro.query import GraphQueryError
from oneiro.records import ConversationMessage, State

MESSAGE = ConversationMessage.KIND
#: The conversation the digest is said in: the owner's own chat. A reminder is said in
#: `task-<id>`, beside the other notices about that item.
DIGEST_CONVERSATION = "main"
#: The id prefix a reminder's key uses, so a reader can tell the two apart.
REMIND_KEY = "remind-"
#: The labels the two carry, on top of `notice`: a reader can tell a digest from a
#: reminder without guessing at an id, and a check can find them without one either.
DIGEST_LABEL = "digest"
REMINDER_LABEL = "reminder"
#: How many messages of an item's conversation are read to see whether the owner has
#: answered it. The newest are enough: any owner message after the item's last state is
#: an answer, and the walk stops at the newest stored ones either way.
SILENCE_MESSAGES = 20
#: The four states in which an item is unfinished: the owner's word, not persistence, is
#: what carries it further. `running` is not here: an attempt in flight is being worked,
#: not waiting to be remembered.
UNFINISHED = (State.QUEUED.value, State.WAITING.value, State.UNCERTAIN.value,
              State.FAILED.value)


# ---------- what the owner declared ----------


def digest_switch() -> bool | None:
    """Whether the morning digest is on, or None when the setting cannot be read.

    None is not False: a switch nobody can read must not be reported as the owner
    having turned it off, so the caller says which of the two it was.
    """
    try:
        return bool(config.value("initiative.digest"))
    except ValueError:
        return None


def reminder_switch() -> bool | None:
    """Whether a repeat reminder may be said, or None when it cannot be read."""
    try:
        return bool(config.value("initiative.reminders"))
    except ValueError:
        return None


def reminder_minutes() -> int | None:
    """How long an item may stay unfinished before it is reminded, or None.

    A value that cannot be read — a hand-edited file the settings reader refuses — means
    no reminder: a silence the owner did not ask for is worse than a reminder that waits
    for a readable setting. The declared minimum is one minute: a reminder with no wait at
    all would not be about an item that waited.
    """
    try:
        value = int(config.value("initiative.reminder_after"))
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def _gate() -> str:
    """Why Oneiro may not speak first right now, or an empty string."""
    level = tasks.level()
    if tasks.speaks_up(level):
        return ""
    return (f"initiative is {level}: Oneiro does not speak up first, so neither the "
            f"digest nor a reminder is said")


# ---------- the quiet window ----------


def window_end(window: tuple[int, int], at: datetime) -> datetime:
    """The moment the quiet window named by `window` ends on this date."""
    return at.replace(hour=window[1] // 60, minute=window[1] % 60, second=0, microsecond=0)


def window_start(window: tuple[int, int], end: datetime) -> datetime:
    """When that window began: earlier the same day, or the evening before.

    With `22:00-09:00` the window that ends at 09:00 began at 22:00 the day before,
    which is what makes the digest cover the whole quiet period and not just its
    morning half.
    """
    start = end.replace(hour=window[0] // 60, minute=window[0] % 60, second=0, microsecond=0)
    return start if start <= end else start - timedelta(days=1)


def digest_window(window: tuple[int, int], at: datetime) -> tuple[datetime, datetime] | None:
    """The quiet window this moment reports on, or None when none has ended recently.

    Once the quiet hours have ended on this date, that window is the one to report —
    late, if the process was not running when they ended, but never missing. While they
    are still running, the previous date's window is reported only if its own awake span
    has not passed: a digest two days late is not a morning digest, it is noise, and the
    honest answer for it is that the period is not reported rather than that it "did not
    happen".
    """
    end = window_end(window, at)
    if at >= end:
        return window_start(window, end), end
    previous_end = end - timedelta(days=1)
    previous_start = window_start(window, previous_end)
    if at < previous_start + timedelta(days=1):
        return previous_start, previous_end
    return None


# ---------- reading what the records say ----------


def _when(value: Any) -> datetime | None:
    """One stored instant, or None when it cannot be read as one."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _order(snapshot_state: tasks.Snapshot) -> list[str]:
    """Task ids oldest first, the way they were asked for."""
    return sorted(snapshot_state.tasks,
                  key=lambda tid: (snapshot_state.tasks[tid]["created_at"],
                                   int(snapshot_state.tasks[tid].get("__sequence__") or 0)))


def _in_period(snapshot_state: tasks.Snapshot, start: datetime, end: datetime
               ) -> tuple[list[str], list[str]]:
    """Tasks whose newest attempt inside the period finished, and those that did not.

    One line per task: the attempt that counts is the newest one inside the window, so
    a task that failed and was then finished by a later attempt is reported as done
    rather than listed twice.
    """
    finished: list[str] = []
    stuck: list[str] = []
    for task_id in _order(snapshot_state):
        title = str(snapshot_state.tasks[task_id].get("title") or task_id)
        runs = sorted(snapshot_state.runs.get(task_id, ()),
                      key=lambda row: int(row.get("attempt") or 1), reverse=True)
        for row in runs:
            moment = _when(row.get("updated_at"))
            if moment is None or not start <= moment <= end:
                continue
            state = str(row.get("state") or "")
            if state == State.COMPLETED.value:
                finished.append(title)
            elif state in (State.FAILED.value, State.UNCERTAIN.value):
                stuck.append(title)
            break
    return finished, stuck


def _open_now(snapshot_state: tasks.Snapshot,
              resolved: dict[str, tuple[str, str]]) -> list[str]:
    """Every item still unfinished, by title, in the order it was asked for."""
    return [str(snapshot_state.tasks[task_id].get("title") or task_id)
            for task_id in _order(snapshot_state)
            if resolved[task_id][0] in UNFINISHED]


async def _answered_since(owner: Any, conversation_id: str, moment: datetime) -> bool:
    """Whether the owner has written in this item's conversation since that moment."""
    found = await recall.history(owner, conversation_id, limit=SILENCE_MESSAGES,
                                 exclude_id=None)
    for row in found.rows:
        if row.get("role") != "owner":
            continue
        spoken = _when(row.get("updated_at")) or _when(row.get("created_at"))
        if spoken is not None and spoken > moment:
            return True
    return False


async def _said(owner: Any, conversation_id: str, key: str, moment: datetime
                ) -> dict[str, Any] | None:
    """The notice this key already carries, if it was said.

    One walk of one record, so it is paid on every tick: the walk stops at the first
    page (the notice asked for is the newest of its conversation) which is why the
    already-said answer is cheap — and it has to be, because an already-said answer is
    what every tick after the quiet hours end gets.
    """
    return await recall.latest(owner, MESSAGE,
                              tasks.notice_id(conversation_id, "", moment, key))


def _answer(existing: dict[str, Any]) -> dict[str, Any]:
    """A stored notice, read as the answer that was already given."""
    return {"said": False, "already": True, "id": str(existing.get("id") or ""),
            "text": str(existing.get("text") or ""), "at": str(existing.get("updated_at") or ""),
            "held": tasks.HELD in (existing.get("labels") or ()), "duplicate": True}


async def _say(owner: Any, conversation_id: str, text: str, *, at: datetime, key: str,
               label: str) -> dict[str, Any]:
    """Say one keyed notice once, or read back the answer that is already stored.

    Two ticks in the same moment cannot both write it: the store refuses a repeated key
    with different content, and that refusal is evidence the answer exists — so the
    record is read back and reported rather than raised out of a tick. A refusal with
    nothing stored under the key is passed on, because then it is not a duplicate, it is
    a defect, and a tick that hides it would be the worse outcome.
    """
    existing = await _said(owner, conversation_id, key, at)
    if existing is not None:
        return _answer(existing)
    try:
        written = await tasks.notify(owner, conversation_id, text, at=at, key=key,
                                     labels=(label,))
    except GraphQueryError:
        written_anyway = await _said(owner, conversation_id, key, at)
        if written_anyway is None:
            raise
        return _answer(written_anyway)
    return {"said": not written["duplicate"], "already": written["duplicate"],
            "id": str(written["record"]["id"]), "text": text, "held": written["held"],
            "at": str(written["record"].get("updated_at") or ""),
            "duplicate": written["duplicate"]}


# ---------- what the owner reads ----------


def digest_text(quiet: str, finished: list[str], stuck: list[str],
                open_now: list[str]) -> str:
    """The digest: what happened while the owner was quiet, and what is open now.

    Deterministic for a closed window, because the record it becomes is read back
    rather than rewritten: the same period always reads the same way.
    """
    lines = [f"While you were quiet ({quiet}): {len(finished)} finished, "
             f"{len(stuck)} did not."]
    lines += [f"- done: {title}" for title in finished]
    lines += [f"- did not finish: {title}" for title in stuck]
    still_open = [title for title in open_now if title not in stuck]
    if still_open:
        lines.append(f"Still open: {len(still_open)}: " + ", ".join(still_open))
    return "\n".join(lines)[:tasks.NOTES_CHARS]


def reminder_text(title: str, why: str, waited_minutes: int) -> str:
    """One reminder: what is unfinished, why, and how long it has waited."""
    return (f"Still unfinished: {title}\n{why} — {waited_minutes} minute(s) without "
            f"an answer.")[:tasks.NOTES_CHARS]


# ---------- the two moments ----------


async def digest(owner: Any, *, at: datetime | None = None) -> dict[str, Any]:
    """The one word about the quiet hours that have ended, or why there is none.

    Read before written: a notice with this window's key is one answer to this window,
    and the store refuses a repeated operation ID whose content differs — so the record
    that exists is read back rather than built again from whatever the records say now.
    """
    moment = (at or tasks.utcnow()).astimezone()
    blocked = _gate()
    if blocked:
        return {"said": False, "why": blocked}
    declared = tasks.declared_quiet_hours()
    window = tasks.quiet_window()
    if window is None:
        return {"said": False, "why": (
            f"the quiet hours {declared!r} cannot be read, so no quiet period is known"
            if declared else
            "quiet hours are not set, so there is no quiet period to report on")}
    covered = digest_window(window, moment)
    if covered is None:
        return {"said": False, "why": (
            f"the quiet hours {declared} have not ended yet; nothing is said about them "
            f"before {window_end(window, moment).isoformat(timespec='minutes')}")}
    start, end = covered
    if start == end:
        return {"said": False, "why": (f"the quiet hours {declared} name no length, so "
                                       f"there is no period to report on")}
    allowed = digest_switch()
    if allowed is None:
        return {"said": False, "why": ("the morning digest setting cannot be read, so "
                                       "nothing is said")}
    if not allowed:
        return {"said": False, "why": "the morning digest is switched off in the settings"}
    # Read before anything else is walked: after the quiet hours end, every tick asks
    # this question, and the answer is "already said" until the next window ends — so
    # the honest cheap answer has to come before the report that costs a whole snapshot.
    key = f"digest-{end:%Y%m%d}"
    told = await _said(owner, DIGEST_CONVERSATION, key, moment)
    if told is not None:
        return {**_answer(told),
                "why": (f"the quiet hours {declared} that ended "
                        f"{end.isoformat(timespec='minutes')} were already reported "
                        f"at {told['updated_at']}")}
    snapshot_state = await tasks.snapshot(owner)
    resolved = tasks.states(snapshot_state)
    finished, stuck = _in_period(snapshot_state, start, end)
    text = digest_text(declared, finished, stuck, _open_now(snapshot_state, resolved))
    written = await _say(owner, DIGEST_CONVERSATION, text, at=moment, key=key,
                         label=DIGEST_LABEL)
    return {**written, "conversation_id": DIGEST_CONVERSATION, "finished": finished,
            "stuck": stuck, "quiet": declared,
            "period": [start.isoformat(timespec="minutes"),
                       end.isoformat(timespec="minutes")], "why": ""}


async def reminders(owner: Any, *, at: datetime | None = None) -> dict[str, Any]:
    """One reminder per unfinished item nobody has answered, and never a second one."""
    moment = (at or tasks.utcnow()).astimezone()
    nothing: dict[str, Any] = {"said": [], "considered": 0, "held_back": []}
    blocked = _gate()
    if blocked:
        return {**nothing, "why": blocked}
    allowed = reminder_switch()
    if allowed is None:
        return {**nothing, "why": "the repeat reminder setting cannot be read, so nothing "
                                 "is reminded"}
    if not allowed:
        return {**nothing, "why": "the repeat reminder is switched off in the settings"}
    delay = reminder_minutes()
    if delay is None:
        return {**nothing, "why": "the reminder delay cannot be read, so nothing is reminded"}
    snapshot_state = await tasks.snapshot(owner)
    resolved = tasks.states(snapshot_state)
    said: list[dict[str, Any]] = []
    held_back: list[str] = []
    considered = 0
    for task_id in _order(snapshot_state):
        state, why = resolved[task_id]
        if state not in UNFINISHED:
            continue
        considered += 1
        row = snapshot_state.tasks[task_id]
        conversation = f"task-{task_id}"
        key = REMIND_KEY + task_id
        raised = _when(row.get("updated_at")) or moment
        waited = moment - raised
        if waited < timedelta(minutes=delay):
            held_back.append(f"{task_id}: unfinished for "
                             f"{int(waited.total_seconds() // 60)} of {delay} minute(s)")
            continue
        if await _answered_since(owner, conversation, raised):
            held_back.append(f"{task_id}: you answered it, so nothing is repeated")
            continue
        minutes = int(waited.total_seconds() // 60)
        text = reminder_text(str(row.get("title") or task_id), why, minutes)
        written = await _say(owner, conversation, text, at=moment, key=key,
                            label=REMINDER_LABEL)
        if written["already"]:
            held_back.append(f"{task_id}: already reminded at {written['at']}")
            continue
        said.append({"task_id": task_id, "state": state, "text": written["text"],
                     "held": written["held"], "id": written["id"],
                     "already": written["already"], "waited_minutes": minutes,
                     "conversation_id": conversation})
    return {"said": said, "considered": considered, "held_back": held_back,
            "why": "" if said else ("nothing is unfinished" if not considered
                                    else "no unfinished item is due a reminder")}


async def tick(owner: Any, *, at: datetime | None = None) -> dict[str, Any]:
    """One look at the clock for what Oneiro says first.

    The digest before the reminder: the morning's summary, then the nudge about what
    is still open. Both are skipped, with the reason, whenever the level does not let
    Oneiro speak first.
    """
    moment = (at or tasks.utcnow()).astimezone()
    report: dict[str, Any] = {"at": moment.isoformat(timespec="minutes"),
                              "level": tasks.level(), "digest": None, "reminders": None,
                              "why": ""}
    blocked = _gate()
    if blocked:
        report["why"] = blocked
        return report
    report["digest"] = await digest(owner, at=moment)
    report["reminders"] = await reminders(owner, at=moment)
    return report
