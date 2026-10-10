"""MCP inside the product: our list, the import, the transports and the policy.

Every transport test runs a **real** child process and a **real** HTTP server on
loopback, speaking the real protocol; no JSON-RPC reply is faked. The stub is only
the model, as everywhere else in this suite.

The rules under test, one at a time:

* the list is ours, read in the shapes other clients write, and their files are
  only ever read;
* a list this build cannot read is reported and never overwritten;
* a server that does not come up is a named failure, and no tool of it is offered;
* an MCP tool is an ordinary tool: same policy, same approval, same Action record;
* a call whose answer never came is UNCERTAIN, and it is not repeated.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chat_fakes import GraphStub, MemoryLinks, Model, csrf_of, isolate, make_app, post
from oneiro import agent, approvals, cli, config, mcp, mcp_surface
from oneiro.agent import default_registry, run_turn
from oneiro.chat import ModelReply, ToolCall
from oneiro.mcp_surface import call_tool
from oneiro.records import EffectOutcome, State
from oneiro.runtime import Runtime
from oneiro.tools import Policy

CLIENT = "mcp-test-0001"

#: A real MCP server: line-delimited JSON-RPC over stdio, as the ecosystem speaks.
FAKE_SERVER = r'''
import json, sys, time

TOOLS = [
    {"name": "echo", "description": "Repeat the text back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "slow", "description": "Answer after a long wait.",
     "inputSchema": {"type": "object", "properties": {}}},
]

def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "serverInfo": {"name": "fake", "version": "1"}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") == "slow":
            time.sleep(30)                     # the answer never comes in time
        text = (params.get("arguments") or {}).get("text", "")
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"content": [{"type": "text", "text": "echo: " + text}]}})
'''

DEAD_SERVER = r'''
import sys
sys.stderr.write("this server has no idea what it is\n")
raise SystemExit(3)
'''


class Remote(BaseHTTPRequestHandler):
    """A real remote MCP server: one POST per request, JSON or event stream back."""

    def do_POST(self) -> None:                       # noqa: N802 (http.server's spelling)
        length = int(self.headers.get("content-length") or 0)
        request = json.loads(self.rfile.read(length) or b"{}")
        method = request.get("method")
        if method == "notifications/initialized":
            self._answer(b"", "application/json", 202)
            return
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {},
                      "serverInfo": {"name": "remote-fake", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "shout", "description": "Say it louder.",
                                 "inputSchema": {"type": "object",
                                                 "properties": {"text": {"type": "string"}},
                                                 "required": ["text"]}}]}
        elif method == "tools/call":
            text = (request.get("params") or {}).get("arguments", {}).get("text", "")
            result = {"content": [{"type": "text", "text": text.upper()}]}
        else:
            self._answer(json.dumps({"jsonrpc": "2.0", "id": request.get("id"),
                                     "error": {"message": "no such method"}}).encode(), 400)
            return
        payload = json.dumps({"jsonrpc": "2.0", "id": request.get("id"),
                              "result": result}).encode("utf-8")
        if self.path.endswith("/sse"):
            # The event-stream spelling some servers answer with.
            self._answer(b"event: message\ndata: " + payload + b"\n\n", "text/event-stream")
        else:
            self._answer(payload, "application/json")

    def _answer(self, body: bytes, content_type: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Mcp-Session-Id", "remote-session-1")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        return None


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    # The hub is process-wide state. A fresh one per test keeps a dead session from
    # an earlier test from being read as an open server in this one.
    mcp.set_hub(None)
    try:
        yield
    finally:
        mcp.set_hub(None)


@pytest.fixture()
def servers(tmp_path: Path, monkeypatch) -> Path:
    """A real local server, a real dead one, and a real remote one on loopback."""
    (tmp_path / "fake_server.py").write_text(FAKE_SERVER, encoding="utf-8")
    (tmp_path / "dead_server.py").write_text(DEAD_SERVER, encoding="utf-8")
    remote = ThreadingHTTPServer(("127.0.0.1", 0), Remote)
    threading.Thread(target=remote.serve_forever, daemon=True).start()
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcp": {
        "fake": {"type": "local", "command": [sys.executable, str(tmp_path / "fake_server.py")],
                 "environment": {"FAKE_TOKEN": "yes"}, "enabled": True, "extra_key": "kept"},
        "dead": {"type": "local", "command": [sys.executable, str(tmp_path / "dead_server.py")]},
        "remote": {"type": "remote", "url": f"http://127.0.0.1:{remote.server_port}/mcp"},
        "sse": {"type": "remote", "url": f"http://127.0.0.1:{remote.server_port}/sse"},
    }}, indent=2), encoding="utf-8")
    monkeypatch.setenv("ONEIRO_MCP_FILE", str(path))
    try:
        yield path
    finally:
        remote.shutdown()


def owner_for(tmp_path, links) -> Runtime:
    return Runtime(graph=GraphStub(links, tmp_path / "graph-writer.lock"))


def actions(owner) -> list[dict]:
    page = asyncio.run(owner.memory_page(limit=500))
    return [row for row in page["items"] if row["kind"] == "action"]


def write_settings(tmp_path, values: dict) -> None:
    (tmp_path / "settings.json").write_text(json.dumps(values), encoding="utf-8")


# ---------- the list itself ----------


def test_the_list_is_read_in_the_open_dictionary(servers: Path):
    document = mcp.load()

    assert set(document.servers) == {"fake", "dead", "remote", "sse"}
    assert document.servers["fake"].command[1].endswith("fake_server.py")
    assert document.servers["fake"].environment == (("FAKE_TOKEN", "yes"),)
    assert document.servers["remote"].kind == mcp.REMOTE
    assert document.servers["fake"].extra["extra_key"] == "kept"


def test_the_older_shapes_are_read_too(tmp_path: Path):
    """`mcp.servers` and a bare `mcpServers` map are what other clients write."""
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"mcp": {"servers": {
        "a": {"command": "npx", "args": ["-y", "thing"], "env": {"K": "v"}}}}}), encoding="utf-8")
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"mcpServers": {
        "b": {"command": "python", "args": ["server.py"], "enabled": True}}}), encoding="utf-8")

    first, second = mcp.load(old), mcp.load(legacy)

    assert first.servers["a"].command == ("npx", "-y", "thing")
    assert first.servers["a"].environment == (("K", "v"),)
    assert second.servers["b"].command == ("python", "server.py")


def test_a_name_that_cannot_be_a_tool_name_is_refused(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcp": {"a.b": {"command": ["python"]},
                                        "good": {"command": ["python"]}}}), encoding="utf-8")

    document = mcp.load(path)

    assert set(document.servers) == {"good"}
    assert document.problems[0]["name"] == "a.b" and "dot" in document.problems[0]["reason"]


def test_saving_keeps_what_this_build_did_not_understand(servers: Path):
    document = mcp.load()

    document.save(changes={"fake": document.servers["fake"].with_enabled(False)})

    again = json.loads(servers.read_text(encoding="utf-8"))["mcp"]
    assert again["fake"]["enabled"] is False
    assert again["fake"]["extra_key"] == "kept"          # not dropped by a rewrite
    assert "dead" in again


def test_a_list_that_cannot_be_read_is_reported_and_not_overwritten(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text("{ this is not json", encoding="utf-8")

    document = mcp.load(path)

    assert document.error and document.servers == {}
    with pytest.raises(mcp.McpError):
        document.save()
    assert path.read_text(encoding="utf-8") == "{ this is not json"


def test_an_import_reads_the_other_clients_and_writes_only_ours(tmp_path: Path):
    client_file = tmp_path / "client-mcp.json"
    untouched = {"mcpServers": {"theirs": {"command": "npx", "args": ["-y", "theirs"]}}}
    client_file.write_text(json.dumps(untouched), encoding="utf-8")
    ours = tmp_path / "mcp.json"
    clients = [("OpenCode", client_file, "opencode"),
               ("Cursor", tmp_path / "nope.json", "mcpServers")]

    report = mcp.survey(clients)

    assert [row.client for row in report] == ["OpenCode", "Cursor"]
    assert report[0].found and report[0].servers[0].name == "theirs"
    assert report[1].found is False

    plan = mcp.preview(mcp.load(ours), report)
    assert set(plan["add"]) == {"theirs"}
    assert not ours.exists(), "a preview must write nothing"

    written = mcp.apply_import(mcp.load(ours), report)

    assert written["written"] == ["theirs"]
    assert json.loads(ours.read_text(encoding="utf-8"))["mcp"]["theirs"]["command"] == \
        ["npx", "-y", "theirs"]
    assert json.loads(client_file.read_text(encoding="utf-8")) == untouched


def test_an_import_never_overwrites_a_name_the_owner_already_has(tmp_path: Path):
    client_file = tmp_path / "client.json"
    client_file.write_text(json.dumps({"mcpServers": {
        "shared": {"command": "python", "args": ["theirs.py"]}}}), encoding="utf-8")
    ours = tmp_path / "mcp.json"
    ours.write_text(json.dumps({"mcp": {"shared": {"command": ["python", "ours.py"]}}}),
                    encoding="utf-8")

    plan = mcp.preview(mcp.load(ours), mcp.survey([("OpenCode", client_file, "opencode")]))

    assert plan["add"] == {} and plan["already"] == ["shared"]


def test_the_survey_names_the_clients_and_writes_nothing(tmp_path: Path):
    """The real survey of this machine, read-only."""
    report = mcp.survey()

    assert [row.client for row in report] == [label for label, _, _ in mcp.CLIENTS]
    for row in report:
        assert Path(row.path).is_absolute()
        assert row.to_dict()["found"] is bool(row.found)


# ---------- the transports, with real servers ----------


def test_a_local_server_opens_lists_and_calls(servers: Path):
    hub = mcp.hub()
    report = asyncio.run(hub.open("fake"))

    assert report["opened"] is True and report["tools"] == 2
    registry = hub.registry()
    assert set(registry) == {"fake.echo", "fake.slow"}
    assert registry["fake.echo"].effect == mcp.EFFECT
    assert registry["fake.echo"].required == ("text",)

    outcome = asyncio.run(hub.call("fake.echo", {"text": "hi"}))
    assert outcome["ok"] is True and outcome["state"] == "completed"
    assert outcome["text"] == "echo: hi"
    assert hub.catalogs["fake"] and hub.sessions["fake"].calls == 1     # type: ignore[attr-defined]

    hub.close()
    assert [row["state"] for row in hub.states() if row["name"] == "fake"] == ["closed"]


def test_a_remote_server_answers_over_http_and_over_an_event_stream(servers: Path):
    hub = mcp.hub()

    assert asyncio.run(hub.open("remote"))["opened"] is True
    assert asyncio.run(hub.open("sse"))["opened"] is True
    assert asyncio.run(hub.call("remote.shout", {"text": "quiet"}))["text"] == "QUIET"
    assert asyncio.run(hub.call("sse.shout", {"text": "quiet"}))["text"] == "QUIET"
    hub.close()


def test_a_dead_server_is_a_named_failure_and_the_others_still_open(servers: Path):
    hub = mcp.hub()

    reports = asyncio.run(hub.open_enabled())

    # In the order the list declares them, every enabled server was attempted.
    assert [row["name"] for row in reports] == ["fake", "dead", "remote", "sse"]
    assert [row["opened"] for row in reports] == [True, False, True, True]
    rows = {row["name"]: row for row in hub.states()}
    assert rows["dead"]["state"] == "failed" and "no idea" in rows["dead"]["failure"]
    assert rows["fake"]["state"] == "open" and rows["fake"]["tools"] == 2
    assert "dead.echo" not in hub.registry(), "a dead server offers no tools"
    assert asyncio.run(hub.call("fake.echo", {"text": "alive"}))["ok"] is True
    hub.close()


def test_a_tool_of_a_server_that_is_not_open_is_refused_by_name(servers: Path):
    outcome = asyncio.run(mcp.hub().call("fake.echo", {"text": "hi"}))

    assert outcome["ok"] is False and outcome["state"] == "failed"
    assert "not open in this process" in outcome["reason"]


def test_a_call_whose_answer_never_comes_is_uncertain(servers: Path):
    mcp.set_hub(mcp.Hub(request_timeout=1.0))
    hub = mcp.hub()
    assert asyncio.run(hub.open("fake"))["opened"] is True

    outcome = asyncio.run(hub.call("fake.slow", {}))

    assert outcome["state"] == "uncertain" and outcome["ok"] is False
    assert "did not answer within" in outcome["reason"] and "not repeated" in outcome["reason"]
    hub.close()


# ---------- the policy ----------


def test_the_declared_permission_decides_an_mcp_call(servers: Path):
    """`permissions.exec` is not a setting nobody reads."""
    mcp.set_hub(mcp.Hub())
    hub = mcp.hub()
    asyncio.run(hub.open("fake"))
    tool = hub.registry()["fake.echo"]

    write_settings(hub.document().path.parent, {"permissions.exec": "allow"})
    allowed = agent.default_policy().check(tool, "manager", {"text": "x"})
    write_settings(hub.document().path.parent, {"permissions.exec": "deny"})
    refused = agent.default_policy().check(tool, "manager", {"text": "x"})
    hub.close()

    assert allowed[0] == "allow", allowed
    assert refused[0] == "deny" and "refused by the configured permissions" in refused[1]
    assert Policy({}).check(tool, "manager", {"text": "x"})[0] == "ask"


def test_every_role_may_use_a_server_tool_and_a_role_boundary_still_holds(servers: Path):
    mcp.set_hub(mcp.Hub())
    hub = mcp.hub()
    asyncio.run(hub.open("fake"))
    tool = hub.registry()["fake.echo"]

    for role in ("manager", "researcher", "executor"):
        assert Policy({}).check(tool, role, {"text": "x"})[0] in ("allow", "ask")
    assert Policy({}).check(tool, "nobody", {"text": "x"})[0] == "deny"
    hub.close()


def test_the_mcp_settings_are_in_force_not_merely_declared():
    """Every MCP setting is either acted on by this build or visibly declared only.

    `mcp.source` is the retired harness's own list: nothing reads it any more, so
    it must say so on the page instead of looking like a working setting. The two
    that govern this build are in force and must not carry that sentence.
    """
    from oneiro import settings_registry

    rows = {setting.key: setting for setting in settings_registry.SETTINGS}

    assert rows["mcp.file"].pending is False
    assert rows["mcp.autostart"].pending is False
    assert rows["mcp.source"].pending is True


# ---------- through the agent ----------


def test_a_turn_is_offered_mcp_tools_only_while_a_server_is_open(servers: Path, tmp_path: Path):
    closed = default_registry(Runtime(), "main")
    assert not [name for name in closed if name.startswith(("fake.", "dead.", "remote."))]

    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))
    opened = default_registry(Runtime(), "main")

    assert "fake.echo" in opened
    assert "dead.echo" not in opened
    mcp.hub().close()


def test_an_mcp_call_needs_the_declared_permission_and_is_recorded(servers: Path, tmp_path: Path):
    """Row 6: a server tool call in the graph, under the same policy as any tool."""
    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))
    owner = owner_for(tmp_path, MemoryLinks())
    policy = Policy({"decisions": {"mcp_call": "ask"}})

    def asking(_messages, **_kwargs):
        return ModelReply("", (ToolCall("call-1", "fake.echo", {"text": "hi"}),))

    def answering(_messages, **_kwargs):
        return ModelReply("I asked the owner first.")

    first = asyncio.run(_turn_with(owner, "echo something", "turn-ask-0001", policy,
                                  [asking, answering]))

    assert first["steps"][0]["decision"] == "ask"
    assert first["steps"][0]["tool"] == "fake.echo"
    assert first["reply"]["text"] == "I asked the owner first."
    pending = asyncio.run(approvals.pending(owner))
    assert [row["tool"] for row in pending] == ["fake.echo"]
    assert [row["state"] for row in actions(owner)] == [State.WAITING.value]
    assert "echo: hi" not in json.dumps(actions(owner)), "nothing ran while waiting"

    # The owner's own grant releases exactly this call, and the call lands in the graph.
    asyncio.run(approvals.decide(owner, pending[0]["id"], granted=True))

    def again(_messages, **_kwargs):
        return ModelReply("", (ToolCall("call-1", "fake.echo", {"text": "hi"}),))

    def done(_messages, **_kwargs):
        return ModelReply("the server said echo: hi")

    second = asyncio.run(_turn_with(owner, "echo it again", "turn-grant-0001", policy,
                                   [again, done]))

    assert second["steps"][0]["decision"] == "allow"
    assert second["steps"][0]["ok"] is True
    assert "echo: hi" in second["steps"][0]["result"]
    assert "the server said echo: hi" == second["reply"]["text"]
    # The record says where the effect landed — the server — in the words the MCP
    # surface uses too, so a turn and a typed call read the same way.
    landed = [row["effect"]["target"] for row in actions(owner)
              if row["effect"]["kind"] == mcp.EFFECT and row["decision"] == "allow"]
    assert landed == ["fake"], "an mcp_call names the server it reached"
    # The store serves newest first, so the order here is the order they happened in.
    recorded = [(row["decision"], row["state"], row["effect"]["outcome"])
                for row in reversed(actions(owner)) if row["effect"]["kind"] == mcp.EFFECT]
    assert recorded == [("ask", State.WAITING.value, EffectOutcome.NONE.value),
                        ("allow", State.COMPLETED.value, EffectOutcome.SUCCEEDED.value)]
    assert asyncio.run(approvals.granted_for(owner, "fake.echo", {"text": "hi"})) is None, \
        "the grant was spent on the call it released"
    mcp.hub().close()


async def _turn_with(owner, text: str, client_id: str, policy: Policy, replies: list) -> dict:
    """One turn whose model answers from a script, so the path is the production one."""
    script = list(replies)

    def call(messages, **_kwargs):
        return script.pop(0)(messages)

    return await run_turn(owner, text, client_id, "main",
                          registry=default_registry(owner, "main"), policy=policy, call=call)


def test_a_tool_that_is_not_offered_is_named_and_the_conversation_goes_on(servers: Path,
                                                                        tmp_path: Path):
    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))
    owner = owner_for(tmp_path, MemoryLinks())

    def asking(_messages, **_kwargs):
        return ModelReply("", (ToolCall("call-1", "dead.echo", {"text": "hi"}),))

    def answering(_messages, **_kwargs):
        return ModelReply("that server is not part of this run, so I answered in words.")

    result = asyncio.run(_turn_with(owner, "ask the dead one", "turn-dead-0001",
                                   Policy({"decisions": {"mcp_call": "allow"}}),
                                   [asking, answering]))

    assert result["steps"][0]["decision"] == "deny"
    assert "no tool named dead.echo" in result["steps"][0]["reason"]
    assert result["reply"]["text"].startswith("that server is not part of this run")
    mcp.hub().close()


def test_a_call_that_may_have_happened_stops_the_turn_as_uncertain(servers: Path,
                                                                  tmp_path: Path):
    mcp.set_hub(mcp.Hub(request_timeout=1.0))
    asyncio.run(mcp.hub().open("fake"))
    owner = owner_for(tmp_path, MemoryLinks())
    asked = {"count": 0}

    def asking(_messages, **_kwargs):
        asked["count"] += 1
        return ModelReply("", (ToolCall("call-1", "fake.slow", {}),))

    result = asyncio.run(_turn_with(owner, "do the slow thing", "turn-slow-0001",
                                   Policy({"decisions": {"mcp_call": "allow"}}), [asking]))

    assert result["steps"][0]["state"] == State.UNCERTAIN.value
    assert result["steps"][0]["may_retry"] is False
    assert result["reply"]["state"] == State.UNCERTAIN.value
    assert asked["count"] == 1, "the turn asked the model again after an unknown outcome"
    assert [row["effect"]["outcome"] for row in actions(owner)] == \
        [EffectOutcome.UNCERTAIN.value]
    mcp.hub().close()


# ---------- the HTTP surface ----------


def test_the_http_surface_lists_sources_opens_tools_and_calls(servers: Path, tmp_path: Path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        csrf = csrf_of(client)

        listing = client.get("/api/mcp").json()
        assert listing["file"].endswith("mcp.json")
        assert [row["name"] for row in listing["servers"]] == ["dead", "fake", "remote", "sse"]
        assert {row["state"] for row in listing["servers"]} == {"closed"}
        assert listing["autostart"] is True
        assert listing["nothing_declared"] is False
        assert {row["client"] for row in listing["sources"]} == {row[0] for row in mcp.CLIENTS}

        assert post(client, "/api/mcp", {}, csrf).status_code in (404, 405)

        opened = post(client, "/api/mcp/fake/open", {}, csrf)
        assert opened.status_code == 200 and opened.json()["tools"] == 2

        tools = client.get("/api/mcp/fake/tools").json()
        assert {row["key"] for row in tools["tools"]} == {"fake.echo", "fake.slow"}

        broken = post(client, "/api/mcp/dead/open", {}, csrf)
        assert broken.status_code == 503 and "no idea" in broken.json()["reason"]

        called = post(client, "/api/mcp/fake/call",
                      {"tool": "echo", "arguments": {"text": "over http"}}, csrf)
        assert called.status_code == 200, called.text
        assert called.json()["text"] == "echo: over http"
        assert called.json()["may_retry"] is False
        assert called.json()["recorded"] is True

        refused = post(client, "/api/mcp/dead/call", {"tool": "echo", "arguments": {}}, csrf)
        assert refused.status_code == 403 and refused.json()["decision"] == "deny"

        assert client.get("/api/mcp/nowhere/tools").status_code == 404
        assert post(client, "/api/mcp/nowhere/open", {}, csrf).status_code == 404
        assert post(client, "/api/mcp/fake/call", {"arguments": {}}, csrf).status_code == 400
        assert post(client, "/api/mcp/fake/call", {"tool": "echo", "arguments": []},
                    csrf).status_code == 400
        assert client.post("/api/mcp/fake/call",
                           json={"tool": "echo"}).status_code == 403      # no token


def test_the_http_surface_imports_enables_and_disables(servers: Path, tmp_path: Path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        csrf = csrf_of(client)

        plan = post(client, "/api/mcp/import", {}, csrf).json()
        assert plan["written"] == [] and plan["already"] == []

        assert post(client, "/api/mcp/sse/disable", {}, csrf).json()["enabled"] is False
        assert {row["name"]: row["state"] for row in client.get("/api/mcp").json()["servers"]}[
            "sse"] == "disabled"
        assert post(client, "/api/mcp/sse/enable", {}, csrf).json()["enabled"] is True
        assert post(client, "/api/mcp/nowhere/enable", {}, csrf).status_code == 404


def test_turning_a_server_off_stops_its_tools_right_away(servers: Path, tmp_path: Path):
    """Disabling is a switch, not a note for the next launch.

    An open server whose tools stayed on offer after the owner turned it off would
    be the wiring lying about a capability: the next turn could still call it. Off
    means the session is let go and nothing is offered; on means the entry is on
    again and the server opens when it is asked to.
    """
    write_settings(tmp_path, {"mcp.autostart": False})
    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))
    assert "fake.echo" in mcp.registry() and "fake" in mcp.hub().sessions

    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        csrf = csrf_of(client)
        off = post(client, "/api/mcp/fake/disable", {}, csrf).json()
        assert off["enabled"] is False and off["closed"] is True
        assert "fake.echo" not in mcp.registry(), "an off server must offer nothing"
        assert "fake" not in mcp.hub().sessions
        row = {item["name"]: item for item in client.get("/api/mcp").json()["servers"]}["fake"]
        assert row["state"] == "disabled" and row["open"] is False and row["tools"] == 0
        # No surface starts a server the owner turned off, and the refusal says so.
        assert asyncio.run(mcp.hub().open("fake"))["opened"] is False
        refused = client.get("/api/mcp/fake/tools")
        assert refused.status_code == 503 and "turned off" in refused.json()["reason"]
        assert "fake" not in mcp.hub().sessions and "fake" not in mcp.hub().failures

        on = post(client, "/api/mcp/fake/enable", {}, csrf).json()
        assert on["enabled"] is True and on["closed"] is False
        row = {item["name"]: item for item in client.get("/api/mcp").json()["servers"]}["fake"]
        assert row["state"] == "closed", "on and not open yet is what the file says"
    mcp.hub().close()


def test_a_declared_refusal_refuses_a_call_from_the_surface_and_records_it(servers: Path,
                                                                         tmp_path: Path):
    write_settings(tmp_path, {"permissions.exec": "deny"})
    owner = owner_for(tmp_path, MemoryLinks())
    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))

    result = asyncio.run(call_tool(owner, "fake.echo", {"text": "hi"}, client_id=CLIENT))

    assert result["decision"] == "deny" and result["ok"] is False
    assert "refused by the configured permissions" in result["reason"]
    recorded = actions(owner)
    assert [row["decision"] for row in recorded] == ["deny"]
    assert [row["state"] for row in recorded] == [State.FAILED.value]
    mcp.hub().close()


def test_the_record_is_written_before_the_call_so_an_unrecordable_call_does_not_run(
        servers: Path, tmp_path: Path):
    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))

    class Broken(Runtime):
        async def publish(self, record, operation_id, *, expected_revision: int = 0):
            raise RuntimeError("the memory is not there")

    owner = Broken(graph=GraphStub(MemoryLinks(), tmp_path / "graph-writer.lock"))

    result = asyncio.run(call_tool(owner, "fake.echo", {"text": "hi"}, client_id=CLIENT))

    assert result["decision"] == "deny" and result["recorded"] is False
    assert "the call was not made" in result["reason"] and "RuntimeError" in result["reason"]
    mcp.hub().close()


def test_autostart_off_leaves_the_servers_closed_and_on_opens_them(servers: Path, tmp_path: Path):
    """`mcp.autostart` is what starts the enabled servers with the process."""
    write_settings(tmp_path, {"mcp.autostart": False})
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        time.sleep(0.3)
        assert mcp.hub().sessions == {}
        assert client.get("/api/mcp").json()["autostart"] is False

    write_settings(tmp_path, {"mcp.autostart": True})
    mcp.set_hub(None)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and len(mcp.hub().sessions) < 3:
            time.sleep(0.2)
        assert "fake" in mcp.hub().sessions and "remote" in mcp.hub().sessions
        assert "dead" not in mcp.hub().sessions
        assert client.get("/api/mcp").json()["autostart"] is True


# ---------- the command line ----------


def test_the_command_line_reads_opens_and_calls(tmp_path: Path, monkeypatch, capsys,
                                               servers: Path):
    links = MemoryLinks()
    monkeypatch.setattr(mcp_surface, "Runtime", lambda: owner_for(tmp_path, links))

    assert cli.main(["mcp", "list"]) == 0
    listed = capsys.readouterr().out
    assert "fake" in listed and "remote" in listed and "autostart: on" in listed

    assert cli.main(["mcp", "sources"]) == 0
    assert "OpenCode" in capsys.readouterr().out

    assert cli.main(["mcp", "import"]) == 0
    assert "nothing was written" in capsys.readouterr().out
    # A write has to name what it takes; taking everything is its own flag.
    assert cli.main(["mcp", "import", "--write"]) == 2
    assert "--only" in capsys.readouterr().out
    assert cli.main(["mcp", "import", "--write", "--only", "fake"]) == 0
    assert "nothing new to add" in capsys.readouterr().out

    assert cli.main(["mcp", "open", "fake"]) == 0
    assert "open with 2 tool(s)" in capsys.readouterr().out

    assert cli.main(["mcp", "tools", "fake"]) == 0
    assert "fake.echo" in capsys.readouterr().out

    assert cli.main(["mcp", "open", "dead"]) == 1
    assert "did not come up" in capsys.readouterr().out

    assert cli.main(["mcp", "tools", "nowhere"]) == 2
    assert "no server named nowhere" in capsys.readouterr().out

    assert cli.main(["mcp", "disable", "sse"]) == 0
    assert "sse: disabled" in capsys.readouterr().out
    assert cli.main(["mcp", "enable", "sse"]) == 0
    assert "sse: enabled" in capsys.readouterr().out
    assert cli.main(["mcp", "disable", "nowhere"]) == 2
    assert "no server named nowhere" in capsys.readouterr().out

    assert cli.main(["mcp", "call", "fake.echo", '{"text": "from the terminal"}']) == 0
    called = capsys.readouterr().out
    assert "echo: from the terminal" in called and "recorded as act-" in called
    # One call, one record: the newest revision of that record says what happened.
    recorded = actions(owner_for(tmp_path, links))
    assert {row["id"] for row in recorded} == {recorded[0]["id"]}
    assert recorded[0]["tool"] == "fake.echo"
    assert recorded[0]["state"] == State.COMPLETED.value
    assert recorded[0]["provenance"] == "verified_tool_outcome"

    assert cli.main(["mcp", "call", "fake.echo", "not json"]) == 2
    assert "must be a JSON object" in capsys.readouterr().out
    assert cli.main(["mcp", "call"]) == 2
    assert "server.tool" in capsys.readouterr().out

    assert cli.main(["mcp", "call", "fake.echo", '{"text": "x"}', "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["server"] == "fake"


def test_the_command_line_does_not_call_when_the_record_cannot_be_written(
        tmp_path: Path, monkeypatch, capsys, servers: Path):
    class Broken(Runtime):
        async def publish(self, record, operation_id, *, expected_revision: int = 0):
            raise RuntimeError("the memory is not there")

    mcp.set_hub(mcp.Hub())
    asyncio.run(mcp.hub().open("fake"))
    monkeypatch.setattr(mcp_surface, "Runtime",
                        lambda: Broken(graph=GraphStub(MemoryLinks(),
                                                       tmp_path / "graph-writer.lock")))

    assert cli.main(["mcp", "call", "fake.echo", '{"text": "hi"}']) == 1
    said = capsys.readouterr().out
    assert "the call was not made" in said and "RuntimeError" in said
    mcp.hub().close()


def test_the_page_marks_as_inactive_exactly_what_is_inactive(tmp_path: Path):
    """The page says "not in this build yet" once per setting that is declared only.

    Counting them is what keeps the sentence honest in both directions: the MCP
    settings are in force now, so they must not carry it, and everything still
    waiting for its package must.
    """
    from oneiro import pages

    description = config.describe()
    markup = pages.render("settings", description, error="", facts=None)

    declared_only = [row["key"] for row in description["settings"] if row["pending"]]
    assert markup.count("Declared here; the part of Oneiro that") == len(declared_only)
    assert "mcp.file" not in declared_only and "mcp.autostart" not in declared_only
