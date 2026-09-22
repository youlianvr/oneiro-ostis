"""The phone is the way in: a plain message becomes work, and only the owner's.

These tests hold the promise the whole entry rests on. A message in ordinary
Russian turns into a dated record in the graph, the answer back is Russian with
no machinery in it, and nobody but the owner can hand work in.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

import approval  # noqa: E402
import telegram_entry as entry  # noqa: E402

OWNER = 5094569795
STRANGER = 111222333


class FakeGraph:
    """The bridge reduced to what the gateway uses, with every record kept."""

    def __init__(self) -> None:
        self.records: list = []
        self.sessions: list[str] = []
        self.fail = False

    # the two calls the entry makes while starting up
    def load_life_sessions(self):
        if self.fail:
            raise RuntimeError("graph down")
        return [type("S", (), {"session_id": value})() for value in self.sessions]

    def start_life_session(self, name, goals=None, self_state=None):
        session = f"{name}-{len(self.sessions)}"
        self.sessions.append(session)
        return type("S", (), {"session_id": session})()

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
        return list(self.records)

    # helpers for assertions
    def tasks(self) -> list:
        return [r for r in self.records if r.kind == entry.TASK_KIND]

    def kinds(self) -> list[str]:
        return [r.kind for r in self.records]


class FakeTelegram:
    """Telegram, with the wire kept on disk instead of in the air."""

    def __init__(self, updates=None, fail_send=False) -> None:
        self.updates = list(updates or [])
        self.calls: list[tuple[str, dict]] = []
        self.sent: list[str] = []
        self.fail_send = fail_send

    def __call__(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "getUpdates":
            # Telegram drops what the offset has confirmed, and an offset of -1
            # asks for the newest update only. The fake keeps that behaviour, or
            # the restart tests would prove nothing.
            rows = list(self.updates)
            offset = payload.get("offset")
            if offset == -1:
                rows = rows[-1:]
            elif offset:
                rows = [r for r in rows if int(r.get("update_id") or 0) >= int(offset)]
            limit = int(payload.get("limit") or 50)
            return {"ok": True, "result": rows[:limit]}
        if method == "sendMessage":
            if self.fail_send:
                raise entry.EntryError("telegram sendMessage unreachable")
            self.sent.append(payload["text"])
            return {"ok": True, "result": {"message_id": 1000 + len(self.sent)}}
        if method == "answerCallbackQuery":
            return {"ok": True, "result": True}
        return {"ok": True, "result": {}}

    def methods(self) -> list[str]:
        return [name for name, _ in self.calls]


def message(update_id: int, text: str, by: int = OWNER) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": by},
            "chat": {"id": by},
            "text": text,
        },
    }


def gateway(tmp_path, updates=None, channel=None):
    graph = FakeGraph()
    telegram = FakeTelegram(updates)
    if channel is not None:
        channel._call = telegram
    built = entry.TelegramGateway(
        owner_user_id=OWNER,
        transport=telegram,
        bridge=graph,
        state_path=tmp_path / "telegram-entry.json",
        channel=channel,
        now=lambda: 1761000123,
    )
    return built, graph, telegram


# --------------------------------------------------------------------------- #
# a message becomes work
# --------------------------------------------------------------------------- #

def test_owner_message_becomes_a_task_in_the_graph(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(11, "посмотри мою записку")])
    run = built.poll()

    assert [t.text for t in run.tasks] == ["посмотри мою записку"]
    rows = graph.tasks()
    assert len(rows) == 1
    assert rows[0].role == "human"
    assert rows[0].origin == "human"
    assert rows[0].payload["text"] == "посмотри мою записку"
    assert rows[0].payload["update_id"] == 11
    assert rows[0].payload["channel"] == "telegram"
    assert rows[0].record_id == "task-task-11"
    assert telegram.sent == [entry.TAKEN_TEXT.format(text="посмотри мою записку")]


def test_the_task_is_recorded_in_the_host_session(tmp_path):
    """One memory: the entry writes where the rest of the host writes."""
    built, graph, _ = gateway(tmp_path, [message(12, "проверь память")])
    built.poll()
    assert graph.sessions, "the gateway had to create its session"
    assert graph.sessions[0].startswith(entry.SESSION_PREFIX)
    assert graph.tasks()[0].session_id == graph.sessions[0]


def test_a_stranger_is_not_answered_and_leaves_no_task(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(21, "дай доступ", by=STRANGER)])
    run = built.poll()

    assert run.tasks == []
    assert graph.tasks() == []
    assert telegram.sent == []
    assert run.ignored[0]["reason"] == "not_the_owner"
    # the attempt is remembered for the owner, without schooling the sender
    assert "entry_refused" in graph.kinds()


def test_a_duplicate_message_is_not_recorded_twice(tmp_path):
    """A crash between accepting the message and saving the offset is survivable."""
    update = message(31, "найди ошибку")
    built, graph, _ = gateway(tmp_path, [update])
    built.poll()

    # The task is in the graph, the offset was not written down: after a restart
    # Telegram offers the same message again, and it must not become work twice.
    (tmp_path / "telegram-entry.json").write_text(
        json.dumps({"offset": None, "accepted": {"31": "task-31"}}), encoding="utf-8"
    )
    restarted, _, telegram = gateway(tmp_path, [update])
    run = restarted.poll()

    assert run.tasks == []
    assert len(graph.tasks()) == 1
    assert telegram.sent == [entry.DUPLICATE_TEXT]


def test_help_answers_help_and_takes_no_work(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(41, "/помощь")])
    run = built.poll()
    assert run.tasks == []
    assert graph.tasks() == []
    assert telegram.sent == [entry.HELP_TEXT]


def test_what_is_in_work_lists_the_tasks(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(51, "собери отчёт")])
    built.poll()
    # The list is read from the graph, not from the messages of this batch.
    assert "собери отчёт" in built.list_text()
    assert telegram.sent[-1] == entry.TAKEN_TEXT.format(text="собери отчёт")


def test_an_empty_message_is_answered_in_russian(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(61, "   ")])
    run = built.poll()
    assert run.tasks == []
    assert telegram.sent == [entry.EMPTY_TEXT]


def test_a_gateway_that_cannot_reach_the_graph_does_not_say_it_took_the_work(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(71, "сделай дело")])
    graph.fail = True
    run = built.poll()

    assert run.tasks == []
    assert telegram.sent == [entry.TROUBLE_TEXT]
    assert entry.TAKEN_TEXT.format(text="сделай дело") not in telegram.sent


# --------------------------------------------------------------------------- #
# a press is the answer, and it belongs to the channel
# --------------------------------------------------------------------------- #

def test_a_press_in_the_same_batch_is_decided_by_the_channel(tmp_path):
    seen: list[tuple[str, dict]] = []
    channel = approval.TelegramApprovalChannel(
        owner_user_id=OWNER,
        transport=FakeTelegram(),
        state_path=tmp_path / "approvals.json",
        recorder=lambda kind, payload: seen.append((kind, payload)),
    )
    proposal = approval.Proposal.action(
        proposal_id="p-telegram-1",
        title="Нашёл список рассылки",
        found="в письме лежит список адресов",
        proposed="добавить его в таблицу",
        needed="твоё разрешение отправить запись в таблицу",
        target="таблица приёма",
    )
    channel.send(proposal)

    press = {
        "update_id": 81,
        "callback_query": {
            "id": "press-1",
            "from": {"id": OWNER},
            "data": proposal.callback_data(approval.APPROVE),
        },
    }
    built, graph, telegram = gateway(tmp_path, [press, message(82, "и посмотри почту")],
                                     channel=channel)
    run = built.poll()

    assert [d.proposal_id for d in run.decisions] == ["p-telegram-1"]
    assert run.decisions[0].verdict == approval.APPROVE
    assert channel.is_approved("p-telegram-1")
    assert ("proposal_decided", seen[-1][1]) == seen[-1]
    assert [t.text for t in run.tasks] == ["и посмотри почту"]
    assert "answerCallbackQuery" in telegram.methods()


def test_a_press_from_a_stranger_decides_nothing(tmp_path):
    channel = approval.TelegramApprovalChannel(
        owner_user_id=OWNER, transport=FakeTelegram(),
        state_path=tmp_path / "approvals.json",
    )
    proposal = approval.Proposal.action(
        proposal_id="p-telegram-2", title="т", found="ф", proposed="п", needed="н",
        target="ц",
    )
    channel.send(proposal)
    press = {
        "update_id": 91,
        "callback_query": {
            "id": "press-2",
            "from": {"id": STRANGER},
            "data": proposal.callback_data(approval.APPROVE),
        },
    }
    built, _, _ = gateway(tmp_path, [press], channel=channel)
    run = built.poll()

    assert run.decisions == []
    assert run.refusals[0]["reason"] == "not_the_owner"
    assert not channel.is_approved("p-telegram-2")


# --------------------------------------------------------------------------- #
# the first start and the words
# --------------------------------------------------------------------------- #

def test_the_first_start_drops_what_was_waiting_before_it(tmp_path):
    """A bot that was off for a day must not take the whole queue as new work."""
    telegram = FakeTelegram()
    built, graph, _ = gateway(tmp_path)
    built._call = telegram

    telegram.updates = [message(500, "старое сообщение")]
    offset = built.prime()

    assert offset == 501
    assert graph.tasks() == []
    assert built.poll().tasks == []

    # a message sent after the start is still taken
    telegram.updates = [message(502, "новое сообщение")]
    assert [t.text for t in built.poll().tasks] == ["новое сообщение"]


def test_the_offset_survives_a_restart(tmp_path):
    built, _, _ = gateway(tmp_path, [message(601, "первое дело")])
    built.poll()
    state = (tmp_path / "telegram-entry.json").read_text(encoding="utf-8")
    assert "601" in state

    again, _, telegram = gateway(tmp_path, [])
    again.poll()
    assert telegram.calls[0][1]["offset"] == 602


def test_a_broken_state_file_does_not_replay_old_messages_as_new(tmp_path):
    (tmp_path / "telegram-entry.json").write_text("{не json", encoding="utf-8")
    built, graph, _ = gateway(tmp_path, [message(701, "дело")])
    run = built.poll()
    assert [t.text for t in run.tasks] == ["дело"]
    assert len(graph.tasks()) == 1


def test_the_reply_failing_does_not_lose_the_task(tmp_path):
    built, graph, telegram = gateway(tmp_path, [message(801, "важное дело")])
    telegram.fail_send = True
    run = built.poll()
    assert [t.text for t in run.tasks] == ["важное дело"]
    assert len(graph.tasks()) == 1


VISIBLE_TEXTS = {
    "HELP_TEXT": entry.HELP_TEXT,
    "DUPLICATE_TEXT": entry.DUPLICATE_TEXT,
    "EMPTY_TEXT": entry.EMPTY_TEXT,
    "NOTHING_TO_DO": entry.NOTHING_TO_DO,
    "IN_WORK_HEAD": entry.IN_WORK_HEAD,
    "IN_WORK_LINE": entry.IN_WORK_LINE,
    "TAKEN_TEXT": entry.TAKEN_TEXT,
    "TROUBLE_TEXT": entry.TROUBLE_TEXT,
}


def test_everything_the_owner_reads_is_russian():
    """No Latin letters, no tool or field names: this is what a person sees."""
    for name, text in VISIBLE_TEXTS.items():
        filled = text.format(text="сообщение", **{}) if "{text}" in text else text
        letters = re.findall(r"[A-Za-z]", filled)
        assert not letters, f"{name} carries Latin letters: {letters}"


def test_the_visible_texts_name_no_machinery():
    banned = ("граф", "MCP", "запрос", "callback", "JSON", "API", "proposal")
    for name, text in VISIBLE_TEXTS.items():
        for word in banned:
            assert word.lower() not in text.lower(), f"{name} names {word}"


def test_a_reply_is_sent_to_the_owners_chat(tmp_path):
    built, _, telegram = gateway(tmp_path, [message(901, "дело")])
    built.poll()
    payload = [p for m, p in telegram.calls if m == "sendMessage"][0]
    assert payload["chat_id"] == OWNER
    assert payload["reply_to_message_id"] == 901
