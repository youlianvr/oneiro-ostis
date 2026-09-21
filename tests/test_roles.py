"""Offline tests for the live roles: JSON extraction, schemas, one retry."""

import json

import pytest

from llm import ModelReply
from roles import SchemaError, extract_json, manager, researcher

CHECKS = ["unit-tests", "offline-suite"]


class ScriptedPool:
    """Returns scripted answers in order; records which roles were asked."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.roles: list[str] = []

    def reply(self, role, messages, *, tools=None, budget=None, temperature=None):
        self.roles.append(role)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return ModelReply(message={"role": "assistant", "content": item}, usage={}, model="fake")


def researcher_answer(titles):
    return json.dumps({"proposals": [
        {"title": title, "rationale": "потому что тест отсутствует",
         "acceptance": ["проверка проходит"], "evidence": ["python/roles.py"],
         "check_id": "unit-tests", "risk": "low"}
        for title in titles
    ]}, ensure_ascii=False)


def test_extract_json_accepts_fences_and_nested_objects():
    assert extract_json('```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
    assert extract_json('prefix {"a": "}"} suffix') == {"a": "}"}
    with pytest.raises(SchemaError):
        extract_json("no json here")


def test_researcher_builds_proposals_with_stable_ids():
    pool = ScriptedPool([researcher_answer(["Один", "Два"])])
    proposals = researcher(pool, "dossier", CHECKS, prefix="run-c1-p")

    assert [p.proposal_id for p in proposals] == ["run-c1-p1", "run-c1-p2"]
    assert proposals[0].check_id == "unit-tests"
    assert proposals[0].acceptance == ("проверка проходит",)


def test_researcher_retries_once_on_schema_error():
    broken = json.dumps({"proposals": [{"title": "Нет критериев", "rationale": "x",
                                        "check_id": "unit-tests", "risk": "low"}]})
    pool = ScriptedPool([broken, researcher_answer(["Починенный"])])

    proposals = researcher(pool, "dossier", CHECKS)

    assert len(pool.roles) == 2
    assert proposals[0].title == "Починенный"


def test_researcher_rejects_unknown_check_id_twice():
    bad = json.dumps({"proposals": [{"title": "t", "rationale": "r",
                                     "acceptance": ["a"], "check_id": "rm -rf /",
                                     "risk": "low"}]})
    pool = ScriptedPool([bad, bad])

    with pytest.raises(SchemaError, match="check_id"):
        researcher(pool, "dossier", CHECKS)


def test_manager_assigns_a_valid_choice():
    from swarm import Proposal
    proposals = [
        Proposal("p1", "Первый", "r", ("a",), check_id="unit-tests"),
        Proposal("p2", "Второй", "r", ("a",), check_id="unit-tests"),
    ]
    answer = json.dumps({"action": "assign_worker", "chosen": "p2",
                         "reason": "дешевле", "concerns": ["мало данных"]}, ensure_ascii=False)
    pool = ScriptedPool([answer])

    decision = manager(pool, proposals, "dossier")

    assert decision.action == "assign_worker"
    assert decision.chosen == "p2"
    assert decision.evidence == ("мало данных",)


def test_manager_cannot_choose_an_unoffered_or_unknown_action():
    from swarm import Proposal
    proposals = [Proposal("p1", "Первый", "r", ("a",), check_id="unit-tests")]
    bad_choice = json.dumps({"action": "assign_worker", "chosen": "p9", "reason": "x"})
    bad_action = json.dumps({"action": "merge", "reason": "x"})
    pool = ScriptedPool([bad_choice, bad_choice])

    with pytest.raises(SchemaError, match="chosen"):
        manager(pool, proposals, "dossier")

    pool = ScriptedPool([bad_action, bad_action])
    with pytest.raises(SchemaError, match="action"):
        manager(pool, proposals, "dossier")
