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


def seed_session(tmp_path, messages, files, step_limit=8):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    for name, content in files.items():
        path = worktree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return WorkerSession(
        pool=ScriptedPool(messages), proposal=make_proposal(),
        worktree_root=worktree, check_command=("python", "-c", "print('check-ok')"),
        scope=".", step_limit=step_limit,
    )


def test_worker_replaces_a_snippet_in_an_existing_file(tmp_path):
    session = seed_session(
        tmp_path,
        [
            tool_call("replace_in_file",
                      {"path": "seed.txt", "old_text": "beta", "new_text": "BETA"}),
            tool_call("finish", {"summary": "готово"}),
        ],
        {"seed.txt": "alpha\nbeta\ngamma\n"},
    )
    outcome = session.run()

    assert outcome.status == "done"
    assert (tmp_path / "wt" / "seed.txt").read_text(encoding="utf-8") == "alpha\nBETA\ngamma\n"
    assert any(action.get("tool") == "replace_in_file" for action in outcome.actions)


def test_worker_refuses_a_snippet_that_is_missing_or_ambiguous(tmp_path):
    original = "dup\ndup\n"
    session = seed_session(
        tmp_path,
        [
            tool_call("replace_in_file",
                      {"path": "twice.txt", "old_text": "dup", "new_text": "x"}),
            tool_call("replace_in_file",
                      {"path": "twice.txt", "old_text": "absent", "new_text": "x"}),
            tool_call("finish", {"summary": "готово"}),
        ],
        {"twice.txt": original},
    )
    outcome = session.run()

    assert outcome.status == "done"
    assert (tmp_path / "wt" / "twice.txt").read_text(encoding="utf-8") == original


def test_worker_refuses_to_stub_out_a_large_file(tmp_path):
    big = "line of code\n" * 400  # 5200 bytes: over the shrink guard
    session = seed_session(
        tmp_path,
        [
            tool_call("write_file", {"path": "big.py", "content": "stub"}),
            tool_call("finish", {"summary": "готово"}),
        ],
        {"big.py": big},
    )
    outcome = session.run()

    assert outcome.status == "done"
    assert (tmp_path / "wt" / "big.py").read_text(encoding="utf-8") == big


def test_worker_reads_plain_text_so_snippets_can_be_copied(tmp_path):
    session = seed_session(tmp_path, [], {"plain.txt": "alpha\nbeta\n"})

    assert session._read_file("plain.txt") == "alpha\nbeta\n"


def test_worker_reads_a_window_and_says_what_is_left(tmp_path):
    body = "\n".join(f"line {index}" for index in range(1, 2001))
    session = seed_session(tmp_path, [], {"long.txt": body})

    window = session._read_file("long.txt", start_line=900)

    assert window.startswith("line 900")
    assert "showed lines 900-1299 of 2000" in window


def test_worker_finishes_in_the_grace_window_after_the_step_limit(tmp_path):
    messages = [
        tool_call("write_file", {"path": "note.txt", "content": "hello"}),
        tool_call("finish", {"summary": "готово"}),
    ]
    outcome = make_session(tmp_path, messages, step_limit=1).run()

    assert outcome.status == "done"
    assert outcome.summary == "готово"
    assert outcome.steps == 1
    assert (tmp_path / "wt" / "note.txt").read_text(encoding="utf-8") == "hello"


def test_worker_gives_up_when_the_grace_window_is_wasted(tmp_path):
    messages = [
        tool_call("write_file", {"path": "note.txt", "content": "hello"}),
        tool_call("list_files", {}),
        tool_call("list_files", {}),
    ]
    outcome = make_session(tmp_path, messages, step_limit=1).run()

    assert outcome.status == "gave_up"
    assert "grace" in outcome.summary


def test_worker_gives_up_at_the_step_limit_without_any_change(tmp_path):
    messages = [tool_call("list_files", {}) for _ in range(4)]
    outcome = make_session(tmp_path, messages, step_limit=1).run()

    assert outcome.status == "gave_up"
    assert outcome.summary == "step limit reached (1)"
