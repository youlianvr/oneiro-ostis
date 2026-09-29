"""The manager as a counterpart: memory in the graph, honest question outcomes.

These tests hold the two promises of unit 3. Two consecutive owner messages
reach the same conversation session and the graph shows both turns. The
question tool returns exactly the channel's three outcomes and never lets
words become approval.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

import approval  # noqa: E402
from question_tool import (  # noqa: E402
    CONVERSATION_KIND_HUMAN,
    CONVERSATION_KIND_MANAGER,
    QuestionTool,
    QuestionToolError,
    Conversation,
    speak,
)

OWNER = 5094569795


class FakeBridge:
    def __init__(self) -> None:
        self.records: list = []
        self.fail = False

    def record_organization_event(self, **kwargs):
        if self.fail:
            raise RuntimeError("graph down")
        kwargs.setdefault("recorded_at", 1761000000)
        record = type("R", (), kwargs)()
        self.records.append(record)
        return record

    def load_organization_events(self, session_id=None):
        if self.fail:
            raise RuntimeError("graph down")
        return [r for r in self.records
                if session_id is None or r.session_id == session_id]


class FakeChannel:
    """The approval channel, reduced to what the tool uses."""

    def __init__(self) -> None:
        self.sent: list[approval.Proposal] = []
        self.open: list[str] = []
        self.answer: dict[str, approval.Answer] = {}

    def open_proposals(self):
        return list(self.open)

    def send(self, proposal):
        self.sent.append(proposal)
        self.open.append(proposal.proposal_id)

    def verdict_of(self, proposal_id):
        row = self.answer.get(proposal_id)
        return dict(row) if row else None


def conversation(tmp_path) -> tuple[Conversation, FakeBridge]:
    bridge = FakeBridge()
    return Conversation(bridge=bridge, session_id="host-cowagent-life-0"), bridge


def test_two_owner_messages_reach_one_session_and_the_graph_shows_both():
    talk, bridge = conversation(None)
    talk.add_human_turn("первое дело", at=100)
    talk.add_human_turn("а теперь второе", at=200)
    talk.add_manager_turn("принял, работаю", at=300)

    history = talk.history()
    assert [t["text"] for t in history] == ["первое дело", "а теперь второе",
                                            "принял, работаю"]
    assert [t["side"] for t in history] == ["human", "human", "manager"]
    kinds = [r.kind for r in bridge.records]
    assert kinds == [CONVERSATION_KIND_HUMAN, CONVERSATION_KIND_HUMAN,
                     CONVERSATION_KIND_MANAGER]
    assert all(r.session_id == "host-cowagent-life-0" for r in bridge.records)


def test_history_survives_a_restart_because_the_graph_is_the_memory():
    talk, bridge = conversation(None)
    talk.add_human_turn("напомни, что я просил", at=100)

    # a new process builds its own Conversation over the same bridge state
    revived = Conversation(bridge=bridge, session_id="host-cowagent-life-0")
    assert revived.history()[0]["text"] == "напомни, что я просил"


def test_empty_turns_are_refused():
    talk, _ = conversation(None)
    with pytest.raises(QuestionToolError):
        talk.add_human_turn("   ")


def test_history_unreadable_graph_raises_instead_of_inventing():
    talk, bridge = conversation(None)
    bridge.fail = True
    with pytest.raises(QuestionToolError):
        talk.history()


def proposal(pid: str = "p-q3-1") -> approval.Proposal:
    return approval.Proposal.action(
        proposal_id=pid, title="t", found="f", proposed="p", needed="n", target="z",
    )


def test_question_tool_returns_the_press_verdict():
    channel = FakeChannel()
    tool = QuestionTool(channel=channel)
    pressed = approval.answer_from_decision(approval.Decision(
        proposal_id="p-q3-1", verdict=approval.APPROVE, by_user_id=OWNER, at=5,
    ))

    def wait(pid):
        # in reality waiting ends when the channel closes the question
        channel.open.remove(pid)
        return pressed

    answer = tool.ask(proposal(), wait=wait)

    assert answer.approves and answer.answered
    assert channel.sent and channel.open == []


def test_free_text_answer_is_delivered_to_the_conversation_too():
    """Decision 4: words close the question AND become a conversation turn."""
    talk, bridge = conversation(None)
    channel = FakeChannel()
    tool = QuestionTool(channel=channel)
    spoken = approval.answer_from_text(
        "p-q3-1", "да, но сначала покажи список",
        by_user_id=OWNER, at=7,
    )

    answer = tool.ask(proposal(), wait=lambda pid: spoken, conversation=talk)

    assert answer.outcome == approval.FREE_TEXT
    assert not answer.approves
    view = answer.for_manager()
    assert view["answered"] is False
    assert view["text"] == "да, но сначала покажи список"
    assert "ask the question again" in view["instruction"]
    # double delivery: the manager's question and the owner's words are turns
    sides = [(r.kind, (r.payload or {}).get("text")) for r in bridge.records]
    assert (CONVERSATION_KIND_MANAGER, approval.render(proposal())) in sides
    assert (CONVERSATION_KIND_HUMAN, "да, но сначала покажи список") in sides


def test_the_same_question_is_not_sent_twice():
    channel = FakeChannel()
    channel.open.append("p-q3-1")
    tool = QuestionTool(channel=channel)
    with pytest.raises(QuestionToolError):
        tool.ask(proposal("p-q3-1"), wait=lambda pid: None)
    assert channel.sent == []


def test_speak_sends_and_records_the_turn():
    talk, bridge = conversation(None)
    calls: list[tuple[str, dict]] = []

    def transport(method, payload):
        calls.append((method, payload))
        return {"ok": True, "result": {}}

    result = speak(
        "Нашёл слабое место в разборе строк, могу взяться.",
        transport=transport, chat_id=OWNER, last_initiative_at=None,
        now=lambda: 1000, conversation=talk,
    )
    assert result["status"] == "sent" and result["at"] == 1000
    assert calls[0][0] == "sendMessage" and calls[0][1]["chat_id"] == OWNER
    assert bridge.records[-1].kind == CONVERSATION_KIND_MANAGER


def test_speak_is_rate_limited():
    def transport(method, payload):
        return {"ok": True, "result": {}}

    result = speak(
        "снова я", transport=transport, chat_id=OWNER,
        last_initiative_at=1000, now=lambda: 1000 + 60,
        min_interval=6 * 60 * 60,
    )
    assert result["status"] == "skipped"
    assert result["reason"] == "rate_limited"


def test_speak_refused_by_telegram_raises():
    def transport(method, payload):
        return {"ok": False, "description": "blocked"}

    with pytest.raises(QuestionToolError):
        speak("текст", transport=transport, chat_id=OWNER,
              last_initiative_at=None)
