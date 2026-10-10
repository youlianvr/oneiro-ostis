"""The schedule: what its expression means, when it fires, and what the level allows.

Migrated from `test_life_loop.py` (a restart continues the same work instead of
repeating it) and `test_task_runner.py` (a job that was already taken on is not
taken on twice). The night organization's `jobs.json` is the model for the
expression and nothing here reads or writes another program's state: the
schedules are Oneiro's own records.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from chat_fakes import GraphStub, MemoryLinks, Model, csrf_of, isolate, make_app, post
from oneiro import cli, schedule, tasks, web
from oneiro.chat import ModelReply
from oneiro.query import GraphQueryError
from oneiro.records import Schedule, State
from oneiro.runtime import Runtime

CLIENT = "client-0001-aaaa"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def add_schedule(owner, *, title="Every minute", cron="* * * * *", client_id=CLIENT,
                 role="executor"):
    return asyncio.run(schedule.add(owner, title=title, cron=cron, role=role,
                                    client_id=client_id))["schedule"]


def at(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ---------- the expression ----------


def test_the_expression_reader_accepts_the_standard_forms():
    assert schedule.Cron.parse("*/5 * * * *").values[0] == frozenset(range(0, 60, 5))
    assert schedule.Cron.parse("0 9 * * 1-5").values[4] == frozenset({1, 2, 3, 4, 5})
    assert schedule.Cron.parse("30 6,18 1,15 * *").values[0] == frozenset({30})
    assert schedule.Cron.parse("30 6,18 1,15 * *").values[1] == frozenset({6, 18})
    assert schedule.Cron.parse("@daily").text == "0 0 * * *"
    assert schedule.Cron.parse("@hourly").values[0] == frozenset({0})
    assert schedule.Cron.parse("0 9 * * 7").values[4] == frozenset({0})   # 7 is Sunday too


def test_an_expression_it_cannot_read_is_refused_with_the_field():
    for text, message in (("", "needs an expression"),
                          ("0 9 * *", "five fields"),
                          ("99 * * * *", "minute"),
                          ("0 25 * * *", "hour: 25"),
                          ("*/0 * * * *", "positive number"),
                          ("0 9 * * monday", "weekday"),
                          ("5-1 * * * *", "smaller")):
        with pytest.raises(schedule.ScheduleError, match=message):
            schedule.Cron.parse(text)


def test_the_next_fire_is_the_next_named_minute():
    cron = schedule.Cron.parse("0 9 * * *")

    assert cron.next_after(at(2026, 10, 9, 8, 30)) == at(2026, 10, 9, 9, 0)
    assert cron.next_after(at(2026, 10, 9, 9, 0)) == at(2026, 10, 10, 9, 0)
    assert cron.matches(at(2026, 10, 9, 9, 0)) is True
    assert cron.matches(at(2026, 10, 9, 9, 1)) is False


def test_a_restricted_day_and_weekday_mean_either():
    """The standard's rule: reading it as "both" would skip the days asked for."""
    either = schedule.Cron.parse("0 0 1 * 1")            # the 1st, or any Monday
    assert either.matches(at(2026, 10, 1, 0, 0))         # Thursday the 1st
    assert either.matches(at(2026, 10, 5, 0, 0))         # Monday the 5th
    assert not either.matches(at(2026, 10, 6, 0, 0))

    only_day = schedule.Cron.parse("0 0 1 * *")
    assert only_day.matches(at(2026, 10, 1, 0, 0))
    assert not only_day.matches(at(2026, 10, 5, 0, 0))


# ---------- firing ----------


def test_a_scheduled_task_fires_and_appears_in_the_history(tmp_path, monkeypatch):
    """Acceptance row 8: a task fired on schedule, from creation to the record."""
    model = Model(monkeypatch, replies=[ModelReply("the scheduled work is done")])
    owner = owner_for(tmp_path, MemoryLinks())
    added = add_schedule(owner, title="Every minute")

    report = asyncio.run(schedule.tick(owner, at=tasks.utcnow() + timedelta(minutes=2),
                                       call=model._call))

    assert len(report["fired"]) == 1 and report["due"] == []
    firing = report["fired"][0]
    assert firing["schedule_id"] == added["id"] and firing["duplicate_task"] is False
    assert model.calls, "the scheduled task was worked, not merely recorded"

    history = asyncio.run(tasks.history(owner, firing["task_id"]))
    assert history["state"] == State.COMPLETED.value
    assert history["runs"][0]["notes"] == "the scheduled work is done"
    assert history["labels"] == [f"schedule:{added['id']}"]
    assert "Every minute" in history["title"]

    # The schedule remembers what it did, which is what a restart reads.
    stored = asyncio.run(schedule.current(owner))[added["id"]]
    assert stored["last_fired_at"] and stored["last_task_id"] == firing["task_id"]


def test_firing_the_same_minute_twice_makes_one_task(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    added = add_schedule(owner)
    moment = tasks.utcnow().replace(second=0, microsecond=0) + timedelta(minutes=1)

    first = asyncio.run(schedule.fire(owner, asyncio.run(schedule.current(owner))[added["id"]],
                                      at=moment))
    second = asyncio.run(schedule.fire(owner, asyncio.run(schedule.current(owner))[added["id"]],
                                       at=moment))

    assert first["task_id"] == second["task_id"] and second["duplicate_task"] is True
    assert len(asyncio.run(tasks.view(owner)).tasks) == 1
    assert asyncio.run(tasks.view(owner)).tasks[0]["attempts"] == 0


def test_a_restart_does_not_fire_the_same_minute_twice(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("done"), ModelReply("done")])
    owner = owner_for(tmp_path, MemoryLinks())
    add_schedule(owner)
    moment = tasks.utcnow() + timedelta(minutes=2)
    first = asyncio.run(schedule.tick(owner, at=moment, call=model._call))
    assert len(first["fired"]) == 1
    asked = len(model.calls)

    again = asyncio.run(schedule.tick(owner, at=moment, call=model._call))

    assert again["fired"] == [] and again["why"] == "nothing is due"
    assert len(model.calls) == asked
    assert len(asyncio.run(tasks.view(owner)).tasks) == 1


def test_a_stored_expression_that_cannot_be_read_is_named_and_not_guessed(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    record = Schedule(id="sched-broken", cron="every morning", task_title="Vague",
                      state=State.QUEUED)
    asyncio.run(owner.publish(record.to_dict(), "sched-broken"))

    row = asyncio.run(schedule.listing(owner))["schedules"][0]

    assert row["problem"].startswith("five fields are expected")
    assert row["next_at"] == "" and row["due_now"] is False
    report = asyncio.run(schedule.tick(owner, at=tasks.utcnow() + timedelta(days=400)))
    assert report["fired"] == [] and report["why"] == "nothing is due"


# ---------- what the level allows ----------


def test_a_due_schedule_is_named_and_left_alone_when_the_level_forbids_it(tmp_path, monkeypatch):
    model = Model(monkeypatch, replies=[ModelReply("the scheduled work is done")])
    owner = owner_for(tmp_path, MemoryLinks())
    added = add_schedule(owner, title="Held back")
    moment = tasks.utcnow() + timedelta(minutes=2)

    for level in ("off", "on_command"):
        monkeypatch.setenv("ONEIRO_INITIATIVE_LEVEL", level)
        report = asyncio.run(schedule.tick(owner, at=moment, call=model._call))
        assert report["fired"] == [] and report["due"] == [
            {"id": added["id"], "title": "Held back", "cron": "* * * * *"}]
        assert level in report["why"] and "does not fire" in report["why"]
        assert asyncio.run(tasks.view(owner)).tasks == []

    monkeypatch.setenv("ONEIRO_INITIATIVE_LEVEL", "scheduled")
    report = asyncio.run(schedule.tick(owner, at=moment, call=model._call))

    assert len(report["fired"]) == 1 and report["due"] == [] and model.calls
    assert len(asyncio.run(tasks.view(owner)).tasks) == 1


# ---------- calling one off ----------


def test_a_schedule_is_called_off_not_deleted(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())
    added = add_schedule(owner)

    removed = asyncio.run(schedule.remove(owner, added["id"], client_id=CLIENT))

    assert removed["removed"] is True
    stored = asyncio.run(owner.memory_entity(added["id"]))
    assert stored is not None                      # the history is kept
    assert stored["state"] == State.CANCELLED.value and stored["enabled"] is False
    assert asyncio.run(schedule.listing(owner))["schedules"][0]["enabled"] is False
    assert asyncio.run(schedule.remove(owner, added["id"], client_id=CLIENT))["duplicate"] is True
    assert asyncio.run(schedule.tick(owner, at=tasks.utcnow() + timedelta(minutes=2)))[
        "fired"] == []


def test_an_unknown_schedule_is_refused_with_a_reason(tmp_path):
    owner = owner_for(tmp_path, MemoryLinks())

    with pytest.raises(schedule.ScheduleError, match="no schedule with that id"):
        asyncio.run(schedule.remove(owner, "sched-nothing", client_id=CLIENT))
    with pytest.raises(schedule.ScheduleError, match="five fields"):
        asyncio.run(schedule.add(owner, title="x", cron="0 9 * *", client_id=CLIENT))
    with pytest.raises(schedule.ScheduleError, match="researcher or executor"):
        asyncio.run(schedule.add(owner, title="x", cron="* * * * *", role="manager",
                                 client_id=CLIENT))


# ---------- the clock itself ----------


def test_the_clock_keeps_ticking_until_it_is_cancelled():
    class Counting:
        def __init__(self) -> None:
            self.pages = 0

        async def memory_page(self, **_):
            self.pages += 1
            return {"items": [], "cursor": None, "scanned": 0, "skipped": [], "total": 0}

    counting = Counting()

    async def scenario() -> None:
        ticking = asyncio.create_task(schedule.loop(counting, interval=0.01))
        await asyncio.sleep(0.1)
        ticking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ticking

    asyncio.run(scenario())

    assert counting.pages >= 3


def test_a_failed_tick_is_reported_and_the_clock_keeps_its_place():
    """A scheduler that dies on one bad record stops every future schedule."""
    errors: list[Exception] = []

    class Broken:
        def __init__(self) -> None:
            self.pages = 0

        async def memory_page(self, **_):
            self.pages += 1
            raise GraphQueryError("server_unreachable", "the graph is not there")

    broken = Broken()

    async def scenario() -> None:
        ticking = asyncio.create_task(schedule.loop(broken, interval=0.01,
                                                    on_error=errors.append))
        await asyncio.sleep(0.08)
        ticking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await ticking

    asyncio.run(scenario())

    assert broken.pages > 1, "the clock gave up after one failed tick"
    assert errors and isinstance(errors[0], GraphQueryError)


def test_the_app_starts_the_clock_when_it_is_asked_to(tmp_path, monkeypatch):
    """The product's own entrypoint runs the clock; a test app can leave it off."""
    Model(monkeypatch, replies=[ModelReply("fired by the clock")])
    links = MemoryLinks()
    old = (tasks.utcnow() - timedelta(minutes=5)).isoformat(timespec="seconds")
    record = Schedule(id="sched-due", cron="* * * * *", task_title="Every minute",
                      created_at=old, updated_at=old, state=State.QUEUED)
    asyncio.run(owner_for(tmp_path, links).publish(record.to_dict(), "sched-due"))

    def app(*, scheduler: bool):
        # A fresh store per app: closing one releases the writer lease, and the
        # app under test must open its own.
        return web.create_app(runtime=owner_for(tmp_path, links), scheduler=scheduler)

    with TestClient(app(scheduler=False)) as quiet:
        time.sleep(0.2)
        assert quiet.get("/api/tasks").json()["tasks"] == [], "the clock ran unasked"

    with TestClient(app(scheduler=True)) as ticking:
        deadline = time.monotonic() + 3
        found: list[dict] = []
        while time.monotonic() < deadline:
            found = ticking.get("/api/tasks").json()["tasks"]
            # The clock creates the task and then runs it, and the run takes a few
            # milliseconds: the first poll that sees the task may well see it in flight.
            # What this test is about is that the clock fired it *and the work finished*,
            # so it waits for the state to settle rather than asserting on whichever
            # millisecond the poll happened to land.
            if found and found[0]["state"] in (State.COMPLETED.value, State.FAILED.value):
                break
            time.sleep(0.05)
        # Read the task again while the app is still open: its store is gone after.
        final = found[0] if found else {}

    assert found, "the app's own clock never fired a due schedule"
    assert final["state"] == State.COMPLETED.value
    assert final["labels"] == ["schedule:sched-due"]


# ---------- the command line ----------


def test_the_command_line_lists_and_calls_off_schedules(tmp_path, monkeypatch, capsys):
    links = MemoryLinks()
    monkeypatch.setattr(cli, "Runtime", lambda: owner_for(tmp_path, links))

    assert cli.main(["schedules", "list"]) == 0
    assert "no schedules yet" in capsys.readouterr().out

    assert cli.main(["schedules", "add", "--title", "Nightly notes",
                     "--cron", "0 9 * * *"]) == 0
    added = capsys.readouterr().out
    assert "Nightly notes" in added and "0 9 * * *" in added

    assert cli.main(["schedules", "list"]) == 0
    listed = capsys.readouterr().out
    assert "Nightly notes" in listed and "next: " in listed
    assert "initiative is scheduled" in listed

    schedule_id = listed.split()[0]
    assert cli.main(["schedules", "remove", schedule_id]) == 0
    assert "called off" in capsys.readouterr().out
    assert asyncio.run(owner_for(tmp_path, links).memory_entity(schedule_id))["state"] \
        == State.CANCELLED.value


# ---------- over HTTP ----------


def test_the_schedule_surface_over_http(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        csrf = csrf_of(client)
        created = post(client, "/api/schedules",
                       {"title": "Every minute", "cron": "* * * * *", "client_id": CLIENT},
                       csrf)
        assert created.status_code == 200
        schedule_id = created.json()["schedule"]["id"]

        listed = client.get("/api/schedules").json()
        assert [row["cron"] for row in listed["schedules"]] == ["* * * * *"]
        assert listed["fires"] is True and listed["level"] == "scheduled"
        # Created just now, so the next minute is in the future: nothing is due.
        assert listed["schedules"][0]["due_now"] is False

        bad = post(client, "/api/schedules",
                   {"title": "x", "cron": "0 9 * *", "client_id": "client-0002-aaaa"}, csrf)
        assert bad.status_code == 400 and "five fields" in bad.json()["error"]

        ticked = post(client, "/api/schedules/tick", {}, csrf)
        assert ticked.status_code == 200 and ticked.json()["fired"] == []

        removed = post(client, f"/api/schedules/{schedule_id}/remove",
                       {"client_id": CLIENT}, csrf)
        assert removed.status_code == 200 and removed.json()["removed"] is True
        assert client.get("/api/schedules").json()["schedules"][0]["enabled"] is False
        assert client.post(f"/api/schedules/{schedule_id}/remove",
                          json={}).status_code == 403
