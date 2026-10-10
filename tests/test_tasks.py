"""A task and its runs: the lifecycle, one attempt at a time, and honest states.

Migrated from `test_task_runner.py`, `test_worker.py`, `test_swarm_protocol.py`,
`test_life_loop.py` and `test_heartbeat.py`: the rules those files carried that
still exist in this product, each one named where it came from.

* a job that was already taken on is not taken on twice and the owner is not told
  twice (`test_task_runner`);
* an attempt that produced nothing is reported as such, with the reason, and gives
  up after a bounded number of tries (`test_task_runner`);
* the owner's own words are what the work runs on, and they are recorded as the
  owner's instruction rather than as a model's claim (`test_task_runner`);
* restart continues the same work instead of starting a second one (`test_life_loop` resumes
  the session, `test_heartbeat` continues one biography). One deliberate change: an attempt
  that stopped reporting is reported UNCERTAIN and is **not** resumed by itself, because
  whether it changed anything is unknown; the task continues as the next attempt once the
  owner starts it (acceptance row 11). A failed attempt, by contrast, is picked up again on
  its own up to the bounded number of tries;
* a write outside the allowed folder is the owner's decision — asked by default and
  never landing without it (`test_worker`, the path rule; the plan's
  `permissions.write_outside`);
* roles are boundaries, not labels (`test_swarm_protocol`, where the manager could
  not pick an unoffered option and the worker could not return the main branch).

Retired with the modules they tested (W9) and deliberately not carried here: the
git worktree, branch and "run the declared check before finishing" machinery of
the night organization, which the v1 product does not have.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from chat_fakes import GraphStub, MemoryLinks, Model, csrf_of, isolate, make_app, post
from oneiro import agent, cli, tasks
from oneiro.chat import ChatError, ModelReply
from oneiro.records import State
from oneiro.runtime import Runtime
from oneiro.tools import Policy, Tool

CLIENT = "client-0001-aaaa"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    """The real store over the in-memory link graph, ready to publish."""
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def add(owner, title, *, client_id=CLIENT, role="executor", detail="", blocked_by=()):
    return asyncio.run(tasks.create(owner, title=title, detail=detail, role=role,
                                    blocked_by=blocked_by, client_id=client_id))["task"]


def items(owner) -> list[dict]:
    return asyncio.run(tasks.view(owner)).tasks


def one(owner, task_id: str) -> dict:
    return {row["id"]: row for row in items(owner)}[task_id]


def stored(owner, task_id: str) -> dict:
    """The stored task record, which is what the run is handed."""
    return next(row for row in of_kind(owner, "task") if row["id"] == task_id)


def of_kind(owner, kind: str) -> list[dict]:
    return [row for row in asyncio.run(owner.memory_page(limit=500))["items"]
            if row["kind"] == kind]


def write_settings(path, values: dict) -> None:
    """A settings file as the owner writes it, since `save` would refuse these."""
    path.write_text(json.dumps(values), encoding="utf-8")


def slow_tool(effect: str, seconds: float, name: str = "slow_tool") -> Tool:
    def handler(context, arguments):
        time.sleep(seconds)
        return {"finished": True}

    return Tool(name, "test tool", {"path": {"type": "string"}}, ("path",), ("executor",),
                effect, handler)


# ---------- what exists, and what it says ----------


def test_a_new_task_is_queued_and_says_why(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Read the notes", detail="and summarise them", role="researcher")

    row = one(owner, task["id"])

    assert row["state"] == State.QUEUED.value and row["why"] == "not started yet"
    assert row["role"] == "researcher" and row["attempts"] == 0 and row["runs"] == []
    # The owner asked: it is recorded as their instruction, not as a model's claim.
    assert task["provenance"] == "owner_instruction"


def test_the_same_ask_twice_is_one_task(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    first = asyncio.run(tasks.create(owner, title="Read the notes", client_id=CLIENT))
    second = asyncio.run(tasks.create(owner, title="Read the notes", client_id=CLIENT))

    assert first["duplicate"] is False and second["duplicate"] is True
    assert len(items(owner)) == 1


def test_a_task_without_a_title_or_with_an_unknown_role_is_refused(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())

    with pytest.raises(tasks.TaskError, match="needs a title"):
        asyncio.run(tasks.create(owner, title="   ", client_id=CLIENT))
    with pytest.raises(tasks.TaskError, match="researcher or executor"):
        asyncio.run(tasks.create(owner, title="x", role="manager", client_id=CLIENT))
    with pytest.raises(tasks.TaskError, match="no such task"):
        asyncio.run(tasks.create(owner, title="x", client_id=CLIENT,
                                 blocked_by=("task-nothing",)))
    with pytest.raises(tasks.TaskError, match="no task with that id"):
        asyncio.run(tasks.history(owner, "task-nothing"))


# ---------- one attempt ----------


def test_an_attempt_runs_the_turn_and_records_what_came_of_it(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("The notes say to keep it small.")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Read the notes", detail="Say what they contain.")

    result = asyncio.run(tasks.run_now(owner, task["id"], call=model._call))

    assert result["state"] == State.COMPLETED.value
    assert result["run"]["state"] == State.COMPLETED.value
    assert result["run"]["notes"] == "The notes say to keep it small."
    row = one(owner, task["id"])
    assert row["state"] == State.COMPLETED.value and row["why"] == "finished"
    assert row["attempts"] == 1 and row["runs"][0]["attempt"] == 1
    # An executor task is not the manager: the reply carries the role it ran as.
    assert row["runs"][0]["role"] == "executor"
    # The work happened in the task's own conversation, not in the owner's chat.
    assert {message["conversation_id"] for message in of_kind(owner, "conversation_message")} == {
        f"task-{task['id']}"}


def test_the_instruction_and_the_reply_belong_to_the_attempt(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("done")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "One thing", detail="with a detail")
    result = asyncio.run(tasks.run_now(owner, task["id"], call=model._call))

    stored_messages = of_kind(owner, "conversation_message")
    instruction = next(row for row in stored_messages if row["id"].startswith("msg-"))
    reply = next(row for row in stored_messages if row["id"].startswith("reply-"))

    assert instruction["id"] == "msg-" + result["run"]["id"]
    assert instruction["role"] == "owner"
    assert instruction["text"] == "One thing\n\nwith a detail"
    assert reply["id"] == "reply-" + result["run"]["id"]
    assert reply["role"] == "executor" and reply["text"] == "done"


def test_a_finished_task_is_not_started_again_by_the_process(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("done")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "One thing")
    asyncio.run(tasks.run_now(owner, task["id"], call=model._call))
    asked = len(model.calls)

    report = asyncio.run(tasks.tick(owner, call=model._call))

    assert report["worked"] is None and report["why"] == "no task is ready"
    assert len(model.calls) == asked
    assert one(owner, task["id"])["attempts"] == 1


def test_a_turn_that_fails_reports_the_reason_and_makes_no_reply(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ChatError("the provider is down")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Never finishes")

    result = asyncio.run(tasks.run_now(owner, task["id"], call=model._call))

    assert result["state"] == State.FAILED.value
    assert "the provider is down" in result["run"]["notes"]
    assert one(owner, task["id"])["why"] == "ready for attempt 2 of 3"


def test_a_task_gives_up_after_the_bounded_number_of_attempts(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ChatError("the provider is down")] * 3)
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Never finishes")

    for _ in range(3):
        asyncio.run(tasks.run_now(owner, task["id"], retry=True, call=model._call))

    row = one(owner, task["id"])
    assert row["attempts"] == 3 and row["state"] == State.FAILED.value
    assert "gave up after 3 attempts" in row["why"]
    assert asyncio.run(tasks.tick(owner, call=model._call))["worked"] is None


# ---------- a restart ----------


def test_an_attempt_that_stopped_reporting_is_unknown_and_is_not_repeated(tmp_path, monkeypatch):
    """Acceptance row 9: the work is not done a second time after a restart."""
    model = Model(monkeypatch, replies=[ModelReply("this must never be produced")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Work that was interrupted")
    started = asyncio.run(tasks.start(owner, task["id"]))
    assert started["started"] is True and tasks.is_held(started["run"]["id"]) is True
    # The process that opened this attempt is gone, so nothing holds it any more.
    tasks.release(started["run"]["id"])

    row = one(owner, task["id"])
    assert row["state"] == State.UNCERTAIN.value
    assert "did not report back" in row["why"]

    again = asyncio.run(tasks.start(owner, task["id"]))
    assert again["started"] is False and "already open" in again["why"]

    report = asyncio.run(tasks.tick(owner, call=model._call))

    assert report["reconciled"] == [started["run"]["id"]]
    assert report["worked"] is None
    assert model.calls == []
    newest = of_kind(owner, "run")[0]                 # newest publication first
    assert newest["state"] == State.UNCERTAIN.value
    assert "never reported back" in newest["notes"]


def test_reconciling_an_interrupted_attempt_happens_once(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Interrupted")
    started = asyncio.run(tasks.start(owner, task["id"]))
    tasks.release(started["run"]["id"])

    assert asyncio.run(tasks.reconcile(owner)) == [started["run"]["id"]]
    assert asyncio.run(tasks.reconcile(owner)) == []


def test_an_attempt_this_process_holds_is_not_reconciled_away(tmp_path):
    """A run that is being worked right now is in flight, not interrupted."""
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "In flight")
    started = asyncio.run(tasks.start(owner, task["id"]))

    assert asyncio.run(tasks.reconcile(owner)) == []
    assert one(owner, task["id"])["state"] == State.RUNNING.value
    assert "in flight" in one(owner, task["id"])["why"]
    assert asyncio.run(tasks.start(owner, task["id"]))["started"] is False
    tasks.release(started["run"]["id"])


def test_only_the_owner_starts_another_attempt_after_an_unknown_outcome(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("the second try finished")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Work that was interrupted")
    started = asyncio.run(tasks.start(owner, task["id"]))
    tasks.release(started["run"]["id"])              # the process is gone
    assert asyncio.run(tasks.tick(owner, call=model._call))["worked"] is None

    result = asyncio.run(tasks.run_now(owner, task["id"], retry=True, call=model._call))

    assert result["state"] == State.COMPLETED.value
    row = one(owner, task["id"])
    assert row["attempts"] == 2 and row["state"] == State.COMPLETED.value
    assert [attempt["attempt"] for attempt in row["runs"]] == [2, 1]


def test_an_effect_that_did_not_finish_leaves_the_task_uncertain_and_unretried(tmp_path, monkeypatch):
    # The declared bound, read as the product reads it: whole seconds, no lower.
    monkeypatch.setenv("ONEIRO_AGENT_TOOL_TIMEOUT", "1")
    model = Model(monkeypatch, replies=[
        Model.tool("slow_write", {"path": "a.txt"}, "call-1"),
        ModelReply("this reply must never be produced"),
    ])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Write slowly")
    run = asyncio.run(tasks.start(owner, task["id"]))["run"]
    registry = {"slow_write": slow_tool("workspace_write", 1.5, "slow_write")}

    result = asyncio.run(tasks.work(owner, stored(owner, task["id"]), run, registry=registry,
                                    policy=Policy({"decisions": {"workspace_write": "allow"}}),
                                    call=model._call))

    assert result["state"] == State.UNCERTAIN.value
    assert one(owner, task["id"])["state"] == State.UNCERTAIN.value
    assert len(model.calls) == 1, "the turn stopped instead of asking the model to carry on"
    monkeypatch.delenv("ONEIRO_AGENT_TOOL_TIMEOUT")
    assert asyncio.run(tasks.tick(owner, call=model._call))["worked"] is None
    assert len(model.calls) == 1


# ---------- dependencies ----------


def test_a_pause_holds_the_dependents_and_lets_unrelated_work_through(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("the first is done")])
    owner = owner_for(tmp_path, MemoryLinks())
    first = add(owner, "The thing everything waits for", client_id="client-0001")
    dependent = add(owner, "The dependent", client_id="client-0002",
                    blocked_by=[first["id"]])
    grandchild = add(owner, "Waiting on the dependent", client_id="client-0003",
                     blocked_by=[dependent["id"]])
    free = add(owner, "Unrelated work", client_id="client-0004")

    by_id = {row["id"]: row for row in items(owner)}
    assert by_id[dependent["id"]]["state"] == State.WAITING.value
    assert "The thing everything waits for" in by_id[dependent["id"]]["why"]
    assert by_id[grandchild["id"]]["state"] == State.WAITING.value
    assert by_id[free["id"]]["state"] == State.QUEUED.value

    report = asyncio.run(tasks.tick(owner, call=model._call))

    assert report["worked"]["id"] == first["id"]
    # The pause is lifted one step, and nothing else was held back.
    after = {row["id"]: row["state"] for row in items(owner)}
    assert after[first["id"]] == State.COMPLETED.value
    assert after[dependent["id"]] == State.QUEUED.value
    assert after[grandchild["id"]] == State.WAITING.value
    assert after[free["id"]] == State.QUEUED.value


def test_a_task_that_waits_cannot_be_started_by_hand_either(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    blocker = add(owner, "The blocker", client_id="client-0001")
    dependent = add(owner, "The dependent", client_id="client-0002", blocked_by=[blocker["id"]])

    started = asyncio.run(tasks.start(owner, dependent["id"], retry=True))

    assert started["started"] is False
    assert "waiting" in started["why"] and "The blocker" in started["why"]


# ---------- the roles ----------


def test_a_task_offers_only_the_tools_its_role_may_use(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("nothing to do"), ModelReply("nothing to do")])
    owner = owner_for(tmp_path, MemoryLinks())
    executor = add(owner, "An executor task", client_id="client-0001", role="executor")
    researcher = add(owner, "A researcher task", client_id="client-0002", role="researcher")

    asyncio.run(tasks.run_now(owner, executor["id"], call=model._call))
    asyncio.run(tasks.run_now(owner, researcher["id"], call=model._call))

    offered = [[tool["function"]["name"] for tool in tools or ()] for tools in model.offered]
    # The policy would refuse these anyway; not offering them is the difference
    # between a boundary the model works within and a refusal it has to read.
    assert "write_file" in offered[0] and "ask_owner" not in offered[0]
    assert "write_file" not in offered[1] and "read_file" in offered[1]


def test_a_write_outside_the_working_folder_asks_and_nothing_lands_there(tmp_path, monkeypatch):
    """The plan's promise: an outside write is the owner's decision, not a cell.

    The old behaviour refused every path outside the folder outright, which made
    `permissions.write_outside` a setting nothing read. Now the effect of the call is
    `write_outside`, the default permission for it asks, the call is recorded as
    waiting and nothing is written until the owner decides.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    write_settings(tmp_path / "settings.json", {"tools.workspace": str(workspace)})
    outside = tmp_path / "escaped.txt"
    model = Model(monkeypatch, replies=[
        Model.tool("write_file", {"path": "../escaped.txt", "text": "nope"}, "call-1"),
        ModelReply("that write needs your confirmation, so nothing was written"),
    ])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Try to write outside")

    result = asyncio.run(tasks.run_now(owner, task["id"], call=model._call))

    assert not outside.exists() and not workspace.joinpath("escaped.txt").exists()
    step = result["steps"][0]
    assert step["tool"] == "write_file" and step["ok"] is False
    assert step["decision"] == "ask" and step["effect"] == "write_outside"
    assert "confirmation" in model.messages[1][-1]["content"]


# ---------- what the owner is told ----------


def test_a_finished_task_says_so_in_its_own_conversation(tmp_path, monkeypatch):
    """The task's own conversation is where its outcome is said.

    Nothing about the quiet window is asserted here, because the default window is
    22:00-09:00 and such an assertion would depend on the hour the suite runs at.
    Whether a notice is held is asserted where the window is declared explicitly:
    `test_quiet_hours_hold_a_notice_without_hiding_it` and
    `test_an_empty_quiet_window_is_never_quiet`. Whatever the hour, the notice is
    written and readable, which is what this test is for.
    """
    model = Model(monkeypatch, replies=[ModelReply("all done")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Say when it is done")

    asyncio.run(tasks.run_now(owner, task["id"], call=model._call))

    spoken = asyncio.run(tasks.notices(owner))
    assert len(spoken["notices"]) == 1
    notice = spoken["notices"][0]
    assert notice["conversation_id"] == f"task-{task['id']}"
    assert "Say when it is done" in notice["text"] and "all done" in notice["text"]
    # Whichever side of the quiet window this run landed on, the reason and the
    # label agree — never "held" with nothing said about why.
    assert ("quiet hours" in notice["why"]) if notice["held"] else notice["why"] == ""


def test_the_same_words_in_the_same_minute_are_one_notice(tmp_path):
    """A retried attempt must not tell the owner the same thing twice.

    The record is a function of the words and the minute, which is also what
    keeps the write from being refused as a collision when the two attempts
    happen to land either side of a second boundary.
    """
    owner = owner_for(tmp_path, MemoryLinks())
    moment = tasks.utcnow().replace(second=5)

    first = asyncio.run(tasks.notify(owner, "task-x", "the same words", at=moment))
    second = asyncio.run(tasks.notify(owner, "task-x", "the same words",
                                      at=moment + timedelta(seconds=30)))

    assert first["duplicate"] is False and second["duplicate"] is True
    assert len(asyncio.run(tasks.notices(owner))["notices"]) == 1


def test_quiet_hours_hold_a_notice_without_hiding_it(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEIRO_INITIATIVE_QUIET", "00:00-23:59")
    model = Model(monkeypatch, replies=[ModelReply("all done")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Say when it is done")

    asyncio.run(tasks.run_now(owner, task["id"], call=model._call))

    notice = asyncio.run(tasks.notices(owner))["notices"][0]
    assert notice["held"] is True and "quiet hours" in notice["why"]
    # Held is not hidden: the memory is the truth, the label is the interruption.
    stored_notices = [row for row in of_kind(owner, "conversation_message")
                      if row["id"].startswith("notice-")]
    assert len(stored_notices) == 1 and "held" in stored_notices[0]["labels"]


def test_an_empty_quiet_window_is_never_quiet(tmp_path):
    """The settings page promises "empty means never quiet", so it has to be true."""
    write_settings(tmp_path / "settings.json", {"initiative.quiet_hours": ""})

    assert tasks.quiet_window() is None
    assert tasks.quiet_at(tasks.utcnow().astimezone()) is False


def test_a_quiet_window_that_cannot_be_read_is_never_quiet(tmp_path):
    """A hand-edited file must not decide to be silent, nor break the notice.

    A number where text was expected is refused by the settings reader, so the
    window is unreadable in exactly the way a hand-edited file makes it. The
    notice still has to be written: losing it would be the worse failure.
    """
    write_settings(tmp_path / "settings.json", {"initiative.quiet_hours": 2200})
    owner = owner_for(tmp_path, MemoryLinks())

    assert tasks.declared_quiet_hours() == ""
    assert tasks.quiet_window() is None
    assert tasks.quiet_at(tasks.utcnow().astimezone()) is False
    written = asyncio.run(tasks.notify(owner, "task-x", "the work is done"))
    assert written["held"] is False
    assert asyncio.run(tasks.notices(owner))["notices"][0]["held"] is False


def test_suggestions_need_the_proactive_level_and_the_setting(tmp_path, monkeypatch):
    owner = owner_for(tmp_path, MemoryLinks())
    add(owner, "Half-finished work")

    monkeypatch.setenv("ONEIRO_INITIATIVE_LEVEL", "scheduled")
    quiet = asyncio.run(tasks.suggestions(owner))
    assert quiet["suggestions"] == [] and "does not speak up first" in quiet["why"]

    monkeypatch.setenv("ONEIRO_INITIATIVE_LEVEL", "proactive")
    monkeypatch.setenv("ONEIRO_INITIATIVE_SUGGESTIONS", "false")
    switched_off = asyncio.run(tasks.suggestions(owner))
    assert switched_off["suggestions"] == [] and "switched off" in switched_off["why"]

    monkeypatch.setenv("ONEIRO_INITIATIVE_SUGGESTIONS", "true")
    spoken = asyncio.run(tasks.suggestions(owner))
    assert [row["title"] for row in spoken["suggestions"]] == ["Half-finished work"]
    assert spoken["suggestions"][0]["why"] == "not started yet"


# ---------- what may start on its own ----------


def test_with_initiative_off_the_process_starts_nothing(tmp_path, monkeypatch):
    """Acceptance row 8, the other half: nothing starts with `off`."""
    monkeypatch.setenv("ONEIRO_INITIATIVE_LEVEL", "off")
    model = Model(monkeypatch, replies=[ModelReply("this must not be produced")])
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Ready work")

    report = asyncio.run(tasks.tick(owner, call=model._call))

    assert report["worked"] is None and "initiative is off" in report["why"]
    assert model.calls == [] and one(owner, task["id"])["attempts"] == 0
    # The owner's own word still runs it: `off` is about what starts by itself.
    assert asyncio.run(tasks.run_now(owner, task["id"], call=model._call))[
        "state"] == State.COMPLETED.value


def test_on_command_also_keeps_the_process_from_picking_work_up(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEIRO_INITIATIVE_LEVEL", "on_command")
    model = Model(monkeypatch, replies=[ModelReply("must not be produced")])
    owner = owner_for(tmp_path, MemoryLinks())
    add(owner, "Ready work")

    report = asyncio.run(tasks.tick(owner, call=model._call))

    assert report["worked"] is None and "only what you ask for" in report["why"]
    assert model.calls == []


def test_an_unreadable_level_is_the_cautious_one_and_says_so(tmp_path):
    write_settings(tmp_path / "settings.json", {"initiative.level": "banana"})

    assert tasks.level() == "off"
    assert tasks.picks_up_work(tasks.level()) is False
    # Cautious is not silent: a surface has to be able to say why.
    assert "initiative.level" in tasks.settings_error()


# ---------- the HTTP surface ----------


def test_the_task_surface_over_http_creates_lists_and_runs(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("over http")])
    links = MemoryLinks()
    with TestClient(make_app(tmp_path, links)) as client:
        csrf = csrf_of(client)
        created = post(client, "/api/tasks", {"title": "Over HTTP", "client_id": CLIENT}, csrf)
        assert created.status_code == 200
        task_id = created.json()["task"]["id"]

        listed = client.get("/api/tasks").json()
        assert [row["title"] for row in listed["tasks"]] == ["Over HTTP"]
        assert listed["tasks"][0]["state"] == State.QUEUED.value
        # Every declared initiative setting is on the wire, not only in the file:
        # the page reads the level, whether it picks work up, the quiet window and
        # why nothing is suggested.
        assert listed["level"] == "scheduled" and listed["picks_up_work"] is True
        assert listed["quiet_hours"] == "22:00-09:00"
        assert listed["suggestions"] == []
        assert "does not speak up first" in listed["suggests_why"]

        run = post(client, f"/api/tasks/{task_id}/run", {"retry": False}, csrf)
        assert run.status_code == 200 and run.json()["state"] == State.COMPLETED.value

        after = client.get("/api/tasks").json()
        assert after["tasks"][0]["state"] == State.COMPLETED.value
        assert after["tasks"][0]["last_result"] == "over http"
        assert after["notices"] and "Over HTTP" in after["notices"][0]["text"]

        # The run history of one task is its own surface, newest attempt first.
        history = client.get(f"/api/tasks/{task_id}")
        assert history.status_code == 200
        assert history.json()["id"] == task_id
        assert [(row["attempt"], row["state"], row["notes"])
                for row in history.json()["runs"]] == [(1, State.COMPLETED.value, "over http")]
        unknown = client.get("/api/tasks/task-nothing")
        assert unknown.status_code == 404 and "no task with that id" in unknown.json()["error"]

        refused = client.post("/api/tasks", json={"title": "no token", "client_id": CLIENT})
        assert refused.status_code == 403


def test_a_bad_task_request_over_http_says_what_is_wrong(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        csrf = csrf_of(client)
        assert client.post("/api/tasks", json={"title": "x", "client_id": CLIENT}).status_code == 403
        empty = post(client, "/api/tasks", {"title": "  ", "client_id": CLIENT}, csrf)
        assert empty.status_code == 400 and "title" in empty.json()["error"]
        role = post(client, "/api/tasks",
                    {"title": "x", "role": "manager", "client_id": CLIENT}, csrf)
        assert role.status_code == 400 and "researcher" in role.json()["error"]
        missing = post(client, "/api/tasks/task-nothing/run", {"retry": False}, csrf)
        assert missing.status_code == 404


# ---------- the command line ----------


def test_the_command_line_reads_and_prints_not_only_refuses(tmp_path, monkeypatch, capsys):
    """The terminal is a real surface, so its happy path is exercised here."""
    links = MemoryLinks()
    created = asyncio.run(tasks.create(owner_for(tmp_path, links), title="Read the notes",
                                       client_id=CLIENT))
    task_id = created["task"]["id"]
    # Each command holds its own runtime, exactly as the entrypoint does.
    monkeypatch.setattr(cli, "Runtime", lambda: owner_for(tmp_path, links))

    assert cli.main(["tasks", "list"]) == 0
    listed = capsys.readouterr().out
    assert "Read the notes" in listed and "not started yet" in listed
    assert "initiative:" in listed

    assert cli.main(["tasks", "add", "--title", "Another thing", "--role", "researcher"]) == 0
    added = capsys.readouterr().out
    assert "Another thing" in added and "run it with: oneiro tasks run" in added

    assert cli.main(["tasks", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["title"] for row in payload["tasks"]] == ["Read the notes", "Another thing"]
    assert payload["tasks"][1]["role"] == "researcher"

    # The history of one task reads in the terminal too, attempts and their notes.
    assert cli.main(["tasks", "show", task_id]) == 0
    shown = capsys.readouterr().out
    assert "Read the notes" in shown and "not started yet" in shown

    assert cli.main(["tasks", "show", task_id, "--json"]) == 0
    history = json.loads(capsys.readouterr().out)
    assert history["id"] == task_id and history["runs"] == []

    # A task that is not there is refused, and the command says so.
    assert cli.main(["tasks", "run", "task-nothing"]) == 2
    captured = capsys.readouterr()
    assert "no task with that id" in captured.out + captured.err

    assert cli.main(["tasks", "show", "task-nothing"]) == 2
    captured = capsys.readouterr()
    assert "no task with that id" in captured.out + captured.err
    assert cli.main(["tasks", "show"]) == 2
    assert "a task id is required" in capsys.readouterr().out


# ---------- the chat keeps answering (measured) ----------


def test_the_chat_answers_while_a_task_is_running(tmp_path):
    """Acceptance row 10, measured rather than asserted from a comment.

    The task's provider call sleeps, exactly as a slow provider does, and a chat
    turn is timed while that call is in flight. Both run on this event loop, so
    what is measured is the real path, not a simulation of it.
    """
    owner = owner_for(tmp_path, MemoryLinks())
    task = add(owner, "Slow work")
    record = stored(owner, task["id"])           # read before the loop starts

    def slow(messages, *, base_url, api_key, model, tools=None, timeout=60.0):
        time.sleep(0.6)
        return ModelReply("the slow work is done")

    def fast(messages, *, base_url, api_key, model, tools=None, timeout=60.0):
        return ModelReply("a quick answer about the weather")

    async def scenario() -> tuple[dict, float]:
        run = (await tasks.start(owner, task["id"]))["run"]
        working = asyncio.create_task(tasks.work(owner, record, run, call=slow))
        await asyncio.sleep(0.1)                 # let the task reach its provider call
        started = time.monotonic()
        answer = await agent.run_turn(owner, "how is the weather?", "client-chat-0001", "main",
                                      call=fast, registry={})
        elapsed = time.monotonic() - started
        await working
        return answer, elapsed

    answer, elapsed = asyncio.run(scenario())

    assert answer["reply"]["text"] == "a quick answer about the weather"
    assert elapsed < 0.3, f"the chat waited {elapsed:.3f}s behind a running task"
    assert one(owner, task["id"])["state"] == State.COMPLETED.value
