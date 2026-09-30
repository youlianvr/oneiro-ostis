"""The manager as a counterpart: a conversation kept in the graph, a question
tool, and a voice of its own.

Two things live here. The conversation: every owner message and every manager
reply is an organization event, so the history survives any restart and is read
back the way every other fact about the work is read. The tool: when the
manager needs an answer, it calls :func:`ask`, which sends the question through
the approval channel and returns exactly one of the three outcomes — confirmed,
rejected, or the owner's own words as ``free_text`` with the standing
re-ask instruction. Words close a question, only a button approves.

The manager may also speak first. :func:`speak` sends a message that has no
question behind it; it is rate-limited here, and it can never sign anything:
the only signing path in the system remains a button press on a proposal.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import approval

CONVERSATION_KIND_HUMAN = "conversation_human"
CONVERSATION_KIND_MANAGER = "conversation_manager"
QUESTION_TOOL_KIND = "question_tool"

DEFAULT_MIN_INITIATIVE_INTERVAL = 6 * 60 * 60  # six hours between initiatives


class QuestionToolError(RuntimeError):
    """The conversation or the question tool was refused for a stated reason."""


class Conversation:
    """Owner-and-manager talk, stored as organization events in the graph.

    The graph is the memory, not this process: after any restart the next
    session reads the same turns back with :meth:`history`. ``session_id`` is
    the long-lived session the whole host writes into, so the conversation and
    the rest of the biography do not split in half.
    """

    def __init__(
        self,
        *,
        bridge,
        session_id: str,
        recorder: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self._bridge = bridge
        self.session_id = session_id
        self._record = recorder

    def add_human_turn(self, text: str, *, at: Optional[int] = None) -> dict:
        if not text.strip():
            raise QuestionToolError("refusing to record an empty turn")
        payload = {
            "text": text.strip(),
            "at": int(at if at is not None else time.time()),
        }
        self._bridge.record_organization_event(
            session_id=self.session_id,
            role="human",
            kind=CONVERSATION_KIND_HUMAN,
            payload=payload,
            origin="human",
            verified=True,
        )
        if self._record is not None:
            self._record("conversation_turn", {"side": "human", **payload})
        return payload

    def add_manager_turn(self, text: str, *, at: Optional[int] = None) -> dict:
        if not text.strip():
            raise QuestionToolError("refusing to record an empty turn")
        payload = {
            "text": text.strip(),
            "at": int(at if at is not None else time.time()),
        }
        self._bridge.record_organization_event(
            session_id=self.session_id,
            role="manager",
            kind=CONVERSATION_KIND_MANAGER,
            payload=payload,
            origin="model",
            verified=True,
        )
        if self._record is not None:
            self._record("conversation_turn", {"side": "manager", **payload})
        return payload

    def history(self, limit: int = 20) -> list[dict]:
        """The conversation so far, oldest first, read from the graph."""
        try:
            records = self._bridge.load_organization_events(session_id=self.session_id)
        except Exception as exc:  # the graph being down must not invent history
            raise QuestionToolError(f"could not read the conversation: {exc}") from exc
        turns = [
            {
                "side": "human" if r.kind == CONVERSATION_KIND_HUMAN else "manager",
                "text": str((r.payload or {}).get("text") or ""),
                "at": int((r.payload or {}).get("at") or r.recorded_at or 0),
            }
            for r in records
            if r.kind in (CONVERSATION_KIND_HUMAN, CONVERSATION_KIND_MANAGER)
        ]
        return turns[-limit:]


class QuestionTool:
    """Ask the owner through the approval channel; deliver the honest outcome.

    The three outcomes are the channel's, unchanged: a press decides, words
    close the question as ``free_text`` with the re-ask instruction, and
    nothing here can turn words into approval.
    """

    def __init__(self, *, channel: approval.TelegramApprovalChannel,
                 now: Callable[[], int] = lambda: int(time.time())) -> None:
        self.channel = channel
        self._now = now

    def ask(self, proposal: approval.Proposal, *,
            wait: Callable[[str], approval.Answer],
            conversation: Optional[Conversation] = None) -> approval.Answer:
        """Send one question and wait for its outcome.

        ``wait`` blocks until the answer arrives — the gateway's poll loop owns
        the Telegram connection, so waiting is the caller's job, not ours. The
        owner's words are also delivered to the conversation as an ordinary
        turn (double delivery, PLAN-V2 decision 4); the manager's framing
        question is delivered as its own turn.
        """
        if proposal.proposal_id in self.channel.open_proposals():
            raise QuestionToolError(
                f"question {proposal.proposal_id} was already sent"
            )
        self.channel.send(proposal)
        if conversation is not None:
            conversation.add_manager_turn(approval.render(proposal))
        answer = wait(proposal.proposal_id)
        if conversation is not None and answer.outcome == approval.FREE_TEXT:
            conversation.add_human_turn(answer.text)
        return answer


def speak(
    text: str,
    *,
    transport: Callable[[str, dict], dict],
    chat_id: int,
    last_initiative_at: Optional[int],
    now: Callable[[], int] = lambda: int(time.time()),
    min_interval: int = DEFAULT_MIN_INITIATIVE_INTERVAL,
    conversation: Optional[Conversation] = None,
) -> dict:
    """A manager message with no question behind it, rate-limited.

    Returns what happened: ``sent`` with the moment, or ``skipped`` with the
    reason. This path has no verdict behind it and cannot create one: it only
    writes to the chat and to the conversation, never to a proposal.
    """
    moment = int(now())
    if last_initiative_at is not None and \
            moment - int(last_initiative_at) < min_interval:
        return {"status": "skipped", "reason": "rate_limited",
                "next_allowed_at": int(last_initiative_at) + min_interval}
    if not text.strip():
        return {"status": "skipped", "reason": "empty_text"}
    answer = transport("sendMessage", {
        "chat_id": chat_id,
        "text": text.strip(),
        "disable_web_page_preview": True,
    })
    if not answer.get("ok"):
        raise QuestionToolError(
            f"telegram refused the initiative: {answer.get('description')}"
        )
    if conversation is not None:
        conversation.add_manager_turn(text, at=moment)
    return {"status": "sent", "at": moment}
