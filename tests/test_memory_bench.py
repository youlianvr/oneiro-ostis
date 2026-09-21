"""Offline tests for the LongMemEval memory benchmark.

Nothing here touches the network or the live OSTIS: the graph store runs
against a fake bridge that keeps sessions in a dict, the judge and the arms run
against fake clients, and the dataset functions run against a tiny JSON file.
The property that matters most, that the graph arm and the flat arm show the
model the same bytes for the same sessions, is asserted directly.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "memory"))

import arms
import dataset as dataset_module
import judge as judge_module
from retrieval import bm25_scores, rank_graph, rank_lexical, time_window, tokenize
from stores import FlatJournal, GraphStore, render_content, search_flat


def make_session(session_id, date, epoch, turns):
    return {"session_id": session_id, "date": date, "date_epoch": epoch,
            "turns": [{"role": role, "content": text} for role, text in turns]}


def make_question(**overrides):
    defaults = dict(
        question_id="q1",
        question_type="single-session-user",
        question="What was the issue with my car?",
        answer="GPS system not functioning",
        question_date="2023/04/10 (Mon) 23:07",
        question_epoch=dataset_module.parse_date("2023/04/10 (Mon) 23:07")[1],
        haystack=[make_session("s1", "2023/04/08 (Sat) 21:36", 1680984960,
                               [("user", "I got my car serviced."),
                                ("assistant", "How did it go?")])],
        answer_session_ids=["s1"],
    )
    defaults.update(overrides)
    return dataset_module.Question(**defaults)


class FakeBridge:
    """In-memory stand-in for OneiroBridge's memory methods."""

    def __init__(self):
        self.corpora = {}

    def save_memory_sessions(self, corpus, sessions, batch=25):
        self.corpora.setdefault(corpus, {})
        for session in sessions:
            self.corpora[corpus][session["session_id"]] = json.loads(json.dumps(session))
        return len(sessions)

    def load_memory_sessions(self, corpus):
        return list(self.corpora.get(corpus, {}).values())


class FakeClient:
    def __init__(self, model="fake-model", replies=None):
        self.model = model
        self.replies = list(replies or ["yes"])
        self.prompts = []

    def chat(self, messages, tools=None, max_tokens=None):
        self.prompts.append(messages[0]["content"])
        text = self.replies.pop(0) if self.replies else "yes"
        return {"content": text}, {"prompt_tokens": 11, "completion_tokens": 2}


# ------------------------------------------------------------------ dataset

def test_parse_date_reads_the_benchmark_format():
    text, epoch = dataset_module.parse_date("2023/04/10 (Mon) 23:07")
    assert text == "2023/04/10 (Mon) 23:07"
    assert epoch > 0
    assert dataset_module.parse_date("not a date")[1] == 0


def test_cap_haystack_keeps_evidence_and_is_deterministic():
    sessions = [make_session(f"s{i}", "2023/01/01 (Sun) 10:00", 1000 + i,
                             [("user", f"note {i}")]) for i in range(30)]
    capped = dataset_module.cap_haystack(sessions, ["s7"], cap=10, seed=5, question_id="q")
    ids = [session["session_id"] for session in capped]
    assert "s7" in ids
    assert len(capped) == 10
    again = dataset_module.cap_haystack(sessions, ["s7"], cap=10, seed=5, question_id="q")
    assert [session["session_id"] for session in again] == ids
    other = dataset_module.cap_haystack(sessions, ["s7"], cap=10, seed=6, question_id="q")
    other_ids = [session["session_id"] for session in other]
    assert len(other_ids) == 10 and "s7" in other_ids
    # a different seed draws different distractors (the needle never moves)
    assert set(other_ids) != set(ids)


def test_iter_questions_decodes_array_item_by_item(tmp_path):
    path = tmp_path / "tiny.json"
    path.write_text(json.dumps([{"question_id": "a"}, {"question_id": "b"}]), encoding="utf-8")
    assert [raw["question_id"] for raw in dataset_module.iter_questions(path)] == ["a", "b"]


def test_select_questions_is_balanced_and_repeatable():
    pool = []
    for kind, count in dataset_module.DEFAULT_SAMPLE.items():
        for index in range(count + 3):
            pool.append(make_question(question_id=f"{kind}-{index}", question_type=kind))
    first = dataset_module.select_questions(pool, seed=11)
    second = dataset_module.select_questions(pool, seed=11)
    assert [q.question_id for q in first] == [q.question_id for q in second]
    per_type = {}
    for question in first:
        per_type[question.question_type] = per_type.get(question.question_type, 0) + 1
    assert per_type == dataset_module.DEFAULT_SAMPLE


# ---------------------------------------------------------------- retrieval

def test_tokenize_drops_stopwords_and_short_tokens():
    assert tokenize("What is the issue with my car?") == ["issue", "car"]


def test_bm25_ranks_the_relevant_session_first():
    sessions = [
        make_session("s1", "", 0, [("user", "I am baking bread with sourdough")]),
        make_session("s2", "", 0, [("user", "My car has a GPS system issue")]),
        make_session("s3", "", 0, [("user", "Planning a trip to Norway")]),
    ]
    scores = bm25_scores("What was the issue with my car GPS?", sessions)
    assert scores[1] == max(scores)


def test_time_window_relative_phrases():
    now = dataset_module.parse_date("2023/04/10 (Mon) 23:07")[1]
    window = time_window("What did I do last week?", now)
    assert window is not None
    assert abs((now - window.start) - 7 * 86400) < 2
    assert window.holds(now - 3 * 86400)
    assert not window.holds(now - 10 * 86400)


def test_time_window_calendar_mentions():
    now = dataset_module.parse_date("2023/04/10 (Mon) 23:07")[1]
    assert time_window("What happened on May 15?", now) is not None
    year = time_window("What did I read about in 2022?", now)
    assert year is not None and year.start < year.end
    assert time_window("How many books did I read?", now) is None


def test_rank_graph_prefers_the_named_window():
    now = dataset_module.parse_date("2023/04/10 (Mon) 23:07")[1]
    sessions = [
        make_session("old", "2023/02/01 (Wed) 10:00", now - 60 * 86400,
                     [("user", "I bought a new camera lens")]),
        make_session("recent", "2023/04/08 (Sat) 10:00", now - 2 * 86400,
                     [("user", "I bought a new camera lens")]),
    ]
    ranked = rank_graph("What camera lens did I buy last week?", sessions, k=2, question_epoch=now)
    assert ranked[0]["session_id"] == "recent"
    assert ranked[0]["why"] == "time_window"


def test_rank_lexical_has_no_time_awareness():
    now = dataset_module.parse_date("2023/04/10 (Mon) 23:07")[1]
    sessions = [
        make_session("old", "2023/02/01 (Wed) 10:00", now - 60 * 86400,
                     [("user", "I bought a new camera lens")]),
        make_session("recent", "2023/04/08 (Sat) 10:00", now - 2 * 86400,
                     [("user", "I bought a new camera lens")]),
    ]
    ranked = rank_lexical("What camera lens did I buy last week?", sessions, k=2)
    assert all(row["why"] == "lexical" for row in ranked)


# ------------------------------------------------------------------- stores

def test_flat_journal_roundtrip_and_search(tmp_path):
    journal = FlatJournal(tmp_path)
    sessions = [
        make_session("s1", "2023/01/01 (Sun) 10:00", 1000, [("user", "I play the violin")]),
        make_session("s2", "2023/01/02 (Mon) 10:00", 2000, [("user", "My car needs service")]),
    ]
    journal.write("corpus", sessions)
    read_back = journal.read("corpus")
    assert [session["session_id"] for session in read_back] == ["s1", "s2"]
    assert read_back[1]["content"] == render_content(sessions[1]["turns"])
    hits = search_flat(journal, "corpus", "car service", k=1)
    assert hits[0]["session_id"] == "s2"
    assert hits[0]["score"] > 0


def test_graph_store_roundtrip_with_fake_bridge():
    bridge = FakeBridge()
    store = GraphStore(bridge)
    sessions = [
        make_session("s1", "2023/01/01 (Sun) 10:00", 1000, [("user", "I play the violin")]),
        make_session("s2", "2023/01/02 (Mon) 10:00", 2000, [("user", "My car needs service")]),
    ]
    assert store.write("corpus", sessions) == 2
    assert {session["session_id"] for session in store.read("corpus")} == {"s1", "s2"}
    hits = store.search("corpus", "car service", k=1, question_epoch=2500)
    assert hits[0]["session_id"] == "s2"


def test_both_arms_show_the_same_bytes_for_the_same_sessions(tmp_path):
    sessions = [
        make_session("s1", "2023/01/01 (Sun) 10:00", 1000,
                     [("user", "First line"), ("assistant", "Second line")]),
        make_session("s2", "2023/01/02 (Mon) 10:00", 2000, [("user", "Later note")]),
    ]
    journal = FlatJournal(tmp_path)
    journal.write("c", sessions)
    flat_rows = journal.read("c")
    graph_rows = sessions

    flat_render = arms.render_sessions(flat_rows)
    graph_render = arms.render_sessions(graph_rows)
    assert flat_render == graph_render
    assert "### Session 1:" in flat_render and "Current Date" not in flat_render


# --------------------------------------------------------------------- arms

def test_prompt_none_is_the_question_alone():
    question = make_question()
    assert arms.build_prompt("none", question) == question.question


def test_prompt_full_uses_the_official_wording_and_every_session():
    question = make_question()
    prompt = arms.build_prompt("full", question)
    assert prompt.startswith("I will give you several history chats")
    assert "### Session 1:" in prompt
    assert "Current Date: 2023/04/10 (Mon) 23:07" in prompt
    assert prompt.rstrip().endswith("Answer:")


def test_prompt_for_retrieval_arms_contains_only_retrieved_sessions():
    question = make_question()
    retrieved = [make_session("s1", "2023/04/08 (Sat) 21:36", 1680984960,
                              [("user", "I got my car serviced.")])]
    prompt = arms.build_prompt("graph", question, retrieved)
    assert "I got my car serviced." in prompt


def test_answer_reads_usage_and_model():
    client = FakeClient(replies=["The GPS system was not working."])
    result = arms.answer(client, "prompt")
    assert result["text"] == "The GPS system was not working."
    assert result["prompt_tokens"] == 11


# -------------------------------------------------------------------- judge

def test_judge_prompt_shapes_per_type():
    for question_type in judge_module.TEMPLATES:
        prompt = judge_module.build_prompt(question_type, "Q?", "gold", "response")
        assert "Question: Q?" in prompt and "Model Response: response" in prompt
    abstention = judge_module.build_prompt("multi-session", "Q?", "gold", "response", abstention=True)
    assert "unanswerable" in abstention


def test_judge_label_is_yes_in_the_response():
    client = FakeClient(replies=["No."])
    assert judge_module.verdict(client, "multi-session", "q", "a", "r")["passed"] is False
    client = FakeClient(replies=["Yes, it contains the answer."])
    assert judge_module.verdict(client, "multi-session", "q", "a", "r")["passed"] is True


def test_judge_unknown_type_fails_loudly():
    with pytest.raises(ValueError):
        judge_module.build_prompt("not-a-type", "q", "a", "r")
