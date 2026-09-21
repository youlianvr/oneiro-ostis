"""The two stores under test, holding the same sessions two ways.

``FlatJournal`` is one text file per corpus: word search reads it back with
nothing but the text itself. ``GraphStore`` writes typed records into OSTIS
through the bridge: the session date is a numeric relation, the body a JSON
payload, membership is a relation to the corpus node. Both return the same
canonical session dicts, so the prompts the two arms see are byte-identical.
"""

from __future__ import annotations

import re
from pathlib import Path

from retrieval import bm25_scores, rank_graph, rank_lexical

BLOCK_RE = re.compile(
    r"### Session ID: (?P<sid>\S+)\nSession Date: (?P<date>[^\n]*)\nSession Content:\n"
    r"(?P<body>.*?)(?=\n### Session ID: |\Z)",
    re.S,
)


def render_content(turns: list[dict]) -> str:
    """The official LongMemEval natural-language turn rendering."""
    return "".join(f"\n\n{turn.get('role', '')}: {str(turn.get('content', '')).strip()}"
                   for turn in turns)


class FlatJournal:
    """One journal file per corpus; search is word search over its blocks."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, corpus: str) -> Path:
        return self.root / f"journal_{corpus}.txt"

    def write(self, corpus: str, sessions: list[dict]) -> Path:
        blocks = []
        for session in sessions:
            content = render_content(session.get("turns", []))
            blocks.append(
                f"### Session ID: {session['session_id']}\n"
                f"Session Date: {session.get('date', '')}\n"
                f"Session Content:\n{content}\n"
            )
        path = self.path(corpus)
        path.write_text("".join(blocks), encoding="utf-8")
        return path

    def read(self, corpus: str) -> list[dict]:
        path = self.path(corpus)
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8")
        sessions = []
        for match in BLOCK_RE.finditer(text):
            body = match.group("body")
            if body.endswith("\n"):
                body = body[:-1]
            sessions.append({
                "session_id": match.group("sid"),
                "date": match.group("date"),
                "date_epoch": 0,
                "turns": [],
                "content": body,
            })
        return sessions

    def search(self, corpus: str, question: str, k: int) -> list[dict]:
        sessions = self.read(corpus)
        if not sessions:
            return []
        scores = bm25_scores(question, [{"turns": [{"role": "", "content": session["content"]}],
                                        "date": session.get("date", "")}
                                       for session in sessions])
        order = sorted(range(len(sessions)), key=lambda i: (-scores[i], i))
        picked = []
        for index in order[:k]:
            row = dict(sessions[index])
            row["score"] = round(scores[index], 4)
            row["why"] = "lexical"
            picked.append(row)
        return picked


class GraphStore:
    """Typed sessions in OSTIS, read and ranked through the bridge."""

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def write(self, corpus: str, sessions: list[dict]) -> int:
        return self.bridge.save_memory_sessions(corpus, sessions)

    def read(self, corpus: str) -> list[dict]:
        return self.bridge.load_memory_sessions(corpus)

    def search(self, corpus: str, question: str, k: int,
               question_epoch: int) -> list[dict]:
        return rank_graph(question, self.read(corpus), k, question_epoch)


def search_flat(journal: FlatJournal, corpus: str, question: str, k: int) -> list[dict]:
    return rank_lexical(question, journal.read(corpus), k)


__all__ = ["FlatJournal", "GraphStore", "render_content", "search_flat", "rank_lexical"]
