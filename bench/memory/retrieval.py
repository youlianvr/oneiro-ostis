"""Retrieval: BM25 over session text, temporal cues, and the two policies.

The benchmark's two memory arms share the tokenizer and the scorer on purpose:
the difference under test is the store and the ranking policy, not the
arithmetic. ``rank_lexical`` is plain word search over the journal;
``rank_graph`` uses the typed dates the graph carries: a question that names a
time window is first answered from inside that window, and near-ties are
preferring the more recent session (time first, similarity second).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

DAY = 86400.0
WEEK = 7 * DAY

STOPWORDS = frozenset(
    """a an the and or but if then else of to in on at for with about as by is are was were be
    been being it its this that these those i you he she we they my your his her our their me him
    them do does did have has had can could will would should may might must not no yes from than
    so such very just also there here what which who when where why how""".split()
)

TOKEN_RE = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall((text or "").lower())
            if len(token) > 1 and token not in STOPWORDS]


def session_text(session: dict) -> str:
    """What the scorer reads: the session's visible text, dates included.

    Graph sessions arrive as turns, journal sessions as one rendered blob;
    both shapes must score identically, so the text includes whichever is set.
    """
    turns = " ".join(f"{turn.get('role', '')} {turn.get('content', '')}"
                     for turn in session.get("turns", []))
    return f"{session.get('date', '')} {session.get('content') or ''} {turns}"


class BM25:
    """Okapi BM25 over a small corpus held in memory."""

    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.doc_count = len(docs)
        self.avg_len = (sum(len(doc) for doc in docs) / self.doc_count) if docs else 0.0
        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for doc in docs:
            counts: dict[str, int] = {}
            for token in doc:
                counts[token] = counts.get(token, 0) + 1
            self.tf.append(counts)
            for token in counts:
                df[token] = df.get(token, 0) + 1
        self.idf = {
            token: math.log(1.0 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            for token, freq in df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        results = [0.0] * self.doc_count
        for index, counts in enumerate(self.tf):
            length = sum(counts.values()) or 1
            total = 0.0
            for token in query_tokens:
                freq = counts.get(token)
                if not freq:
                    continue
                idf = self.idf.get(token, 0.0)
                total += idf * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                )
            results[index] = total
        return results


def bm25_scores(question: str, sessions: list[dict]) -> list[float]:
    return BM25([tokenize(session_text(session)) for session in sessions]).scores(tokenize(question))


# ---------------------------------------------------------------- time windows

_MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}
_MONTHS.update({name[:3]: number for name, number in list(_MONTHS.items())})

_FULL_DATE_RE = re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b")
_MONTH_DAY_RE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_DAY_MONTH_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(_MONTHS) + r")\.?\b", re.I)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_RELATIVE_RE = re.compile(
    r"\b(?:last|past|previous|this)\s+(\d+)?\s*(day|week|month|year)s?\b", re.I)
_YESTERDAY_RE = re.compile(r"\byesterday\b", re.I)
_TODAY_RE = re.compile(r"\btoday\b", re.I)


@dataclass
class TimeWindow:
    start: int
    end: int

    def holds(self, epoch: int) -> bool:
        return bool(epoch) and self.start <= epoch <= self.end


def _stamp(year: int, month: int = 1, day: int = 1, hour: int = 0, minute: int = 0) -> int:
    try:
        return int(datetime(year, month, day, hour, minute).timestamp())
    except ValueError:
        return 0


def time_window(question: str, question_epoch: int) -> Optional[TimeWindow]:
    """The window a question names, if it names one.

    Deliberately modest: explicit calendar dates, month-day mentions, relative
    spans (yesterday, last week, last N months) and a bare year. Questions
    without a cue return None and the ranking stays purely lexical.
    """
    if not question_epoch:
        return None
    text = question or ""
    match = _FULL_DATE_RE.search(text)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        stamp = _stamp(year, month, day)
        return TimeWindow(stamp - 2 * DAY, stamp + 2 * DAY) if stamp else None
    match = _MONTH_DAY_RE.search(text)
    if not match:
        match = _DAY_MONTH_RE.search(text)
    if match:
        first, second = match.group(1), match.group(2)
        if first.isdigit():
            day, month = int(first), _MONTHS.get(second.lower(), 0)
        else:
            month, day = _MONTHS.get(first.lower(), 0), int(second)
        year = datetime.fromtimestamp(question_epoch).year
        stamp = _stamp(year, month, day)
        return TimeWindow(stamp - 2 * DAY, stamp + 2 * DAY) if stamp else None
    match = _YESTERDAY_RE.search(text)
    if match:
        return TimeWindow(int(question_epoch - 1.5 * DAY), int(question_epoch - 0.5 * DAY))
    match = _TODAY_RE.search(text)
    if match:
        return TimeWindow(int(question_epoch - DAY), int(question_epoch + DAY))
    match = _RELATIVE_RE.search(text)
    if match:
        amount = int(match.group(1) or 1)
        unit = match.group(2).lower()
        spans = {"day": DAY, "week": WEEK, "month": 30 * DAY, "year": 365 * DAY}
        span = spans[unit] * amount
        return TimeWindow(int(question_epoch - span), int(question_epoch))
    match = _YEAR_RE.search(text)
    if match:
        year = int(match.group(1))
        return TimeWindow(_stamp(year, 1, 1), _stamp(year + 1, 1, 1) - 1)
    return None


def _recency(sessions: list[dict]) -> list[float]:
    stamps = [int(session.get("date_epoch") or 0) for session in sessions]
    low, high = min(stamps), max(stamps)
    if high <= low:
        return [0.0] * len(sessions)
    return [(stamp - low) / (high - low) for stamp in stamps]


def rank_lexical(question: str, sessions: list[dict], k: int) -> list[dict]:
    """Flat store policy: pure word search, no notion of time."""
    scores = bm25_scores(question, sessions)
    order = sorted(range(len(sessions)), key=lambda i: (-scores[i], i))
    picked = []
    for index in order[:k]:
        row = dict(sessions[index])
        row["score"] = round(scores[index], 4)
        row["why"] = "lexical"
        picked.append(row)
    return picked


def rank_graph(question: str, sessions: list[dict], k: int,
               question_epoch: int) -> list[dict]:
    """Graph store policy: the time window first, similarity second.

    With a window: sessions inside it are ranked first; if the window holds
    fewer than k, the remainder is filled lexically from outside it, so recall
    is never traded for neatness. Inside any pool, a near-tie goes to the more
    recent session.
    """
    if not sessions:
        return []
    scores = bm25_scores(question, sessions)
    recency = _recency(sessions)
    peak = max(scores) if scores else 0.0
    combined = [score + 0.25 * peak * recency[i] for i, score in enumerate(scores)]

    window = time_window(question, question_epoch)
    inside = [i for i, session in enumerate(sessions) if window and window.holds(session["date_epoch"])]
    outside = [i for i in range(len(sessions)) if i not in set(inside)]
    inside.sort(key=lambda i: (-combined[i], i))
    outside.sort(key=lambda i: (-combined[i], i))
    order = (inside + outside) if inside else outside

    picked = []
    inside_set = set(inside)
    for index in order[:k]:
        row = dict(sessions[index])
        row["score"] = round(combined[index], 4)
        row["why"] = "time_window" if index in inside_set else "lexical"
        picked.append(row)
    return picked
