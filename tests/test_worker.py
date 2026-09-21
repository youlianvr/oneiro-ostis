"""Offline tests for the worker: tool loop, path jail, step limit."""

import json
from pathlib import Path

from llm import ModelReply
from swarm import Proposal
from worker import WorkerSession


class ScriptedPool:
    def __init__(self, messages):
        self.messages = list(messages)
        self.calls = 0

    def reply(self, role, messages, *, tools=None, budget=None, temperature=None):
        self.calls += 1
        item = self.messages.pop(0)
        return ModelReply(message=item, usage={}, model="fake")


def tool_call(name, arguments, call_id="c1"):
    return {
        "role": "assistant", "content": "",
        "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }


def make_proposal():
    return Proposal("p1", "Добавить заметку", "нужен файл", ("файл создан",),
                    check_id="unit-tests")


def make_session(tmp_path, messages, check=("python", "-c", "print('check-ok')"),
                 step_limit=8):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / "seed.txt").write_text("seed", encoding="utf-8")
    return WorkerSession(
        pool=ScriptedPool(messages), proposal=make_proposal(),
        worktree_root=worktree, check_command=check, scope=".",
        step_limit=step_limit,
    )


def test_worker_writes_and_runs_the_check(tmp_path):
    messages = [
        tool_call("list_files", {}),
        tool_call("write_file", {"path": "sub/note.txt", "content": "hello"}),
        tool_call("run_check", {}),
        tool_call("finish", {"summary": "готово"}),
    ]
    outcome = make_session(tmp_path, messages).run()

    assert outcome.status == "done"
    assert outcome.summary == "готово"
    assert (tmp_path / "wt" / "sub" / "note.txt").read_text(encoding="utf-8") == "hello"
    assert any(action.get("tool") == "run_check" and action.get("exit") == 0
               for action in outcome.actions)
    assert any(action.get("tool") == "write_file" for action in outcome.actions)


def test_worker_cannot_write_outside_the_worktree(tmp_path):
    outside = tmp_path / "escaped.txt"
    messages = [
        tool_call("write_file", {"path": "../escaped.txt", "content": "nope"}),
        tool_call("finish", {"summary": "готово"}),
    ]
    outcome = make_session(tmp_path, messages).run()

    assert outcome.status == "done"
    assert not outside.exists()


def test_worker_gives_up_at_the_step_limit(tmp_path):
    messages = [tool_call("list_files", {}) for _ in range(3)]
    outcome = make_session(tmp_path, messages, step_limit=2).run()

    assert outcome.status == "gave_up"
    assert outcome.steps == 2


def test_worker_answers_unknown_tools_without_crashing(tmp_path):
    messages = [
        tool_call("delete_everything", {"path": "/"}),
        tool_call("finish", {"summary": "готово"}),
    ]
    outcome = make_session(tmp_path, messages).run()

    assert outcome.status == "done"
