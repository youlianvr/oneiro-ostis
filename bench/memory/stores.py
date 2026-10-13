"""The two stores under test, holding the same sessions two ways.

``FlatJournal`` is one text file per corpus: word search reads it back with nothing but the
text itself. ``GraphStore`` publishes every session of a corpus as a typed record into OSTIS
and reads the corpus back out of the graph before ranking it, so the graph arm is a real
round trip through the graph and not a writer reading its own list back.

Both return the same canonical session dicts, so the prompts the two arms see are
byte-identical. The one deliberate difference is what a store carries as *data*:

* the graph arm's record holds the session's own date as a machine-readable field, so
  ``rank_graph`` can open a time window before it looks at similarity;
* the journal has that date only inside the text it was given, which is why the flat arm
  scores it as words and has no window to open at all.

Under the retired bridge the date was a numeric graph relation and the body a JSON payload;
the v1 rewrite replaced that vocabulary with typed records (``oneiro.records``), so a session
now travels as a record whose labels carry its date. What the arm tests — a store that keeps
structure a search can use, against one that keeps text — is unchanged, and this paragraph
is here so the change is named in the code rather than quietly implied.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from retrieval import bm25_scores, rank_graph, rank_lexical

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT / "python") not in sys.path:
    sys.path.insert(0, str(PROJECT / "python"))

from oneiro.graph_worker import GraphWorker            # noqa: E402
from oneiro.records import Note, Provenance, State, decode  # noqa: E402
from oneiro.store import MAX_LINK_BYTES               # noqa: E402

#: Where a session's own date travels in the record, as ``date-epoch=<seconds>``: a
#: machine-readable field, which is exactly what the flat journal does not have. ``=`` is
#: the separator rather than ``:`` because a benchmark date text contains one
#: ("2023/05/20 (Sat) 10:00").
EPOCH_FIELD = "date-epoch="
#: How long one graph call of the bench's own may take. The product's lane default is ten
#: seconds, which is right for a page view; a lane that publishes a hundred records in a row
#: beside everything else on the machine is allowed the demo measurement's own 30 s.
LANE_TIMEOUT = 30.0
#: How many records one page read asks for. Pages are walked to the end, so this is a
#: bound on one round trip, not on the corpus.
PAGE_LIMIT = 200

BLOCK_RE = re.compile(
    r"### Session ID: (?P<sid>\S+)\nSession Date: (?P<date>[^\n]*)\nSession Content:\n"
    r"(?P<body>.*?)(?=\n### Session ID: |\Z)",
    re.S,
)


def render_content(turns: list[dict]) -> str:
    """The official LongMemEval natural-language turn rendering."""
    return "".join(f"\n\n{turn.get('role', '')}: {str(turn.get('content', '')).strip()}"
                   for turn in turns)


def _key(corpus: str, session_id: str) -> str:
    """A stream-safe identity for one session: the ids a graph entry can be named by.

    Session ids in the dataset are not bounded identifiers (they carry underscores and
    arbitrary text), so the entry and the record are named by a digest of the corpus and
    the session id. The id itself travels in the record's labels, where free text is
    allowed, and is what ``session_from_record`` reads back.
    """
    digest = hashlib.sha256(f"{corpus}\0{session_id}".encode("utf-8")).hexdigest()
    return "lme-session-" + digest[:48]


def _field(labels: tuple[str, ...], name: str) -> str:
    """One ``name=value`` field of a record's labels; empty when the record lacks it."""
    prefix = name + "="
    for label in labels:
        if label.startswith(prefix):
            return label[len(prefix):]
    return ""


def session_record(corpus: str, session: dict) -> Note:
    """One held session as a record: text in ``body``, the session's own date as a field."""
    content = session.get("content")
    if content is None:
        content = render_content(session.get("turns", []))
    session_id = str(session.get("session_id", ""))
    date_text = str(session.get("date", ""))
    epoch = int(session.get("date_epoch") or 0)
    record = Note(
        id=_key(corpus, session_id),
        topic=f"LongMemEval session {session_id}",
        body=content,
        sources=(corpus,),
        labels=("lme-session", f"corpus={corpus}", f"session={session_id}",
                f"date={date_text}", f"{EPOCH_FIELD}{epoch}"),
        provenance=Provenance.OBSERVATION,
        state=State.COMPLETED,
    )
    size = len(record.to_json().encode("utf-8"))
    if size > MAX_LINK_BYTES:
        raise ValueError(f"session {session_id} of {corpus} is {size} bytes and does not fit "
                         f"the graph's {MAX_LINK_BYTES}-byte record bound")
    return record


def session_from_record(record: Note) -> dict:
    """The canonical session dict a held record stands for.

    The shape matches what ``FlatJournal.read`` returns, because that is the point of the
    comparison: the graph arm's content and the journal's content are the same text, and
    the date is either a typed field (here) or words inside that text (there).
    """
    return {
        "session_id": _field(record.labels, "session"),
        "date": _field(record.labels, "date"),
        "date_epoch": int(_field(record.labels, "date-epoch") or 0),
        "turns": [],
        "content": record.body,
    }


def cell_record(run_tag: str, cell: dict) -> Note:
    """One measured cell as a record: the whole cell in ``body``, its key fields as labels.

    The retired stand wrote a bare JSON payload per cell under the name
    ``memory_bench_result_<tag>_<question>_<arm>_r<n>``. That name is kept as the record's
    topic so the old and the new evidence line up by name, and the cell's own fields are
    repeated as labels so a reader can select cells in the graph without parsing the body.
    """
    name = (f"memory_bench_result_{run_tag}_{cell['question_id']}_{cell['arm']}"
            f"_r{cell['run']}")
    labels = ("memory-bench-cell", f"run={run_tag}", f"stage={cell['stage']}",
              f"question={cell['question_id']}", f"type={cell['question_type']}",
              f"arm={cell['arm']}", f"run_index={cell['run']}", f"status={cell['status']}",
              f"judge={cell.get('judge_label') or 'unjudged'}",
              f"passed={bool(cell.get('judge_passed'))}",
              f"recall={cell.get('recall_at_k')}",
              f"answer-model={cell.get('answer_model') or 'none'}",
              f"judge-model={cell.get('judge_model') or 'none'}")
    body = json.dumps(cell, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    record = Note(
        id="lme-cell-" + hashlib.sha256(f"{run_tag}\0{name}".encode("utf-8")).hexdigest()[:48],
        topic=name,
        body=body,
        sources=(run_tag,),
        labels=labels,
        provenance=Provenance.VERIFIED_TOOL_OUTCOME,
        state=State.COMPLETED,
    )
    size = len(record.to_json().encode("utf-8"))
    if size > MAX_LINK_BYTES:
        raise ValueError(f"cell {name} is {size} bytes and does not fit the graph's "
                         f"{MAX_LINK_BYTES}-byte record bound")
    return record


class RecordLane:
    """One graph lane of the bench's own, driven from a synchronous run.

    ``GraphWorker`` is asynchronous because the product serves pages from it; a benchmark is
    a batch job and stays synchronous. So the lane owns one private event loop for its whole
    life and runs every call on it: one worker, one loop, calls in order. The worker never
    sees two event loops, and nothing is left half-dispatched between calls.
    """

    def __init__(self, stream: str, url: str, lease_path: Path,
                 timeout: float = LANE_TIMEOUT) -> None:
        self.stream = stream
        self.published = 0
        self._worker = GraphWorker(url, stream, Path(lease_path), timeout=timeout)
        self._loop = asyncio.new_event_loop()

    def publish(self, record: Note) -> dict[str, Any]:
        """Append one record to this lane's stream and confirm the graph holds it."""
        result = self._run(self._worker.call("append", record=record.to_dict(),
                                             operation_id=record.id, expected_revision=0))
        self.published += 1
        return result

    def records(self) -> list[Note]:
        """Every record in this lane's stream, decoded, newest first, paged to the end."""
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            page = self._run(self._worker.call("page", cursor=cursor, limit=PAGE_LIMIT))
            rows.extend(page["items"])
            cursor = page["cursor"]
            if not cursor:
                break
        return [decode(row) for row in rows]

    def save(self) -> dict[str, Any]:
        """Ask the graph for its native Save; the report says what that did and did not prove."""
        return self._run(self._worker.save())

    def close(self) -> None:
        try:
            self._run(self._worker.close())
        finally:
            self._loop.close()

    def _run(self, coroutine: Any) -> Any:
        return self._loop.run_until_complete(coroutine)


def lane_for(stream: str, *, url: str, data_root: Path,
             timeout: float = LANE_TIMEOUT) -> RecordLane:
    """A lane whose stream is this name's own, so a read walks only its own records."""
    return RecordLane(stream, url, Path(data_root) / f"{stream}.lock", timeout=timeout)


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
    """Typed sessions in OSTIS, written and read through a lane of the bench's own."""

    def __init__(self, lane: RecordLane) -> None:
        self.lane = lane

    def write(self, corpus: str, sessions: list[dict]) -> int:
        """Publish one record per session; the graph confirms every one of them."""
        written = 0
        for session in sessions:
            self.lane.publish(session_record(corpus, session))
            written += 1
        return written

    def read(self, corpus: str) -> list[dict]:
        """Read this corpus back out of the graph, as canonical session dicts."""
        held = [record for record in self.lane.records()
                if isinstance(record, Note) and corpus in record.sources]
        held.reverse()          # pages come newest first; the corpus was written in order
        return [session_from_record(record) for record in held]

    def search(self, corpus: str, question: str, k: int,
               question_epoch: int) -> list[dict]:
        return rank_graph(question, self.read(corpus), k, question_epoch)


def search_flat(journal: FlatJournal, corpus: str, question: str, k: int) -> list[dict]:
    return rank_lexical(question, journal.read(corpus), k)


__all__ = ["FlatJournal", "GraphStore", "RecordLane", "cell_record", "lane_for",
           "rank_lexical", "render_content", "search_flat", "session_from_record",
           "session_record"]
