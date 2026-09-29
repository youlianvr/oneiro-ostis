"""The owner's phone is the way in: plain words become work.

A person who is not a programmer writes the bot in ordinary words. That message
is not a chat line to be answered and forgotten: it is recorded, dated, in the
same graph that holds every other fact about the work, and the job is taken from
there. The graph is the truth, so a task survives the restart of anything else.

This module owns the Telegram connection, and it is the only thing that does.
Telegram moves its update offset on every read, so two independent readers of
the same bot steal each other's updates: the second one never sees what the first
one consumed. Here everything arrives through one place, then splits: a message
is work handed in by the owner, a button press is an answer to a question the
agent already asked, and it goes to the approval channel that owns decisions,
and a written answer to an open question closes that question as free_text.

What the owner reads is English and nothing else (PLAN-V2 decision 6): no tool
names, no field names, no branch names, no trace of how the work is done.
Technical detail (which request failed, which record was written) goes into the
graph and the log, where it belongs, because the person on the phone is deciding
about his own work, not debugging our machinery.

Only the owner's own account hands in work. A stranger is not answered at all:
there is nothing to say to him, and nothing he should learn about this machine.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve()
PROJECT = HERE.parent.parent
if str(PROJECT / "python") not in sys.path:
    sys.path.insert(0, str(PROJECT / "python"))

import approval  # noqa: E402
from bridge import OneiroBridge  # noqa: E402

TOKEN_ENV = approval.TELEGRAM_TOKEN_ENV
OWNER_ENV = approval.TELEGRAM_OWNER_ENV
STATE_PATH = PROJECT / "state" / "telegram-entry.json"
# The same long-lived session the host writes into: one memory, not two. The
# constant is repeated from ``host/ostis_mcp.py`` on purpose, so a change there
# is visible here rather than silently splitting the record in half.
SESSION_PREFIX = "host-cowagent"
TASK_KIND = "task"
PROPOSAL_SENT_KIND = "proposal_sent"
PROPOSAL_DECIDED_KIND = "proposal_decided"
# How many accepted messages are remembered by id. Telegram re-sends an update
# until its offset is confirmed, so the same message can arrive twice after a
# crash; past this many, the graph itself is the duplicate check.
REMEMBERED_UPDATES = 200


# --------------------------------------------------------------------------- #
# the words the owner reads
# --------------------------------------------------------------------------- #

HELP_TEXT = (
    "Hello. I am the assistant: I work on this computer and remember everything I "
    "have done, as records of the work.\n"
    "Write in plain words what needs to be done. I will take it on and tell you "
    "when I reach the point where your decision is needed."
)
TAKEN_TEXT = (
    "Taken on: \u201c{text}\u201d.\n"
    "If your decision is needed, I will ask with buttons right here."
)
ANSWERED_TEXT = (
    "Answer received, the question is closed: \u201c{text}\u201d.\n"
    "I did not press the button: words alone change nothing."
)
DUPLICATE_TEXT = "I already accepted this message and will not take it twice."
EMPTY_TEXT = "There is no text in the message. Write in words what needs doing."
NOTHING_TO_DO = "Nothing is in work right now."
IN_WORK_HEAD = "In work right now:"
IN_WORK_LINE = "\u2022 {text}"
TROUBLE_TEXT = (
    "I could not accept the task: my memory is not answering right now. "
    "I will try again in a minute."
)

HELP_WORDS = {"/start", "/help", "help", "start"}
LIST_WORDS = {"/tasks", "/what", "tasks", "what's in progress", "what is in progress"}


class EntryError(RuntimeError):
    """A failure with two faces: one for the log, one for the phone.

    The technical line goes into the graph and the log; the human line is what
    the owner reads, and it never names a request, a field or a tool.
    """

    def __init__(self, technical: str, human: str = "") -> None:
        super().__init__(technical)
        self.technical = technical
        self.human = human or TROUBLE_TEXT


@dataclass(frozen=True)
class IncomingTask:
    """One thing the owner asked for, as it arrived from his account."""

    update_id: int
    text: str
    at: int
    by_user_id: int
    task_id: str = ""

    def __post_init__(self) -> None:
        if not self.task_id:
            object.__setattr__(self, "task_id", f"task-{self.update_id}")


@dataclass
class EntryRun:
    """What one pass over the owner's messages did."""

    tasks: list[IncomingTask] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    ignored: list[dict] = field(default_factory=list)
    decisions: list = field(default_factory=list)
    refusals: list[dict] = field(default_factory=list)
    text_answers: list = field(default_factory=list)
    next_offset: Optional[int] = None


def telegram_transport(token: str, timeout: float = 20.0) -> Callable[[str, dict], dict]:
    """A Bot API call as a plain function, so tests hand in their own."""

    def call(method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{token}/{method}"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise EntryError(f"telegram {method} failed: {exc.code} {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EntryError(f"telegram {method} unreachable: {exc}") from exc

    return call


class TelegramGateway:
    """One connection, two directions: work in, answers out.

    The gateway does not do any work itself. It records the task and answers the
    phone; the agent picks the task up from the graph, and the verdict comes back
    as an answer to a question the agent asked through the approval channel.
    """

    def __init__(
        self,
        *,
        owner_user_id: int,
        token: Optional[str] = None,
        chat_id: Optional[int] = None,
        transport: Optional[Callable[[str, dict], dict]] = None,
        state_path: Optional[Path] = None,
        channel: Optional[approval.TelegramApprovalChannel] = None,
        bridge: Optional[OneiroBridge] = None,
        now: Callable[[], int] = lambda: int(time.time()),
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        resolved = token or approval._walk_env(None, TOKEN_ENV)
        if not resolved and transport is None:
            raise EntryError(f"no bot token: set {TOKEN_ENV} or pass one")
        self.owner_user_id = int(owner_user_id)
        self.chat_id = int(chat_id) if chat_id is not None else self.owner_user_id
        self._call = transport or telegram_transport(resolved or "")
        self.state_path = Path(state_path) if state_path else STATE_PATH
        self._bridge = bridge
        self._session: Optional[str] = None
        self._now = now
        self._log = logger
        self._offset: Optional[int] = None
        self._accepted: dict[str, str] = {}
        self._load()
        # The approval channel answers questions; the gateway reads the presses
        # and hands them over, so decisions stay in one place with one record.
        self.channel = channel or self._build_channel()

    # -- state ------------------------------------------------------------- #

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt state file must not replay old messages as new work.
            return
        offset = state.get("offset")
        self._offset = int(offset) if offset else None
        self._accepted = {str(k): str(v) for k, v in (state.get("accepted") or {}).items()}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        accepted = list(self._accepted.items())[-REMEMBERED_UPDATES:]
        payload = {"offset": self._offset, "accepted": dict(accepted)}
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    # -- the graph --------------------------------------------------------- #

    def graph(self) -> OneiroBridge:
        if self._bridge is None:
            self._bridge = OneiroBridge()
            self._bridge.connect()
        return self._bridge

    def session_id(self) -> str:
        """The long-lived session the whole host writes into, created once."""
        if self._session:
            return self._session
        bridge = self.graph()
        try:
            for record in reversed(bridge.load_life_sessions()):
                if record.session_id.startswith(SESSION_PREFIX):
                    self._session = record.session_id
                    return self._session
        except Exception as exc:  # the graph is the truth; failing silently would lie
            raise EntryError(f"could not read sessions from the graph: {exc}") from exc
        created = bridge.start_life_session(
            f"{SESSION_PREFIX}-life",
            goals=[{"text": "work as the owner's assistant with the graph as its memory",
                    "origin": "rule"}],
            self_state={"phase": "host", "origin": "rule"},
        )
        self._session = created.session_id
        return self._session

    def tasks(self) -> list[dict]:
        """Every task handed in, oldest first, straight from the graph."""
        found: list[dict] = []
        try:
            records = self.graph().load_organization_events()
        except Exception as exc:
            raise EntryError(f"could not read the graph: {exc}") from exc
        for record in records:
            if record.kind != TASK_KIND or record.role != "human":
                continue
            payload = record.payload or {}
            found.append(
                {
                    "task_id": str(payload.get("task_id") or record.record_id),
                    "text": str(payload.get("text") or ""),
                    "at": int(payload.get("at") or record.recorded_at or 0),
                    "update_id": int(payload.get("update_id") or 0),
                }
            )
        return found

    def record_task(self, task: IncomingTask) -> str:
        """Write the task down. The same message is never recorded twice."""
        if not task.text.strip():
            raise EntryError("refusing to record an empty task")
        if self._is_recorded(task):
            return task.task_id
        bridge = self.graph()
        bridge.record_organization_event(
            session_id=self.session_id(),
            role="human",
            kind=TASK_KIND,
            payload={
                "task_id": task.task_id,
                "text": task.text.strip(),
                "at": task.at,
                "update_id": task.update_id,
                "channel": "telegram",
            },
            origin="human",
            verified=True,
            record_id=f"{TASK_KIND}-{task.task_id}",
        )
        return task.task_id

    def _is_recorded(self, task: IncomingTask) -> bool:
        try:
            return any(row["task_id"] == task.task_id for row in self.tasks())
        except EntryError:
            # The graph is unreachable. The caller must not answer "taken",
            # because nothing was taken: the honest path is the error message.
            raise

    # -- reading Telegram -------------------------------------------------- #

    def poll(self, limit: int = 50) -> EntryRun:
        """Read everything waiting, split it, and answer the phone.

        Messages become tasks; button presses go to the approval channel, which
        alone decides who may answer and which proposal is still open.
        """
        answer = self._call(
            "getUpdates",
            {
                "offset": self._offset,
                "limit": limit,
                "timeout": 0,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        if not answer.get("ok"):
            raise EntryError(f"Telegram refused the read: {answer.get('description')}")
        updates = answer.get("result") or []
        run = EntryRun()
        for update in updates:
            update_id = int(update.get("update_id") or 0)
            if update_id:
                run.next_offset = max(run.next_offset or 0, update_id + 1)
        presses = [u for u in updates if u.get("callback_query")]
        if presses and self.channel is not None:
            decided = self.channel.handle_presses(presses)
            run.decisions.extend(decided.decisions)
            run.refusals.extend(decided.refusals)
        for update in updates:
            message = update.get("message")
            if not message:
                continue
            self._handle_message(message, run)
        self._offset = run.next_offset or self._offset
        self._save()
        return run

    def prime(self) -> Optional[int]:
        """On the very first start, forget whatever was waiting before it.

        A bot that has been off for a day wakes up with a queue, and nothing in it
        was handed in just now: treating the queue as fresh work would bury the
        owner in stale tasks. The offset jumps to the newest id instead. Do this
        only when there is no remembered offset, and start the gateway before
        asking a question, because priming also drops a press that arrived while
        nothing was listening.
        """
        answer = self._call(
            "getUpdates",
            {"offset": -1, "limit": 1, "timeout": 0,
             "allowed_updates": ["message", "callback_query"]},
        )
        if not answer.get("ok"):
            raise EntryError(f"Telegram refused the first read: {answer.get('description')}")
        rows = answer.get("result") or []
        if rows:
            newest = max(int(row.get("update_id") or 0) for row in rows)
            self._offset = newest + 1
            self._save()
        return self._offset

    def _handle_message(self, message: dict, run: EntryRun) -> None:
        update_id = int(message.get("message_id") or 0)
        by_user = int(((message.get("from") or {}).get("id")) or 0)
        text = (message.get("text") or "").strip()
        if by_user != self.owner_user_id:
            # A stranger gets no answer at all. The refusal is recorded locally
            # so the owner can see somebody tried, without schooling the sender.
            run.ignored.append({"reason": "not_the_owner", "by_user_id": by_user})
            self._note("entry_refused", {"reason": "not_the_owner", "by_user_id": by_user})
            return
        if update_id and str(update_id) in self._accepted:
            run.replies.append(self.say(DUPLICATE_TEXT))
            return
        if not text:
            run.replies.append(self.say(EMPTY_TEXT, message=message))
            return
        lowered = text.lower()
        if lowered in HELP_WORDS or lowered.rstrip("!") in HELP_WORDS:
            run.replies.append(self.say(HELP_TEXT, message=message))
            return
        if lowered in LIST_WORDS:
            run.replies.append(self.say(self.list_text(), message=message))
            return
        routed = self._route_to_open_question(text, update_id, by_user, run)
        if routed:
            return
        task = IncomingTask(update_id=update_id, text=text, at=self._now(),
                            by_user_id=by_user)
        try:
            self.record_task(task)
        except EntryError as exc:
            self._log_line(f"entry: could not record task: {exc.technical}")
            self._note("entry_failed", {"reason": exc.technical[:200], "update_id": update_id})
            run.replies.append(self.say(exc.human, message=message))
            return
        self._accepted[str(update_id)] = task.task_id
        self._save()
        run.tasks.append(task)
        run.replies.append(self.say(TAKEN_TEXT.format(text=task.text), message=message))
        self._note("task_taken", {"task_id": task.task_id, "update_id": update_id,
                                  "at": task.at})

    def _route_to_open_question(self, text: str, update_id: int, by_user: int,
                                run: EntryRun) -> bool:
        """A written answer closes the open question it belongs to.

        Words are context, never a verdict: the question closes as ``free_text``,
        what the owner said travels to the manager both as the question's answer
        and as an ordinary conversation turn, and nothing here becomes a task.
        Only a button press can ever approve.
        """
        if self.channel is None:
            return False
        try:
            open_ids = self.channel.open_proposals()
        except approval.ApprovalError as exc:
            self._log_line(f"entry: could not read open questions: {exc}")
            return False
        if not open_ids:
            return False
        proposal_id = open_ids[-1]
        try:
            answer = self.channel.answer_with_text(
                proposal_id, text, by_user_id=by_user, at=self._now()
            )
        except approval.ApprovalError as exc:
            # Not the owner, or the question closed in the same batch: fall
            # through so the words are not swallowed by a closed door.
            self._log_line(f"entry: text refused for {proposal_id}: {exc}")
            return False
        self._accepted[str(update_id)] = f"{proposal_id}:{update_id}"
        self._save()
        run.text_answers.append(answer)
        run.replies.append(self.say(ANSWERED_TEXT.format(text=text), message=None))
        self._note("question_answered_text", {
            "proposal_id": proposal_id, "update_id": update_id,
            "outcome": answer.outcome, "at": answer.at,
        })
        return True

    def list_text(self) -> str:
        rows = self.tasks()
        if not rows:
            return NOTHING_TO_DO
        lines = [IN_WORK_HEAD]
        for row in rows[-10:]:
            lines.append(IN_WORK_LINE.format(text=row["text"]))
        return "\n".join(lines)

    # -- answering the phone ------------------------------------------------ #

    def say(self, text: str, message: Optional[dict] = None) -> str:
        """Send one owner-facing line to the phone. Returns the text that was sent."""
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if message is not None:
            payload["reply_to_message_id"] = int(message.get("message_id") or 0)
        try:
            answer = self._call("sendMessage", payload)
        except EntryError as exc:
            # The reply is cosmetic compared with the task: the work is already
            # recorded, so a failed answer is logged, not raised.
            self._log_line(f"entry: the reply did not go out: {exc.technical}")
            return text
        if not answer.get("ok"):
            self._log_line(f"entry: Telegram refused the reply: {answer.get('description')}")
        return text

    def _build_channel(self) -> Optional[approval.TelegramApprovalChannel]:
        owner = approval._walk_env(None, OWNER_ENV)
        if not owner:
            return None
        # One connection, shared with the gateway: the channel must not open its
        # own, or the two readers start stealing updates from each other.
        return approval.TelegramApprovalChannel(
            owner_user_id=int(owner),
            transport=self._call,
            state_path=PROJECT / "state" / "approvals.json",
            recorder=self._note,
        )

    def _note(self, kind: str, payload: dict) -> None:
        """Every step leaves a record: the graph is what the next session reads."""
        try:
            bridge = self.graph()
            bridge.record_organization_event(
                session_id=self.session_id(),
                role="human" if kind.endswith(("_decided", "_taken")) else "agent",
                kind=kind,
                payload=payload,
                origin="human" if kind.endswith("_decided") else "rule",
                verified=True,
            )
        except Exception as exc:
            self._log_line(f"entry: could not record \"{kind}\": {exc}")

    def _log_line(self, line: str) -> None:
        if self._log is not None:
            self._log(line)
            return
        print(line, file=sys.stderr, flush=True)

    # -- the loop ----------------------------------------------------------- #

    def run_once(self, limit: int = 50) -> EntryRun:
        return self.poll(limit=limit)

    def run_forever(self, pause: float = 2.0) -> None:
        """Watch the phone until stopped. Nothing here touches the graph records."""
        while True:
            try:
                self.run_once()
            except EntryError as exc:
                self._log_line(f"entry: failure in the loop: {exc.technical}")
            time.sleep(pause)


def gateway_from_env(**kwargs) -> TelegramGateway:
    """Build the gateway the way the rest of the project reads keys."""
    owner = approval._walk_env(None, OWNER_ENV)
    if not owner:
        raise EntryError(
            f"no owner id: set {OWNER_ENV} in the environment or a .env above {PROJECT}",
            human="The assistant is not configured: I do not know whose messages to accept.",
        )
    return TelegramGateway(owner_user_id=int(owner), **kwargs)


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    once = "--once" in args
    try:
        gateway = gateway_from_env()
    except EntryError as exc:
        print(f"Failure: {exc.technical}", file=sys.stderr)
        return 1
    if "--prime" in args:
        offset = gateway.prime()
        print(f"first read done, message offset: {offset}")
        return 0
    if once:
        run = gateway.run_once()
        print(f"tasks taken: {len(run.tasks)}  ignored: {len(run.ignored)}  "
              f"decided: {len(run.decisions)}  refusals: {len(run.refusals)}")
        return 0
    if gateway._offset is None:
        gateway.prime()
    gateway._log_line("entry: watching for your messages")
    gateway.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
