"""Asking the human, where only the human can answer.

A proposal is one improvement the agent wants to make to itself: a branch, a
short human explanation, and the evidence it produced. The channel renders it
with exactly two buttons. A decision exists only as a button press made from
the owner's own account: there is no text path, no model path, and no second
press. The bot cannot answer its own question, and a decision survives a
restart because it is written to disk and to the graph.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

CALLBACK_NAMESPACE = "oneiro"
APPROVE = "approve"
REJECT = "reject"
VERDICTS = (APPROVE, REJECT)
MAX_CALLBACK_BYTES = 64
PROPOSAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "approvals.json"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_OWNER_ENV = "TELEGRAM_CHAT_ID"


class ApprovalError(RuntimeError):
    """The channel refused to do something that would have been dishonest."""


CHANGE = "change"
ACTION = "action"
KINDS = (CHANGE, ACTION)


@dataclass(frozen=True)
class Proposal:
    """One thing waiting for a human answer, in the words that person needs.

    Two kinds share the same answer path. A *change* is the agent editing itself:
    it has a branch and a risk of breaking code. An *action* is the agent doing
    something in the world on the owner's behalf (writing a row into a database,
    filing a letter, moving documents) and it has a target instead of a branch,
    because what is at stake is where the effect lands, not which files changed.
    """

    proposal_id: str
    title: str
    changed: str
    gives: str
    risks: str
    branch: str = ""
    files: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    kind: str = CHANGE
    target: str = ""

    def __post_init__(self) -> None:
        if not PROPOSAL_ID_PATTERN.match(self.proposal_id or ""):
            raise ApprovalError(
                f"proposal id must be a short slug, got {self.proposal_id!r}"
            )
        if self.kind not in KINDS:
            raise ApprovalError(f"unknown proposal kind {self.kind!r}")
        for name in ("title", "changed", "gives", "risks"):
            value = getattr(self, name)
            if not value or not value.strip():
                raise ApprovalError(f"proposal {self.proposal_id}: {name} is empty")
        if self.kind == CHANGE and not (self.branch or "").strip():
            raise ApprovalError(f"proposal {self.proposal_id}: a change needs a branch")
        if self.kind == CHANGE and self.target:
            raise ApprovalError(f"proposal {self.proposal_id}: a change has no target")
        if self.kind == ACTION and not (self.target or "").strip():
            raise ApprovalError(
                f"proposal {self.proposal_id}: an action must name where it lands"
            )
        if self.kind == ACTION and self.branch:
            raise ApprovalError(f"proposal {self.proposal_id}: an action has no branch")

    @classmethod
    def change(cls, *, proposal_id, title, changed, gives, risks, branch,
               files=(), evidence=()) -> "Proposal":
        return cls(proposal_id=proposal_id, title=title, changed=changed, gives=gives,
                   risks=risks, branch=branch, files=tuple(files),
                   evidence=tuple(evidence), kind=CHANGE)

    @classmethod
    def action(cls, *, proposal_id, title, found, proposed, needed, target,
               evidence=()) -> "Proposal":
        """A question about doing something in the world, before it is done."""
        return cls(proposal_id=proposal_id, title=title, changed=found, gives=proposed,
                   risks=needed, target=target, evidence=tuple(evidence), kind=ACTION)

    def callback_data(self, verdict: str) -> str:
        if verdict not in VERDICTS:
            raise ApprovalError(f"unknown verdict {verdict!r}")
        data = f"{CALLBACK_NAMESPACE}:{verdict}:{self.proposal_id}"
        if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
            raise ApprovalError("callback data exceeds the Telegram limit")
        return data


@dataclass(frozen=True)
class Decision:
    proposal_id: str
    verdict: str
    by_user_id: int
    at: int
    message_id: Optional[int] = None

    @property
    def approved(self) -> bool:
        return self.verdict == APPROVE


@dataclass
class PollResult:
    decisions: list[Decision] = field(default_factory=list)
    refusals: list[dict] = field(default_factory=list)
    next_offset: Optional[int] = None


def render(proposal: Proposal) -> str:
    """The message the owner reads: plain words, no jargon, no promises."""
    if proposal.kind == ACTION:
        lines = [
            f"{proposal.title}",
            "",
            f"Что я нашёл: {proposal.changed}",
            f"Что предлагаю сделать: {proposal.gives}",
            f"Что мне нужно от тебя: {proposal.risks}",
            "",
            f"Куда это попадёт: {proposal.target}",
        ]
    else:
        lines = [
            f"{proposal.title}",
            "",
            f"Что я хочу изменить: {proposal.changed}",
            f"Что это даёт: {proposal.gives}",
            f"Что может сломать: {proposal.risks}",
            "",
            f"Ветка: {proposal.branch}",
        ]
    if proposal.files:
        lines.append("Файлы: " + ", ".join(proposal.files[:6]))
    if proposal.evidence:
        lines.append("Проверки: " + "; ".join(proposal.evidence[:4]))
    lines += ["", f"Номер: {proposal.proposal_id}", "Решение принимается только кнопкой."]
    return "\n".join(lines)


def keyboard(proposal: Proposal) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Принять", "callback_data": proposal.callback_data(APPROVE)},
                {"text": "Отклонить", "callback_data": proposal.callback_data(REJECT)},
            ]
        ]
    }


def _walk_env(env_path_hint: Optional[Path], name: str) -> Optional[str]:
    """Environment first, then a nearby ``.env``, the way the provider key works."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    start = env_path_hint or Path(__file__).resolve()
    for parent in list(start.parents)[:8]:
        env_file = parent / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                found = line.split("=", 1)[1].strip().strip('"').strip("'")
                if found:
                    return found
    return None


def telegram_transport(token: str, timeout: float = 20.0) -> Callable[[str, dict], dict]:
    """A Bot API call as a plain function, so tests can hand in their own."""

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
            raise ApprovalError(f"telegram {method} failed: {exc.code} {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApprovalError(f"telegram {method} unreachable: {exc}") from exc

    return call


class TelegramApprovalChannel:
    """One message per proposal, one decision per proposal, owner only."""

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        owner_user_id: int,
        chat_id: Optional[int] = None,
        transport: Optional[Callable[[str, dict], dict]] = None,
        state_path: Optional[Path] = None,
        recorder: Optional[Callable[[str, dict], None]] = None,
        now: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        resolved = token or _walk_env(None, TELEGRAM_TOKEN_ENV)
        if not resolved and transport is None:
            raise ApprovalError(f"no bot token: set {TELEGRAM_TOKEN_ENV} or pass one")
        self.owner_user_id = int(owner_user_id)
        self.chat_id = int(chat_id) if chat_id is not None else self.owner_user_id
        self._call = transport or telegram_transport(resolved or "")
        self.state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        self._record = recorder
        self._now = now
        self._pending: dict[str, int] = {}
        self._decided: dict[str, dict] = {}
        self._load()

    # -- state -------------------------------------------------------------

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt state file must not silently approve anything: start empty.
            return
        self._pending = {str(k): int(v) for k, v in (state.get("pending") or {}).items()}
        self._decided = dict(state.get("decided") or {})

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pending": self._pending, "decided": self._decided}
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def _note(self, kind: str, payload: dict) -> None:
        if self._record is not None:
            self._record(kind, payload)

    # -- asking ------------------------------------------------------------

    def send(self, proposal: Proposal) -> dict:
        """Post the proposal once. Sending the same one twice is refused."""
        if proposal.proposal_id in self._pending:
            raise ApprovalError(f"proposal {proposal.proposal_id} was already sent")
        if proposal.proposal_id in self._decided:
            raise ApprovalError(f"proposal {proposal.proposal_id} was already decided")
        answer = self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": render(proposal),
                "reply_markup": keyboard(proposal),
                "disable_web_page_preview": True,
            },
        )
        if not answer.get("ok"):
            raise ApprovalError(f"telegram refused the message: {answer.get('description')}")
        message_id = int((answer.get("result") or {}).get("message_id") or 0)
        self._pending[proposal.proposal_id] = message_id
        self._save()
        self._note(
            "proposal_sent",
            {
                "proposal_id": proposal.proposal_id,
                "title": proposal.title,
                "branch": proposal.branch,
                "message_id": message_id,
                "at": self._now(),
            },
        )
        return answer

    # -- answering ---------------------------------------------------------

    def poll(self, offset: Optional[int] = None, limit: int = 50) -> PollResult:
        """Read presses. Only the owner's press on a known pending proposal decides."""
        answer = self._call(
            "getUpdates",
            {"offset": offset, "limit": limit, "timeout": 0, "allowed_updates": ["callback_query"]},
        )
        if not answer.get("ok"):
            raise ApprovalError(f"telegram refused getUpdates: {answer.get('description')}")
        result = PollResult()
        for update in answer.get("result") or []:
            update_id = int(update.get("update_id") or 0)
            if update_id:
                result.next_offset = max(result.next_offset or 0, update_id + 1)
            press = update.get("callback_query")
            if not press:
                # Text never decides anything, so anything that is not a press is
                # not even looked at as one.
                continue
            self._handle_press(press, result)
        return result

    def _handle_press(self, press: dict, result: PollResult) -> None:
        data = str(press.get("data") or "")
        # A Telegram User carries ``id``; there is no ``user_id`` on the press.
        by_user = int(((press.get("from") or {}).get("id")) or 0)
        press_id = press.get("id")
        if not data.startswith(CALLBACK_NAMESPACE + ":"):
            return
        parts = data.split(":", 2)
        verdict = parts[1] if len(parts) > 1 else ""
        proposal_id = parts[2] if len(parts) > 2 else ""
        refusal = self._refusal_reason(verdict, proposal_id, by_user)
        if refusal:
            result.refusals.append({"reason": refusal, "proposal_id": proposal_id, "by": by_user})
            self._note(
                "proposal_refused",
                {"reason": refusal, "proposal_id": proposal_id, "by_user_id": by_user,
                 "at": self._now()},
            )
            self._acknowledge(press_id, refusal)
            return
        decision = Decision(
            proposal_id=proposal_id,
            verdict=verdict,
            by_user_id=by_user,
            at=self._now(),
            message_id=self._pending.get(proposal_id),
        )
        self._pending.pop(proposal_id, None)
        self._decided[proposal_id] = {
            "verdict": verdict, "by_user_id": by_user, "at": decision.at,
        }
        self._save()
        self._note(
            "proposal_decided",
            {"proposal_id": proposal_id, "verdict": verdict, "by_user_id": by_user,
             "at": decision.at, "message_id": decision.message_id},
        )
        result.decisions.append(decision)
        self._acknowledge(press_id, verdict)

    def _refusal_reason(self, verdict: str, proposal_id: str, by_user: int) -> Optional[str]:
        if verdict not in VERDICTS:
            return "unknown_verdict"
        if by_user != self.owner_user_id:
            return "not_the_owner"
        if proposal_id in self._decided:
            return "already_decided"
        if proposal_id not in self._pending:
            return "unknown_proposal"
        return None

    def _acknowledge(self, press_id: Optional[str], verdict: str) -> None:
        if not press_id:
            return
        text = "Принято" if verdict == APPROVE else "Отклонено"
        try:
            self._call("answerCallbackQuery",
                       {"callback_query_id": press_id, "text": text})
        except ApprovalError:
            # The decision is already recorded; a missing acknowledgement is cosmetic.
            pass

    # -- reading state -----------------------------------------------------

    @property
    def pending(self) -> dict:
        return dict(self._pending)

    @property
    def decided(self) -> dict:
        return dict(self._decided)

    def is_approved(self, proposal_id: str) -> bool:
        """The only thing a caller may treat as permission."""
        return (self._decided.get(proposal_id) or {}).get("verdict") == APPROVE


def channel_from_env(**kwargs) -> TelegramApprovalChannel:
    """Build the channel the way the rest of the project reads keys."""
    token = _walk_env(None, TELEGRAM_TOKEN_ENV)
    owner = _walk_env(None, TELEGRAM_OWNER_ENV)
    if not owner:
        raise ApprovalError(f"no owner id: set {TELEGRAM_OWNER_ENV}")
    return TelegramApprovalChannel(token=token, owner_user_id=int(owner), **kwargs)
