"""The approval channel has one job: a human decides, and nobody else can."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

from approval import (  # noqa: E402
    APPROVE,
    REJECT,
    ApprovalError,
    Decision,
    Proposal,
    TelegramApprovalChannel,
    keyboard,
    render,
)

OWNER = 5094569795
STRANGER = 111222333


def proposal(proposal_id: str = "p01-two-buttons") -> Proposal:
    return Proposal(
        proposal_id=proposal_id,
        title="Нашёл, что ускорить",
        changed="переписал разбор строк так, чтобы не читать файл дважды",
        gives="на больших файлах вдвое меньше чтений",
        risks="если в файле нет переводов строки, поведение не изменится",
        branch="agent/selfimprove-p01",
        files=("python/approval.py",),
        evidence=("tests/test_approval.py: 13 passed",),
    )


class FakeTelegram:
    """The Bot API, reduced to the calls this channel actually makes."""

    def __init__(self, updates: list[dict] | None = None, ok: bool = True) -> None:
        self.updates = list(updates or [])
        self.ok = ok
        self.sent: list[dict] = []
        self.answered: list[dict] = []
        self.fail_methods: set[str] = set()
        self._message_id = 100
        self.polls = 0

    def __call__(self, method: str, payload: dict) -> dict:
        if method in self.fail_methods:
            raise ApprovalError(f"telegram {method} unreachable: simulated")
        if method == "sendMessage":
            self.sent.append(payload)
            self._message_id += 1
            return {"ok": self.ok, "result": {"message_id": self._message_id},
                    "description": None if self.ok else "chat not found"}
        if method == "getUpdates":
            self.polls += 1
            batch, self.updates = self.updates, []
            return {"ok": self.ok, "result": batch,
                    "description": None if self.ok else "conflict"}
        if method == "answerCallbackQuery":
            self.answered.append(payload)
            return {"ok": True, "result": True}
        raise AssertionError(f"unexpected method {method}")

    def press(self, data: str, user_id: int, press_id: str = "cb1") -> None:
        self.updates.append(
            {"update_id": 1, "callback_query": {"id": press_id, "data": data,
                                                "from": {"id": user_id}}}
        )


def channel(tmp_path: Path, fake: FakeTelegram, **kwargs) -> TelegramApprovalChannel:
    return TelegramApprovalChannel(
        owner_user_id=OWNER,
        transport=fake,
        state_path=tmp_path / "approvals.json",
        **kwargs,
    )


def test_render_names_every_field_and_no_em_dash():
    text = render(proposal())
    for fragment in ("Нашёл, что ускорить", "Что я хочу изменить", "Что это даёт",
                     "Что может сломать", "Ветка: agent/selfimprove-p01", "Принять"):
        if fragment == "Принять":
            continue
        assert fragment in text
    assert "\u2014" not in text


def test_keyboard_carries_two_buttons_within_the_telegram_limit():
    markup = keyboard(proposal("p" * 40))["inline_keyboard"][0]
    labels = [button["text"] for button in markup]
    assert labels == ["Принять", "Отклонить"]
    for button in markup:
        assert len(button["callback_data"].encode("utf-8")) <= 64
    assert markup[0]["callback_data"].endswith(":" + "p" * 40)


def test_proposal_without_risks_is_refused_before_it_is_sent():
    with pytest.raises(ApprovalError):
        Proposal(proposal_id="p02", title="т", changed="ч", gives="д", risks="  ",
                 branch="b")


def test_the_same_proposal_is_never_sent_twice(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    subject.send(proposal())
    with pytest.raises(ApprovalError):
        subject.send(proposal())
    assert len(fake.sent) == 1


def test_a_failed_send_leaves_nothing_pending(tmp_path):
    fake = FakeTelegram()
    fake.fail_methods.add("sendMessage")
    subject = channel(tmp_path, fake)
    with pytest.raises(ApprovalError):
        subject.send(proposal())
    assert subject.pending == {}
    assert subject.is_approved("p01-two-buttons") is False


def test_only_the_owners_press_decides(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    subject.send(proposal())
    fake.press(proposal().callback_data(APPROVE), STRANGER, press_id="cb9")
    result = subject.poll()
    assert result.decisions == []
    assert [r["reason"] for r in result.refusals] == ["not_the_owner"]
    assert subject.is_approved("p01-two-buttons") is False
    assert "p01-two-buttons" in subject.pending


def test_the_owner_press_decides_once(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    subject.send(proposal())
    fake.press(proposal().callback_data(APPROVE), OWNER, press_id="cb1")
    first = subject.poll()
    assert len(first.decisions) == 1
    assert isinstance(first.decisions[0], Decision)
    assert first.decisions[0].approved is True
    assert subject.is_approved("p01-two-buttons") is True
    assert fake.answered[0]["text"] == "Принято"

    fake.press(proposal().callback_data(APPROVE), OWNER, press_id="cb2")
    second = subject.poll()
    assert second.decisions == []
    assert [r["reason"] for r in second.refusals] == ["already_decided"]
    assert subject.is_approved("p01-two-buttons") is True


def test_rejection_is_terminal_and_not_permission(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    subject.send(proposal())
    fake.press(proposal().callback_data(REJECT), OWNER)
    result = subject.poll()
    assert result.decisions[0].approved is False
    assert subject.is_approved("p01-two-buttons") is False
    assert "p01-two-buttons" not in subject.pending


def test_a_press_for_an_unknown_proposal_is_refused(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    fake.press("oneiro:approve:never-sent", OWNER)
    result = subject.poll()
    assert result.decisions == []
    assert [r["reason"] for r in result.refusals] == ["unknown_proposal"]
    assert subject.is_approved("never-sent") is False


def test_text_never_decides_anything(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    subject.send(proposal())
    fake.updates.append({"update_id": 7, "message": {"text": "да, принимай",
                                                     "from": {"id": OWNER}}})
    result = subject.poll()
    assert result.decisions == []
    assert result.refusals == []
    assert subject.is_approved("p01-two-buttons") is False


def test_a_press_from_another_namespace_is_ignored(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    fake.press("othertool:approve:p01-two-buttons", OWNER)
    result = subject.poll()
    assert result.decisions == [] and result.refusals == []


def test_a_decision_survives_a_restart(tmp_path):
    fake = FakeTelegram()
    subject = channel(tmp_path, fake)
    subject.send(proposal())
    fake.press(proposal().callback_data(APPROVE), OWNER)
    subject.poll()

    restarted = channel(tmp_path, fake)
    assert restarted.is_approved("p01-two-buttons") is True
    assert restarted.decided["p01-two-buttons"]["verdict"] == APPROVE


def test_a_corrupt_state_file_approves_nothing(tmp_path):
    state = tmp_path / "approvals.json"
    state.write_text("{ this is not json", encoding="utf-8")
    fake = FakeTelegram()
    subject = TelegramApprovalChannel(owner_user_id=OWNER, transport=fake,
                                      state_path=state)
    assert subject.pending == {} and subject.decided == {}
    assert subject.is_approved("p01-two-buttons") is False


def test_every_decision_is_recorded_for_the_graph(tmp_path):
    records: list[tuple[str, dict]] = []
    fake = FakeTelegram()
    subject = channel(tmp_path, fake, recorder=lambda kind, payload: records.append((kind, payload)))
    subject.send(proposal())
    fake.press(proposal().callback_data(APPROVE), OWNER)
    subject.poll()
    kinds = [kind for kind, _ in records]
    assert kinds == ["proposal_sent", "proposal_decided"]
    decided = records[1][1]
    assert decided["by_user_id"] == OWNER and decided["verdict"] == APPROVE
    assert json.loads((tmp_path / "approvals.json").read_text(encoding="utf-8"))["decided"]


def test_a_refused_press_is_recorded_too(tmp_path):
    records: list[tuple[str, dict]] = []
    fake = FakeTelegram()
    subject = channel(tmp_path, fake, recorder=lambda kind, payload: records.append((kind, payload)))
    subject.send(proposal())
    fake.press(proposal().callback_data(APPROVE), STRANGER)
    subject.poll()
    assert records[-1][0] == "proposal_refused"
    assert records[-1][1]["reason"] == "not_the_owner"
    assert records[-1][1]["by_user_id"] == STRANGER
