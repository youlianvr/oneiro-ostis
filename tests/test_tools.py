"""The tool surface: what a call may do, what it may not, and who decides.

The policy is metadata plus configuration. Nothing in this file has to consult a
prompt, a model or a stored record, which is the point: a tool call is allowed
because the reviewed metadata and the settings allow it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oneiro import config
from oneiro.records import Approval, Provenance
from oneiro.tools import (EFFECTS, EFFECTS_WITHOUT_SETTING, EFFECT_SETTINGS, ROLE_EFFECTS,
                          Policy, Tool, ToolError, arguments_digest, build_registry,
                          declared_write_effect, fetch_url, public_url, put, readable,
                          resolves_inside, write_target)

LIMIT = 2000


def tool(name: str, effect: str, roles=("manager",), properties=None, required=()) -> Tool:
    return Tool(name, "test tool", properties or {}, required, roles, effect, lambda c, a: {})


def policy(**settings) -> Policy:
    """A policy with no declared decisions, so the reviewed defaults answer."""
    return Policy({"internet_enabled": False, **settings})


# ---------- metadata is a boundary, not a comment ----------


def test_an_effect_outside_the_tools_roles_is_refused_at_definition_time():
    with pytest.raises(ToolError, match="role boundaries"):
        # The manager role has no write effect: that rule cannot be written around.
        tool("sneaky_write", "workspace_write", roles=("manager",))


def test_an_unknown_effect_or_role_is_refused():
    with pytest.raises(ToolError):
        tool("odd", "teleport")
    with pytest.raises(ToolError):
        tool("odd", "read", roles=("observer",))


def test_every_declared_effect_belongs_to_at_least_one_role():
    owned = set().union(*ROLE_EFFECTS.values())
    assert EFFECTS - owned == {"autostart"}, "an effect nobody may use must be deliberate"


def test_the_schema_tells_the_model_exactly_what_is_accepted():
    subject = tool("read_file", "read", properties={"path": {"type": "string"}},
                   required=("path",))
    parameters = subject.schema()["function"]["parameters"]
    assert parameters["required"] == ["path"]
    assert parameters["additionalProperties"] is False


@pytest.mark.parametrize("arguments", [
    "not an object",
    {},
    {"path": "ok", "extra": 1},
    {"path": 7},
])
def test_invalid_arguments_are_refused_with_a_reason(arguments):
    subject = tool("read_file", "read", properties={"path": {"type": "string"}},
                   required=("path",))
    with pytest.raises(ToolError):
        subject.validate(arguments)


def test_an_integer_is_not_accepted_where_a_boolean_was_declared():
    subject = tool("flag", "read", properties={"on": {"type": "boolean"}}, required=("on",))
    with pytest.raises(ToolError, match="boolean"):
        subject.validate({"on": 1})


def test_an_enum_value_is_enforced():
    subject = tool("pick", "read", properties={"mode": {"type": "string", "enum": ["a", "b"]}},
                   required=("mode",))
    subject.validate({"mode": "a"})
    with pytest.raises(ToolError, match="not one of"):
        subject.validate({"mode": "c"})


# ---------- the policy decides; the model does not ----------


def test_a_role_boundary_denial_is_permanent():
    decision, reason = policy().check(tool("write_file", "workspace_write", roles=("executor",)),
                                      "manager", {}, )
    assert decision == "deny" and "manager" in reason


def test_an_unknown_role_is_denied_even_with_an_owner_approval():
    subject = tool("read_file", "read", properties={"path": {"type": "string"}},
                   required=("path",))
    decision, _ = policy().check(subject, "intruder", {"path": "x"}, approved=True)
    assert decision == "deny"


def test_internet_access_is_denied_until_it_is_enabled():
    subject = tool("fetch_url", "web_read", properties={"url": {"type": "string"}},
                   required=("url",))
    arguments = {"url": "https://example.com/"}
    assert policy().check(subject, "manager", arguments)[0] == "deny"
    decision, reason = policy(internet_enabled=True).check(subject, "manager", arguments)
    assert decision == "ask" and "exact outbound URL" in reason
    decision, reason = policy(internet_enabled=True).check(subject, "manager", arguments,
                                                          trusted_url=True)
    assert decision == "allow"


def test_a_sensitive_effect_asks_and_an_owner_approval_allows_that_call():
    subject = tool("delete_file", "delete", roles=("executor",),
                   properties={"path": {"type": "string"}}, required=("path",))
    arguments = {"path": "notes.txt"}
    assert policy().check(subject, "executor", arguments)[0] == "ask"
    decision, reason = policy().check(subject, "executor", arguments, approved=True)
    assert decision == "allow" and "approved" in reason


def test_the_declared_decision_is_what_decides_a_write():
    subject = tool("write_file", "workspace_write", roles=("executor",),
                   properties={"path": {"type": "string"}, "text": {"type": "string"}},
                   required=("path", "text"))
    arguments = {"path": "a.txt", "text": "hello"}
    assert policy().check(subject, "executor", arguments)[0] == "allow"
    asks = policy(decisions={"workspace_write": "ask"})
    assert asks.check(subject, "executor", arguments)[0] == "ask"
    refuses = policy(decisions={"workspace_write": "deny"})
    assert refuses.check(subject, "executor", arguments)[0] == "deny"
    # An approval releases a question, never a refusal.
    assert refuses.check(subject, "executor", arguments, approved=True)[0] == "deny"


def test_a_declared_allow_outranks_the_reviewed_sensitive_default():
    subject = tool("delete_file", "delete", roles=("executor",),
                   properties={"path": {"type": "string"}}, required=("path",))
    assert policy().check(subject, "executor", {"path": "a.txt"})[0] == "ask"
    allowed = policy(decisions={"delete": "allow"})
    assert allowed.check(subject, "executor", {"path": "a.txt"})[0] == "allow"


def test_every_effect_is_governed_or_deliberately_not():
    """A new effect must be given a permission or declared as needing none."""
    assert set(EFFECT_SETTINGS) | EFFECTS_WITHOUT_SETTING == EFFECTS
    assert not set(EFFECT_SETTINGS) & EFFECTS_WITHOUT_SETTING
    for effect, setting in EFFECT_SETTINGS.items():
        assert setting in config._BY_KEY, f"{effect} is governed by {setting}, which is not declared"


def test_a_bad_arguments_object_is_refused_before_the_effect_is_considered():
    subject = tool("write_file", "workspace_write", roles=("executor",),
                   properties={"path": {"type": "string"}, "text": {"type": "string"}},
                   required=("path", "text"))
    with pytest.raises(ToolError):
        policy(decisions={"workspace_write": "ask"}).check(subject, "executor", {"path": "a.txt"})


# ---------- an approval covers one exact call ----------


def test_the_argument_digest_ignores_key_order_and_notices_a_change():
    first = arguments_digest({"path": "a.txt", "text": "hello"})
    reordered = arguments_digest({"text": "hello", "path": "a.txt"})
    changed = arguments_digest({"path": "b.txt", "text": "hello"})
    assert first == reordered
    assert first != changed


def approval(tool_name="write_file", digest="", **changes) -> Approval:
    fields = {"id": "approval-1", "action_id": "act-1", "tool": tool_name,
              "arguments_digest": digest, "granted": True,
              "provenance": Provenance.OWNER_INSTRUCTION}
    fields.update(changes)
    return Approval(**fields)


def test_an_approval_covers_exactly_one_call():
    digest = arguments_digest({"path": "a.txt", "text": "hello"})
    granted = approval(digest=digest)
    assert granted.covers("write_file", digest) is True
    assert granted.covers("write_file", arguments_digest({"path": "a.txt", "text": "bye"})) is False
    assert granted.covers("delete_file", digest) is False


def test_a_stale_or_unowned_approval_covers_nothing():
    digest = arguments_digest({"path": "a.txt"})
    assert approval(digest=digest, granted=False).covers("write_file", digest) is False
    assert approval(digest=digest, provenance=Provenance.MODEL_CLAIM).covers(
        "write_file", digest) is False


def test_an_approval_without_an_action_or_tool_cannot_exist():
    with pytest.raises(ValueError):
        Approval(id="a", action_id="", tool="write_file")
    with pytest.raises(ValueError):
        Approval(id="a", action_id="act-1", tool="")


# ---------- files: credential material and confinement ----------


@pytest.mark.parametrize("name", ["/home/owner/.env", "/keys/.env.local", "id_rsa",
                                  "server.pem", "private.key"])
def test_credential_material_is_never_readable(name):
    with pytest.raises(ToolError, match="credential"):
        readable(name, max_bytes=LIMIT)


def test_an_ordinary_file_is_readable(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    assert readable(str(tmp_path / "notes.txt"), max_bytes=LIMIT).is_file()


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/hosts", "sub/../../elsewhere.txt"])
def test_a_path_that_leaves_the_folder_is_an_outside_write_not_an_escape(tmp_path, path):
    """`..` is resolved, not trusted: what leaves the folder is named as such.

    It is not silently allowed either — the effect it gets is the one governed by
    `permissions.write_outside`, which asks by default.
    """
    assert resolves_inside(tmp_path, path) is False
    assert declared_write_effect(tmp_path, path) == "write_outside"


def test_an_internal_directory_is_still_protected_inside_the_folder(tmp_path):
    with pytest.raises(ToolError, match="protected"):
        write_target(tmp_path, ".git/config", effect="workspace_write", max_bytes=LIMIT)
    with pytest.raises(ToolError, match="protected"):
        write_target(tmp_path, ".runtime/state.json", effect="workspace_write", max_bytes=LIMIT)


def test_a_nested_path_inside_the_workspace_is_allowed(tmp_path):
    target = write_target(tmp_path, "notes/todo.txt", effect="workspace_write", max_bytes=LIMIT)
    assert target == (tmp_path / "notes" / "todo.txt").resolve()
    assert declared_write_effect(tmp_path, "notes/todo.txt") == "workspace_write"


def test_the_workspace_root_itself_is_not_writable(tmp_path):
    with pytest.raises(ToolError, match="working folder itself"):
        write_target(tmp_path, ".", effect="workspace_write", max_bytes=LIMIT)


def test_the_effect_of_a_write_follows_the_path_it_names(tmp_path):
    """One tool, two acts: inside the folder and outside it are not the same write."""
    tools = build_registry(tmp_path, internet=False, max_bytes=LIMIT)
    subject = tools["write_file"]
    inside = {"path": "notes/a.txt", "text": "x"}
    outside = {"path": str(tmp_path.parent / "elsewhere.txt"), "text": "x"}
    assert subject.effect_for(inside) == "workspace_write"
    assert subject.effect_for(outside) == "write_outside"
    assert subject.effect == "workspace_write", "the declared effect is the offered one"


def test_an_outside_write_is_governed_by_its_own_declared_permission(tmp_path):
    subject = build_registry(tmp_path, internet=False, max_bytes=LIMIT)["write_file"]
    inside = {"path": "a.txt", "text": "x"}
    outside = {"path": "../a.txt", "text": "x"}
    declared = {"workspace_write": "allow", "write_outside": "ask"}

    assert policy(decisions=declared).check(subject, "executor", inside)[0] == "allow"
    asked = policy(decisions=declared).check(subject, "executor", outside)
    assert asked[0] == "ask" and "write_outside" in asked[1]
    # The owner's grant for exactly this call releases it, as for any other effect.
    assert policy(decisions=declared).check(subject, "executor", outside,
                                            approved=True)[0] == "allow"
    # A declared refusal stays a boundary even with a grant.
    refused = policy(decisions={"workspace_write": "allow", "write_outside": "deny"})
    assert refused.check(subject, "executor", outside, approved=True)[0] == "deny"


def test_without_a_declared_decision_an_outside_write_asks(tmp_path):
    """The reviewed default for an outside write is a question, never silence."""
    subject = build_registry(tmp_path, internet=False, max_bytes=LIMIT)["write_file"]
    decision, reason = policy().check(subject, "executor", {"path": "../a.txt", "text": "x"})
    assert decision == "ask" and "write_outside" in reason


def test_an_allowed_outside_write_lands_and_a_refused_one_never_does(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    target = tmp_path / "outside" / "note.txt"
    subject = build_registry(root, internet=False, max_bytes=LIMIT)["write_file"]
    allowed = policy(decisions={"workspace_write": "allow", "write_outside": "allow"})
    arguments = {"path": str(target), "text": "written outside"}

    assert allowed.check(subject, "executor", arguments)[0] == "allow"
    assert subject.handler is not None
    report = subject.handler({}, arguments)
    assert target.read_text(encoding="utf-8") == "written outside"
    assert report["bytes"] == len("written outside")

    refused = policy(decisions={"workspace_write": "allow", "write_outside": "deny"})
    assert refused.check(subject, "executor", arguments)[0] == "deny"
    assert target.read_text(encoding="utf-8") == "written outside", "nothing rewrote it"


def test_an_outside_write_still_refuses_credentials_and_configuration(tmp_path):
    subject = build_registry(tmp_path, internet=False, max_bytes=LIMIT)["write_file"]
    assert subject.handler is not None
    with pytest.raises(ToolError, match="credential"):
        subject.handler({}, {"path": str(tmp_path / "outside" / ".env"), "text": "x"})
    with pytest.raises(ToolError, match="configuration"):
        subject.handler({}, {"path": str(tmp_path / "outside" / "settings.json"), "text": "x"})
    assert not (tmp_path / "outside").exists()


def test_a_write_over_the_limit_leaves_the_previous_file_intact(tmp_path):
    target = tmp_path / "notes.txt"
    put(target, "small", max_bytes=LIMIT)
    with pytest.raises(ToolError, match="limit"):
        put(target, "x" * (LIMIT + 1), max_bytes=LIMIT)
    assert target.read_text(encoding="utf-8") == "small"
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_write_reports_what_it_wrote(tmp_path):
    report = put(tmp_path / "a" / "b.txt", "hello", max_bytes=LIMIT)
    assert report["bytes"] == 5 and len(report["sha256"]) == 64
    assert Path(report["written"]).read_text(encoding="utf-8") == "hello"


# ---------- the web: public destinations only ----------


@pytest.mark.parametrize("url", [
    "ftp://example.com/", "http://user:secret@example.com/", "http://example.com:8080/",
    "http://127.0.0.1:80/", "http://localhost/", "https://example.com/#fragment",
])
def test_only_an_exact_public_url_is_accepted(url):
    with pytest.raises(ToolError):
        public_url(url)


def test_a_private_address_is_refused_before_any_request_is_made():
    with pytest.raises(ToolError, match="private and loopback"):
        fetch_url("http://10.0.0.5/", max_bytes=LIMIT, timeout=0.1)


# ---------- the declared set follows the configuration ----------


def test_without_a_workspace_no_write_tool_is_offered():
    names = set(build_registry(None, internet=False, max_bytes=LIMIT))
    assert "write_file" not in names
    assert {"read_file", "list_files", "fetch_url"} <= names


def test_with_a_workspace_the_executor_gets_the_write_tool(tmp_path):
    tools = build_registry(tmp_path, internet=False, max_bytes=LIMIT)
    assert tools["write_file"].roles == ("executor",)
    assert "manager" not in tools["write_file"].roles
    # The manager is refused for the outside write too, by the effect it implies.
    assert policy(decisions={"write_outside": "allow"}).check(
        tools["write_file"], "manager", {"path": "../a.txt", "text": "x"})[0] == "deny"


def test_the_collaboration_tools_appear_only_when_the_runtime_supplies_them(tmp_path):
    plain = build_registry(tmp_path, internet=False, max_bytes=LIMIT)
    assert "ask_owner" not in plain and "remember" not in plain
    wired = build_registry(tmp_path, internet=False, max_bytes=LIMIT,
                           ask=lambda question: {"asked": question},
                           remember=lambda role, text, sources: {"kept": text})
    assert wired["ask_owner"].effect == "coordinate"
    assert wired["remember"].effect == "note"


def test_every_offered_tool_has_a_json_schema_the_provider_can_read():
    tools = build_registry(None, internet=False, max_bytes=LIMIT)
    for name, subject in tools.items():
        body = subject.schema()
        assert body["type"] == "function" and body["function"]["name"] == name
        json.dumps(body)          # must survive the request body
