"""Live check for W2: MCP inside the product, exercised the way it is used.

Run it with `python tests/live_w2_check.py`. It is not a unit test — it is the
end-to-end evidence the plan asks for, reached through the surfaces the product
actually exposes:

* a **real local MCP server** as a child process of the product, speaking real
  line-delimited JSON-RPC over stdio, which writes down every call it receives —
  so the proof that the call arrived comes from the other side of the pipe, not
  from our own bookkeeping;
* a **real remote MCP server** on loopback, reached over HTTP JSON-RPC, which
  records what it was asked and which session header it was given;
* the product's own list in `mcp.file`, written by hand in the OpenCode
  dictionary (`mcp.<name>` with `type`/`command`/`url`/`enabled`/`environment`),
  with one deliberately broken server in it;
* the **agent turn**: the stub model asks for `localdemo.echo` and the call is
  decided by the same `Policy`, recorded in the same graph and answered to the
  model as any built-in tool call would be;
* the **same call under `permissions.exec=ask`**: it does not run, a pending
  approval appears in the records, the owner's own grant releases exactly that
  one call, and a repeat asks again;
* a **broken server named and bounded**: it is a failure with its own stderr
  text, it never holds a turn, and its tools are never offered to the model.

The two stubs are the model provider and the graph: a loopback HTTP provider for
the chat-completions shape, and the RecordStore over an in-memory link graph with
the worker's exact result shapes. The owner's settings, data root, memory graph
and MCP lists are not read or written except where reading is the point: the
other clients' configs are surveyed read-only and their bytes are compared
before and after.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w2-live-"))
LOCAL_LOG = WORK / "local_server_received.jsonl"
DEMO_TOKEN = "demo-" + hashlib.sha256(str(WORK).encode("utf-8")).hexdigest()[:12]
MCP_FILE = WORK / "mcp.json"
IMPORT_FILE = WORK / "imported-by-hand.json"
BROKEN_NOTE = "no credentials for the demo service"

LOCAL_SERVER = r'''
import json, os, sys

LOG = os.environ.get("DEMO_LOG", "")
TOOLS = [
    {"name": "echo", "description": "Repeat the text back as this server heard it.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "whoami", "description": "Say which process answered.",
     "inputSchema": {"type": "object", "properties": {}}},
]

def note(entry):
    if not LOG:
        return
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")

def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()

note({"event": "started", "pid": os.getpid(), "cwd": os.getcwd(),
      "demo_token": os.environ.get("DEMO_TOKEN", "")})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "serverInfo": {"name": "local-demo", "version": "1"}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name"))
        arguments = params.get("arguments") or {}
        note({"event": "call", "pid": os.getpid(), "tool": name, "arguments": arguments})
        if name == "whoami":
            text = "local-demo on pid %d" % os.getpid()
        else:
            text = "echo: " + str(arguments.get("text", ""))
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"content": [{"type": "text", "text": text}]}})
'''

BROKEN_SERVER = r'''
import sys
sys.stderr.write("''' + BROKEN_NOTE + r'''\n")
raise SystemExit(3)
'''


class RemoteMcp(BaseHTTPRequestHandler):
    """A real MCP server over HTTP: one POST per request, JSON back."""

    received: list[dict] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        message = json.loads(self.rfile.read(length) or b"{}")
        method = str(message.get("method") or "")
        params = message.get("params") or {}
        RemoteMcp.received.append({
            "method": method, "params": params,
            "accept": self.headers.get("Accept", ""),
            "session": self.headers.get("Mcp-Session-Id", "")})
        session = ""
        if method == "initialize":
            result: dict = {"protocolVersion": "2024-11-05", "capabilities": {},
                            "serverInfo": {"name": "remote-demo", "version": "1"}}
            session = "demo-session-1"
        elif method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        elif method == "tools/list":
            result = {"tools": [{"name": "echo", "description": "Echo over HTTP.",
                                 "inputSchema": {"type": "object", "properties": {
                                     "text": {"type": "string"}}, "required": ["text"]}}]}
        elif method == "tools/call":
            text = (params.get("arguments") or {}).get("text", "")
            result = {"content": [{"type": "text", "text": "remote echo: " + str(text)}]}
        else:
            result = {}
        payload = json.dumps({"jsonrpc": "2.0", "id": message.get("id"),
                              "result": result}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: object) -> None:
        return None


class Provider(BaseHTTPRequestHandler):
    """The stub model: it asks for an MCP tool, then answers with the result."""

    offered: list[list[str]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages") or []
        offered = [str(tool["function"]["name"]) for tool in (body.get("tools") or [])]
        Provider.offered.append(offered)
        results = [str(item.get("content") or "") for item in messages
                   if item.get("role") == "tool"]
        asked = ""
        for item in reversed(messages):
            if item.get("role") == "user":
                asked = str(item.get("content") or "")
                break
        if results:
            message: dict = {"role": "assistant",
                             "content": "the server said: " + results[-1]}
        else:
            if "broken" in asked:
                name, arguments = "broken.echo", {"text": asked}
            elif "remote" in asked:
                name, arguments = "remotedemo.echo", {"text": asked}
            else:
                name, arguments = "localdemo.echo", {"text": asked}
            message = {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call-1", "type": "function",
                 "function": {"name": name, "arguments": json.dumps(arguments)}}]}
        payload = json.dumps({"choices": [{"message": message}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: object) -> None:
        return None


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Browser:
    """Real HTTP with the token the page sends, exactly as the console does."""

    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.token = self.get("/api/session")["csrf"]

    def _open(self, request: urllib.request.Request) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:      # a refusal is an answer too
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"error": raw[:200]}

    def get(self, path: str) -> dict:
        request = urllib.request.Request(self.base + path)
        _status, body = self._open(request)
        return body

    def status_get(self, path: str) -> tuple[int, dict]:
        return self._open(urllib.request.Request(self.base + path))

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Oneiro-CSRF": self.token},
            method="POST")
        return self._open(request)


def say(line: str = "") -> None:
    print(line, flush=True)


def fingerprints(paths: list[Path]) -> dict[str, str]:
    """What every other client's config looks like right now."""
    prints: dict[str, str] = {}
    for path in paths:
        if path.is_file():
            prints[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        else:
            prints[str(path)] = "(no such file)"
    return prints


def records(browser: Browser, limit: int = 500) -> list[dict]:
    """Every stored revision the application will show, newest first."""
    return browser.get(f"/api/memory/records?limit={limit}")["items"]


def main() -> int:
    (WORK / "mcp_local_demo.py").write_text(LOCAL_SERVER, encoding="utf-8")
    (WORK / "mcp_broken_demo.py").write_text(BROKEN_SERVER, encoding="utf-8")

    # The two stubs that stand in for real things outside this check: the model
    # provider, and the memory graph (the real RecordStore over an in-memory link
    # graph, in the worker's exact result shapes).
    remote = ThreadingHTTPServer(("127.0.0.1", 0), RemoteMcp)
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=remote.serve_forever, daemon=True).start()
    threading.Thread(target=provider.serve_forever, daemon=True).start()

    # Nothing of the owner's is touched: settings, data root, keys and the MCP
    # list all live in the temporary folder.
    os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
    os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "no-keys.env")
    os.environ["ONEIRO_MCP_FILE"] = str(MCP_FILE)
    os.environ["ONEIRO_MCP_AUTOSTART"] = "true"
    os.environ["ONEIRO_LLM_BASE_URL"] = f"http://127.0.0.1:{provider.server_port}/v1"
    os.environ["ONEIRO_LLM_API_KEY"] = "live-check-key"
    os.environ["ONEIRO_LLM_MODEL"] = "stub/live-check"
    os.environ["ONEIRO_UI_LANGUAGE"] = "en"

    import uvicorn                                                  # noqa: E402
    from chat_fakes import GraphStub, MemoryLinks                   # noqa: E402
    from oneiro import approvals, config, mcp, web                  # noqa: E402
    from oneiro.records import State                                # noqa: E402
    from oneiro.runtime import Runtime                              # noqa: E402

    # The product's own list, written by hand in the dictionary other clients use.
    MCP_FILE.write_text(json.dumps({
        "mcp": {
            "localdemo": {"type": "local",
                          "command": [sys.executable, str(WORK / "mcp_local_demo.py")],
                          "enabled": True,
                          "environment": {"DEMO_LOG": str(LOCAL_LOG),
                                          "DEMO_TOKEN": DEMO_TOKEN}},
            "remotedemo": {"type": "remote",
                           "url": f"http://127.0.0.1:{remote.server_port}/mcp",
                           "enabled": True},
            "broken": {"type": "local",
                       "command": [sys.executable, str(WORK / "mcp_broken_demo.py")],
                       "enabled": True},
            "offdemo": {"type": "local",
                        "command": [sys.executable, str(WORK / "mcp_local_demo.py")],
                        "enabled": False},
        }
    }, indent=2) + "\n", encoding="utf-8")

    client_paths = [Path(path) for _label, path, _shape in mcp.CLIENTS]
    before = fingerprints(client_paths)

    links = MemoryLinks()
    stub = GraphStub(links, WORK / "graph-writer.lock")
    runtime = Runtime(graph=stub)
    app = web.create_app(runtime=runtime, scheduler=False)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           access_log=False, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    browser: Browser | None = None
    for _ in range(100):
        try:
            browser = Browser(port)
            break
        except OSError:
            time.sleep(0.1)
    if browser is None:
        say("the application never answered on its port")
        return 1

    say(f"Oneiro on http://127.0.0.1:{port} (temporary root {WORK})")
    say(f"stub provider on http://127.0.0.1:{provider.server_port}/v1, "
        f"remote MCP server on http://127.0.0.1:{remote.server_port}/mcp")
    say(f"the product's own list: {MCP_FILE}")
    say()

    say("== the servers, as the application opened them at launch (mcp.autostart) ==")
    deadline = time.monotonic() + 60
    seen: dict = {}
    while time.monotonic() < deadline:
        seen = browser.get("/api/mcp")
        states = {row["name"]: row["state"] for row in seen["servers"]}
        if (states.get("localdemo") == "open" and states.get("remotedemo") == "open"
                and states.get("broken") == "failed"):
            break
        time.sleep(0.5)
    say(f"file {seen['file']}, autostart {seen['autostart']}, "
        f"nothing declared: {seen['nothing_declared']}")
    for row in seen["servers"]:
        say(f"  {row['name']:<12} {row['kind']:<7} {'on' if row['enabled'] else 'off':<4} "
            f"{row['state']:<9} {row['tools']:>2} tool(s)  {row['source']}")
        if row["failure"]:
            say(f"      why: {row['failure']}")
    for problem in seen["problems"]:
        say(f"  could not read {problem['name']}: {problem['reason']}")
    say()
    if {row["name"]: row["state"] for row in seen["servers"]}.get("localdemo") != "open":
        say("the local demo server never opened; the rest of the check will say so as well")
    say()

    say("== what the other clients on this machine declare (read only) ==")
    for report in seen["sources"]:
        if not report["found"]:
            say(f"  {report['client']:<16} {report['path']}  (no such file here)")
            continue
        declared = ", ".join(f"{row['name']} ({row['kind']})" for row in report["servers"])
        say(f"  {report['client']:<16} {report['path']}")
        say(f"      declares: {declared or 'nothing'}"
            + (f"  {report['error']}" if report["error"] else ""))
    say()

    say("== the tools one server offers, over the HTTP surface ==")
    status, found = browser.status_get("/api/mcp/localdemo/tools")
    say(f"  GET /api/mcp/localdemo/tools -> {status}, declared={found.get('declared')}, "
        f"opened={found.get('opened')}")
    for row in found.get("tools") or []:
        required = (row["schema"] or {}).get("required") or []
        say(f"    {row['key']}  required={required}  {row['description']}")
    status, missing = browser.status_get("/api/mcp/nowhere/tools")
    say(f"  GET /api/mcp/nowhere/tools -> {status} {missing.get('error')}")
    say()

    say("== a call typed by the owner, over the HTTP surface ==")
    status, called = browser.post("/api/mcp/localdemo/call", {
        "tool": "whoami", "arguments": {},
        "client_id": "live-w2-owner-call-0001"})
    say(f"  POST /api/mcp/localdemo/call -> {status}")
    say(f"    decision {called['decision']}, outcome {called['outcome']}, text {called['text']!r}")
    say(f"    recorded as {called['action_id']}, may_retry {called['may_retry']}")
    say()

    say("== the settings that govern this, as the settings layer reports them ==")
    described = {row["key"]: row for row in browser.get("/api/settings")["settings"]}
    for key in ("mcp.file", "mcp.autostart", "permissions.exec"):
        row = described[key]
        say(f"  {key} = {row['value']!r}  (from {row['source']}, pending={row.get('pending')})")
    say()

    say("== an agent turn that calls a local MCP tool (permissions.exec=allow) ==")
    browser.post("/api/settings", {"permissions.exec": "allow"})
    turn = browser.post("/api/message", {
        "text": "Please ask the local demo server to echo this line back to me.",
        "client_id": "live-w2-agent-local-0001"})[1]
    say(f"  reply {turn['reply']['id']}: {turn['reply']['text']!r}")
    for step in turn["steps"]:
        say(f"    step {step['index']} {step['tool']}: {step['decision']} -> {step['state']} "
            f"({step['effect']}/{step['outcome']}), recorded as {step['action_id']}")
    say(f"  the model was offered {len(Provider.offered[-1])} tools, among them: "
        + ", ".join(sorted(name for name in Provider.offered[-1] if "." in name)))
    say()

    say("== the same turn's record, read back from the graph ==")
    stored = records(browser)
    mcp_actions = [row for row in stored if row["kind"] == "action"
                   and str(row.get("tool", "")).startswith("localdemo.")]
    for row in sorted(mcp_actions, key=lambda item: item["__sequence__"]):
        effect = row.get("effect") or {}
        say(f"  {row['id']}  {row['tool']}  decision {row['decision']}  "
            f"effect {effect.get('kind')} on {effect.get('target')} -> {effect.get('outcome')}")
        say(f"    state {row['state']}, from {row['provenance']}, labels {row['labels']}")
        say(f"    result {str(row['result'])[:160]!r}")
    say()

    say("== what the child process itself recorded receiving ==")
    if LOCAL_LOG.is_file():
        for line in LOCAL_LOG.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry["event"] == "started":
                say(f"  started pid {entry['pid']}, demo_token "
                    f"{'matches the one in our list' if entry['demo_token'] == DEMO_TOKEN else 'DIFFERENT'}")
            else:
                say(f"  received {entry['tool']} with {entry['arguments']} on pid {entry['pid']}")
    else:
        say("  the local server wrote nothing down")
    say()

    say("== an agent turn that calls the remote MCP server ==")
    turn = browser.post("/api/message", {
        "text": "Now ask the remote demo server to echo this instead.",
        "client_id": "live-w2-agent-remote-0001"})[1]
    say(f"  reply {turn['reply']['id']}: {turn['reply']['text']!r}")
    for step in turn["steps"]:
        say(f"    step {step['index']} {step['tool']}: {step['decision']} -> {step['state']} "
            f"({step['outcome']})")
    for entry in RemoteMcp.received:
        detail = ""
        if entry["method"] == "tools/call":
            detail = f" name={(entry['params'] or {}).get('name')} " \
                     f"arguments={(entry['params'] or {}).get('arguments')}"
        say(f"  the remote server was asked {entry['method']}{detail}"
            + (f"  [session {entry['session']}]" if entry["session"] else ""))
    say()

    say("== a broken server: named, bounded, and never a tool the model is offered ==")
    status, refused = browser.status_get("/api/mcp/broken/tools")
    say(f"  GET /api/mcp/broken/tools -> {status}: {refused.get('reason')}")
    status, opened = browser.post("/api/mcp/broken/open", {})
    say(f"  POST /api/mcp/broken/open -> {status}: {opened.get('reason')}")
    asked = time.monotonic()
    turn = browser.post("/api/message", {
        "text": "Ask the broken demo server to echo something, please.",
        "client_id": "live-w2-agent-broken-0001"})[1]
    say(f"  the turn still answered in {time.monotonic() - asked:.2f}s: "
        f"{turn['reply']['text']!r}")
    for step in turn["steps"]:
        say(f"    step {step['index']} {step['tool']}: {step['decision']} -> {step['state']} "
            f"— {step['reason']}")
    say(f"  the model was offered {len(Provider.offered[-1])} tools, and none of them is the "
        f"broken server's: "
        + ("no tool with a dot from it" if not any(
            name.startswith("broken.") for name in Provider.offered[-1]) else "SOMETHING WENT WRONG"))
    say()

    say("== switching a server off and on, through the surface ==")
    row_of = lambda: {item["name"]: item for item in browser.get("/api/mcp")["servers"]}
    status, off = browser.post("/api/mcp/localdemo/disable", {})
    row = row_of()["localdemo"]
    say(f"  POST /api/mcp/localdemo/disable -> {status}: enabled={off.get('enabled')} "
        f"state={row['state']} open={row['open']} tools={row['tools']} "
        f"(session let go: {off.get('closed')})")
    status, gone = browser.status_get("/api/mcp/localdemo/tools")
    say(f"  GET /api/mcp/localdemo/tools -> {status}: {gone.get('reason')}")
    status, switched_on = browser.post("/api/mcp/localdemo/enable", {})
    row = row_of()["localdemo"]
    say(f"  POST /api/mcp/localdemo/enable -> {status}: enabled={row['enabled']} "
        f"state={row['state']} (it opens when asked, not by itself)")
    browser.post("/api/mcp/localdemo/open", {})
    status, back = browser.status_get("/api/mcp/localdemo/tools")
    say(f"  GET /api/mcp/localdemo/tools -> {status}, open again with "
        f"{sorted(item['key'] for item in back.get('tools') or [])}")
    status, again_call = browser.post("/api/mcp/localdemo/call", {
        "tool": "whoami", "arguments": {}, "client_id": "live-w2-owner-call-0002"})
    say(f"  the first call was answered by {called['text']!r}")
    say(f"  a call after the switch answered {again_call['text']!r} — the process that served "
        f"the first one was really let go")
    say()

    say("== the same call under permissions.exec=ask: the owner decides ==")
    browser.post("/api/settings", {"permissions.exec": "ask"})
    text = "Echo this exact line through the local demo server, if you may."
    first = browser.post("/api/message", {"text": text,
                                          "client_id": "live-w2-agent-ask-0001"})[1]
    say(f"  reply: {first['reply']['text']!r}")
    for step in first["steps"]:
        say(f"    step {step['index']} {step['tool']}: {step['decision']} -> {step['state']} "
            f"— {step['reason']}")
    pending = [row for row in records(browser)
               if row["kind"] == "approval" and row.get("state") == State.WAITING.value]
    say(f"  proposals waiting for the owner: {len(pending)}")
    for row in pending:
        say(f"    {row['id']}  tool {row['tool']}  digest {row['arguments_digest'][:16]}  "
            f"state {row['state']}")
    if not pending:
        say("  nothing was waiting, so the grant path below cannot be shown")
        server.should_exit = True
        remote.shutdown()
        provider.shutdown()
        return 1

    say("  the owner grants exactly that call (the same call the console card will make):")
    decided = asyncio.run(approvals.decide(runtime, pending[0]["id"], granted=True,
                                           actor="owner", reason="the live check's owner"))
    say(f"    {decided['id']}: granted={decided['granted']} state={decided['state']} "
        f"from {decided['provenance']}")
    again = browser.post("/api/message", {"text": text,
                                          "client_id": "live-w2-agent-grant-0001"})[1]
    say(f"  the repeated turn ran it: {again['reply']['text']!r}")
    for step in again["steps"]:
        say(f"    step {step['index']} {step['tool']}: {step['decision']} -> {step['state']} "
            f"({step['outcome']}), recorded as {step['action_id']}")
    once_more = browser.post("/api/message", {"text": text,
                                              "client_id": "live-w2-agent-second-0001"})[1]
    say(f"  and a third identical turn asks again: {once_more['reply']['text']!r}")
    for step in once_more["steps"]:
        say(f"    step {step['index']} {step['tool']}: {step['decision']} -> {step['state']} "
            f"— {step['reason']}")
    spent = [row for row in records(browser) if row["kind"] == "approval"
             and row.get("consumed_action_id")]
    say(f"  grants spent on exactly one call: "
        + ", ".join(f"{row['id']} -> {row['consumed_action_id']}" for row in spent))
    say()

    say("== the command line, as its own process against the same list ==")
    environment = {**os.environ, "PYTHONPATH": str(PROJECT / "python"),
                   "ONEIRO_MCP_FILE": str(MCP_FILE)}

    def cli(*argv: str, mcp_file: Path | None = None) -> int:
        env = {**environment}
        if mcp_file is not None:
            env["ONEIRO_MCP_FILE"] = str(mcp_file)
        finished = subprocess.run([sys.executable, "-m", "oneiro", *argv], env=env,
                                  capture_output=True, text=True, timeout=180)
        say(f"  $ oneiro {' '.join(argv)}   (exit {finished.returncode})")
        for line in (finished.stdout or finished.stderr).splitlines():
            say(f"      {line}")
        return finished.returncode

    cli("mcp", "list")
    cli("mcp", "tools", "localdemo")
    declared: list[str] = []
    for report in seen["sources"]:
        declared.extend(row["name"] for row in report["servers"])
    if declared:
        cli("mcp", "import", "--write", "--only", *declared[:2], mcp_file=IMPORT_FILE)
        imported = json.loads(IMPORT_FILE.read_text(encoding="utf-8"))
        say(f"  our file after the import holds: "
            f"{sorted((imported.get('mcp') or {}).keys())}")
    else:
        say("  this machine declares no servers in the other clients, so the import has "
            "nothing to take; it is shown in preview only")
        cli("mcp", "import", mcp_file=IMPORT_FILE)
    # `oneiro mcp call` records the call, so it needs the memory graph; pointing it
    # at the owner's live graph is exactly what this check must not do. The calling
    # path of the command line is covered against a substitute runtime in
    # tests/test_mcp.py instead.
    say("  (the call subcommand itself is left to the tests: it opens the memory graph)")
    say()

    say("== nothing of anyone else's was written ==")
    after = fingerprints(client_paths)
    for path in sorted(before):
        say(f"  {path}: {'unchanged' if before[path] == after[path] else 'CHANGED'}"
            f"  ({before[path]})")
    say(f"  our own list is the only file the product wrote: {MCP_FILE}")
    say()

    say("== the memory this check used ==")
    say(f"  temporary root:  {WORK}")
    say(f"  graph records:   {len(stub.store.page(limit=500).items)} stored revisions")
    say(f"  the owner's settings and data root were never touched "
        f"(settings file: {config.describe()['path']})")
    say()

    mcp.hub().close()
    server.should_exit = True
    time.sleep(0.5)
    remote.shutdown()
    provider.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
