"""A job from the phone ends at a button, and the button's record closes it."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

import approval  # noqa: E402
import task_runner as runner_module  # noqa: E402


class FakeBridge:
    def __init__(self, records=None):
        self.records = list(records or [])

    def load_organization_events(self, session_id=None):
        return list(self.records)

    def record_organization_event(self, **kwargs):
        kwargs.setdefault("recorded_at", 1761000000)
        kwargs.setdefault("origin", "rule")
        kwargs.setdefault("verified", True)
        kwargs.setdefault("session_id", "host-cowagent-life")
        record = type("R", (), kwargs)()
        self.records.append(record)
        return record

    def kinds(self):
        return [r.kind for r in self.records]

    def of(self, kind):
        return [r for r in self.records if r.kind == kind]


class FakeChannel:
    def __init__(self):
        self.sent = []

    def send(self, proposal):
        self.sent.append(proposal)
        return {"ok": True, "result": {"message_id": 1}}

    def is_approved(self, proposal_id):
        return False


def record(kind, payload, role="manager"):
    return type("R", (), {
        "record_id": f"{kind}-{len(payload)}", "session_id": "host-cowagent-life",
        "role": role, "kind": kind, "payload": payload, "origin": "rule",
        "verified": True, "recorded_at": 1761000000,
    })()


def task_record(task_id="task-12", text="посмотри, что не доделано"):
    return record("task", {"task_id": task_id, "text": text, "update_id": 12}, role="human")


def packet_record(pr_id="pr-1", summary="Поправил разбор строк"):
    return record("pr_packet", {
        "pr_id": pr_id, "branch": "agent/tg12-c1", "merged": False,
        "owner_approved": False, "summary": summary,
        "changed_paths": ["projects/ostis/oneiro-ostis/python/life_loop.py"],
        "tests": ["python -m pytest -q -p no:cacheprovider tests/test_swarm_protocol.py"],
    })


def make_runner(bridge, channel=None, cycle=None):
    calls: list[tuple] = []

    def run_cycle(config, task_text):
        calls.append((config, task_text))
        if cycle is not None:
            return cycle(config, task_text)
        return {"prs": [{"pr_id": "pr-1", "branch": "agent/tg12-c1",
                         "changed_paths": ["python/life_loop.py"], "tests": []}],
                "status": "finished"}

    built = runner_module.TaskRunner(
        bridge=bridge,
        channel=channel or FakeChannel(),
        repo_root=Path("/repo"),
        project_root=Path("/repo/projects/ostis/oneiro-ostis"),
        worktrees_root=Path("/repo/projects/ostis/oneiro-ostis/worktrees"),
        session_id="host-cowagent-life",
        run_cycle=run_cycle,
        say=lambda text: calls.append(("said", text)),
        echo=lambda _line: None,
    )
    return built, calls


# --------------------------------------------------------------------------- #
# reading the graph
# --------------------------------------------------------------------------- #

def test_a_job_with_nothing_done_yet_is_ready_to_work():
    bridge = FakeBridge([task_record()])
    runner, _ = make_runner(bridge)
    states = runner.states()
    assert list(states) == ["task-12"]
    assert states["task-12"].ready_to_work


def test_a_job_that_was_asked_about_and_answered_is_neither_ready_nor_waiting():
    bridge = FakeBridge([
        task_record(),
        record("task_started", {"task_id": "task-12"}),
        record("task_question", {"task_id": "task-12", "proposal_id": "keep-task-12"}),
        record("proposal_decided", {"proposal_id": "keep-task-12", "verdict": "approve",
                                    "by_user_id": 5094569795}, role="human"),
    ])
    runner, _ = make_runner(bridge)
    state = runner.states()["task-12"]
    assert state.decision == "approve"
    assert not state.ready_to_work
    assert not state.waiting


def test_the_oldest_unfinished_job_is_taken_first():
    bridge = FakeBridge([
        record("task", {"task_id": "task-2", "text": "второе"}, role="human"),
        record("task", {"task_id": "task-10", "text": "первое"}, role="human"),
    ])
    runner, _ = make_runner(bridge)
    assert runner.next_job().task_id == "task-10"


# --------------------------------------------------------------------------- #
# doing the work
# --------------------------------------------------------------------------- #

def test_the_owners_words_are_what_the_cycle_works_on():
    bridge = FakeBridge([task_record()])
    runner, calls = make_runner(bridge)
    runner.work(runner.states()["task-12"])
    config, task_text = [item for item in calls if item[0] != "said"][0]
    assert task_text == "посмотри, что не доделано"
    assert config.cycles == 1
    assert config.run_tag == "tg12-a1"


def test_work_ends_at_a_question_with_two_buttons():
    bridge = FakeBridge([task_record(), packet_record()])
    channel = FakeChannel()
    runner, calls = make_runner(bridge, channel=channel)
    proposal_id = runner.work(runner.states()["task-12"])

    assert proposal_id == "keep-task-12-a1"
    assert len(channel.sent) == 1
    message = approval.render(channel.sent[0])
    assert "A change is ready for the job: \u201cпосмотри, что не доделано\u201d" in message
    assert "What I want to change: a small change in the assistant's work" in message
    assert "without your press, nothing changes" in message
    assert "task_started" in bridge.kinds()
    asked = bridge.of("task_question")[0]
    assert asked.payload["proposal_id"] == "keep-task-12-a1"
    assert asked.payload["packet"]["branch"] == "agent/tg12-c1"
    said = [text for kind, text in calls if kind == "said"]
    assert said[0].startswith("Taken on")


def test_a_cycle_that_produced_no_packet_is_reported_honestly():
    bridge = FakeBridge([task_record()])
    runner, calls = make_runner(bridge, cycle=lambda config, text: {"prs": [], "status": "finished"})
    assert runner.work(runner.states()["task-12"]) is None

    assert bridge.of("task_question") == []
    failed = bridge.of("task_failed")[0]
    assert failed.payload["task_id"] == "task-12"
    said = [text for kind, text in calls if kind == "said"]
    assert "the change could not be prepared" in said[-1]


def test_a_second_attempt_does_not_greet_the_owner_again():
    """A process that restarts mid-work must not repeat "taken on"."""
    bridge = FakeBridge([
        task_record(),
        record("task_started", {"task_id": "task-12", "attempt": 1}),
        packet_record(),
    ])
    runner, calls = make_runner(bridge)
    runner.work(runner.states()["task-12"])

    said = [text for kind, text in calls if kind == "said"]
    assert not any(text.startswith("Taken on") for text in said)


def test_a_job_that_failed_once_is_worked_again():
    bridge = FakeBridge([
        task_record(),
        record("task_started", {"task_id": "task-12"}),
        record("task_failed", {"task_id": "task-12", "attempt": 1, "reason": "no packet"}),
    ])
    runner, _ = make_runner(bridge)
    state = runner.states()["task-12"]

    assert state.failures == 1
    assert state.ready_to_work


def test_a_retry_asks_a_new_question_and_does_not_promise_a_third_try():
    """The id changes because the channel refuses to send one proposal twice."""
    bridge = FakeBridge([
        task_record(),
        record("task_failed", {"task_id": "task-12", "attempt": 1, "reason": "no packet"}),
        packet_record(pr_id="pr-2"),
    ])
    channel = FakeChannel()
    runner, calls = make_runner(bridge, channel=channel,
                               cycle=lambda config, text: {
                                   "prs": [{"pr_id": "pr-2", "branch": "agent/x",
                                            "changed_paths": [], "tests": []}],
                                   "status": "finished"})
    proposal_id = runner.work(runner.states()["task-12"])

    assert proposal_id == "keep-task-12-a2"
    config = [item for item in calls if item[0] != "said"][0][0]
    assert config.run_tag == "tg12-a2"


def test_out_of_attempts_the_job_is_left_alone():
    bridge = FakeBridge(
        [task_record()]
        + [record("task_failed", {"task_id": "task-12", "attempt": n, "reason": "no packet"})
           for n in (1, 2, 3)]
    )
    runner, _ = make_runner(bridge)

    assert runner.states()["task-12"].failures == 3
    assert not runner.states()["task-12"].ready_to_work
    assert runner.next_job() is None


def test_the_last_failure_does_not_promise_another_attempt():
    bridge = FakeBridge([
        task_record(),
        record("task_failed", {"task_id": "task-12", "attempt": 1, "reason": "no packet"}),
        record("task_failed", {"task_id": "task-12", "attempt": 2, "reason": "no packet"}),
    ])
    runner, calls = make_runner(bridge, cycle=lambda config, text: {"prs": [], "status": "finished"})
    assert runner.work(runner.states()["task-12"]) is None

    said = [text for kind, text in calls if kind == "said"]
    assert "not taking it on again today" in said[-1]


def test_a_packet_the_graph_does_not_know_is_not_claimed_as_work():
    """The loop may say it delivered something; the record decides."""
    bridge = FakeBridge([task_record()])  # no packet record at all
    runner, _ = make_runner(bridge)
    assert runner.work(runner.states()["task-12"]) is None
    assert bridge.of("task_failed")


# --------------------------------------------------------------------------- #
# the verdict comes back as a record
# --------------------------------------------------------------------------- #

def test_an_approved_verdict_closes_the_job_and_says_so():
    bridge = FakeBridge([
        task_record(),
        record("task_question", {"task_id": "task-12", "proposal_id": "keep-task-12"}),
        record("proposal_decided", {"proposal_id": "keep-task-12", "verdict": "approve"},
               role="human"),
    ])
    runner, calls = make_runner(bridge)
    state = runner.states()["task-12"]
    assert runner.collect(state) == "approve"

    done = bridge.of("task_done")[0]
    assert done.payload["verdict"] == "approve"
    assert done.role == "human"
    said = [text for kind, text in calls if kind == "said"]
    assert "not merged into the main work" in said[-1]


def test_a_rejected_verdict_closes_the_job_and_says_so():
    bridge = FakeBridge([
        task_record(),
        record("task_question", {"task_id": "task-12", "proposal_id": "keep-task-12"}),
        record("proposal_decided", {"proposal_id": "keep-task-12", "verdict": "reject"},
               role="human"),
    ])
    runner, calls = make_runner(bridge)
    assert runner.collect(runner.states()["task-12"]) == "reject"
    assert bridge.of("task_done")[0].payload["verdict"] == "reject"
    said = [text for kind, text in calls if kind == "said"]
    assert "was put aside" in said[-1]


def test_a_job_that_still_waits_is_not_closed_twice():
    bridge = FakeBridge([
        task_record(),
        record("task_question", {"task_id": "task-12", "proposal_id": "keep-task-12"}),
    ])
    runner, _ = make_runner(bridge)
    assert runner.collect(runner.states()["task-12"]) is None
    assert bridge.of("task_done") == []


def test_a_tick_closes_what_was_answered_and_asks_about_a_new_job():
    bridge = FakeBridge([
        record("task", {"task_id": "task-1", "text": "первое"}, role="human"),
        record("task_question", {"task_id": "task-1", "proposal_id": "keep-task-1"}),
        record("proposal_decided", {"proposal_id": "keep-task-1", "verdict": "reject"},
               role="human"),
        record("task", {"task_id": "task-2", "text": "второе"}, role="human"),
        packet_record(pr_id="pr-1"),
    ])
    runner, _ = make_runner(bridge)
    result = runner.tick()
    assert "closed task-1" in result["moved"]
    assert "asked about task-2" in result["moved"]
    assert bridge.of("task_done")[0].payload["task_id"] == "task-1"
    assert bridge.of("task_question")[-1].payload["task_id"] == "task-2"


# --------------------------------------------------------------------------- #
# the words
# --------------------------------------------------------------------------- #

VISIBLE = {
    "STARTED_TEXT": runner_module.STARTED_TEXT,
    "FAILED_TEXT": runner_module.FAILED_TEXT,
    "FAILED_LAST_TEXT": runner_module.FAILED_LAST_TEXT,
    "APPROVED_TEXT": runner_module.APPROVED_TEXT,
    "REJECTED_TEXT": runner_module.REJECTED_TEXT,
}


def test_everything_the_owner_reads_from_the_runner_is_english():
    banned = re.compile(r"\b(graph|MCP|JSON|API|branch|commit|PR)\b", re.IGNORECASE)
    for name, text in VISIBLE.items():
        filled = text.format(text="a message") if "{text}" in text else text
        assert not re.findall(r"[\u0400-\u04FF]", filled), f"{name} carries Cyrillic"
        assert not banned.search(filled), f"{name} names machinery"


def test_the_owner_is_told_which_part_changes_not_which_file():
    bridge = FakeBridge([task_record(), packet_record()])
    channel = FakeChannel()
    runner, _ = make_runner(bridge, channel=channel)
    runner.work(runner.states()["task-12"])

    message = approval.render(channel.sent[0])
    assert "python/life_loop.py" not in message
    assert ".py" not in message
    assert "the assistant's daily round of work" in message


def test_an_unknown_file_becomes_words_instead_of_a_path():
    assert runner_module.human_part(
        "projects/ostis/oneiro-ostis/python/new_thing.py") == "an inner part of the assistant"
    assert runner_module.human_part(
        "projects/x/tests/test_swarm_protocol.py") == "the assistant's checks"
    assert runner_module.human_parts(
        ["a/python/swarm.py", "b/python/swarm.py", "c/python/worker.py"]) == [
            "how the roles agree on work", "the assistant working with the project's files"]


def test_the_owner_is_never_told_an_internal_number():
    """The proposal id lives in the button data, not in the sentence."""
    bridge = FakeBridge([task_record(), packet_record()])
    channel = FakeChannel()
    runner, _ = make_runner(bridge, channel=channel)
    runner.work(runner.states()["task-12"])
    message = approval.render(channel.sent[0])
    assert "keep-task-12" not in message
