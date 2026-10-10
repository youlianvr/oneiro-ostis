"""Approvals and questions as records: who may decide, and what a decision covers.

Every test here goes through the graph, because the properties being checked are
about what is stored: a grant that names one exact call, a decision that cannot be
overwritten, and an answer that is never a permission.
"""
from __future__ import annotations

import asyncio

import pytest

from chat_fakes import GraphStub, MemoryLinks, isolate
from oneiro import approvals, questions, recall
from oneiro.records import Approval, Provenance, State
from oneiro.runtime import Runtime

CALL = {"path": "notes.txt", "text": "hello"}
OTHER = {"path": "notes.txt", "text": "goodbye"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


class Owner:
    """One runtime over an in-memory graph; `reopen` is the process restarting."""

    def __init__(self, tmp_path, links: MemoryLinks | None = None) -> None:
        self.path = tmp_path
        self.links = links or MemoryLinks()
        self.runtime = Runtime(graph=GraphStub(self.links, tmp_path / "writer.lock"))

    def close(self) -> None:
        asyncio.run(self.runtime._graph.close())

    def reopen(self) -> "Owner":
        """The process restarted: a new runtime over the same stored graph."""
        self.close()
        return Owner(self.path, self.links)


def request(owner: Owner, arguments: dict = CALL, tool: str = "write_file",
            action_id: str = "act-turn-1") -> dict:
    return asyncio.run(approvals.request(owner.runtime, action_id=action_id, tool=tool,
                                         arguments=arguments, reason="review mode"))


def granted(owner: Owner, arguments: dict = CALL, tool: str = "write_file"):
    return asyncio.run(approvals.granted_for(owner.runtime, tool, arguments))


# ---------- a request releases nothing ----------


def test_a_request_waits_and_releases_nothing(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)

    assert stored["granted"] is False and stored["state"] == State.WAITING.value
    assert granted(owner) is None
    pending = asyncio.run(approvals.pending(owner.runtime))
    assert [row["id"] for row in pending] == [stored["id"]]


def test_a_second_request_for_the_same_call_does_not_duplicate_it(tmp_path):
    owner = Owner(tmp_path)
    first = request(owner)
    second = request(owner, action_id="act-turn-2")

    assert first["id"] == second["id"]
    assert len(asyncio.run(approvals.pending(owner.runtime))) == 1


def test_the_request_id_follows_the_tool_and_the_exact_arguments(tmp_path):
    owner = Owner(tmp_path)
    assert request(owner)["id"] != request(owner, arguments=OTHER)["id"]


# ---------- the owner decides, once, about one call ----------


def test_the_owner_grants_one_exact_call(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)
    decided = asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=True))

    assert decided["granted"] is True
    assert decided["state"] == State.COMPLETED.value
    assert decided["provenance"] == Provenance.OWNER_INSTRUCTION.value
    assert granted(owner) is not None
    assert granted(owner, arguments=OTHER) is None
    assert asyncio.run(approvals.pending(owner.runtime)) == []


def test_a_refusal_is_a_decision_and_never_a_grant(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)
    decided = asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=False,
                                           reason="not now"))

    assert decided["granted"] is False
    assert decided["state"] == State.CANCELLED.value
    assert granted(owner) is None


def test_a_second_decision_is_refused_and_the_first_one_stands(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)
    asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=True))

    with pytest.raises(approvals.ApprovalError) as failure:
        asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=False))
    assert failure.value.reason == approvals.ALREADY_DECIDED
    assert granted(owner) is not None, "the first decision was not overwritten"


def test_only_the_owner_decides(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)

    with pytest.raises(approvals.ApprovalError) as failure:
        asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=True,
                                     actor="researcher"))
    assert failure.value.reason == approvals.NOT_THE_OWNER
    assert granted(owner) is None
    assert len(asyncio.run(approvals.pending(owner.runtime))) == 1


def test_deciding_something_that_was_never_asked_is_refused(tmp_path):
    owner = Owner(tmp_path)
    with pytest.raises(approvals.ApprovalError) as failure:
        asyncio.run(approvals.decide(owner.runtime, "approval-nothing", granted=True))
    assert failure.value.reason == approvals.UNKNOWN_PROPOSAL


def test_a_grant_written_without_the_owner_releases_nothing(tmp_path):
    # The shape the agent's own code can write: granted text, wrong provenance.
    owner = Owner(tmp_path)
    request(owner)
    row = asyncio.run(recall.latest(owner.runtime, "approval",
                                    approvals.approval_id("write_file", CALL)))
    forged = {**row, "granted": True, "state": State.COMPLETED.value,
              "provenance": Provenance.SYSTEM.value}
    asyncio.run(owner.runtime.publish(forged, "forged-" + row["id"],
                                      expected_revision=int(row["__revision__"])))

    assert granted(owner) is None, "a model claim is not the owner's permission"


# ---------- a grant is spent once ----------


def test_a_grant_is_consumed_by_the_action_it_released(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)
    asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=True))
    grant = granted(owner)
    assert grant is not None

    used = asyncio.run(approvals.consume(owner.runtime, grant, "act-turn-2"))

    assert used["consumed_action_id"] == "act-turn-2"
    assert granted(owner) is None, "the same grant must not release a second action"
    with pytest.raises(ValueError, match="already been consumed"):
        Approval.from_dict(used).consumed_by("act-turn-3")


def test_a_restart_keeps_a_decision_and_a_consumption(tmp_path):
    owner = Owner(tmp_path)
    stored = request(owner)
    asyncio.run(approvals.decide(owner.runtime, stored["id"], granted=True))
    asyncio.run(approvals.consume(owner.runtime, granted(owner), "act-turn-2"))

    restarted = owner.reopen()

    assert granted(restarted) is None, "a spent grant is still spent after a restart"
    with pytest.raises(approvals.ApprovalError) as failure:
        asyncio.run(approvals.decide(restarted.runtime, stored["id"], granted=True))
    assert failure.value.reason == approvals.ALREADY_DECIDED
    assert asyncio.run(approvals.pending(restarted.runtime)) == []


# ---------- questions: the owner's words are not a permission ----------


def ask(owner: Owner, text: str = "Which folder should I search?"):
    return asyncio.run(questions.ask(owner.runtime, text, conversation_id="main-chat"))


def test_a_question_waits_until_it_is_answered(tmp_path):
    owner = Owner(tmp_path)
    stored = ask(owner)

    assert stored["state"] == State.WAITING.value and stored["answer"] == ""
    assert [row["id"] for row in asyncio.run(questions.unanswered(owner.runtime))] == [stored["id"]]

    answered = asyncio.run(questions.answer(owner.runtime, stored["id"], "In the notes folder."))

    assert answered["answer"] == "In the notes folder."
    assert answered["question"] == stored["question"], "the question is kept with its answer"
    assert answered["state"] == State.COMPLETED.value
    assert asyncio.run(questions.unanswered(owner.runtime)) == []


def test_free_text_answer_never_becomes_a_permission(tmp_path):
    owner = Owner(tmp_path)
    stored = ask(owner, "Should I write notes.txt?")
    asyncio.run(questions.answer(owner.runtime, stored["id"], "approve"))

    assert granted(owner) is None
    assert asyncio.run(approvals.pending(owner.runtime)) == []


def test_asking_the_same_question_again_keeps_the_answer(tmp_path):
    owner = Owner(tmp_path)
    stored = ask(owner)
    asyncio.run(questions.answer(owner.runtime, stored["id"], "Notes."))

    again = ask(owner)

    assert again["id"] == stored["id"] and again["answer"] == "Notes."


def test_answering_twice_an_unknown_or_empty_question_is_refused(tmp_path):
    owner = Owner(tmp_path)
    stored = ask(owner)
    asyncio.run(questions.answer(owner.runtime, stored["id"], "Notes."))

    for question_id, text, reason in (
        (stored["id"], "Again.", questions.ALREADY_ANSWERED),
        ("ask-nothing", "Hello.", questions.UNKNOWN_QUESTION),
        (stored["id"], "   ", questions.EMPTY_ANSWER),
    ):
        with pytest.raises(questions.QuestionError) as failure:
            asyncio.run(questions.answer(owner.runtime, question_id, text))
        assert failure.value.reason == reason


def test_two_questions_in_different_conversations_stay_separate(tmp_path):
    owner = Owner(tmp_path)
    first = asyncio.run(questions.ask(owner.runtime, "Which folder?", conversation_id="a-chat"))
    second = asyncio.run(questions.ask(owner.runtime, "Which folder?", conversation_id="b-chat"))

    assert first["id"] != second["id"]
    assert first["conversation_id"] == "a-chat"
    assert len(asyncio.run(questions.unanswered(owner.runtime))) == 2
