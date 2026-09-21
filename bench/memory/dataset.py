"""LongMemEval data: where it lives, how it is read, how a run samples it.

The dataset stays outside the repository (15 MB oracle, 277 MB s-cleaned):
``ONEIRO_LME_DIR`` or ``~/.openclaw/datasets/longmemeval``. The s file is
decoded question by question from the raw text, so a sample never materialises
the whole 277 MB as Python objects.

The canonical session dict used by every store and arm:

    {"session_id": str, "date": str, "date_epoch": int,
     "turns": [{"role": str, "content": str}, ...]}
"""

from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

DEFAULT_DIR = Path(os.environ.get("ONEIRO_LME_DIR") or (Path.home() / ".openclaw" / "datasets" / "longmemeval"))
ORACLE_FILE = "longmemeval_oracle.json"
S_FILE = "longmemeval_s_cleaned.json"

ALL_TYPES = (
    "single-session-user",
    "single-session-assistant",
    "multi-session",
    "temporal-reasoning",
    "knowledge-update",
    "single-session-preference",
)

# Fifty questions, weighted towards the types where memory has to do work.
DEFAULT_SAMPLE = {
    "single-session-user": 7,
    "single-session-assistant": 6,
    "multi-session": 12,
    "temporal-reasoning": 12,
    "knowledge-update": 9,
    "single-session-preference": 4,
}

_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})(?:\s*\([^)]*\))?(?:\s+(\d{1,2}):(\d{2}))?")


def parse_date(text: str) -> tuple[str, int]:
    """Session/question date text and its epoch seconds; 0 when unparseable."""
    match = _DATE_RE.search(text or "")
    if not match:
        return (text or ""), 0
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour, minute = int(match.group(4) or 0), int(match.group(5) or 0)
    try:
        stamp = datetime(year, month, day, hour, minute)
    except ValueError:
        return (text or ""), 0
    return (text or ""), int(stamp.timestamp())


@dataclass
class Question:
    """One benchmark question with its haystack already cut to size."""

    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    question_epoch: int
    haystack: list[dict] = field(default_factory=list)
    answer_session_ids: list[str] = field(default_factory=list)

    @property
    def is_abstention(self) -> bool:
        """LongMemEval marks unanswerable questions in the id itself."""
        return "_abs" in self.question_id

    @property
    def evidence(self) -> list[dict]:
        wanted = set(self.answer_session_ids)
        return [session for session in self.haystack if session["session_id"] in wanted]

    def oracle_sessions(self) -> list[dict]:
        """The full-context setting: every session in the oracle haystack."""
        return list(self.haystack)


def session_to_dict(session_id: str, date_text: str, turns_raw: list) -> dict:
    _, epoch = parse_date(date_text)
    turns = [
        {"role": str(turn.get("role", "")), "content": str(turn.get("content", ""))}
        for turn in turns_raw
        if isinstance(turn, dict)
    ]
    return {"session_id": session_id, "date": date_text, "date_epoch": epoch, "turns": turns}


def iter_questions(path: Path) -> Iterator[dict]:
    """Decode a top-level JSON array item by item (the s file is 277 MB)."""
    text = Path(path).read_text(encoding="utf-8")
    start = text.find("[")
    if start < 0:
        raise ValueError(f"{path} is not a JSON array")
    decoder = json.JSONDecoder()
    index = start + 1
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n,":
            index += 1
        if index >= length or text[index] == "]":
            return
        obj, index = decoder.raw_decode(text, index)
        yield obj


def cap_haystack(haystack: list[dict], answer_session_ids: list[str],
                 cap: Optional[int], seed: int, question_id: str) -> list[dict]:
    """Keep every evidence session and a seeded sample of the distractors.

    The full s haystack is ~500 sessions; a cap makes the run affordable while
    the needle (the evidence) is never dropped, so the question stays
    answerable. The sample is deterministic for a given run seed.
    """
    if cap is None or len(haystack) <= cap:
        return haystack
    evidence_ids = set(answer_session_ids)
    evidence = [session for session in haystack if session["session_id"] in evidence_ids]
    rest = [session for session in haystack if session["session_id"] not in evidence_ids]
    rng = random.Random(f"{seed}:{question_id}")
    rng.shuffle(rest)
    keep = evidence + rest[: max(0, cap - len(evidence))]
    order = {session["session_id"]: i for i, session in enumerate(haystack)}
    return sorted(keep, key=lambda session: order[session["session_id"]])


def to_question(raw: dict, *, cap: Optional[int] = None, seed: int = 0) -> Question:
    dates = raw.get("haystack_dates") or []
    ids = raw.get("haystack_session_ids") or []
    haystack = []
    for index, turns_raw in enumerate(raw.get("haystack_sessions") or []):
        session_id = str(ids[index]) if index < len(ids) else f"s{index}"
        date_text = str(dates[index]) if index < len(dates) else ""
        haystack.append(session_to_dict(session_id, date_text, turns_raw))
    answer_ids = [str(value) for value in (raw.get("answer_session_ids") or [])]
    haystack = cap_haystack(haystack, answer_ids, cap, seed, str(raw.get("question_id", "")))
    date_text, epoch = parse_date(raw.get("question_date", ""))
    return Question(
        question_id=str(raw.get("question_id", "")),
        question_type=str(raw.get("question_type", "")),
        question=str(raw.get("question", "")),
        answer=str(raw.get("answer", "")),
        question_date=date_text,
        question_epoch=epoch,
        haystack=haystack,
        answer_session_ids=answer_ids,
    )


def select_questions(questions: list[Question], per_type: Optional[dict] = None,
                     seed: int = 20260921) -> list[Question]:
    """A deterministic type-balanced sample; same seed, same questions."""
    wanted = per_type or DEFAULT_SAMPLE
    by_type: dict[str, list[Question]] = {}
    for question in questions:
        by_type.setdefault(question.question_type, []).append(question)
    selected: list[Question] = []
    for question_type, count in wanted.items():
        pool = list(by_type.get(question_type, []))
        rng = random.Random(f"{seed}:{question_type}")
        rng.shuffle(pool)
        selected.extend(pool[:count])
    return sorted(selected, key=lambda question: question.question_id)


def load_questions(name: str = "oracle", *, data_dir: Optional[Path] = None,
                   per_type: Optional[dict] = None, seed: int = 20260921,
                   cap: Optional[int] = None, limit: Optional[int] = None) -> list[Question]:
    """Load a sample: ``oracle`` (evidence sessions) or ``s`` (full haystacks)."""
    path = Path(data_dir or DEFAULT_DIR) / (ORACLE_FILE if name == "oracle" else S_FILE)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found; download it first (see bench/memory/README.md)"
        )
    selected_ids: Optional[set[str]] = None
    if name != "oracle":
        # Two passes over the big file: decide the sample from the light fields,
        # then keep only the sampled questions' haystacks in memory.
        light = [
            Question(
                question_id=str(raw.get("question_id", "")),
                question_type=str(raw.get("question_type", "")),
                question=str(raw.get("question", "")),
                answer="",
                question_date="",
                question_epoch=0,
            )
            for raw in iter_questions(path)
        ]
        selected_ids = {question.question_id for question in select_questions(light, per_type, seed)}
        if limit:
            selected_ids = set(sorted(selected_ids)[:limit])
    questions: list[Question] = []
    for raw in iter_questions(path):
        if selected_ids is not None and str(raw.get("question_id", "")) not in selected_ids:
            continue
        questions.append(to_question(raw, cap=cap, seed=seed))
        if limit and len(questions) >= limit:
            break
    if name == "oracle":
        questions = select_questions(questions, per_type, seed)
        if limit:
            questions = questions[:limit]
    return questions
