"""The agent turn: what runs, what is refused, and what is recorded.

The graph is the real RecordStore and the loop is the production one; only the
provider is a stub (`chat_fakes.Model`). Every assertion here is about a fact
that lands in the store or in what the model was actually told.
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from chat_fakes import (GraphStub, MemoryLinks, Model, csrf_of, isolate, make_app, post)
from oneiro import agent, approvals, config
from oneiro.chat import ChatError, ModelReply, ToolCall
from oneiro.records import Action, State
from oneiro.runtime import Runtime
from oneiro.tools import Policy, Tool, arguments_digest, build_registry

LIMIT = 2000
CONVERSATION = "main-chat"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    """A runtime over the in-memory graph, ready to publish but never `start()`ed."""
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def page_of(owner: Runtime, *, limit: int = 500) -> list[dict]:
    return asyncio.run(owner.memory_page(limit=limit))["items"]


def actions_of(owner: Runtime) -> list[dict]:
    return [row for row in page_of(owner) if row["kind"] == "action"]


def slow_tool(effect: str, seconds: float, name: str = "slow_tool") -> Tool:
    """A tool that blocks a worker thread, like a real write or a slow read."""

    def handler(context, arguments):
        time.sleep(seconds)
        return {"finished": True, "path": arguments.get("path", "")}

    return Tool(name, "test tool", {"path": {"type": "string"}}, ("path",), ("executor",),
                effect, handler)


def run(owner, model, text, client_id, *, role="manager", registry=None, policy=None,
        tool_timeout=30.0):
    return asyncio.run(agent.run_turn(owner, text, client_id, CONVERSATION, role=role,
                                      registry=registry, policy=policy,
                                      call=model._call, tool_timeout=tool_timeout))


# ---------- an allowed call: run, recorded, and given to the model ----------


def test_an_allowed_tool_call_is_recorded_and_its_result_reaches_the_model(tmp_path, monkeypatch):
    note = tmp_path / "notes.txt"
    note.write_text("the plan is to keep it small", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(note)}, "call-1"),
        ModelReply("The note says to keep it small."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "what does the note say?", "client-0001-aaaa")

    assert result["reply"]["text"] == "The note says to keep it small."
    assert result["reply"]["role"] == "manager"
    step = result["steps"][0]
    assert step["tool"] == "read_file"
    assert step["decision"] == "allow" and step["ok"] is True
    assert step["effect"] == "read" and step["outcome"] == "none"
    assert step["may_retry"] is True
    # The model saw the file's text, and the tool result is labelled as data.
    tool_messages = [m for m in model.messages[1] if m["role"] == "tool"]
    assert "the plan is to keep it small" in tool_messages[0]["content"]
    assert "returned" in tool_messages[0]["content"]
    # One row in the store, carrying the decision and the step number.
    rows = actions_of(owner)
    assert len(rows) == 1 and rows[0]["tool"] == "read_file"
    assert rows[0]["decision"] == "allow" and rows[0]["state"] == State.COMPLETED.value
    assert rows[0]["run_id"] == "reply-client-0001-aaaa"
    assert rows[0]["labels"] == ["step:1"]


def test_two_calls_in_one_message_are_two_steps_and_both_run(tmp_path, monkeypatch):
    """A step is one call, not one message: both calls publish their own action ID.

    Measured 2026-10-12: the two calls of one message shared that message's index, so
    they published the same `act-<reply>-<index>` with different content, the store
    refused the second with `operation_collision`, and the turn died before it could
    answer — which is how seven of the eleven attempts a live measurement made at the
    task that asks for two tools at once were lost.
    """
    first = tmp_path / "alpha.txt"
    first.write_text("a zebra lives here", encoding="utf-8")
    second = tmp_path / "beta.txt"
    second.write_text("nothing to see here", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        ModelReply("", (ToolCall("call-1", "read_file", {"path": str(first)}),
                        ToolCall("call-2", "read_file", {"path": str(second)}))),
        ModelReply("Both files were read."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "read both files", "client-0004-dddd")

    assert result["reply"]["text"] == "Both files were read."
    assert [step["index"] for step in result["steps"]] == [1, 2]
    rows = sorted(actions_of(owner), key=lambda row: row["id"])
    assert [row["id"] for row in rows] == ["act-reply-client-0004-dddd-1",
                                           "act-reply-client-0004-dddd-2"]
    assert [row["labels"] for row in rows] == [["step:1"], ["step:2"]]
    tool_messages = [m for m in model.messages[1] if m["role"] == "tool"]
    assert len(tool_messages) == 2, "each call's result came back as its own message"


def test_the_stored_record_is_what_makes_a_replayed_turn_equal(tmp_path, monkeypatch):
    note = tmp_path / "notes.txt"
    note.write_text("keep it small", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(note)}, "call-1"),
        ModelReply("Small it is."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())
    first = run(owner, model, "read it", "client-0002-bbbb")
    calls = list(model.calls)

    again = run(owner, model, "read it", "client-0002-bbbb")

    assert again["replayed"] is True and model.calls == calls, "no second model call"
    assert again["reply"] == first["reply"]
    assert again["steps"] == first["steps"], "steps are rebuilt from the stored records"
    assert again["context"] is None


# ---------- refusals: recorded, and honestly reported to the model ----------


def test_a_call_for_a_tool_that_does_not_exist_is_refused_and_recorded(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[
        ModelReply("", (ToolCall("call-1", "run_sandbox", {"command": ["rm", "-rf", "/"]}),)),
        ModelReply("That tool does not exist, so I did not run anything."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "delete everything", "client-0003-cccc")

    step = result["steps"][0]
    assert step["decision"] == "deny" and step["ok"] is False
    assert step["state"] == State.FAILED.value
    assert "no tool named run_sandbox" in step["reason"]
    assert "did not run" in model.messages[1][-1]["content"]
    assert "run_sandbox" not in {t["function"]["name"] for t in model.offered[0]}


def test_a_role_boundary_refusal_keeps_the_file_and_is_recorded(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = build_registry(workspace, internet=False, max_bytes=LIMIT)
    model = Model(monkeypatch, replies=[
        Model.tool("write_file", {"path": "a.txt", "text": "x"}, "call-1"),
        ModelReply("I cannot write files from a chat turn."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "write a file", "client-0004-dddd", registry=registry)

    step = result["steps"][0]
    assert step["decision"] == "deny" and "manager" in step["reason"]
    assert step["effect"] == "workspace_write"
    assert not (workspace / "a.txt").exists(), "the refusal is not just a message"
    assert actions_of(owner)[0]["provenance"] == "system"
    assert "manager" in model.messages[1][-1]["content"]


def test_malformed_arguments_are_refused_rather_than_guessed(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[
        ModelReply("", (ToolCall("call-1", "read_file", {}, "the arguments are not valid JSON"),)),
        ModelReply("I will ask again properly."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "read something", "client-0005-eeee")

    step = result["steps"][0]
    assert step["decision"] == "deny" and "not valid JSON" in step["reason"]
    assert step["arguments"] == {} and step["ok"] is False


# ---------- a write that asks: a pending approval, and nothing run ----------


def test_review_mode_publishes_a_pending_approval_and_runs_nothing(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = build_registry(workspace, internet=False, max_bytes=LIMIT)
    # The declared decision that asks: `permissions.write_workspace = ask`.
    policy = Policy({"decisions": {"workspace_write": "ask"}, "internet_enabled": False})
    model = Model(monkeypatch, replies=[
        Model.tool("write_file", {"path": "a.txt", "text": "x"}, "call-1"),
        ModelReply("I need your confirmation before writing a.txt."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "write a.txt", "client-0006-ffff", role="executor",
                 registry=registry, policy=policy)

    step = result["steps"][0]
    assert step["decision"] == "ask" and step["state"] == State.WAITING.value
    assert not (workspace / "a.txt").exists()
    approvals = [row for row in page_of(owner) if row["kind"] == "approval"]
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["granted"] is False and approval["state"] == State.WAITING.value
    assert approval["tool"] == "write_file"
    # The approval names exactly these arguments, so it cannot release another call.
    assert approval["arguments_digest"] == arguments_digest({"path": "a.txt", "text": "x"})
    assert "did not run" in model.messages[1][-1]["content"]


# ---------- an effect that did not finish is uncertain, never retried ----------


def test_a_write_that_does_not_finish_is_uncertain_and_the_turn_stops(tmp_path, monkeypatch):
    registry = {"slow_write": slow_tool("workspace_write", 0.5, "slow_write")}
    model = Model(monkeypatch, replies=[
        Model.tool("slow_write", {"path": "a.txt"}, "call-1"),
        ModelReply("this reply must never be produced"),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "write slowly", "client-0007-gggg", role="executor",
                 registry=registry, tool_timeout=0.05)

    assert len(model.calls) == 1, "the model was not asked to carry on"
    assert result["reply"]["role"] == "system"
    assert result["reply"]["state"] == State.UNCERTAIN.value
    assert "unknown" in result["reply"]["text"]
    step = result["steps"][0]
    assert step["state"] == State.UNCERTAIN.value
    assert step["outcome"] == "uncertain"
    assert step["may_retry"] is False
    row = actions_of(owner)[0]
    assert row["state"] == State.UNCERTAIN.value
    assert row["effect"]["outcome"] == "uncertain"
    # The rule that matters: the record itself refuses a blind retry.
    assert Action.from_dict(row).may_retry() is False
    assert Action.from_dict(row).requires_inspection() is True


def test_a_read_that_does_not_finish_is_a_failure_that_may_be_retried(tmp_path, monkeypatch):
    registry = {"slow_read": slow_tool("read", 0.5, "slow_read")}
    model = Model(monkeypatch, replies=[
        Model.tool("slow_read", {"path": "a.txt"}, "call-1"),
        ModelReply("The read timed out."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "read slowly", "client-0008-hhhh", role="executor",
                 registry=registry, tool_timeout=0.05)

    step = result["steps"][0]
    assert step["state"] == State.FAILED.value and step["outcome"] == "none"
    assert step["may_retry"] is True
    assert result["reply"]["text"] == "The read timed out.", "nothing changed, so no alarm"
    assert "did not finish" in model.messages[1][-1]["content"]


def test_an_owner_grant_lets_the_same_call_run_once_and_no_further(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = build_registry(workspace, internet=False, max_bytes=LIMIT)
    review = Policy({"decisions": {"workspace_write": "ask"}, "internet_enabled": False})
    write_call = {"path": "a.txt", "text": "x"}
    owner = owner_for(tmp_path, MemoryLinks())

    # 1. The first attempt asks instead of writing.
    asked = Model(monkeypatch, replies=[
        Model.tool("write_file", write_call, "call-1"),
        ModelReply("I need your confirmation."),
    ])
    first = run(owner, asked, "write a.txt", "client-0100-aaaa", role="executor",
                registry=registry, policy=review)
    assert first["steps"][0]["decision"] == "ask"
    assert not (workspace / "a.txt").exists()

    # 2. The owner grants that exact call from the console.
    approval_id = approvals.approval_id("write_file", write_call)
    asyncio.run(approvals.decide(owner, approval_id, granted=True))

    # 3. The same call is asked again and now runs, once.
    again = Model(monkeypatch, replies=[
        Model.tool("write_file", write_call, "call-1"),
        ModelReply("Written, as you approved."),
    ])
    second = run(owner, again, "write a.txt", "client-0101-bbbb", role="executor",
                 registry=registry, policy=review)

    step = second["steps"][0]
    assert step["decision"] == "allow" and step["ok"] is True
    assert "approved" in step["reason"]
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "x"
    spent = [row for row in page_of(owner)
             if row["kind"] == "approval" and row.get("consumed_action_id")]
    assert spent and spent[0]["consumed_action_id"] == step["action_id"]

    # 4. The grant is spent: a third attempt asks again rather than writing.
    third_model = Model(monkeypatch, replies=[
        Model.tool("write_file", write_call, "call-1"),
        ModelReply("Confirm once more, please."),
    ])
    third = run(owner, third_model, "write a.txt", "client-0102-cccc", role="executor",
                registry=registry, policy=review)
    assert third["steps"][0]["decision"] == "ask"
    assert asyncio.run(approvals.granted_for(owner, "write_file", write_call)) is None


def test_a_handler_that_raises_is_a_failed_call_not_a_dead_turn(tmp_path, monkeypatch):
    def explode(context, arguments):
        raise OSError("the disk said no")

    registry = {"boom": Tool("boom", "test", {"path": {"type": "string"}}, ("path",),
                             ("executor",), "workspace_write", explode)}
    model = Model(monkeypatch, replies=[
        Model.tool("boom", {"path": "a.txt"}, "call-1"),
        ModelReply("That write failed, so nothing was written."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "write", "client-0009-iiii", role="executor", registry=registry)

    step = result["steps"][0]
    assert step["decision"] == "allow" and step["ok"] is False
    assert step["state"] == State.FAILED.value and step["outcome"] == "failed"
    assert step["may_retry"] is True
    assert "the disk said no" in step["result"]


# ---------- asking the owner, and the step limit ----------


def test_asking_the_owner_leaves_a_question_and_keeps_the_turn_moving(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[
        Model.tool("ask_owner", {"question": "Which folder should I search?"}, "call-1"),
        ModelReply("I have asked you which folder to search."),
    ])
    owner = owner_for(tmp_path, MemoryLinks())

    result = run(owner, model, "find my notes", "client-0010-jjjj")

    questions = [row for row in page_of(owner) if row["kind"] == "question"]
    assert len(questions) == 1
    assert questions[0]["question"] == "Which folder should I search?"
    assert questions[0]["answer"] == ""
    assert questions[0]["state"] == State.WAITING.value
    assert "has not answered" in model.messages[1][-1]["content"]
    assert result["steps"][0]["ok"] is True
    assert "answered" not in result["reply"]["text"].lower()


def test_the_step_limit_ends_the_turn_with_a_statement_not_a_pretend_answer(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("", (ToolCall("call-1", "list_files",
                                                                 {"path": str(tmp_path)}),))
                                        for _ in range(6)])
    owner = owner_for(tmp_path, MemoryLinks())

    result = asyncio.run(agent.run_turn(owner, "list forever", "client-0011-kkkk", CONVERSATION,
                                        call=model._call, max_steps=2))

    assert result["reply"]["role"] == "system"
    assert result["reply"]["state"] == State.FAILED.value
    assert "stopped after 2 tool steps" in result["reply"]["text"]
    assert len(result["steps"]) == 2
    assert len(model.calls) == 2, "no third model call after the limit"


# ---------- what the model is offered, and what it is not ----------


def test_the_offered_tools_follow_the_settings(tmp_path, monkeypatch):
    """The declared defaults offer the workspace write; an empty folder does not."""
    model = Model(monkeypatch, replies=[ModelReply("nothing to read")])
    owner = owner_for(tmp_path, MemoryLinks())

    run(owner, model, "hello", "client-0012-llll")

    offered = {tool["function"]["name"] for tool in model.offered[0]}
    expected = {"read_file", "list_files", "write_file", "fetch_url",
                "ask_owner", "remember", "find_skills", "read_skill",
                "web_search", "read_attachment"}
    assert offered == expected, offered

    # The setting is what decides: point the tool workspace at nothing and the
    # write tool is not offered at all.
    real_value = config.value
    monkeypatch.setattr(config, "value", lambda key, default=None: (
        "" if key == "tools.workspace" else real_value(key, default)))
    second = Model(monkeypatch, replies=[ModelReply("nothing to read")])
    run(owner, second, "hello again", "client-0012-llll-b")
    offered = {tool["function"]["name"] for tool in second.offered[0]}
    assert "write_file" not in offered, "an empty tool workspace offers no write"
    assert "read_file" in offered

    # The same rule for the skill tools: they are offered because a catalog loads, and
    # they go away when the one the settings name cannot be read at all.
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(tmp_path / "not-a-catalog.json"))
    third = Model(monkeypatch, replies=[ModelReply("nothing to read")])
    run(owner, third, "hello a third time", "client-0012-llll-c")
    offered = {tool["function"]["name"] for tool in third.offered[0]}
    assert "find_skills" not in offered, "an unreadable catalog offers no skill tools"
    assert "read_file" in offered


def test_a_web_read_follows_the_declared_internet_setting(tmp_path, monkeypatch):
    """Off refuses with a reason; the shipped default allows a declared read."""
    owner = owner_for(tmp_path, MemoryLinks())
    model = Model(monkeypatch, replies=[
        Model.tool("fetch_url", {"url": "https://example.com/"}, "call-1"),
        ModelReply("I could not reach the web."),
    ])
    config.save({"tools.internet": False})

    result = run(owner, model, "read that page", "client-0013-mmmm")

    step = result["steps"][0]
    assert step["decision"] == "deny" and "internet access is disabled" in step["reason"]
    assert step["outcome"] == "none"

    # The owner's declared default is a free web read; the same call is allowed.
    config.save({"tools.internet": True})
    allowed = Model(monkeypatch, replies=[
        Model.tool("fetch_url", {"url": "https://example.com/"}, "call-2"),
        ModelReply("I read it."),
    ])
    second = run(owner, allowed, "read that page again", "client-0013-mmmm-b")
    assert second["steps"][0]["decision"] == "allow"


def test_the_declared_mode_and_permissions_shape_the_policy():
    """What the settings page shows is what the agent obeys."""
    config.save({"permissions.mode": "workspace", "permissions.delete": "ask"})
    free = agent.default_policy()
    assert free.decision("workspace_write") == "allow"
    assert free.decision("web_read") == "allow"
    assert free.decision("delete") == "ask"
    assert free.decision("publish") == "deny"

    config.save({"permissions.mode": "strict"})
    strict = agent.default_policy()
    assert strict.decision("workspace_write") == "ask" and strict.decision("web_read") == "ask"

    # Every effect that has a setting is read from it, none is left behind.
    config.save({"permissions.mode": "workspace", "permissions.web_read": "deny",
                 "permissions.install": "allow", "permissions.send_publish": "ask"})
    declared = agent.default_policy()
    assert declared.decision("web_read") == "deny"
    assert declared.decision("install") == "allow"
    assert declared.decision("send") == declared.decision("upload") == "ask"


def test_a_permission_set_to_deny_is_a_boundary_even_with_an_approval():
    """`permissions.delete = deny` refuses outright instead of asking."""
    config.save({"permissions.delete": "deny", "permissions.install": "ask"})
    policy = agent.default_policy()
    delete = Tool("delete_file", "test", {"path": {"type": "string"}}, ("path",),
                  ("executor",), "delete")
    install = Tool("install_package", "test", {"name": {"type": "string"}}, ("name",),
                   ("executor",), "install")

    assert policy.check(delete, "executor", {"path": "a.txt"})[0] == "deny"
    # An approval cannot open a boundary the owner closed.
    assert policy.check(delete, "executor", {"path": "a.txt"}, approved=True)[0] == "deny"
    assert policy.check(install, "executor", {"name": "x"})[0] == "ask"


# ---------- long work does not hold up the rest of the chat ----------


def test_memory_reads_keep_answering_while_a_tool_call_is_in_flight(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[
        Model.tool("slow_read", {"path": "a.txt"}, "call-1"),
        ModelReply("done"),
    ])
    registry = {"slow_read": slow_tool("read", 0.4, "slow_read")}
    owner = owner_for(tmp_path, MemoryLinks())

    async def scenario() -> tuple[dict, float]:
        turn = asyncio.create_task(agent.run_turn(
            owner, "read slowly", "client-0014-nnnn", CONVERSATION, registry=registry,
            call=model._call, tool_timeout=5.0))
        await asyncio.sleep(0.1)              # the tool is running in a worker thread
        started = time.monotonic()
        page = await owner.memory_page(limit=50)
        elapsed = time.monotonic() - started
        await turn
        return page, elapsed

    page, elapsed = asyncio.run(scenario())

    assert page["items"], "memory answered while the turn was still in flight"
    assert elapsed < 0.2, f"a memory read waited {elapsed:.3f}s for the tool call"


# ---------- the HTTP path the owner actually uses ----------


def test_the_api_returns_the_steps_and_replays_them_unchanged(tmp_path, monkeypatch):
    note = tmp_path / "notes.txt"
    note.write_text("hello from disk", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(note)}, "call-1"),
        ModelReply("It says hello."),
    ])
    links = MemoryLinks()

    with TestClient(make_app(tmp_path, links)) as client:
        token = csrf_of(client)
        body = {"text": "read the note", "client_id": "client-0015-oooo"}
        first = post(client, "/api/message", body, token).json()
        again = post(client, "/api/message", body, token).json()

    assert first["reply"]["text"] == "It says hello."
    assert first["steps"][0]["tool"] == "read_file"
    assert first["steps"][0]["decision"] == "allow"
    assert first["steps"][0]["reason"], "why a call was allowed is part of the record"
    assert again["replayed"] is True
    assert again["steps"] == first["steps"]
    assert len(model.calls) == 2, "one model call for the tool, one for the answer"


def test_a_provider_outage_after_a_tool_step_keeps_the_step_and_invents_no_reply(
        tmp_path, monkeypatch):
    note = tmp_path / "notes.txt"
    note.write_text("hello", encoding="utf-8")
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(note)}, "call-1"),
        ChatError("the provider is unreachable (URLError)"),
    ])
    links = MemoryLinks()

    with TestClient(make_app(tmp_path, links)) as client:
        token = csrf_of(client)
        response = post(client, "/api/message",
                        {"text": "read it", "client_id": "client-0016-pppp"}, token)
        page = asyncio.run(client.app.state.runtime._graph.call("page", limit=500))

    assert response.status_code == 503 and "unreachable" in response.json()["error"]
    kinds = [row["kind"] for row in page["items"]]
    assert kinds.count("conversation_message") == 1, "the owner's message, and no reply"
    actions = [row for row in page["items"] if row["kind"] == "action"]
    assert len(actions) == 1 and actions[0]["tool"] == "read_file", (
        "the step that did run is still recorded when the model then fails")
