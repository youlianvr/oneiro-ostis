"""Prompt assembly: the official LongMemEval wording, nothing invented.

The templates below are copied from the benchmark's own generation script
(xiaowu0162/LongMemEval, src/generation/run_generation.py) so a full-context
number measured here sits next to the published ones. The retrieval arms use
the same template with their retrieved sessions, and both stores feed the
renderer with the same canonical session dicts, so the graph arm and the flat
arm differ only in what they retrieved.
"""

from __future__ import annotations

ID_HEADER = ("I will give you several history chats between you and a user. "
             "Please answer the question based on the relevant chat history.\n\n\n"
             "History Chats:\n\n")

NO_RETRIEVAL_ANSWER = "{question}"

ANSWER_TEMPLATE = ID_HEADER + "{sessions}\n\nCurrent Date: {date}\nQuestion: {question}\nAnswer:"

ARMS = ("full", "graph", "flat", "none")


def render_sessions(sessions: list[dict], start_index: int = 1) -> str:
    """Official nl rendering in the order given; has_answer is never shown.

    The order is the caller's: the full-context arm passes sessions sorted by
    date (what the benchmark does), the retrieval arms pass their ranking.
    """
    blocks = []
    for index, session in enumerate(sessions, start_index):
        content = session.get("content")
        if content is None:
            content = "".join(
                f"\n\n{turn.get('role', '')}: {str(turn.get('content', '')).strip()}"
                for turn in session.get("turns", [])
            )
        blocks.append(
            f"\n### Session {index}:\nSession Date: {session.get('date', '')}\n"
            f"Session Content:\n{content}\n"
        )
    return "".join(blocks)


def build_prompt(arm: str, question, sessions: list[dict] | None = None) -> str:
    """The exact text a model is shown for one arm and one question."""
    if arm == "none":
        return NO_RETRIEVAL_ANSWER.format(question=question.question)
    if arm == "full":
        ordered = sorted(question.oracle_sessions(),
                         key=lambda session: (session.get("date_epoch") or 0,
                                              str(session.get("session_id", ""))))
        return ANSWER_TEMPLATE.format(
            sessions=render_sessions(ordered),
            date=question.question_date,
            question=question.question,
        )
    if arm not in ("graph", "flat"):
        raise ValueError(f"unknown arm: {arm}")
    return ANSWER_TEMPLATE.format(
        sessions=render_sessions(sessions or []),
        date=question.question_date,
        question=question.question,
    )


def answer(client, prompt: str, max_tokens: int = 500) -> dict:
    """One answer call; the caller decides which client (model) serves it.

    LongMemEval generates with temperature 0 and at most 500 completion
    tokens, so the clients are built with temperature 0 and the cap is passed
    through to the provider.
    """
    message, usage = client.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens)
    return {
        "text": str(message.get("content") or "").strip(),
        "model": client.model,
        "prompt_tokens": int((usage or {}).get("prompt_tokens") or 0),
        "completion_tokens": int((usage or {}).get("completion_tokens") or 0),
    }
