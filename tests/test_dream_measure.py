"""The live leg exercised offline: three repeats, the spread, the two refusals, isolation.

The provider is stubbed at the registry's transport seam, so what is under test is the
measurement itself — the repeats, the ledger arithmetic, the isolation — and not the
network. The isolation check is the one that matters most: a measurement must never be
able to write where the owner's own work lives.
"""
from __future__ import annotations

import asyncio
import importlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from chat_fakes import SECRET, GraphStub, MemoryLinks, Model, isolate
from oneiro import agent, config, models
from oneiro.chat import ChatError, ModelReply
from oneiro.dream import episode, replay
from oneiro.dream.measure import (DEMO_STREAM, LANE_TIMEOUT, PRELUDE, TASKS, MeasureError,
                                  apply_policy, measure, missing_repeats, owner_for,
                                  seed_history, seed_settings, write_fixtures)
from oneiro.dream.policy import BASE, TurnPolicy
from oneiro.query import GraphQueryError
from oneiro.runtime import Runtime

MEASURE = importlib.import_module("oneiro.dream.measure")
TASK = TASKS[0]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def transport_for(prompt_tokens: tuple[int, ...], answer: str = TASK.answers[0]):
    """A provider that bills a different prompt each call, so a spread exists."""
    state = {"calls": 0}

    def transport(messages, *, base_url, api_key, model, tools=None, timeout=60.0):
        index = state["calls"] % len(prompt_tokens)
        state["calls"] += 1
        return ModelReply(answer, usage={"prompt_tokens": prompt_tokens[index],
                                         "completion_tokens": 1},
                          served="stub-model")

    return transport, state


def runtime_for(tmp_path, links: MemoryLinks | None = None) -> Runtime:
    return Runtime(graph=GraphStub(links or MemoryLinks(), tmp_path / "graph-writer.lock"))


def run_measurement(tmp_path, monkeypatch, policy=BASE, *, repeats=3, tasks=(TASK,),
                    tokens=(100, 200, 300)):
    transport, state = transport_for(tokens)
    monkeypatch.setattr(models, "TRANSPORT", transport)
    owner = runtime_for(tmp_path)
    result = asyncio.run(measure(policy, workspace=tmp_path / "workspace",
                                 repeats=repeats, tasks=tasks, owner=owner))
    return result, owner, state


def test_no_task_depends_on_the_process_working_directory(tmp_path):
    """A read is resolved against the cwd, so the fixture must be named absolutely."""
    workspace = tmp_path / "workspace"
    for task in TASKS:
        request = task.request_for(workspace)
        write_fixtures(workspace, task)

        assert "{workspace}" not in request
        assert workspace.as_posix() in request, "the fixture is named absolutely"
        for name in task.files:
            assert (workspace / name).exists(), "and it is where the request says it is"


def test_the_fixture_is_reachable_through_the_real_tool(tmp_path, monkeypatch):
    """The task's own file is read by `read_file` on the request the demo sends."""
    workspace = tmp_path / "workspace"
    task = TASKS[0]
    write_fixtures(workspace, task)
    request = task.request_for(workspace)
    model = Model(monkeypatch, replies=[
        Model.tool("read_file", {"path": str(workspace / "NOTES.md")}, "call-1"),
        ModelReply("It says to keep it small.")])

    result = asyncio.run(agent.run_turn(runtime_for(tmp_path), request, "c-fixture-1",
                                        "dream-fixture", call=model._call))

    step = result["steps"][0]
    assert step["ok"] is True and step["decision"] == "allow"
    assert "keep it small" in step["result"]
    assert task.solved_by(result["reply"]["text"])


def test_a_paraphrase_of_the_answer_still_counts_as_solved():
    """One measured run said "keep things small" for a note that says "keep it small"."""
    task = TASKS[0]

    assert task.solved_by('The notes file contains the plan to keep things small.')
    assert task.solved_by('It says: "the plan is to keep it small".')
    assert not task.solved_by("The file is missing.")
    assert not TASKS[2].solved_by("gamma.txt")


def test_a_measurement_needs_at_least_three_repeats(tmp_path, monkeypatch):
    transport, _ = transport_for((100, 200, 300))
    monkeypatch.setattr(models, "TRANSPORT", transport)

    with pytest.raises(MeasureError) as refused:
        asyncio.run(measure(BASE, workspace=tmp_path / "workspace", repeats=2,
                            tasks=(TASK,), owner=runtime_for(tmp_path)))

    assert "at least 3 repeats" in str(refused.value)


def test_a_knob_the_live_turn_cannot_apply_is_refused_by_name():
    blind = TurnPolicy(name="blind", include_facts=False)

    with pytest.raises(MeasureError) as refused:
        apply_policy(blind)

    assert "include_facts" in str(refused.value)
    assert "cannot be told to change" in str(refused.value)


def test_a_knob_the_live_turn_reads_is_written_into_the_settings():
    apply_policy(TurnPolicy(name="windowed", history_messages=4))

    assert int(config.value("chat.history_messages")) == 4


def test_every_task_runs_three_times_and_the_spread_is_shown(tmp_path, monkeypatch):
    result, _, state = run_measurement(tmp_path, monkeypatch)

    task = result.tasks[0]
    assert len(task.runs) == 3 and task.solved == 3
    assert [run.tokens_in for run in task.runs] == [100, 200, 300]
    assert task.mean_tokens_in == pytest.approx(200.0)
    assert task.spread == pytest.approx(1.0)
    assert task.runs[0].served == ("stub-model",)
    assert result.worst_spread == pytest.approx(1.0)
    assert state["calls"] == 3


def test_each_repeat_gets_a_conversation_with_the_same_prelude(tmp_path, monkeypatch):
    result, owner, _ = run_measurement(tmp_path, monkeypatch, repeats=3)

    conversations = set()
    for run in result.tasks[0].runs:
        turn_id = f"reply-{result.session}-{TASK.name}-r{run.repeat}"
        turn = asyncio.run(episode.read(owner, turn_id))
        conversations.add(turn.conversation_id)
        context = asyncio.run(replay.read_context(owner, turn))
        assert len(context.history) == len(PRELUDE)

    assert len(conversations) == 3, "no repeat sees another repeat's history"


def test_the_demo_gets_a_root_of_its_own_and_copies_no_secret(tmp_path, monkeypatch):
    assert DEMO_STREAM != "product", "the owner's own work is in another stream"
    before = config.snapshot()
    root = tmp_path / "demo"
    workspace = root / "workspace"
    kept = {key: os.environ.get(key)
            for key in ("ONEIRO_SETTINGS_FILE", "ONEIRO_DATA_DIR")}
    try:
        settings = seed_settings(root, workspace)

        assert Path(os.environ["ONEIRO_SETTINGS_FILE"]) == settings
        assert Path(os.environ["ONEIRO_DATA_DIR"]) == root / "runtime"
        assert SECRET not in settings.read_text(encoding="utf-8"), "no secret is copied"
        assert settings != Path(kept["ONEIRO_SETTINGS_FILE"] or ""), "not the owner's file"
        assert config.value("graph.port") == before["graph.port"], \
            "the graph it talks to is the same"
        assert str(config.value("tools.workspace")) == str(workspace)
    finally:
        for key, value in kept.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_the_demo_lane_gets_a_deadline_of_its_own(tmp_path, monkeypatch):
    assert LANE_TIMEOUT > 10.0, "the product's ten-second page deadline is too tight here"

    assert owner_for(tmp_path).timeout == LANE_TIMEOUT


def test_a_graph_failure_is_one_repeat_error_and_not_the_end_of_the_measurement(
        tmp_path, monkeypatch):
    """Seeding is inside the per-run guard: one bad write cannot take the tasks with it."""
    transport, _ = transport_for((100, 200, 300))
    monkeypatch.setattr(models, "TRANSPORT", transport)
    calls = {"n": 0}

    async def flaky(owner, conversation, *, session):
        calls["n"] += 1
        if calls["n"] == 2:
            raise GraphQueryError("graph_timeout", "graph deadline exceeded")
        return await seed_history(owner, conversation, session=session)

    monkeypatch.setattr(MEASURE, "seed_history", flaky)
    result = asyncio.run(measure(BASE, workspace=tmp_path / "workspace", repeats=3,
                                 owner=runtime_for(tmp_path)))

    task = result.tasks[0]
    assert len(task.runs) == 3, "every repeat is still reported"
    assert [len(run.error) > 0 for run in task.runs] == [False, True, False]
    assert task.measured == (task.runs[0], task.runs[2])
    assert "graph_timeout" in task.runs[1].error
    assert task.solved == 2


def test_a_resumed_measurement_runs_only_the_repeats_that_failed(tmp_path, monkeypatch):
    """A repeat that came back is kept; only the one that errored is bought again."""
    transport, state = transport_for((100, 300, 900))
    monkeypatch.setattr(models, "TRANSPORT", transport)
    owner = runtime_for(tmp_path)
    workspace = tmp_path / "workspace"
    real_seed = MEASURE.seed_history
    calls = {"n": 0}

    async def flaky(one, conversation, *, session):
        calls["n"] += 1
        if calls["n"] == 2:
            raise GraphQueryError("graph_timeout", "graph deadline exceeded")
        return await real_seed(one, conversation, session=session)

    monkeypatch.setattr(MEASURE, "seed_history", flaky)
    first = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                                owner=owner))

    assert [bool(run.error) for run in first.tasks[0].runs] == [False, True, False]
    assert missing_repeats(first.tasks[0]) == (2,), "the failed repeat is what is owed"
    assert first.tasks[0].measured == (first.tasks[0].runs[0], first.tasks[0].runs[2])
    monkeypatch.setattr(MEASURE, "seed_history", real_seed)
    spent = state["calls"]

    second = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                                 owner=owner, reuse=first))

    task = second.tasks[0]
    assert state["calls"] == spent + 1, "one turn was bought, not three"
    assert [run.repeat for run in task.runs] == [1, 2, 3]
    assert [run.tokens_in for run in task.runs] == [100, 900, 300]
    assert task.runs[0].session == first.session, "a kept number still names its session"
    assert task.runs[1].session == second.session
    assert task.spread == pytest.approx((900 - 100) / (1300 / 3)), "three repeats, a spread"


def test_a_reused_run_is_scored_again_from_its_own_record(tmp_path, monkeypatch):
    """The verdict is re-read from the turn, so a rule that changed since it ran applies."""
    transport, state = transport_for((100, 200, 300), answer="the notes say nothing useful")
    monkeypatch.setattr(models, "TRANSPORT", transport)
    owner = runtime_for(tmp_path)
    workspace = tmp_path / "workspace"

    first = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                                owner=owner))

    assert first.tasks[0].solved == 0, "the recorded answer does not satisfy the task"

    kinder = replace(TASK, answers=("nothing useful",))
    again = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(kinder,),
                                owner=owner, reuse=first))

    assert state["calls"] == 3, "a run that is kept is not bought again"
    assert again.tasks[0].solved == 3, "the stored verdict was not trusted, it was re-read"
    assert [run.tokens_in for run in again.tasks[0].runs] == [100, 200, 300]


def test_a_reused_run_whose_record_is_gone_is_measured_again(tmp_path, monkeypatch):
    """A payload whose sessions the graph never saw is not evidence; its repeats are run."""
    transport, state = transport_for((100, 200, 300, 400, 500, 600))
    monkeypatch.setattr(models, "TRANSPORT", transport)
    owner = runtime_for(tmp_path)
    workspace = tmp_path / "workspace"

    first = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                                owner=owner))
    stranger = replace(
        first, session="deadbeef",
        tasks=tuple(replace(result, runs=tuple(replace(run, session="deadbeef")
                                                for run in result.runs))
                    for result in first.tasks))

    again = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                                owner=owner, reuse=stranger))

    assert state["calls"] == 6, "nothing could be read back, so every repeat was run"
    assert [run.tokens_in for run in again.tasks[0].runs] == [400, 500, 600]
    assert all(run.session == again.session for run in again.tasks[0].runs)


def test_a_resume_stops_when_the_graph_will_not_serve_its_own_records(tmp_path, monkeypatch):
    """Unreadable is not missing: a resume must not buy again what it already holds."""
    transport, state = transport_for((100, 200, 300, 700))
    monkeypatch.setattr(models, "TRANSPORT", transport)
    owner = runtime_for(tmp_path)
    workspace = tmp_path / "workspace"
    first = asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                                owner=owner))

    async def unreadable(one, turn_id):
        raise GraphQueryError("server_unreachable", "resolve_keynodes failed")

    monkeypatch.setattr(MEASURE.episode, "read", unreadable)
    monkeypatch.setattr(MEASURE, "RECORD_PAUSE", 0.0)

    with pytest.raises(MeasureError) as refused:
        asyncio.run(measure(BASE, workspace=workspace, repeats=3, tasks=(TASK,),
                            owner=owner, reuse=first))

    assert "cannot be read" in str(refused.value)
    assert "cannot be resumed" in str(refused.value)
    assert state["calls"] == 3, "not one turn was bought to replace a measured run"


def test_a_resumed_measurement_must_stay_on_its_candidate(tmp_path, monkeypatch):
    """Runs of one candidate are not the runs of another, so resuming across is refused."""
    first, _, _ = run_measurement(tmp_path, monkeypatch)
    other = replace(first, policy="windowed")

    with pytest.raises(MeasureError) as refused:
        asyncio.run(measure(BASE, workspace=tmp_path / "workspace", repeats=3,
                            tasks=(TASK,), owner=runtime_for(tmp_path), reuse=other))

    assert "windowed" in str(refused.value)
    assert "must stay on the candidate" in str(refused.value)


def test_a_turn_that_fails_is_recorded_as_an_error_and_not_as_a_cost(tmp_path, monkeypatch):
    def failing(messages, **kwargs):
        raise ChatError("the provider refused")

    monkeypatch.setattr(models, "TRANSPORT", failing)
    result = asyncio.run(measure(BASE, workspace=tmp_path / "workspace", repeats=3,
                                 tasks=(TASK,), owner=runtime_for(tmp_path)))

    task = result.tasks[0]
    assert len(task.runs) == 3 and task.measured == ()
    assert all(run.error for run in task.runs)
    assert task.mean_tokens_in == 0.0
    assert task.spread is None, "a side measured not at all has no spread to report"
