"""The offline guard for the memory stand: what it renders, ranks and records.

The stand's whole answer rests on one claim — the two stores under test hold the same text
and differ only in what structure the ranking is allowed to use — so this file checks that
claim without a graph server, without a provider key and without the dataset:

* **the renderer**: the journal and the graph arm are handed byte-identical session text,
  and the prompt builder puts that text in front of the model unchanged;
* **both ranking paths**: the flat arm is pure word search with no notion of time, while the
  graph arm opens the window a question names first and fills the rest from outside it —
  never dropping the evidence to keep the window neat;
* **the record**: one held session survives the trip into the graph and back (id, date,
  epoch, content), with its date as a machine-readable field — which is exactly what the
  journal does not carry;
* **the bookkeeping**: an unjudged cell is counted as unjudged and never as a wrong answer,
  a refused arm is refused by name, and a provider failure is a failure and not a zero.

`bench/memory/README.md` points at this file, so it is the reason a reader can trust the two
stores hold the same content without running the benchmark again.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT = Path(__file__).resolve().parents[1]
for extra in (PROJECT / "python", PROJECT / "bench" / "memory"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import arms as arms_module                       # noqa: E402
import dataset as dataset_module                 # noqa: E402
import model_chain                               # noqa: E402
import run as bench_run                          # noqa: E402
import stores as stores_module                   # noqa: E402
from oneiro.chat import ChatError                # noqa: E402
from oneiro.records import Note, decode          # noqa: E402
from retrieval import bm25_scores, rank_graph, rank_lexical, time_window  # noqa: E402

DAY = 86400
#: One question's date, so a window can be named in a question and found in the sessions.
QUESTION_EPOCH = int(datetime(2023, 10, 1, 12, 0).timestamp())


def epoch_of(day: str) -> int:
    """The epoch of a session date, taken from the calendar rather than from an offset."""
    return int(datetime.strptime(day, "%Y/%m/%d").timestamp())


def session(session_id: str, date: str, day: str, text: str) -> dict:
    """One canonical session in the shape both stores are handed."""
    return {
        "session_id": session_id,
        "date": date,
        "date_epoch": epoch_of(day),
        "turns": [{"role": "user", "content": text},
                  {"role": "assistant", "content": f"about {text}"}],
    }


SESSIONS = [
    session("s-old-bike", "2023/02/01 (Wed) 09:00", "2023/02/01",
            "the bicycle needs a new rear rack"),
    session("s-bike-rack", "2023/09/20 (Wed) 10:00", "2023/09/20",
            "bicycle rack fitted, bicycle rack is steel"),
    session("s-cooking", "2023/09/25 (Mon) 18:00", "2023/09/25",
            "risotto recipe with saffron, cooking for six"),
]


def question(text: str, epoch: int = QUESTION_EPOCH):
    return dataset_module.Question(
        question_id="q-1", question_type="temporal-reasoning", question=text,
        answer="a steel rack", question_date="2023/10/01 (Sun) 12:00",
        question_epoch=epoch, haystack=SESSIONS, answer_session_ids=["s-bike-rack"])


def test_the_two_stores_are_handed_the_same_text(tmp_path: Path) -> None:
    """The comparison is only clean if the store does not change what it holds."""
    journal = stores_module.FlatJournal(tmp_path / "journals")
    journal.write("corpus", SESSIONS)
    flat = {row["session_id"]: row for row in journal.read("corpus")}
    held = {record.topic.split()[-1]: stores_module.session_from_record(record)
            for record in (stores_module.session_record("corpus", row) for row in SESSIONS)}

    assert set(flat) == set(held) == {row["session_id"] for row in SESSIONS}
    for session_id, row in flat.items():
        assert held[session_id]["content"] == row["content"], session_id
        assert held[session_id]["date"] == row["date"], session_id


def test_the_prompt_is_the_same_for_both_arms() -> None:
    """`flat` and `graph` differ in retrieval, never in the wording the model sees."""
    asked = question("Which bicycle rack is fitted?")
    ranking = rank_lexical(asked.question, SESSIONS, 2)
    assert arms_module.build_prompt("flat", asked, ranking) == \
        arms_module.build_prompt("graph", asked, ranking)


def test_the_flat_arm_has_no_time_window_and_the_graph_arm_opens_one(tmp_path: Path) -> None:
    """The typed date is the graph arm's whole advantage, so it is asserted, not assumed."""
    asked = question("What did I fit on 2023/09/20?")
    lexical = rank_lexical(asked.question, SESSIONS, 1)
    typed = rank_graph(asked.question, SESSIONS, 1, asked.question_epoch)

    assert lexical[0]["session_id"] == "s-bike-rack"      # word search finds the words
    assert lexical[0]["why"] == "lexical"                 # and has no window to open
    assert typed[0]["session_id"] == "s-bike-rack"
    assert typed[0]["why"] == "time_window"
    # A journal read carries no typed date at all: the date is words inside its text, which
    # is why the flat arm is scored by words and has no window to open.
    journal = stores_module.FlatJournal(tmp_path / "journals")
    journal.write("corpus", SESSIONS)
    assert {row["date_epoch"] for row in journal.read("corpus")} == {0}


def test_the_graph_arm_fills_k_from_outside_the_window() -> None:
    """Recall is never traded for neatness: a narrow window still returns k sessions."""
    asked = question("What did I fit on 2023/09/20?")
    picked = rank_graph(asked.question, SESSIONS, 3, asked.question_epoch)
    assert len(picked) == 3
    assert len({row["session_id"] for row in picked}) == 3
    assert picked[0]["why"] == "time_window"
    assert sum(1 for row in picked if row["why"] == "lexical") == 2


def test_a_window_with_nothing_inside_falls_back_to_similarity() -> None:
    """A question that names a date nothing happened on is ranked by words alone."""
    asked = question("Which risotto did I cook on 2024/01/01?")
    window = time_window(asked.question, asked.question_epoch)
    assert window is not None
    assert not any(window.holds(row["date_epoch"]) for row in SESSIONS)
    picked = rank_graph(asked.question, SESSIONS, 2, asked.question_epoch)
    assert [row["why"] for row in picked] == ["lexical", "lexical"]
    # The best word match leads, exactly as the flat arm would rank it.
    scores = bm25_scores(asked.question, SESSIONS)
    best = SESSIONS[max(range(len(scores)), key=lambda index: scores[index])]["session_id"]
    assert picked[0]["session_id"] == best


def test_a_held_session_survives_the_record_round_trip() -> None:
    """What the graph arm reads back is what the flat arm was handed."""
    original = SESSIONS[1]
    record = stores_module.session_record("corpus", original)
    assert isinstance(record, Note) and record.state.value == "completed"
    read_back = stores_module.session_from_record(decode(record.to_dict()))
    assert read_back == {
        "session_id": original["session_id"],
        "date": original["date"],
        "date_epoch": original["date_epoch"],
        "turns": [],
        "content": stores_module.render_content(original["turns"]),
    }


def test_a_session_too_large_for_the_graph_is_named_not_truncated() -> None:
    """A record that does not fit is refused by name, so a silent half-session is impossible."""
    huge = session("s-huge", "2023/09/20 (Wed) 10:00", "2023/09/20", "x" * 200_000)
    with pytest.raises(ValueError, match="s-huge"):
        stores_module.session_record("corpus", huge)


def test_a_cell_keeps_the_name_the_old_stand_used() -> None:
    """Old and new evidence line up by name, and a cell's fields are selectable in the graph."""
    cell = {"run_tag": "s-50-4", "stage": "s", "question_id": "q1", "question_type": "multi-session",
            "arm": "graph", "run": 1, "status": "ok", "judge_label": "yes", "judge_passed": True,
            "recall_at_k": 0.8, "answer_model": "m-1", "judge_model": "m-2"}
    record = stores_module.cell_record("s-50-4", cell)
    assert record.topic == "memory_bench_result_s-50-4_q1_graph_r1"
    assert "arm=graph" in record.labels and "judge=yes" in record.labels
    assert json.loads(record.body) == cell


def test_an_unjudged_cell_is_not_a_wrong_answer() -> None:
    """A judge that gave no verdict leaves a hole in the count, not a failure in it."""
    def cell(arm: str, status: str = "ok", label: str = "yes", passed: bool = True) -> dict:
        return {"arm": arm, "status": status, "judge_label": label, "judge_passed": passed,
                "recall_at_k": 0.5, "question_type": "multi-session",
                "prompt_tokens": 10, "completion_tokens": 5}

    summary = bench_run.summarize([cell("graph"), cell("graph", passed=False),
                                   cell("graph", label="", passed=False),
                                   cell("graph", status="provider_error", label="")])
    row = summary["per_arm"]["graph"]
    assert (row["cells"], row["ok"], row["judged"], row["unjudged"]) == (4, 3, 2, 1)
    assert row["accuracy"] == 0.5


def test_the_report_names_where_the_sessions_live_and_what_the_save_proved() -> None:
    payload = {
        "run_tag": "s-50-4", "stage": "s", "questions": 50, "k": 5, "cap": 100,
        "seed": 20260921, "answer_models": ["main"], "judge_models": ["auto/coding"],
        "journals": "/bench/journals",
        "graph": {"stream": "lme-s-50-4", "streams_per_corpus": 50,
                  "sessions_published": 5000, "cells_stream": "lme-cells-s-50-4",
                  "cells_published": 150,
                  "save": {"saved": True, "durable": False, "seconds": 3.5}},
        "summary": bench_run.summarize([]),
        # A cell's verdict belongs to the model that served it, so the report names them:
        # a routing name is not a model, and a row of numbers without the model is a claim
        # about nothing.
        "records": [{"arm": "graph", "answer_model": "codestral-2508",
                     "judge_model": "mistral-code-latest"}],
    }
    report = bench_run.render_report(payload)
    assert "one stream per corpus" in report
    assert '"saved": true' in report and '"durable": false' in report
    assert "lme-cells-s-50-4" in report
    assert "answer codestral-2508 ×1" in report
    assert "judge mistral-code-latest ×1" in report


def test_the_runner_refuses_a_graph_arm_without_a_graph() -> None:
    """An empty context must never be recorded as a graph result again."""
    assert bench_run.main(["--stage", "s", "--arms", "graph", "--no-ostis"]) == 2


def test_a_provider_failure_is_a_provider_failure(monkeypatch) -> None:
    """A refused call raises `ProviderError`, never an AttributeError inside the arms."""
    def refused(*args, **kwargs):
        raise ChatError("the provider answered HTTP 500", status=500, retryable=True)

    monkeypatch.setattr(model_chain, "chat_call", refused)
    client = model_chain.ChatClient("main", "key", "http://127.0.0.1:9/v1")
    with pytest.raises(model_chain.ProviderError, match="main"):
        client.chat([{"role": "user", "content": "hi"}])


def test_the_chain_names_what_served_the_call(monkeypatch) -> None:
    """A row of results belongs to one model, and the record says which one answered."""
    def answered(messages, **kwargs):
        if kwargs["model"] == "main":
            raise ChatError("the provider answered HTTP 429", status=429, retryable=True)
        return SimpleNamespace(content="an answer", usage={"prompt_tokens": 7},
                               served="auto/coding-2026")

    monkeypatch.setattr(model_chain, "chat_call", answered)
    chain = model_chain.ModelChain(["main", "auto/coding"], "http://127.0.0.1:9/v1", "key")
    message, usage = chain.chat([{"role": "user", "content": "hi"}], max_tokens=500)
    assert message["content"] == "an answer"
    assert usage == {"prompt_tokens": 7, "completion_tokens": 0}
    assert chain.model == "auto/coding-2026"
    assert chain.failures and chain.failures[0].startswith("main:")


def test_the_chain_reports_every_reason_when_it_is_exhausted(monkeypatch) -> None:
    def refused(*args, **kwargs):
        raise ChatError("the provider is unreachable (URLError)", retryable=True)

    monkeypatch.setattr(model_chain, "chat_call", refused)
    chain = model_chain.ModelChain(["main", "auto/coding"], "http://127.0.0.1:9/v1", "key")
    with pytest.raises(model_chain.ProviderError) as caught:
        chain.chat([{"role": "user", "content": "hi"}])
    assert "model chain exhausted" in str(caught.value)
    assert "main:" in str(caught.value) and "auto/coding:" in str(caught.value)
