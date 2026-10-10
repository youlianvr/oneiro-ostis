"""Questions to the owner, kept as records: asking is not blocking.

A question is a record, so an unanswered one survives a restart and does not hold
up work that does not depend on it. An answer is a new revision of the same
question, so the question and what the owner said about it stay one history.

The distinction this module protects: an answer is the owner's text and nothing
else. Free text - including the word "approve" - is never a permission; grants
live in `oneiro.approvals` and carry their own provenance.
"""
from __future__ import annotations

import hashlib
from typing import Any

from oneiro import recall
from oneiro.records import Provenance, Question, State

KIND = Question.KIND
UNKNOWN_QUESTION = "unknown_question"
ALREADY_ANSWERED = "already_answered"
EMPTY_ANSWER = "empty_answer"


class QuestionError(ValueError):
    """A question that cannot be answered, with a short machine-readable reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def stored_question(stored: dict[str, Any]) -> Question:
    """The typed record for a stored row. The kind is checked, not assumed."""
    record = Question.from_dict(stored)
    if not isinstance(record, Question):
        raise QuestionError(UNKNOWN_QUESTION, "the stored record is not a question")
    return record


def question_id(text: str, conversation_id: str = "") -> str:
    """One ID per distinct question, so asking again does not duplicate it."""
    digest = hashlib.sha256((conversation_id + "\n" + text.strip()).encode("utf-8")).hexdigest()
    return "ask-" + digest[:24]


async def ask(owner: Any, text: str, *, conversation_id: str = "",
              task_id: str = "") -> dict[str, Any]:
    """Record a question for the owner and return it. No answer is assumed."""
    record = Question(id=question_id(text, conversation_id), question=text.strip(),
                      conversation_id=conversation_id, task_id=task_id,
                      state=State.WAITING, provenance=Provenance.OWNER_INSTRUCTION)
    stored = await recall.latest(owner, KIND, record.id)
    if stored is not None:
        # The same question was asked before: keep the earlier one and its answer.
        return stored
    return (await owner.publish(record.to_dict(), record.id))["record"]


async def answer(owner: Any, question_id_value: str, text: str) -> dict[str, Any]:
    """Record the owner's answer as a new revision of one question."""
    if not text.strip():
        raise QuestionError(EMPTY_ANSWER, "an answer must not be empty")
    stored = await recall.latest(owner, KIND, question_id_value)
    if stored is None:
        raise QuestionError(UNKNOWN_QUESTION, "there is no such question")
    current = stored_question(stored)
    if current.answered:
        raise QuestionError(ALREADY_ANSWERED, "this question already has an answer")
    updated = current.with_answer(text).with_state(State.COMPLETED)
    # A new revision, so its own operation ID, naming the revision it follows.
    return (await owner.publish(updated.to_dict(), "answer-" + current.id,
                                expected_revision=int(stored["__revision__"])))["record"]


async def unanswered(owner: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    """Questions the owner has not answered, newest first, one row per question."""
    found = await recall.scan(owner, lambda row: row.get("kind") == KIND)
    seen: set[str] = set()
    waiting: list[dict[str, Any]] = []
    for row in found.rows:                      # newest first
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        if row.get("state") == State.WAITING.value and not row.get("answer"):
            waiting.append(row)
        if len(waiting) >= limit:
            break
    return waiting
