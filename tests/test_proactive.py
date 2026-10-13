"""The two proactive moments: the digest when the quiet hours end, one reminder after.

What the plan asks this file to pin, and where:

* **the content and the moment of the digest** — what finished inside the quiet window,
  named, and nothing about a window still running
  (`test_the_digest_names_the_window_that_ended_and_waits_for_it_to_end`);
* **the repeat happens once** — one reminder per unfinished item, and a second tick
  finds the first (`test_a_reminder_is_said_once_for_one_unfinished_item`);
* **the quiet window holds them** — a reminder raised inside the quiet hours is stored
  as held, and the digest said at the window's end is not
  (`test_the_quiet_window_holds_a_reminder_and_not_the_digest`);
* **the level decides** — below `proactive` neither is said, and the reason says so
  (`test_oneiro_does_not_speak_first_below_the_proactive_level`);
* **one clock** — both are said from the scheduler's own tick, never from a timer of
  their own (`test_the_scheduler_tick_says_both`).

Every moment here is passed in explicitly, so the suite does not depend on the hour it
runs at; the live check is what exercises the product's real clock.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from chat_fakes import GraphStub, MemoryLinks, csrf_of, isolate, make_app
from oneiro import i18n, proactive, schedule, tasks
from oneiro.query import GraphQueryError
from oneiro.records import ConversationMessage, Provenance, Run, State, Task
from oneiro.runtime import Runtime

#: A fixed local zone: the quiet hours are local, and a test that used the machine's
#: zone would assert different things in different offices.
TZ = timezone(timedelta(hours=3))
#: The afternoon of the same day, after the quiet hours end at 09:00.
AFTER_QUIET = datetime(2026, 10, 13, 9, 5, tzinfo=TZ)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def owner_for(tmp_path, links: MemoryLinks) -> Runtime:
    """The real store over the in-memory link graph, ready to publish."""
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def settings_of(tmp_path, **values) -> None:
    """A settings file as the owner writes it: the defaults this suite needs, changed."""
    declared: dict[str, object] = {"initiative.level": "proactive",
                                   "initiative.quiet_hours": "22:00-09:00",
                                   "initiative.digest": True,
                                   "initiative.reminders": True,
                                   "initiative.reminder_after": 180}
    declared.update(values)
    (tmp_path / "settings.json").write_text(json.dumps(declared), encoding="utf-8")


def stamp(moment: datetime) -> str:
    return moment.astimezone(TZ).isoformat(timespec="seconds")


def publish(owner: Runtime, record) -> None:
    asyncio.run(owner.publish(record.to_dict(), record.id))


def finished_item(owner: Runtime, task_id: str, title: str, at: datetime) -> None:
    """A task whose single attempt finished at that moment, as the product writes one."""
    publish(owner, Task(id=task_id, title=title, assigned_role="executor",
                        state=State.QUEUED, created_at=stamp(at), updated_at=stamp(at),
                        provenance=Provenance.OWNER_INSTRUCTION))
    publish(owner, Run(id=f"run-{task_id}-a1", task_id=task_id, role="executor", attempt=1,
                       state=State.COMPLETED, notes="Done.", created_at=stamp(at),
                       updated_at=stamp(at), provenance=Provenance.SYSTEM))


def failed_item(owner: Runtime, task_id: str, title: str, at: datetime) -> None:
    """A task whose attempt failed, which no further attempt is tried on its own for.

    One attempt is enough to be unfinished: the state a reader sees is `ready for
    attempt 2 of 3`, which is in the unfinished set by the same rule a fresh task is.
    """
    publish(owner, Task(id=task_id, title=title, assigned_role="executor",
                        state=State.QUEUED, created_at=stamp(at), updated_at=stamp(at),
                        provenance=Provenance.OWNER_INSTRUCTION))
    publish(owner, Run(id=f"run-{task_id}-a1", task_id=task_id, role="executor", attempt=1,
                       state=State.FAILED, notes="the model did not answer",
                       created_at=stamp(at), updated_at=stamp(at),
                       provenance=Provenance.SYSTEM))


def stored_notices(owner: Runtime) -> list[dict]:
    return asyncio.run(tasks.notices(owner))["notices"]


# ---------- the digest ----------


def test_the_digest_names_the_window_that_ended_and_waits_for_it_to_end(tmp_path):
    """The content is what the quiet window held, and the moment is its end.

    The work finished at 02:00, inside the window that ends at 09:00. At 08:30 there is
    nothing to say about it yet — the window it belongs to is still running — and at
    09:05 it is said, once, naming the attempt that finished and the one that did not.
    """
    settings_of(tmp_path)
    owner = owner_for(tmp_path, MemoryLinks())
    finished_item(owner, "task-night-0001", "Read the note every minute",
                  datetime(2026, 10, 13, 2, 0, tzinfo=TZ))
    failed_item(owner, "task-night-0002", "Count the lines in the report",
                datetime(2026, 10, 13, 4, 0, tzinfo=TZ))

    before = asyncio.run(proactive.digest(owner, at=datetime(2026, 10, 13, 8, 30, tzinfo=TZ)))
    assert before["said"] is False and "have not ended yet" in before["why"]
    assert stored_notices(owner) == []

    after = asyncio.run(proactive.digest(owner, at=AFTER_QUIET))

    assert after["said"] is True
    assert after["period"] == ["2026-10-12T22:00+03:00", "2026-10-13T09:00+03:00"]
    assert after["finished"] == ["Read the note every minute"]
    assert after["stuck"] == ["Count the lines in the report"]
    assert after["text"] == ("While you were quiet (22:00-09:00): 1 finished, 1 did not.\n"
                             "- done: Read the note every minute\n"
                             "- did not finish: Count the lines in the report")
    assert after["conversation_id"] == "main" and after["held"] is False
    assert [row["conversation_id"] for row in stored_notices(owner)] == ["main"]


def test_one_quiet_window_is_reported_once(tmp_path):
    """A second look at the same morning reads the first answer back, not a new one."""
    settings_of(tmp_path)
    owner = owner_for(tmp_path, MemoryLinks())
    finished_item(owner, "task-night-0001", "Read the note every minute",
                  datetime(2026, 10, 13, 2, 0, tzinfo=TZ))

    asyncio.run(proactive.digest(owner, at=AFTER_QUIET))
    again = asyncio.run(proactive.digest(owner, at=AFTER_QUIET + timedelta(minutes=31)))

    assert again["said"] is False and again["already"] is True
    assert "already reported" in again["why"]
    assert len(stored_notices(owner)) == 1


def test_a_quiet_window_with_nothing_in_it_does_not_invent_work(tmp_path):
    """An empty window is reported as empty rather than passed over in silence."""
    settings_of(tmp_path)
    owner = owner_for(tmp_path, MemoryLinks())

    said = asyncio.run(proactive.digest(owner, at=AFTER_QUIET))

    assert said["said"] is True
    assert said["text"] == "While you were quiet (22:00-09:00): 0 finished, 0 did not."


def test_no_quiet_hours_means_no_digest_and_the_reason_says_so(tmp_path):
    """Empty means never quiet, so there is no period to report on — and it is named."""
    settings_of(tmp_path, **{"initiative.quiet_hours": ""})
    owner = owner_for(tmp_path, MemoryLinks())

    said = asyncio.run(proactive.digest(owner, at=AFTER_QUIET))

    assert said["said"] is False and "no quiet period to report on" in said["why"]
    assert stored_notices(owner) == []


# ---------- the reminder ----------


def test_a_reminder_is_said_once_for_one_unfinished_item(tmp_path):
    """One reminder per unfinished item; the next tick finds the one already said."""
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 10, 0, tzinfo=TZ))

    first = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 10, 5, tzinfo=TZ)))
    second = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 11, 5, tzinfo=TZ)))

    assert [row["task_id"] for row in first["said"]] == ["task-open-0001"]
    assert first["said"][0]["conversation_id"] == "task-task-open-0001"
    assert first["said"][0]["text"].startswith("Still unfinished: Fix the report")
    assert second["said"] == []
    assert any("already reminded" in line for line in second["held_back"])
    assert len(stored_notices(owner)) == 1


def test_a_reminder_waits_for_the_declared_delay(tmp_path):
    """The delay is the owner's: too early is not a reminder, it is an interruption."""
    settings_of(tmp_path, **{"initiative.reminder_after": 60})
    owner = owner_for(tmp_path, MemoryLinks())
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 10, 0, tzinfo=TZ))

    early = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 10, 30, tzinfo=TZ)))
    due = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 11, 5, tzinfo=TZ)))

    assert early["said"] == [] and any("of 60 minute(s)" in line for line in early["held_back"])
    assert [row["task_id"] for row in due["said"]] == ["task-open-0001"]
    assert due["said"][0]["waited_minutes"] == 65


def test_nothing_more_is_said_about_an_item_once_it_is_finished(tmp_path):
    """Handled work stops being reminded: the reminder is about what still waits."""
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    finished_item(owner, "task-done-0001", "Fix the report",
                  datetime(2026, 10, 13, 10, 0, tzinfo=TZ))

    answer = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 10, 5, tzinfo=TZ)))

    assert answer["said"] == [] and answer["considered"] == 0
    assert "nothing is unfinished" in answer["why"]
    assert stored_notices(owner) == []


def test_an_answer_in_the_item_conversation_stops_the_reminder(tmp_path):
    """While nobody answers the item, it is reminded; once somebody does, it is not."""
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 10, 0, tzinfo=TZ))
    publish(owner, ConversationMessage(id="msg-owner-0001", conversation_id="task-task-open-0001",
                                       role="owner", text="I am on it, leave it with me.",
                                       created_at=stamp(datetime(2026, 10, 13, 10, 3, tzinfo=TZ)),
                                       updated_at=stamp(datetime(2026, 10, 13, 10, 3, tzinfo=TZ)),
                                       provenance=Provenance.OWNER_INSTRUCTION,
                                       state=State.COMPLETED))

    answer = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 10, 5, tzinfo=TZ)))
    later = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 12, 0, tzinfo=TZ)))

    assert answer["said"] == [] and later["said"] == []
    assert any("you answered it" in line for line in answer["held_back"])
    assert stored_notices(owner) == []


# ---------- the quiet window, the level, and the one clock ----------


def test_the_quiet_window_holds_a_reminder_and_not_the_digest(tmp_path):
    """Held is not hidden: both are stored, and only the one said at 09:05 interrupts.

    The reminder is raised at 03:00, inside the quiet hours, so it carries the held
    label; the digest is said at 09:05, when the window has ended, so it does not.
    """
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 2, 0, tzinfo=TZ))

    spoken = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 3, 0, tzinfo=TZ)))
    digest = asyncio.run(proactive.digest(owner, at=AFTER_QUIET))

    assert spoken["said"][0]["held"] is True
    held = [row for row in stored_notices(owner) if row["conversation_id"].startswith("task-")]
    assert len(held) == 1 and held[0]["held"] is True
    assert "quiet hours are 22:00-09:00" in held[0]["why"]
    assert digest["said"] is True and digest["held"] is False


def test_oneiro_does_not_speak_first_below_the_proactive_level(tmp_path):
    """`scheduled` starts the tasks you scheduled; it does not let Oneiro speak first."""
    settings_of(tmp_path, **{"initiative.level": "scheduled", "initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 2, 0, tzinfo=TZ))
    finished_item(owner, "task-night-0001", "Read the note every minute",
                  datetime(2026, 10, 13, 2, 0, tzinfo=TZ))

    report = asyncio.run(schedule.tick(owner, at=AFTER_QUIET))

    assert "does not speak up first" in report["proactive"]["why"]
    assert report["proactive"]["digest"] is None and report["proactive"]["reminders"] is None
    assert stored_notices(owner) == []


def test_the_scheduler_tick_says_both(tmp_path):
    """One clock: the digest and the reminder are said from the scheduler's own tick."""
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    finished_item(owner, "task-night-0001", "Read the note every minute",
                  datetime(2026, 10, 13, 2, 0, tzinfo=TZ))
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 2, 0, tzinfo=TZ))

    report = asyncio.run(schedule.tick(owner, at=AFTER_QUIET))
    spoken = report["proactive"]

    assert spoken["digest"]["said"] is True and spoken["digest"]["held"] is False
    assert [row["task_id"] for row in spoken["reminders"]["said"]] == ["task-open-0001"]
    assert len(stored_notices(owner)) == 2


def test_the_switches_stop_the_digest_and_the_reminder(tmp_path):
    """Both are declared, and switching one off is what it says: that one is silent."""
    settings_of(tmp_path, **{"initiative.digest": False, "initiative.reminders": False,
                             "initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    finished_item(owner, "task-night-0001", "Read the note every minute",
                  datetime(2026, 10, 13, 2, 0, tzinfo=TZ))
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 2, 0, tzinfo=TZ))

    report = asyncio.run(proactive.tick(owner, at=AFTER_QUIET))

    assert "digest is switched off" in report["digest"]["why"]
    assert "reminder is switched off" in report["reminders"]["why"]
    assert stored_notices(owner) == []


# ---------- the surface ----------


def test_the_notice_surface_carries_both_and_the_page_names_the_settings(tmp_path):
    """What the owner reads: the notices over HTTP, and the new keys in both languages.

    The records are written through the app's own runtime, because the graph holds one
    writer at a time and a test that made a second one would be measuring the lease
    rather than the surface.
    """
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    links = MemoryLinks()

    with TestClient(make_app(tmp_path, links)) as client:
        owner = client.app.state.runtime
        finished_item(owner, "task-night-0001", "Read the note every minute",
                      datetime(2026, 10, 13, 2, 0, tzinfo=TZ))
        failed_item(owner, "task-open-0001", "Fix the report",
                    datetime(2026, 10, 13, 2, 0, tzinfo=TZ))
        asyncio.run(proactive.tick(owner, at=AFTER_QUIET))

        listed = client.get("/api/tasks").json()
        assert [row["conversation_id"] for row in listed["notices"]] == [
            "task-task-open-0001", "main"]
        assert listed["quiet_hours"] == "22:00-09:00"
        for language in ("ru", "en"):
            screen = client.get(f"/settings?lang={language}").text
            for key in ("initiative.digest", "initiative.reminders",
                        "initiative.reminder_after"):
                label = i18n.t(f"setting.{key}.label", language)
                assert label in screen, f"{key} is missing from the {language} settings page"
        # Neither language is the other's fallback: the Russian is written, not borrowed.
        assert i18n.t("setting.initiative.digest.label", "ru") != \
            i18n.t("setting.initiative.digest.label", "en")


# ---------- the key, which is what makes a notice one answer ----------


def test_a_keyed_notice_is_one_answer_and_a_second_one_is_refused(tmp_path):
    """The key is what makes a notice one answer to one thing.

    The same key with the same words in the same minute is the same notice, and the
    store answers the second ask with the first. The same key at another minute — or
    with other words — is refused as a collision, which is exactly why `digest` reads
    the window's notice before it builds one instead of overwriting an answer already
    given with whatever the records say now.
    """
    owner = owner_for(tmp_path, MemoryLinks())

    first = asyncio.run(tasks.notify(owner, "main", "the same words", at=AFTER_QUIET,
                                     key="digest-20261013"))
    same = asyncio.run(tasks.notify(owner, "main", "the same words", at=AFTER_QUIET,
                                    key="digest-20261013"))

    assert first["duplicate"] is False and same["duplicate"] is True
    assert same["record"]["id"] == first["record"]["id"]
    assert len(stored_notices(owner)) == 1

    with pytest.raises(GraphQueryError, match="operation_collision"):
        asyncio.run(tasks.notify(owner, "main", "a different story entirely",
                                 at=AFTER_QUIET + timedelta(hours=2),
                                 key="digest-20261013"))


def test_a_second_tick_does_not_raise_out_of_the_one_answer(tmp_path):
    """The tick is what must not fail: the store's refusal is read back as the answer."""
    settings_of(tmp_path, **{"initiative.reminder_after": 1})
    owner = owner_for(tmp_path, MemoryLinks())
    failed_item(owner, "task-open-0001", "Fix the report",
                datetime(2026, 10, 13, 10, 0, tzinfo=TZ))
    first = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 10, 5, tzinfo=TZ)))

    # The same key at another minute: nothing may be written twice, and the tick that
    # came second must report the answer rather than fail on it.
    again = asyncio.run(proactive.reminders(owner, at=datetime(2026, 10, 13, 10, 6, tzinfo=TZ)))

    assert first["said"][0]["already"] is False
    assert again["said"] == []
    assert any("already reminded" in line for line in again["held_back"])
    assert len(stored_notices(owner)) == 1
