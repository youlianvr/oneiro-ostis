"""Offline tests for the model-access layer: budget, fallback, evidence."""

import pytest

from llm import (
    BudgetExhausted,
    CallBudget,
    ModelPool,
    ProviderDown,
    load_api_key,
)


class FakeChatClient:
    """Scripted stand-in for the real provider client."""

    script: dict = {}
    calls: list = []

    def __init__(self, model, api_key="", base_url="", temperature=0.2):
        self.model = model

    def chat(self, messages, tools=None):
        FakeChatClient.calls.append(self.model)
        item = FakeChatClient.script[self.model]
        if isinstance(item, Exception):
            raise item
        return item, {}


def make_pool(roles=None, fallback="spare"):
    return ModelPool(
        api_key="test-key", base_url="http://test",
        roles=roles or {"researcher": "primary"},
        fallback=fallback,
        client_factory=FakeChatClient,
    )


def test_budget_charges_then_exhausts():
    budget = CallBudget(max_calls=2)
    budget.charge("a")
    budget.charge("b")
    with pytest.raises(BudgetExhausted):
        budget.charge("c")


def test_reply_uses_the_primary_model():
    FakeChatClient.script = {"primary": {"role": "assistant", "content": "ok"}}
    FakeChatClient.calls = []
    pool = make_pool()

    reply = pool.reply("researcher", [{"role": "user", "content": "hi"}])

    assert reply.model == "primary"
    assert pool.calls[-1].ok is True
    assert "primary" in FakeChatClient.calls


def test_reply_falls_back_when_the_primary_dies():
    FakeChatClient.script = {
        "primary": ProviderDown("primary is down"),
        "spare": {"role": "assistant", "content": "ok"},
    }
    FakeChatClient.calls = []
    pool = make_pool()

    reply = pool.reply("researcher", [])

    assert reply.model == "spare"
    assert [record.model for record in pool.calls] == ["primary", "spare"]
    assert pool.calls[0].ok is False


def test_reply_raises_provider_down_when_the_chain_dies():
    FakeChatClient.script = {
        "primary": ProviderDown("primary is down"),
        "spare": ProviderDown("spare is down"),
    }
    pool = make_pool()

    with pytest.raises(ProviderDown) as failure:
        pool.reply("researcher", [])
    assert "primary is down" in str(failure.value)
    assert "spare is down" in str(failure.value)
    assert [record.ok for record in pool.calls] == [False, False]


def test_budget_exhausted_before_any_call():
    FakeChatClient.script = {"primary": {"role": "assistant", "content": "ok"}}
    FakeChatClient.calls = []
    pool = make_pool()
    budget = CallBudget(max_calls=0)

    with pytest.raises(BudgetExhausted):
        pool.reply("researcher", [], budget=budget)
    assert FakeChatClient.calls == []


def test_evidence_is_json_ready():
    FakeChatClient.script = {"primary": {"role": "assistant", "content": "ok"}}
    pool = make_pool()
    pool.reply("researcher", [])
    evidence = pool.evidence()
    assert evidence and evidence[0]["role"] == "researcher"
    assert evidence[0]["ok"] is True


def test_load_api_key_prefers_environment(monkeypatch):
    monkeypatch.setenv("ONEIRO_API_KEY", "from-env")
    assert load_api_key() == "from-env"
