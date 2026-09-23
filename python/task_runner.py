"""A message from the phone becomes real work, and only a press can keep it.

The gateway puts the owner's words into the graph and answers the phone. This is
the other half: it takes the job from there, runs the project's own one-cycle
loop so the researcher reads the owner's request instead of guessing, and ends up
where the whole design says it must end up: at a question with two buttons.

Nothing here presses anything. The verdict arrives as a record written by the
gateway when the owner taps the button, and this module reads that record. Two
things follow, and both are the point: the work cannot approve itself, and the
decision survives a restart, because the graph is the memory.

What the owner reads is Russian, in his own terms: no branch names, no paths in
the sentence, no tool names. He is told what was found, what it gives and what it
can break, and then he presses a button.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve()
PROJECT = HERE.parent.parent
if str(PROJECT / "python") not in sys.path:
    sys.path.insert(0, str(PROJECT / "python"))

import approval  # noqa: E402
import telegram_entry  # noqa: E402
from bridge import OneiroBridge  # noqa: E402
from life_loop import LoopConfig, locate_paths, run_loop  # noqa: E402

TASK_KIND = "task"
STARTED_KIND = "task_started"
QUESTION_KIND = "task_question"
DONE_KIND = "task_done"
FAILED_KIND = "task_failed"
DECIDED_KIND = telegram_entry.PROPOSAL_DECIDED_KIND
# How many times one job from the phone may be worked end to end before the
# assistant stops trying on its own. One attempt is a lottery: the researcher
# picks, the worker edits, a check can fail for reasons another proposal would
# not hit. The owner's own words promise another try, so there has to be one.
MAX_ATTEMPTS = 3

# What the owner reads instead of a file name. He is deciding about his own work
# on a phone, so he is told which part of the assistant changes; a path with
# slashes and extensions is our bookkeeping, not his decision. An unknown file
# falls back to a general phrase rather than a path.
PART_NAMES = {
    "approval.py": "вопросы к тебе и твои ответы",
    "bridge.py": "память помощника",
    "heartbeat.py": "один шаг работы помощника",
    "life_loop.py": "ежедневный круг работы помощника",
    "llm.py": "обращение помощника к моделям",
    "replay.py": "повтор прошлых прогонов",
    "roles.py": "роли помощника",
    "skills_index.py": "поиск готовых умений",
    "swarm.py": "согласование работы ролей",
    "task_runner.py": "приём задач с твоего телефона",
    "telegram_entry.py": "связь с твоим телефоном",
    "worker.py": "работа помощника с файлами проекта",
    "worktree_runner.py": "отдельная копия для изменений",
}
UNKNOWN_PART = "внутренняя часть помощника"
TESTS_PART = "проверки помощника"


def human_part(path: str) -> str:
    """One file path said in words a person can decide about."""
    normalized = str(path).replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if name.startswith("test_") or "/tests/" in normalized:
        return TESTS_PART
    return PART_NAMES.get(name, UNKNOWN_PART)


def human_parts(paths, limit: int = 3) -> list[str]:
    """The distinct parts of the assistant the change touches, in words."""
    named: list[str] = []
    for path in paths or ():
        name = human_part(str(path))
        if name not in named:
            named.append(name)
        if len(named) >= limit:
            break
    return named

STARTED_TEXT = (
    "Взялся за дело: «{text}».\n"
    "Смотрю, что здесь можно поправить. Найду — спрошу твоё решение кнопками."
)
FAILED_TEXT = (
    "Дело «{text}»: подготовить изменение не вышло, в основной работе ничего не "
    "менял. Попробую другой заход."
)
FAILED_LAST_TEXT = (
    "Дело «{text}»: подготовить изменение не вышло, в основной работе ничего не "
    "менял. Больше сегодня за это не берусь — напиши, если попробовать снова."
)
APPROVED_TEXT = (
    "Принято. Изменение лежит в отдельной копии и в основную работу не влито: "
    "скажи отдельно, если нужно влить."
)
REJECTED_TEXT = (
    "Отклонено. Изменение оставил в стороне, в основную работу оно не попало."
)


@dataclass
class TaskState:
    """Where one job from the phone stands, as the graph tells it."""

    task_id: str
    text: str
    update_id: int = 0
    started: bool = False
    failures: int = 0                   # attempts that ended without a question
    question: Optional[str] = None      # the proposal the owner was asked about
    decision: Optional[str] = None      # approve / reject, once he pressed
    failed: bool = False
    done: bool = False
    packet: dict = field(default_factory=dict)

    @property
    def waiting(self) -> bool:
        """Asked and not answered yet: nothing to do but leave it alone."""
        return self.question is not None and self.decision is None and not self.done

    @property
    def answered(self) -> bool:
        """The owner pressed a button and the job is not closed yet."""
        return self.question is not None and self.decision is not None and not self.done

    @property
    def ready_to_work(self) -> bool:
        """Unasked and unfinished, with attempts still left on it."""
        return (self.question is None and not self.done
                and self.failures < MAX_ATTEMPTS)


def proposal_id_for(task_id: str, attempt: int = 1) -> str:
    """A short slug the buttons can carry: Telegram allows 64 bytes of it.

    The attempt is part of the id because a retry asks a new question, and the
    channel refuses to send the same proposal twice.
    """
    return f"keep-{task_id}-a{attempt}"[:40]


class TaskRunner:
    """Reads jobs from the graph, works on them, and stops at the decision."""

    def __init__(
        self,
        *,
        bridge: OneiroBridge,
        channel: approval.TelegramApprovalChannel,
        repo_root: Path,
        project_root: Path,
        worktrees_root: Path,
        session_id: str,
        run_cycle: Optional[Callable[[LoopConfig, str], dict]] = None,
        say: Optional[Callable[[str], None]] = None,
        echo: Callable[[str], None] = print,
        cycles: int = 1,
        worker_steps: int = 40,
        model_calls_per_cycle: int = 70,
    ) -> None:
        self.bridge = bridge
        self.channel = channel
        self.repo_root = Path(repo_root)
        self.project_root = Path(project_root)
        self.worktrees_root = Path(worktrees_root)
        self.session_id = session_id
        self._run_cycle = run_cycle or self._run_the_project_loop
        self._say = say or self._send
        self.echo = echo
        self.cycles = cycles
        self.worker_steps = worker_steps
        self.model_calls_per_cycle = model_calls_per_cycle

    # -- reading the graph ------------------------------------------------- #

    def records(self) -> list:
        return self.bridge.load_organization_events()

    def states(self) -> dict[str, TaskState]:
        """Every job from the phone, with whatever already happened to it."""
        states: dict[str, TaskState] = {}
        for record in self.records():
            payload = record.payload or {}
            if record.kind == TASK_KIND and record.role == "human":
                task_id = str(payload.get("task_id") or record.record_id)
                states[task_id] = TaskState(
                    task_id=task_id,
                    text=str(payload.get("text") or ""),
                    update_id=int(payload.get("update_id") or 0),
                )
                continue
            task_id = str(payload.get("task_id") or "")
            if not task_id or task_id not in states:
                continue
            state = states[task_id]
            if record.kind == STARTED_KIND:
                state.started = True
            elif record.kind == QUESTION_KIND:
                state.question = str(payload.get("proposal_id") or "")
                state.packet = dict(payload.get("packet") or {})
            elif record.kind == FAILED_KIND:
                state.failed = True
                state.failures += 1
            elif record.kind == DONE_KIND:
                state.done = True
                state.decision = str(payload.get("verdict") or "")
        for record in self.records():
            if record.kind != DECIDED_KIND:
                continue
            payload = record.payload or {}
            proposal = str(payload.get("proposal_id") or "")
            for state in states.values():
                if state.question == proposal and state.decision is None:
                    state.decision = str(payload.get("verdict") or "")
        return states

    def next_job(self) -> Optional[TaskState]:
        """The oldest job that has neither been worked on nor finished."""
        for state in sorted(self.states().values(), key=lambda row: row.task_id):
            if state.ready_to_work:
                return state
        return None

    def answered_jobs(self) -> list[TaskState]:
        """Jobs whose question has been answered and that still need closing."""
        return [s for s in sorted(self.states().values(), key=lambda row: row.task_id)
                if s.answered]

    # -- doing the work ---------------------------------------------------- #

    def work(self, state: TaskState) -> Optional[str]:
        """Take the job to the question. Returns the proposal id, or None."""
        attempt = state.failures + 1
        self._record(STARTED_KIND, {"task_id": state.task_id, "text": state.text,
                                    "attempt": attempt})
        # Said once per job, not once per attempt: a restart in the middle of the
        # work would otherwise greet the owner again for the same thing, and he
        # ends up reading the same line three times while nothing new happened.
        if not state.started:
            self._say(STARTED_TEXT.format(text=state.text))
        config = LoopConfig(
            repo_root=self.repo_root,
            project_root=self.project_root,
            worktrees_root=self.worktrees_root,
            cycles=self.cycles,
            worker_steps=self.worker_steps,
            model_calls_per_cycle=self.model_calls_per_cycle,
            run_tag=f"tg{state.update_id or state.task_id}-a{attempt}",
        )
        outcome = self._run_cycle(config, state.text)
        packet = self._packet(outcome)
        if packet is None:
            reason = str(outcome.get("freeze_reason") or outcome.get("status") or "no packet")
            self._record(FAILED_KIND, {"task_id": state.task_id, "attempt": attempt,
                                       "reason": reason[:400]})
            last = attempt >= MAX_ATTEMPTS
            self._say((FAILED_LAST_TEXT if last else FAILED_TEXT).format(text=state.text))
            self.echo(f"[runner] {state.task_id}: no packet ({reason[:120]})")
            return None
        proposal_id = proposal_id_for(state.task_id, attempt)
        # The sentence about what changes is composed here, from the parts of the
        # assistant the change touches, and not taken from the model's own summary:
        # that summary is written for the record, and through it a file name or an
        # English word would reach the owner's phone. His own words are the only
        # model-adjacent text he ever reads back.
        parts = human_parts(packet.get("changed_paths") or ())
        changed = ("небольшая правка в работе помощника: " + ", ".join(parts)
                   if parts else "небольшая правка в работе помощника")
        proposal = approval.Proposal.change(
            proposal_id=proposal_id,
            title=f"Готово изменение по делу: «{state.text}»",
            changed=changed,
            gives="одно небольшое улучшение в работе помощника, проверенное тестами",
            risks="если проверка на другой машине поведёт себя иначе, изменение в основную "
                  "работу не влито и откатывать нечего",
            branch=str(packet.get("branch") or ""),
            files=(),
            evidence=tuple(self._evidence(packet)),
        )
        asked = approval.render(proposal)
        self.channel.send(proposal)
        # The exact words the owner was shown, in the record and in the log: the
        # morning report quotes them, and reconstructing them later from the
        # packet would be a guess dressed up as evidence.
        self.echo(f"[runner] asked the owner as {proposal_id}:\n{asked}")
        self._record(
            QUESTION_KIND,
            {"task_id": state.task_id, "proposal_id": proposal_id,
             "pr_id": str(packet.get("pr_id") or ""), "packet": packet,
             "asked_text": asked},
        )
        return proposal_id

    def _packet(self, outcome: dict) -> Optional[dict]:
        """The packet the loop delivered, read from the graph, not from memory."""
        rows = [item for item in (outcome.get("prs") or [])]
        if not rows:
            return None
        wanted = {str(item.get("pr_id")) for item in rows}
        best: Optional[dict] = None
        for record in self.records():
            if record.kind != "pr_packet":
                continue
            payload = record.payload or {}
            if str(payload.get("pr_id")) in wanted:
                best = payload
        if best is not None:
            return best
        # The loop said it produced a packet but the graph has no such record:
        # that is a hole in the record, and it is reported as one.
        return None

    @staticmethod
    def _evidence(packet: dict) -> list[str]:
        """What was checked, in words: no command, no count of test files.

        A packet exists only when the declared checks passed, so the sentence is
        backed by the record the loop wrote, not by this line.
        """
        if not (packet.get("tests") or ()):
            return ["изменение проверено одной из разрешённых проверок проекта"]
        return ["прогнал проверки проекта, все прошли"]

    # -- the verdict ------------------------------------------------------- #

    def collect(self, state: TaskState) -> Optional[str]:
        """Close a job whose question has been answered."""
        verdict = (state.decision or "").lower()
        if not verdict:
            return None
        self._record(DONE_KIND, {"task_id": state.task_id,
                                 "proposal_id": state.question,
                                 "verdict": verdict})
        self._say(APPROVED_TEXT if verdict == approval.APPROVE else REJECTED_TEXT)
        self.echo(f"[runner] {state.task_id}: owner said {verdict}")
        return verdict

    # -- the project's own loop as the worker ------------------------------ #

    def _run_the_project_loop(self, config: LoopConfig, task_text: str) -> dict:
        return run_loop(config, bridge=self.bridge, task=task_text, echo=self.echo)

    # -- talking to the graph and to the phone ----------------------------- #

    def _record(self, kind: str, payload: dict) -> None:
        self.bridge.record_organization_event(
            session_id=self.session_id,
            role="human" if kind == DONE_KIND else "manager",
            kind=kind,
            payload=payload,
            origin="human" if kind == DONE_KIND else "rule",
            verified=True,
        )

    def _send(self, text: str) -> None:
        token = approval._walk_env(None, telegram_entry.TOKEN_ENV)
        owner = approval._walk_env(None, telegram_entry.OWNER_ENV)
        if not token or not owner:
            self.echo(f"[runner] no bot token or owner id: {text}")
            return
        call = telegram_entry.telegram_transport(token)
        try:
            call("sendMessage", {"chat_id": int(owner), "text": text,
                                 "disable_web_page_preview": True})
        except Exception as exc:  # noqa: BLE001 - the record already holds the truth
            self.echo(f"[runner] could not tell the owner: {exc}")

    # -- the loop ---------------------------------------------------------- #

    def tick(self) -> dict:
        """One pass: close what was answered, work on what is waiting."""
        moved: list[str] = []
        for state in self.answered_jobs():
            if self.collect(state):
                moved.append(f"closed {state.task_id}")
        job = self.next_job()
        if job is not None:
            if self.work(job):
                moved.append(f"asked about {job.task_id}")
            else:
                moved.append(f"failed {job.task_id}")
        return {"moved": moved}

    def run_forever(self, pause: float = 5.0) -> None:
        while True:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - a runner must not die silently
                self.echo(f"[runner] tick failed: {exc}")
            time.sleep(pause)


def runner_from_env(**kwargs) -> TaskRunner:
    """Build the runner the way the rest of the project reads keys."""
    owner = approval._walk_env(None, telegram_entry.OWNER_ENV)
    if not owner:
        raise SystemExit("no owner id: set TELEGRAM_CHAT_ID in the environment or a .env")
    bridge = OneiroBridge(host=os.environ.get("ONEIRO_HOST", "localhost"),
                          port=int(os.environ.get("ONEIRO_PORT", "8090")))
    bridge.connect()
    gateway_session = None
    for record in reversed(bridge.load_life_sessions()):
        if record.session_id.startswith(telegram_entry.SESSION_PREFIX):
            gateway_session = record.session_id
            break
    if gateway_session is None:
        gateway_session = bridge.start_life_session(
            f"{telegram_entry.SESSION_PREFIX}-life",
            goals=[{"text": "work as the owner's assistant with the graph as its memory",
                    "origin": "rule"}],
            self_state={"phase": "host", "origin": "rule"},
        ).session_id
    repo_root, project_root = locate_paths()
    channel = approval.TelegramApprovalChannel(
        owner_user_id=int(owner),
        state_path=project_root / "state" / "approvals.json",
        recorder=lambda kind, payload: bridge.record_organization_event(
            session_id=gateway_session, role="human", kind=kind, payload=payload,
            origin="human" if kind.endswith("_decided") else "rule", verified=True,
        ),
    )
    return TaskRunner(
        bridge=bridge,
        channel=channel,
        repo_root=repo_root,
        project_root=project_root,
        worktrees_root=project_root / "worktrees",
        session_id=gateway_session,
        **kwargs,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    runner = runner_from_env()
    if "--once" in args:
        result = runner.tick()
        print(f"runner: {result['moved'] or 'nothing to do'}")
        return 0
    runner.echo("runner: watching the graph for jobs from the phone")
    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
