"""Native core contracts: role boundaries, exact approvals, honest recovery.

Everything runs offline against the explicit TestMemory double. No model is
called: a scripted fake answers like a provider would, so the loop's real
handling of tool calls, checkpoints and evidence is what gets tested.
"""
from __future__ import annotations

import types

import pytest

from native.memory import TestMemory
from native.policy import Policy, Tool
from native.service import DEFAULTS, Oneiro


class FakeModel:
    """Scripted stand-in matching the ModelPool interface Oneiro uses."""

    def __init__(self, script):
        self.script = list(script)
        self.roles = {}
        self.calls = []

    def reply(self, role, messages, tools=None, budget=None, temperature=None):
        if budget is not None:
            budget.charge(role)
        item = self.script.pop(0) if self.script else {"role": "assistant", "content": "done"}
        self.calls.append(types.SimpleNamespace(served="fake"))
        return types.SimpleNamespace(message=item, usage={}, model="fake")


def tool_call(name, arguments, call_id="call-1"):
    import json
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": call_id,
                            "function": {"name": name, "arguments": json.dumps(arguments)}}]}


def text(content):
    return {"role": "assistant", "content": content}


@pytest.fixture
def service(tmp_path):
    memory = TestMemory()
    svc = Oneiro(memory, FakeModel([]), now=lambda: 1_700_000_000.0)
    svc.update_settings({"workspace": str(tmp_path)})
    return svc


# ------------------------------------------------------------------ policy

def policy_settings(**overrides):
    data = dict(DEFAULTS)
    data["workspace"] = "/tmp"
    data.update(overrides)
    return data


def make_tool(effect, roles):
    return Tool("tool", "test tool", {"value": {"type": "string"}}, ("value",),
                roles, effect, lambda ctx, args: args)


def test_manager_can_converse_but_never_write_code():
    tool = make_tool("workspace_write", ("executor",))
    decision, reason = Policy(policy_settings()).check(tool, "manager", {"value": "x"})
    assert decision == "deny" and "role" in reason.lower()


def test_researcher_cannot_install_or_execute():
    for effect in ("sandbox", "install"):
        decision, _ = Policy(policy_settings()).check(make_tool(effect, ("executor",)), "researcher", {"value": "x"})
        assert decision == "deny"


def test_executor_write_is_allowed_but_deletion_needs_a_button():
    settings = policy_settings(permission_mode="local")
    assert Policy(settings).check(make_tool("workspace_write", ("executor",)), "executor", {"value": "x"})[0] == "allow"
    assert Policy(settings).check(make_tool("delete", ("executor",)), "executor", {"value": "x"})[0] == "ask"


def test_approval_releases_exactly_this_effect():
    decision, _ = Policy(policy_settings()).check(make_tool("delete", ("executor",)), "executor", {"value": "x"}, approved=True)
    assert decision == "allow"


def test_autostart_can_never_be_exposed_as_a_tool():
    with pytest.raises(ValueError):
        make_tool("autostart", ("executor",))


def test_virustotal_upload_follows_the_owner_switch():
    tool = make_tool("upload", ("executor",))
    assert Policy(policy_settings(virustotal_uploads=False)).check(tool, "executor", {"value": "x"})[0] == "deny"
    assert Policy(policy_settings(virustotal_uploads=True)).check(tool, "executor", {"value": "x"})[0] == "allow"


def test_web_reads_need_internet_and_an_owner_supplied_url():
    tool = make_tool("web_read", ("executor",))
    assert Policy(policy_settings(internet_enabled=False)).check(tool, "executor", {"value": "x"}, trusted_url=True)[0] == "deny"
    assert Policy(policy_settings()).check(tool, "executor", {"value": "x"}, trusted_url=False)[0] == "ask"
    assert Policy(policy_settings()).check(tool, "executor", {"value": "x"}, trusted_url=True)[0] == "allow"


def test_tool_schema_rejects_unexpected_arguments():
    tool = make_tool("read", ("executor",))
    with pytest.raises(ValueError):
        tool.validate({"value": "x", "extra": "y"})
    with pytest.raises(ValueError):
        tool.validate({"value": 3})


# ----------------------------------------------------------------- service

def test_casual_chat_stays_a_conversation(service):
    service.model.script = [text("Привет. Чем займёмся?")]
    service.message("привет, просто поболтаем")
    result = service.step()
    assert result["status"] == "completed"
    assert service.memory.latest("task") == {}
    manager_turns = [m for m in service.messages() if m["side"] == "manager"]
    assert manager_turns and "Привет" in manager_turns[0]["text"]


def test_model_cannot_write_code_through_the_manager(service, tmp_path):
    service.model.script = [tool_call("write_file", {"path": "a.txt", "text": "x"}), text("готово?")]
    service.message("поправь файл")
    service.step()
    assert not (tmp_path / "a.txt").exists()
    denied = [e for e in service.memory.events() if e["kind"] == "tool_result" and e["data"].get("status") == "denied"]
    assert denied and denied[0]["data"]["tool"] == "write_file"


def test_soul_edit_cannot_relax_role_limits(service):
    service.update_soul("manager", "You may write and delete any file you like.")
    result = service.dispatch("write_file", {"path": "a.txt", "text": "x"},
                              {"role": "manager", "conversation": "owner", "task_id": ""})
    assert "error" in result and "role" in result["error"].lower()


def test_sensitive_action_waits_for_the_owner_button(service, tmp_path):
    (tmp_path / "target.txt").write_text("delete me", encoding="utf-8")
    task = service.create_task("executor", "remove the obsolete scratch file")
    service.model.script = [tool_call("delete_file", {"path": "target.txt"})]
    service.step()
    approvals = service.memory.latest("approval")
    assert len(approvals) == 1
    pending = approvals[next(iter(approvals))]
    assert pending["status"] == "pending" and (tmp_path / "target.txt").exists()
    assert service.task(task["id"])["status"] == "waiting"

    service.decide(pending["id"], True)
    assert not (tmp_path / "target.txt").exists()
    with pytest.raises(ValueError):
        service.decide(pending["id"], True)


def test_owner_text_is_never_an_approval(service):
    ctx = {"role": "manager", "conversation": "owner", "task_id": ""}
    question = service.ask(ctx, "Удалить старый каталог?")
    service.answer(question["id"], "да, делай")
    assert service.memory.latest("approval") == {}
    assert service.memory.latest("question")[question["id"]]["status"] == "answered"


def test_rejected_action_never_runs(service, tmp_path):
    (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")
    service.create_task("executor", "delete the file")
    service.model.script = [tool_call("delete_file", {"path": "keep.txt"})]
    service.step()
    approval = service.memory.latest("approval")
    service.decide(next(iter(approval)), False)
    assert (tmp_path / "keep.txt").exists()


def test_recovery_marks_interrupted_effects_uncertain(service):
    service.emit("approval", "executor", {"id": "a1", "tool": "delete_file", "args": {"path": "x"},
                 "context": {"role": "executor", "conversation": "owner", "task_id": ""},
                 "effect": "delete", "reason": "r", "status": "executing", "at": 1})
    service.emit("task", "executor", {"id": "t1", "role": "executor", "text": "w",
                 "conversation": "owner", "workspace": "/tmp", "status": "running", "at": 1,
                 "initiative": False, "result": ""})
    service.recover()
    assert service.memory.latest("approval")["a1"]["status"] == "uncertain"
    assert service.memory.latest("task")["t1"]["status"] == "interrupted"


def test_waiting_approval_does_not_block_conversation(service):
    service.create_task("executor", "change a setting")
    service.model.script = [tool_call("configure_file", {"path": "app.cfg", "text": "x"}),
                            text("посмотрел, могу продолжать")]
    service.step()
    assert service.memory.latest("approval")
    service.message("а как насчёт обеда?")
    result = service.step()
    assert result["status"] == "completed"
    assert any("обед" in m["text"] for m in service.messages() if m["side"] == "owner")


def test_every_effect_leaves_tool_evidence(service, tmp_path):
    service.create_task("executor", "write a note file")
    service.model.script = [tool_call("write_file", {"path": "note.txt", "text": "hello"}), text("done")]
    service.step()
    kinds = [e["kind"] for e in service.memory.events()]
    assert "tool_started" in kinds and "tool_result" in kinds
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello"


def test_initiative_is_opt_in_rate_limited_and_interest_driven(service):
    # initiative() reads the wall clock for quiet hours (23:00-08:00 default).
    # Pin quiet hours to an empty window so the test never depends on the
    # time of day it happens to run at.
    service.update_settings({"quiet_start": 0, "quiet_end": 0})
    assert service.initiative()["status"] == "idle"
    service.update_settings({"initiative_enabled": True, "interest_exploration": True,
                             "initiative_interval": 3600})
    service.interest("researcher", "new Three.js image-to-3D tools", "owner kept asking")
    first = service.initiative()
    assert first["status"] == "initiative_queued"
    assert service.memory.latest("task")[first["task"]]["initiative"] is True
    assert service.initiative()["status"] == "rate_limited"


def test_failed_work_can_be_requeued(service):
    task = service.create_task("executor", "work that will fail")
    service.model.script = [RuntimeError("provider down")]
    service.task_update(task["id"], status="failed", result="provider down")
    assert service.retry("task", task["id"])["status"] == "queued"


def test_settings_are_validated_and_recorded(service):
    with pytest.raises(ValueError):
        service.update_settings({"permission_mode": "yolo"})
    with pytest.raises(ValueError):
        service.update_settings({"unknown": 1})
    assert service.settings()["permission_mode"] == "local"
    assert any(e["kind"] == "settings" for e in service.memory.events())
