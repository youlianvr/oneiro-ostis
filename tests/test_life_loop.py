"""Offline tests for the loop: restart resume, freezes, escalation, dossier."""

import json
from pathlib import Path

import pytest

from bridge import LifeSession
from life_loop import LoopConfig, build_dossier, locate_paths, run_loop
from llm import BudgetExhausted, ModelReply, ProviderDown


class FakeBridge:
    def __init__(self, latest=None):
        self.latest = latest
        self.org_events = []
        self.closed = False

    def load_latest_life_session(self):
        return self.latest

    def start_life_session(self, session_id, *, goals=None, self_state=None):
        session = LifeSession(session_id=session_id, created_at=1,
                              goals=list(goals or []), self_state=dict(self_state or {}))
        self.latest = session
        return session

    def record_life_event(self, session, event, *, origin, verified=False):
        session.events.append({**event, "origin": origin, "verified": verified})
        session.revision += 1
        return session

    def record_organization_event(self, **event):
        self.org_events.append(event)

    def finish_life_session(self, session, *, self_state=None, status="finished"):
        session.status = status
        session.self_state = dict(self_state or {})
        return session

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, replies):
        self.replies = list(replies)

    def reply(self, role, messages, *, tools=None, budget=None, temperature=None):
        if budget is not None:
            budget.charge(role)  # mirror ModelPool so budget tests mean something
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return ModelReply(message={"role": "assistant", "content": item}, usage={},
                          model="fake")

    def evidence(self):
        return []


PROPOSAL_JSON = json.dumps({"proposals": [
    {"title": "Мелкое улучшение", "rationale": "реальная слабость",
     "acceptance": ["проверка проходит"], "evidence": ["python/roles.py"],
     "check_id": "unit-tests", "risk": "low"},
]}, ensure_ascii=False)

ESCALATE_JSON = json.dumps({"action": "escalate", "chosen": None,
                            "reason": "нужно решение владельца", "concerns": []},
                           ensure_ascii=False)


def make_config(tmp_path, cycles=1):
    repo_root, project_root = locate_paths()
    return LoopConfig(
        repo_root=repo_root, project_root=project_root,
        worktrees_root=tmp_path / "worktrees", cycles=cycles,
        interval_seconds=0, run_tag="testrun",
    )


def test_escalation_ends_the_run_with_a_record(tmp_path):
    bridge = FakeBridge()
    pool = FakePool([PROPOSAL_JSON, ESCALATE_JSON])

    outcome = run_loop(make_config(tmp_path), bridge=bridge, pool=pool,
                       sleep=lambda _s: None, echo=lambda _s: None)

    assert outcome["status"] == "waiting_owner"
    assert outcome["prs"] == []
    assert bridge.latest.status == "waiting_owner"
    kinds = [event["kind"] for event in bridge.org_events]
    assert "loop_start" in kinds and "loop_end" in kinds
    assert not (tmp_path / "worktrees").exists()


def test_provider_down_freezes_with_the_reason(tmp_path):
    bridge = FakeBridge()
    pool = FakePool([ProviderDown("both models are down")])

    outcome = run_loop(make_config(tmp_path), bridge=bridge, pool=pool,
                       sleep=lambda _s: None, echo=lambda _s: None)

    assert outcome["status"] == "frozen"
    assert "down" in outcome["freeze_reason"]
    assert bridge.latest.status == "frozen"
    frozen = [event for event in bridge.org_events if event["kind"] == "loop_frozen"]
    assert frozen and "down" in frozen[0]["payload"]["reason"]


def test_budget_exhaustion_freezes_with_the_reason(tmp_path):
    bridge = FakeBridge()
    pool = FakePool([PROPOSAL_JSON, ESCALATE_JSON])
    config = make_config(tmp_path)
    config.model_calls_per_cycle = 0

    outcome = run_loop(config, bridge=bridge, pool=pool,
                       sleep=lambda _s: None, echo=lambda _s: None)

    assert outcome["status"] == "frozen"
    assert "budget" in outcome["freeze_reason"]


def test_restart_resumes_the_same_session(tmp_path):
    previous = LifeSession(session_id="life-old", created_at=1, status="running",
                           events=[], revision=3)
    bridge = FakeBridge(latest=previous)
    pool = FakePool([PROPOSAL_JSON, ESCALATE_JSON])

    outcome = run_loop(make_config(tmp_path), bridge=bridge, pool=pool,
                       sleep=lambda _s: None, echo=lambda _s: None)

    assert outcome["session_id"] == "life-old"
    assert any(event.get("kind") == "process_restart" for event in previous.events)
    kinds = [event["kind"] for event in bridge.org_events]
    assert "loop_resumed" in kinds


def test_dossier_names_the_checks_and_modules(tmp_path):
    dossier = build_dossier(make_config(tmp_path))
    assert "## python modules" in dossier
    assert "unit-tests" in dossier
    assert "python/roles.py" in dossier
