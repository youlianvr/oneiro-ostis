"""Live check for W3: mail in, a draft out, and the press that alone lets it go.

Run it with `python tests/live_drafts_check.py`. It is not a unit test; it is the
evidence § 6 W3 asks for, exercised the way the product is used:

* a real console process on a free port with its own data root, its own settings, its own
  MCP list and its **own graph**, stopped at the end with its exit code read from the
  process. The graph is a container of this check's own (`docker run` from the shipped
  image, its own volume, a free host port): the demo writes a subject of experience nobody
  shares, and the owner's running graph is only ever read — its `product` stream is
  fingerprinted before and after. `--graph-port N` uses a graph that is already running
  instead, and then starts and stops nothing;
* a real mailbox and a real bot behind the product's own MCP transport: a child process
  speaking line-delimited JSON-RPC over stdio, which writes down **every call that
  arrived**. That log is the measurement the whole check rests on;

  **without the owner's press, no send reaches the mailbox at all** — and the check reads
  the log at every step, so the transcript shows the count standing still at zero while a
  draft is written, read, edited, refused and discarded, and moving by exactly one at the
  press;
* real HTTP on the console's drafts, mail and telegram routes, and the **command line in
  its own process** (`oneiro drafts list|show|new|revise|send`), each with its exit
  status, on a root of its own so the CLI's lease does not fight the console's;
* the **tab itself**, in a real browser: the drafts screen is opened, the letter that
  would go out is read on the page, the `draft.state.waiting` card's own button is
  clicked, and the mailbox log is read again — the click, and not a request this check
  made, is what puts the call on the wire. Two pictures of the screen are kept (before
  and after the press), and a browser driver that is missing is reported as an unmet
  check rather than as a pass;
* a second console whose declared permissions refuse sending, where the press is refused
  by name and the transport log stays empty — a boundary no number of presses opens;
* the owner's own data root fingerprinted before and after, and the product stream read
  before and after through the owner's own reader script: this check writes the `demo`
  subject of experience and nothing else;
* the records this run wrote read back at the end **by their own ids**, through a worker
  of this check's own: the shipped reader prints the first 1200 characters of a page, so
  a run's own draft is stored and still not in that tail (measured 2026-10-12), and a
  page is a window rather than an answer about one record.

The demo's records go to the `demo` stream because `runtime.stream` says so — the same
declared setting a person would use, not a code path this check alone can reach.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

from oneiro import config, i18n                               # noqa: E402
from oneiro.graph_worker import GraphWorker                   # noqa: E402

#: The owner's own data root, read from this process's environment: only ever hashed.
OWNER_ROOT = config.data_root()
#: Where this check keeps everything of its own.
(PROJECT / "_tmp").mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="oneiro-w3-live-", dir=PROJECT / "_tmp"))
#: The graph this check runs against. Empty means "bring up a graph of its own"; a port
#: means "use the one already there" (how W2 ran, and the only mode on a machine with no
#: Docker). `ONEIRO_LIVE_GRAPH_PORT` sets it the way W2's callers expect.
GRAPH_PORT = int(os.environ.get("ONEIRO_LIVE_GRAPH_PORT", "0") or 0)
#: The owner's own graph, read-only: only its streams are fingerprinted, never written.
SHARED_PORT = int(os.environ.get("ONEIRO_LIVE_SHARED_GRAPH_PORT", "8096"))
#: The demo's graph: the shipped image, a container name and a volume of its own.
GRAPH_IMAGE = "oneiro-rewrite-machine:checkpoint"
GRAPH_NAME = "oneiro-w3-" + WORK.name.removeprefix("oneiro-w3-live-")
GRAPH_VOLUME = GRAPH_NAME + "-kb"
#: The subject of experience this check writes in, through the declared setting.
STREAM = "demo"

MAIL = "mailbox.send_message"
READ = "mailbox.list_messages"
NOTICE = "bot.send_message"
UPDATES = "bot.get_updates"

TO = "curator@example.org"
SUBJECT = "Отчёт о приёме в десятый класс"
#: A word of this run's own, and the words that carry it. A draft's id is the digest of
#: the call it would make, so without a marker a second run would find the previous run's
#: draft already sent — and would be asking to press a call that has left the machine,
#: which is the same trap the webhook check names. `--marker` says what this run is about;
#: the default is this moment.
MARKER = ""
BODY = ""
REVISED_BODY = ""
SECOND: dict[str, str] = {}
#: The draft the second console writes. Its own bytes, because a draft's id is the digest
#: of the call: reusing the first console's call would find that draft already sent and
#: would be asked to press a call that has left the machine.
BLOCKED: dict[str, str] = {}
#: The draft the **tab** presses, in a real browser: its own bytes for the same reason.
TAB: dict[str, str] = {}


def _this_run(marker: str) -> None:
    """Name this run: the marker goes into every byte the check would send."""
    global MARKER, BODY, REVISED_BODY, SECOND, BLOCKED, TAB
    MARKER = marker
    BODY = f"Отчёт подготовлю к пятнице. [{marker}]"
    REVISED_BODY = f"Отчёт подготовлю к четвергу, как просили. [{marker}]"
    SECOND = {"to": "office@example.org", "subject": f"Ответ по заявлению [{marker}]",
              "body": f"Заявление принято, ответим в течение недели. [{marker}]"}
    BLOCKED = {"to": "denied@example.org", "subject": f"Письмо, которое не уйдёт [{marker}]",
               "body": f"Это письмо не должно уйти, пока отправка запрещена. [{marker}]"}
    TAB = {"to": "tab@example.org", "subject": f"Письмо из вкладки [{marker}]",
           "body": f"Это письмо уходит со вкладки «Черновики», когда вы нажимаете "
                   f"«Отправить». [{marker}]"}


_this_run(os.environ.get("ONEIRO_LIVE_MARKER", "") or
          time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(os.urandom(8)).hexdigest()[:6])
STRANGER_CHAT = 999999
OWNER_CHAT = 424242

#: A real MCP server on stdio, in the shape the ecosystem speaks: two of them, chosen by
#: the role argument. Every `tools/call` that reaches it is written down before it is
#: answered, which is what makes "nothing was sent" a measurement.
FAKE_SERVER = r'''
import json, sys, time

LOG, ROLE = sys.argv[1], sys.argv[2]

TOOLS = {
    "mailbox": [
        {"name": "list_messages", "description": "The newest incoming mail.",
         "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
        {"name": "send_message", "description": "Send one message.",
         "inputSchema": {"type": "object", "required": ["to", "subject", "body"],
                         "properties": {"to": {"type": "string"}, "subject": {"type": "string"},
                                        "body": {"type": "string"}}}},
    ],
    "bot": [
        {"name": "get_updates", "description": "What was written to the bot.",
         "inputSchema": {"type": "object", "properties": {}}},
        {"name": "send_message", "description": "Send one message to a chat.",
         "inputSchema": {"type": "object", "required": ["chat_id", "text"],
                         "properties": {"chat_id": {"type": "integer"},
                                        "text": {"type": "string"}}}},
    ],
}[ROLE]

INBOX = {"messages": [{
    "id": "m-1",
    "from": "Куратор <curator@example.org>",
    "subject": "Отчёт о приёме в десятый класс",
    "body": "Прошу подготовить отчёт к пятнице."}]}
UPDATES = {"ok": True, "result": [
    {"update_id": 1, "message": {"chat": {"id": 424242, "type": "private"}, "text": "привет"}}]}


def note(tool, arguments):
    with open(LOG, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": time.time(), "server": ROLE, "tool": tool,
                                 "arguments": arguments}, ensure_ascii=False) + "\n")


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
                         "serverInfo": {"name": ROLE, "version": "1"}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = request.get("params") or {}
        name, arguments = params.get("name"), params.get("arguments") or {}
        note(name, arguments)
        if name == "list_messages":
            text = json.dumps(INBOX, ensure_ascii=False)
        elif name == "get_updates":
            text = json.dumps(UPDATES, ensure_ascii=False)
        else:
            text = "ok: " + json.dumps(arguments, ensure_ascii=False)
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"content": [{"type": "text", "text": text}]}})
'''

RESULTS: list[tuple[str, bool, str]] = []
#: Commands the shared graph aborted once, printed at the end so nothing about this run
#: is reported as smoother than it was.
RETRIES: list[str] = []


def say(line: str = "") -> None:
    print(line, flush=True)


def check(label: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((label, ok, detail))
    say(f"  [{'ok' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def use_graph(port: int) -> None:
    """The port every console, command and reader of this check is pointed at."""
    global GRAPH_PORT
    GRAPH_PORT = port


def start_private_graph(port: int) -> tuple[bool, str]:
    """A graph of the demo's own, from the shipped image, on a free host port.

    The whole point is that the demo writes a subject nobody shares: the owner's graph on
    8096 belongs to their own work (and, while another agent measures on it, refuses other
    clients outright — measured tonight: `server_unreachable` for every connection for
    twenty minutes, cleared only by a container restart the owner approved). A demo that
    cannot be reproduced without disturbing that service is not a demo.

    Each run has its own container and retained volume. No existing container or
    data is removed, and stopping preserves the evidence for later inspection.
    """
    sources = str(PROJECT / "knowledge-base").replace("\\", "/")
    started = subprocess.run(
        ["docker", "run", "-d", "--name", GRAPH_NAME,
         "-p", f"127.0.0.1:{port}:8090",
         "-v", f"{sources}:/knowledge-base",
         "-v", f"{GRAPH_VOLUME}:/kb.bin",
         "-e", "REBUILD_KB=0",
         "-e", "KB_PATH=/knowledge-base/repo.path",
         "-e", "BINARY_PATH=/example-app/install/sc-machine/bin",
         "-e", "CONFIG_PATH=/knowledge-base/oneiro-ostis.ini",
         "-e", "EXTENSIONS_PATH=/example-app/build/Release/extensions;"
               "/example-app/install/sc-machine/lib/extensions",
         "-e", "SC_SERVER_HOST=0.0.0.0",
         "-e", "SC_SERVER_PARALLEL_ACTIONS=0",
         GRAPH_IMAGE, "run"],
        capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace")
    if started.returncode != 0:
        detail = (started.stderr or started.stdout or "").strip().splitlines()
        return False, detail[-1][:200] if detail else f"docker run exited {started.returncode}"
    return True, started.stdout.strip()[:12]


def stop_private_graph() -> str:
    """Stop only this run's graph; keep its container and volume as evidence."""
    stopped = subprocess.run(["docker", "stop", "--time", "20", GRAPH_NAME], capture_output=True,
                             text=True, timeout=180, encoding="utf-8", errors="replace")
    return (stopped.stdout or stopped.stderr or "").strip()[:80]


def wait_for_graph(env: dict[str, str], seconds: float = 300) -> tuple[bool, str]:
    """Until the demo's own graph answers a read, or the time is up."""
    started = time.monotonic()
    while time.monotonic() - started < seconds:
        if read_stream(env, STREAM, 1, tries=1)[0] == 0:
            return True, f"{time.monotonic() - started:.1f}s after the container started"
        time.sleep(3)
    return False, f"it did not answer a read within {seconds:.0f}s"


def request(port: int, path: str, body: Any = None, *, token: str = "",
            method: str | None = None, tries: int = 8) -> tuple[int, Any]:
    """One real HTTP call, answering with the status even when it is a refusal.

    The graph is a service shared with the owner's own sessions, and it intermittently
    aborts a fresh connection mid-warm-up (measured in this very check: `server_unreachable`
    on one read in five, with nothing else running). A 503 — *nothing could be read just
    now, nothing was changed* — is therefore asked again; the retry is printed and counted,
    so a run that needed it says so instead of looking smoother than it was. Every other
    answer, refusals included, is passed on untouched.
    """
    for attempt in range(1, tries + 1):
        status, payload = _request_once(port, path, body, token=token, method=method)
        if status != 503 or attempt == tries:
            return status, payload
        say(f"  [note] the shared graph answered 503 on {path}; asking again "
            f"(attempt {attempt + 1} of {tries})")
        RETRIES.append(f"HTTP {path} (503, attempt {attempt})")
        time.sleep(1.0 + attempt)
    return status, payload


def _request_once(port: int, path: str, body: Any = None, *, token: str = "",
                  method: str | None = None) -> tuple[int, Any]:
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        if token:
            headers["X-Oneiro-CSRF"] = token
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                  headers=headers, method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(call, timeout=180) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, {"error": raw[:200]}


def fingerprint(root: Path) -> list[str]:
    """A digest per file, so "nothing was written" is a comparison and not a claim."""
    if not root.is_dir():
        return []
    return [f"{path.relative_to(root)} {hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in sorted(root.rglob("*")) if path.is_file()]


def prepare(root: Path, *, allow_sending: bool) -> dict[str, Any]:
    """A console's own world: root, settings, MCP list, and the two servers behind it.

    The reviewed default refuses sending (`permissions.send_publish` is `deny`), so the
    first console declares `ask` — the one thing a person does once before a mailbox of
    their own may answer anybody. The second console keeps the default and shows what
    that refusal costs: nothing goes out, and the bot is not even asked where to write.
    """
    (root / "runtime").mkdir(parents=True, exist_ok=True)
    script = root / "fake_mcp.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    log = root / "calls.jsonl"
    (root / "settings.json").write_text(
        json.dumps({"permissions.send_publish": "ask" if allow_sending else "deny"},
                   ensure_ascii=False), encoding="utf-8")
    (root / "mcp.json").write_text(json.dumps({"mcp": {
        "mailbox": {"type": "local", "enabled": True,
                    "command": [sys.executable, str(script), str(log), "mailbox"]},
        "bot": {"type": "local", "enabled": True,
                "command": [sys.executable, str(script), str(log), "bot"]}}},
        ensure_ascii=False), encoding="utf-8")
    return {"root": root, "log": log}


def base_env(world: dict[str, Any], *, web_port: int) -> dict[str, str]:
    """Everything of the owner's pointed somewhere else, and the graph named explicitly."""
    root: Path = world["root"]
    env = dict(os.environ)
    env.update({
        "ONEIRO_DATA_DIR": str(root / "runtime"),
        "ONEIRO_SETTINGS_FILE": str(root / "settings.json"),
        "ONEIRO_MCP_FILE": str(root / "mcp.json"),
        "ONEIRO_KEYS_FILE": str(root / "no-keys.env"),
        "ONEIRO_WEB_HOST": "127.0.0.1",
        "ONEIRO_WEB_PORT": str(web_port),
        "ONEIRO_PORT": str(GRAPH_PORT),
        # The subject of experience is the declared setting, not this check's private
        # arrangement: the product is asked to write the demo's stream.
        "ONEIRO_STREAM": STREAM,
        # The owner's provider is not called by a check.
        "ONEIRO_LLM_BASE_URL": "http://127.0.0.1:9/v1",
        "ONEIRO_LLM_API_KEY": "live-check-key",
        "ONEIRO_LLM_MODEL": "stub/live-check",
        "ONEIRO_MCP_AUTOSTART": "false",
    })
    for name in ("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"):
        env.pop(name, None)
    return env


def calls(world: dict[str, Any]) -> list[dict[str, Any]]:
    """What the servers were actually asked to do, in the order it arrived."""
    log: Path = world["log"]
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def sends(world: dict[str, Any], tool: str = MAIL) -> list[dict[str, Any]]:
    """Only the calls that put something on the wire: the sends, and nothing else.

    Matched by server **and** tool, because both demo servers declare a `send_message`:
    a filter on the tool name alone counts the bot's message to the owner as mail.
    """
    server, _, name = tool.partition(".")
    return [row for row in calls(world)
            if row["server"] == server and row["tool"] == name]


def start_console(world: dict[str, Any], port: int) -> tuple[subprocess.Popen, Path, Any]:
    """The product's own console in its own process, on a root of the check's own."""
    log_path: Path = world["root"] / "console.log"
    handle = log_path.open("w", encoding="utf-8")
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, str(TESTS / "live_hooks_serve.py"), "--stream", STREAM],
        cwd=str(PROJECT), env=base_env(world, web_port=port), stdout=handle,
        stderr=subprocess.STDOUT, creationflags=creation)
    return process, log_path, handle


def stop(process: subprocess.Popen) -> tuple[int | None, str]:
    """Ask the console to stop the way a person would, and report what it did."""
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
    except (OSError, ValueError):
        process.terminate()
    try:
        return process.wait(timeout=40), "asked to stop"
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=20), "terminated after 40 s without stopping"
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=20), "killed after two waits without stopping"


def wait_ready(process: subprocess.Popen, port: int, seconds: float = 120) -> tuple[bool, str]:
    started = time.monotonic()
    while time.monotonic() - started < seconds and process.poll() is None:
        try:
            if request(port, "/api/session")[0] == 200:
                return True, f"{time.monotonic() - started:.1f}s after start"
        except OSError:
            pass
        time.sleep(0.25)
    return False, f"no answer within {seconds:.0f}s"


def _cli_once(env: dict[str, str], *arguments: str) -> tuple[int, str]:
    finished = subprocess.run([sys.executable, "-m", "oneiro", *arguments],
                              cwd=str(PROJECT),
                              env={**env, "PYTHONPATH": str(PROJECT / "python"),
                                   "PYTHONIOENCODING": "utf-8"},
                              capture_output=True, text=True, timeout=300,
                              encoding="utf-8", errors="replace")
    say(f"        CLI exit {finished.returncode}: oneiro {' '.join(arguments)}")
    return finished.returncode, ((finished.stdout or "") + (finished.stderr or "")).strip()


def _flaked(output: str) -> bool:
    """Whether a command's answer was the shared graph refusing, not the product deciding."""
    return "server_unreachable" in output or "graph_timeout" in output


def cli(env: dict[str, str], *arguments: str) -> tuple[int, str]:
    """One real process of the command line, with its own exit status.

    The graph is a service shared with the owner's own sessions, and a connection it
    aborts while warming up (`server_unreachable`) is a transport event, not a decision of
    the product. When that is what came back, the command is run once more and the retry
    is **reported**, not hidden; any other non-zero exit is passed on as it stands.
    """
    code, output = _cli_once(env, *arguments)
    for attempt in range(1, 6):
        if code == 0 or not _flaked(output):
            return code, output
        RETRIES.append(f"oneiro {' '.join(arguments)}")
        say(f"  [note] the shared graph refused this command (attempt {attempt}); running "
            f"it again: oneiro {' '.join(arguments)}")
        time.sleep(1.0 + attempt)
        code, output = _cli_once(env, *arguments)
    return code, output


def cli_env(world: dict[str, Any]) -> dict[str, str]:
    """The command line's own root, so its lease does not fight the running console's.

    The settings file and the MCP list stay the console's, so the CLI names the same
    servers and logs into the same evidence; only the lock and the keys move aside.
    """
    root: Path = world["root"]
    env = base_env(world, web_port=free_port())
    env["ONEIRO_DATA_DIR"] = str(WORK / "cli")
    (WORK / "cli").mkdir(parents=True, exist_ok=True)
    env["ONEIRO_KEYS_FILE"] = str(WORK / "cli" / "no-keys.env")
    return env


def read_stream(env: dict[str, str], stream: str, limit: int,
                tries: int = 6) -> tuple[int, str]:
    """The owner's own reader, as a separate process: its exit code is the answer.

    Asked again when the graph aborts the connection — the same retry, and the same
    reporting, as every other read here. `tries=1` is what the readiness poll asks for,
    because it is waiting for a graph that is still starting.
    """
    for attempt in range(1, tries + 1):
        finished = subprocess.run(
            [sys.executable, str(PROJECT / "scripts" / "office-graph-read.py"),
             "--stream", stream, "--limit", str(limit)],
            cwd=str(PROJECT), env=env, capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace")
        code = finished.returncode
        output = ((finished.stdout or "") + (finished.stderr or "")).strip()
        if code == 0 or attempt == tries:
            return code, output
        say(f"  [note] the reader of the {stream} stream was refused by the graph; "
            f"asking again (attempt {attempt + 1} of {tries})")
        RETRIES.append(f"read {stream} (attempt {attempt})")
        time.sleep(1.0 + attempt)
    return code, output


def read_records(stream: str, record_ids: list[str]) -> tuple[dict[str, dict[str, Any]], Any, str]:
    """The named records themselves, read through a worker of this check's own.

    A page scan is not enough here. The shipped reader prints the first 1200 characters
    of a page, so a run's own draft can be stored in the stream and still absent from
    that tail (measured 2026-10-12: the tail began with an approval written after the
    draft). Asking the store for each record by its own id answers about exactly what
    this run wrote, and the page's own `candidates` says how much the stream holds.
    """
    worker = GraphWorker(f"ws://127.0.0.1:{GRAPH_PORT}/ws_json", stream, WORK / "check-read.lock")
    found: dict[str, dict[str, Any]] = {}
    candidates: Any = None
    why = ""

    async def run() -> None:
        nonlocal candidates, why
        try:
            candidates = (await worker.call("page", limit=1)).get("candidates")
            for record_id in record_ids:
                record = await worker.call("entity", record_id=record_id)
                if record is not None:
                    found[record_id] = record
        except Exception as exc:                # noqa: BLE001 - the diagnosis is the answer
            why = f"the store could not be read ({exc.__class__.__name__}: {exc})"
        finally:
            await worker.close()

    asyncio.run(run())
    return found, candidates, why


def drive_tab(port: int, draft_id: str, shot: Path) -> dict[str, Any]:
    """Open the drafts screen in a real browser, press the draft there, and report it.

    The console's own script does the work: this opens the page, clicks what the owner
    would click, and reads what the owner would read. A press made with this check's own
    request would prove nothing about the screen, so the only things done here are that
    click and the reads around it — and two pictures of what was actually on screen.

    A browser driver that is not installed answers `{"unavailable": ...}`; the caller
    reports that as an unmet check, never as a pass.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"unavailable": "the browser driver is not installed (playwright + chromium)"}
    after = shot.with_name(shot.stem + "-sent" + shot.suffix)
    seen: dict[str, Any] = {"shot": shot, "shot_after": after}
    with sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"http://127.0.0.1:{port}/drafts", wait_until="networkidle")
            seen["lang"] = page.get_attribute("html", "lang")
            card = page.locator(f'[data-draft="{draft_id}"]')
            card.wait_for(state="visible", timeout=30_000)
            seen["card"] = card.count() == 1
            seen["page_text"] = " ".join(page.inner_text("body").split())
            seen["button"] = card.locator(".draft-send").inner_text().strip()
            seen["state_before"] = card.locator(".pill").first.inner_text().strip()
            page.screenshot(path=str(shot), full_page=True)
            card.locator(".draft-send").click()
            # The page reads the list again from the store once the press has settled, so
            # waiting for the draft among the decided ones is waiting for the store's
            # answer rather than for the click's own memory of itself.
            page.wait_for_function(
                "id => document.querySelector('#draft-settled [data-draft=\"' + id"
                " + '\"]') !== null", arg=draft_id, timeout=30_000)
            page.wait_for_function(
                "said => (document.querySelector('#draft-meter').textContent || '')"
                ".includes(said)", arg=i18n.t("draft.sent", "ru"), timeout=30_000)
            seen["settled_text"] = " ".join(
                page.locator("#draft-settled").inner_text().split())
            seen["meter"] = " ".join(page.locator("#draft-meter").inner_text().split())
            page.screenshot(path=str(after), full_page=True)
        finally:
            browser.close()
    return seen


def listener(pid: int, port: int) -> tuple[str | None, str]:
    """The address the console listens on, from this machine's table. Read-only."""
    command = ["netstat", "-ano"] if os.name == "nt" else ["ss", "-ltnp"]
    try:
        # The table is not UTF-8 on every machine (measured in W2: 0x80 mid-line), and the
        # fields this check reads are ASCII, so undecodable bytes are replaced, not fatal.
        finished = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=60)
    except OSError as exc:
        return None, f"{command[0]} could not be run ({exc.__class__.__name__})"
    if finished.returncode != 0:
        return None, f"{command[0]} exited {finished.returncode}"
    for line in finished.stdout.splitlines():
        fields = line.replace("[::]:", ":").split()
        if "LISTEN" not in line.upper() or f":{port}" not in line or not fields:
            continue
        if os.name == "nt" and fields[-1] != str(pid):
            continue
        if os.name != "nt" and f"pid={pid}" not in line:
            continue
        for token in fields:
            if token.endswith(f":{port}"):
                return token, "found in this machine's table"
    return None, f"no listening socket for pid {pid} on port {port} was reported"


def why_of(payload: dict[str, Any], status: int) -> str:
    """What a route actually said, technical string included: a 503 must name its cause.

    The console deliberately keeps the machine-readable string in `detail` and shows a
    sentence to a person; a check reads both, because “nothing could be read just now” is
    not enough to tell a timeout from an aborted connection.
    """
    if not isinstance(payload, dict):
        return str(payload)[:140]
    said = str(payload.get("detail") or payload.get("error") or "")
    return f"HTTP {status} {payload.get('reason') or ''} {said}".strip()[:140]


def note_of(page: dict[str, Any]) -> dict[str, Any] | None:
    """The stored mail note in a page of records, found by kind rather than by position."""
    for row in page.get("items") or []:
        labels = row.get("labels") or []
        if row.get("kind") == "note" and "mail" in labels:
            return row
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="live_drafts_check")
    parser.add_argument("--marker", default="",
                        help="a word of this run's own, so its drafts are new drafts: a "
                             "draft's id is the digest of the call, and the previous run's "
                             "call has already been sent")
    parser.add_argument("--graph-port", type=int, default=GRAPH_PORT,
                        help="use a graph that is already running on this port, and start "
                             "and stop nothing; without it the check brings up a graph of "
                             "the demo's own")
    args = parser.parse_args(argv)
    if args.marker:
        _this_run(args.marker)

    world = prepare(WORK / "asks", allow_sending=True)
    owner_before = fingerprint(OWNER_ROOT)
    # The owner's own graph, read only: the demo's records must not land in it.
    shared = dict(base_env(world, web_port=0))
    shared["ONEIRO_DATA_DIR"] = str(WORK / "shared-reads")
    shared["ONEIRO_PORT"] = str(SHARED_PORT)
    (WORK / "shared-reads").mkdir(parents=True, exist_ok=True)
    shared_before = read_stream(shared, "product", 1)

    own_graph = args.graph_port == 0
    if own_graph:
        graph_port = free_port()
        started, detail = start_private_graph(graph_port)
        if not started:
            say(f"a graph of the demo's own could not be started: {detail}")
            say("        (run this check with --graph-port N to use one that is already "
                "running, as W2 did)")
            return 1
        use_graph(graph_port)
        say(f"        the demo's own graph: container {GRAPH_NAME} on 127.0.0.1:{graph_port} "
            f"({detail})")
    else:
        use_graph(args.graph_port)
    asks_env = base_env(world, web_port=0)
    say(f"Oneiro: draft check, data root {world['root']}, this run is {MARKER}")
    say(f"        graph named explicitly: ONEIRO_PORT={GRAPH_PORT}, stream {STREAM} "
        f"(runtime.stream)")
    say(f"        the owner's data root is {OWNER_ROOT} ({len(owner_before)} files, read only)")
    say(f"        the owner's graph on {SHARED_PORT} is read only, its streams fingerprinted")
    say(f"        the fake mailbox and bot write every call to {world['log']}")
    say()
    if own_graph:
        ready, why = wait_for_graph(asks_env)
        if not check("the demo's own graph answers a read", ready, why):
            stop_private_graph()
            return 1

    port = free_port()
    process: subprocess.Popen | None = None
    log_path: Path | None = None
    handle: Any = None
    #: The records read back from the store at the end. Empty means the step that would
    #: have named them never ran: the check says that, rather than crashing on the way.
    note_id = draft_id = approval_id = grant_id = second_id = third_id = ""
    try:
        say("== the console comes up on its own port ==")
        process, log_path, handle = start_console(world, port)
        ready, why = wait_ready(process, port)
        say(f"        console pid {process.pid} on http://127.0.0.1:{port}")
        if not check("the console answered on its own port", ready, why):
            say(log_path.read_text(encoding="utf-8", errors="replace")[-1500:])
            if own_graph:
                stop_private_graph()
            return 1
        status, session = request(port, "/api/session")
        token = str(session.get("csrf") or "")
        check("the page token is issued to this session", status == 200 and bool(token),
              f"HTTP {status}")
        status, facts = request(port, "/api/graph")
        check("the explicitly named graph is the one in use", facts.get("verified") is True,
              f"/api/graph {status}: reachable={facts.get('reachable')} "
              f"verified={facts.get('verified')}")
        status, overview = request(port, "/api/mcp")
        rows = {row["name"]: row for row in overview.get("servers") or []}
        check("the mailbox and the bot are declared in the demo's own list",
              sorted(rows) == ["bot", "mailbox"] and rows["mailbox"]["enabled"],
              f"{overview.get('file')}: "
              + ", ".join(f"{name}={rows[name]['state']}" for name in sorted(rows)))
        check("declared is not the same as running: nothing is open yet",
              all(row["state"] == "closed" for row in rows.values()),
              "oneiro.mcp.autostart is off, so a server opens when a draft needs it")

        say()
        say("== a letter arrives and is read, which is not a send ==")
        status, read = request(port, "/api/mail/read",
                               {"tool": READ, "arguments": {"query": "is:unread"}, "limit": 5},
                               token=token)
        check("the mailbox is read through the declared tool", status == 200
              and read.get("ok") is True and read.get("read") == 1,
              (f"HTTP {status} read={read.get('read')} via {read.get('tool')}" if status == 200
               else why_of(read, status)))
        check("no send reached the mailbox while reading",
              sends(world) == [], f"{len(calls(world))} call(s) arrived, all reads or updates")
        # The demo stream is a subject of its own that accumulates run after run, so the
        # page is asked for enough records to hold this run's letter: a limit of twenty
        # finds the note only on a quiet stream and reports a stored letter as missing.
        status, page = request(port, "/api/memory/records?limit=200")
        note = note_of(page) if isinstance(page, dict) else None
        note_id = str((note or {}).get("id") or "")
        check("the letter is kept in the memory as an observation", bool(note)
              and note.get("provenance") == "observation" and SUBJECT in str(note.get("topic")),
              f"HTTP {status} " + (f"{note.get('id')} [{note.get('provenance')}] "
                                   f"{note.get('topic')!r}" if note
                                   else "no mail note was stored (" + why_of(page, status) + ")"))
        status, opened = request(port, "/api/mcp/mailbox/tools")
        keys = [item["key"] for item in opened.get("tools") or []]
        check("the server opened when it was needed, and names its tools",
              status == 200 and opened.get("opened") is True and MAIL in keys and READ in keys,
              f"HTTP {status} tools: {', '.join(keys)}")

        say()
        say("== a reply is written down, and nothing leaves ==")
        status, draft = request(port, "/api/drafts",
                                {"tool": MAIL, "arguments": {"to": TO, "subject": SUBJECT,
                                                             "body": BODY},
                                 "source_id": "mail-m-1"}, token=token)
        draft_id = str(draft.get("id") or "")
        check("the draft is created waiting for the press", status == 201
              and draft.get("state") == "waiting" and draft_id.startswith("draft-"),
              f"HTTP {status} {draft_id} {draft.get('why')}" if status == 201
              else why_of(draft, status))
        check("nothing was sent while writing the draft", sends(world) == [],
              f"sends so far: {len(sends(world))}")
        status, shown = request(port, f"/api/drafts/{draft_id}")
        approval = shown.get("approval") or {}
        approval_id = str(approval.get("id") or "")
        check("the draft and its approval are both waiting, on the record",
              status == 200 and approval.get("state") == "waiting"
              and approval.get("pressed") is False,
              f"approval {approval.get('id')} state={approval.get('state')} "
              f"pressed={approval.get('pressed')}")
        status, refused = request(port, f"/api/drafts/{draft_id}/send", {"dry_run": True},
                                  token=token)
        check("the console refuses to send it without the press", status == 409
              and refused.get("reason") == "not_pressed",
              f"HTTP {status} {refused.get('reason')}: {str(refused.get('error'))[:90]}")
        check("still nothing sent", sends(world) == [], f"sends so far: {len(sends(world))}")

        say()
        say("== the command line, in its own process ==")
        env = cli_env(world)
        code, output = cli(env, "drafts", "list")
        check("`oneiro drafts list` shows the waiting draft, exit 0", code == 0
              and draft_id in output, f"exit {code}: {output.splitlines()[0][:100] if output else ''}")
        code, output = cli(env, "drafts", "show", draft_id)
        check("`oneiro drafts show` prints the exact call", code == 0 and SUBJECT in output
              and TO in output, f"exit {code}: {output.splitlines()[0][:100] if output else ''}")
        code, output = cli(env, "drafts", "send", draft_id, "--dry-run")
        check("`oneiro drafts send --dry-run` refuses an unpressed draft, exit 2", code == 2
              and "not_pressed" in output,
              f"exit {code}: {' '.join(output.split())[:120]}")
        check("the command line sent nothing either", sends(world) == [],
              f"sends so far: {len(sends(world))}")
        code, output = cli(env, "drafts", "revise", draft_id,
                           "--argument", f"to={TO}", "--argument", f"subject={SUBJECT}",
                           "--argument", f"body={REVISED_BODY}")
        status, shown = request(port, f"/api/drafts/{draft_id}")
        check("the command line edits the draft, and an edit is unpressed again", code == 0
              and status == 200
              and (shown.get("arguments") or {}).get("body") == REVISED_BODY
              and (shown.get("approval") or {}).get("pressed") is False,
              f"exit {code}: {' '.join(output.split())[:100]}; body now "
              f"{str((shown.get('arguments') or {}).get('body'))[:48]!r}, "
              f"pressed={(shown.get('approval') or {}).get('pressed')}")
        check("editing sent nothing", sends(world) == [], f"sends so far: {len(sends(world))}")

        say()
        say("== the press, and only the press, puts it on the wire ==")
        code, output = cli(env, "drafts", "send", draft_id)
        after_press = sends(world)
        landed = code == 0
        if code == 2 and "already_settled" in output and len(after_press) == 1:
            # The graph failed between the press and its answer, so the command was run
            # again and found the draft already released: the record and the mailbox agree
            # that exactly one send went out, and the second command did not make a second.
            landed = True
            say("  [note] the press landed on its first attempt; the repeated command was "
                "refused as already settled and sent nothing")
        check("`oneiro drafts send` is the press: it goes out, exactly once",
              landed and len(after_press) == 1,
              f"exit {code}: {' '.join(output.split())[:110]}")
        check("exactly one send reached the mailbox, and it is the edited call",
              len(after_press) == 1 and after_press[0]["arguments"] == {
                  "to": TO, "subject": SUBJECT, "body": REVISED_BODY},
              json.dumps(after_press[0]["arguments"], ensure_ascii=False) if after_press else "none")
        check("the text that was replaced never left the machine",
              BODY not in json.dumps(calls(world), ensure_ascii=False),
              f"the revised body is the only one in {len(calls(world))} logged call(s)")
        status, again = request(port, f"/api/drafts/{draft_id}/send", {}, token=token)
        check("pressing it twice is refused, and sends nothing again", status == 409
              and again.get("reason") == "already_settled" and len(sends(world)) == 1,
              f"HTTP {status} {again.get('reason')}: sends still {len(sends(world))}")
        status, settled = request(port, f"/api/drafts/{draft_id}")
        # The approval this draft now carries is the one the press decided: a draft's id
        # is the digest of its call, so the edit re-raised it under new arguments and the
        # owner's grant names those, not the text the draft was first written with.
        grant_id = str((settled.get("approval") or {}).get("id") or "")
        check("the record says it was sent, by exactly that call",
              status == 200 and settled.get("state") == "completed"
              and settled.get("decision") == "allow"
              and (settled.get("effect") or {}).get("outcome") == "succeeded",
              f"state={settled.get('state')} decision={settled.get('decision')} "
              f"effect={(settled.get('effect') or {}).get('kind')}"
              f"->{(settled.get('effect') or {}).get('outcome')}")

        say()
        say("== the second draft: written by the command line, pressed through HTTP ==")
        code, output = cli(env, "drafts", "new", "--tool", MAIL,
                           "--argument", f"to={SECOND['to']}",
                           "--argument", f"subject={SECOND['subject']}",
                           "--argument", f"body={SECOND['body']}")
        second_id = ""
        status, listed = request(port, "/api/drafts")
        for item in listed.get("drafts") or []:
            if (item.get("arguments") or {}).get("to") == SECOND["to"]:
                second_id = str(item.get("id") or "")
        check("the command line writes a draft the console sees, exit 0", code == 0
              and bool(second_id),
              f"exit {code}: {second_id or output.splitlines()[0][:90]}")
        check("writing it sent nothing", len(sends(world)) == 1,
              f"sends so far: {len(sends(world))}")
        status, sent = request(port, f"/api/drafts/{second_id}/send", {}, token=token)
        check("the console's press releases exactly that call", status == 200
              and sent.get("state") == "completed", f"HTTP {status} state={sent.get('state')}")
        check("the mailbox now holds two sends, in the order they were pressed",
              [row["arguments"].get("to") for row in sends(world)] == [TO, SECOND["to"]],
              json.dumps([row["arguments"].get("to") for row in sends(world)],
                         ensure_ascii=False))

        say()
        say("== a draft can be called off, and a called-off draft is not a send ==")
        status, third = request(port, "/api/drafts",
                                {"tool": MAIL, "arguments": dict(SECOND, to="third@example.org")},
                                token=token)
        third_id = str(third.get("id") or "")
        status, off = request(port, f"/api/drafts/{third_id}/discard", {"reason": "не нужно"},
                              token=token)
        check("the owner's no is recorded as a refusal on the draft", status == 200
              and off.get("state") == "cancelled" and off.get("decision") == "deny",
              f"HTTP {status} state={off.get('state')} decision={off.get('decision')} "
              f"{off.get('result')!r}")
        status, refused = request(port, f"/api/drafts/{third_id}/send", {}, token=token)
        check("a called-off draft cannot be sent afterwards", status == 409
              and refused.get("reason") == "already_settled"
              and len(sends(world)) == 2,
              f"HTTP {status} {refused.get('reason')}: sends still {len(sends(world))}")

        say()
        say("== the notice to the owner's own chat ==")
        status, notice = request(port, "/api/telegram/notice",
                                 {"draft_id": second_id, "tool": NOTICE, "updates_tool": UPDATES,
                                  "chat_id": STRANGER_CHAT}, token=token)
        check("the notice goes to the chat the bot reports, not to one we name",
              status == 200 and notice.get("ok") is True
              and notice.get("chat_id") == OWNER_CHAT,
              f"HTTP {status} chat_id={notice.get('chat_id')} "
              f"(the request asked for {STRANGER_CHAT})")
        bot_sends = sends(world, NOTICE)
        check("the bot was asked who wrote to it, then told once",
              [row["tool"] for row in calls(world) if row["server"] == "bot"]
              == ["get_updates", "send_message"],
              json.dumps([row["tool"] for row in calls(world) if row["server"] == "bot"]))
        check("the bot's send is not counted as mail: two sends on the mailbox, one to you",
              len(sends(world, MAIL)) == 2 and len(bot_sends) == 1,
              f"mailbox {len(sends(world, MAIL))}, bot {len(bot_sends)}")
        check("the notice carries no other chat, and names the draft it is about",
              len(bot_sends) == 1
              and bot_sends[0]["arguments"].get("chat_id") == OWNER_CHAT
              and second_id in str(bot_sends[0]["arguments"].get("text"))
              and str(STRANGER_CHAT) not in json.dumps(calls(world)),
              (f"chat_id={bot_sends[0]['arguments'].get('chat_id')} text: "
               f"{' '.join(str(bot_sends[0]['arguments'].get('text')).split())[:90]}")
              if bot_sends else "the bot received no send at all")

        say()
        say("== every refusal is a named one ==")
        wrong = [
            ("a tool key without a server", {"tool": "mailbox", "arguments": {"text": "x"}},
             400, ""),
            ("arguments that are not an object", {"tool": MAIL, "arguments": "send it"},
             400, ""),
            ("a call the server's own schema refuses",
             {"tool": MAIL, "arguments": {"to": TO, "subject": SUBJECT}}, 400, "bad_arguments"),
            ("a server this build does not have",
             {"tool": "gmail.send_message", "arguments": {"to": TO}}, 404, "unknown_tool"),
        ]
        for what, payload, expected, reason in wrong:
            status, payload_out = request(port, "/api/drafts", payload, token=token)
            ok = status == expected and (not reason or payload_out.get("reason") == reason)
            check(f"{what}: HTTP {status}", ok, f"{payload_out.get('error') or payload_out}")
        status, missing = request(port, "/api/drafts/draft-nothing-here")
        check("a draft that does not exist is named as missing", status == 404
              and missing.get("reason") == "unknown_draft",
              f"HTTP {status} {missing.get('reason')}")
        status, untokened = request(port, "/api/drafts",
                                    {"tool": MAIL, "arguments": {"to": TO, "subject": "s",
                                                                 "body": "b"}})
        check("every write still needs the page token", status == 403,
              f"POST /api/drafts without the token: HTTP {status}")
        check("no refusal turned into a send", len(sends(world)) == 2,
              f"sends still {len(sends(world))}; the transport saw nothing new")

        address, why = listener(process.pid, port)
        check("the console listens on loopback only", address is not None
              and address.startswith("127.0.0.1:"), f"{address or 'not reported'} ({why})")

        say()
        say("== the tab: the draft is pressed on the page itself ==")
        status, from_tab = request(port, "/api/drafts",
                                   {"tool": MAIL, "arguments": dict(TAB)}, token=token)
        tab_id = str(from_tab.get("id") or "")
        before_tab = len(sends(world))
        check("a draft is written for the tab to press, and writing it sent nothing",
              status == 201 and bool(tab_id) and before_tab == 2,
              f"HTTP {status} {tab_id}; sends so far: {before_tab}")
        picture = WORK / "drafts-tab.png"
        shown = drive_tab(port, tab_id, picture)
        if shown.get("unavailable"):
            check("the tab opens in a browser and its press is a click", False,
                  str(shown["unavailable"]))
        else:
            text = str(shown.get("page_text") or "")
            check("the page shows the exact letters that would go out, before any press",
                  bool(shown.get("card")) and TAB["body"] in text
                  and TAB["subject"] in text,
                  f"lang={shown.get('lang')} card={'yes' if shown.get('card') else 'no'}, "
                  f"letters={'shown' if TAB['body'] in text else 'not shown'}")
            check("the button the owner presses is the catalog's own word",
                  shown.get("button") == i18n.t("btn.send_draft", "ru"),
                  f"the page says {shown.get('button')!r}; the catalog says "
                  f"{i18n.t('btn.send_draft', 'ru')!r}")
            after_tab = sends(world)
            check("the click on the page is what sent it: exactly one call left the machine",
                  len(after_tab) == before_tab + 1
                  and after_tab[-1]["arguments"] == dict(TAB),
                  f"{len(after_tab)} send(s) in the log; the last one is "
                  f"{json.dumps(after_tab[-1]['arguments'] if after_tab else None, ensure_ascii=False)[:110]}")
            settled_text = str(shown.get("settled_text") or "")
            check("the page reads the decision back from the store, in the owner's language",
                  TAB["to"] in settled_text
                  and i18n.t("draft.state.completed", "ru") in settled_text
                  and i18n.t("draft.sent", "ru") in str(shown.get("meter") or ""),
                  f"decided card: {settled_text[:130]!r}; status line: "
                  f"{str(shown.get('meter'))[:80]!r}")
            shots = [path for path in (shown.get("shot"), shown.get("shot_after"))
                     if isinstance(path, Path) and path.is_file()]
            check("the screen was photographed before and after the press",
                  len(shots) == 2 and all(path.stat().st_size > 5000 for path in shots),
                  ", ".join(f"{path.name} {path.stat().st_size} bytes" for path in shots))
    finally:
        say()
        say("== the console stops ==")
        if process is not None and handle is not None and log_path is not None:
            code, how = stop(process)
            handle.close()
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            gone = time.monotonic()
            while time.monotonic() - gone < 10:
                try:
                    if request(port, "/api/session")[0] != 200:
                        break
                except OSError:
                    break
                time.sleep(0.25)
            free = True
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    free = False
            except OSError:
                pass
            check("the console stopped and its port is free", free,
                  f"exit code {code} ({how}); the socket no longer answers")
            check("the console's log has no traceback",
                  "Traceback" not in log_text, f"{len(log_text)} characters of log")

    # ---------- a boundary no press opens ----------
    say()
    say("== the boundary: a machine that may send nothing ==")
    deny = prepare(WORK / "denies", allow_sending=False)
    deny_port = free_port()
    process, log_path, handle = start_console(deny, deny_port)
    try:
        ready, why = wait_ready(process, deny_port)
        status, session = request(deny_port, "/api/session")
        token = str(session.get("csrf") or "")
        say(f"        console pid {process.pid} on http://127.0.0.1:{deny_port}, "
            f"permissions.send_publish=deny")
        if not check("the second console answered, with the reviewed default", ready, why):
            say(log_path.read_text(encoding="utf-8", errors="replace")[-1500:])
            if own_graph:
                stop_private_graph()
            return 1
        _status, written = request(deny_port, "/api/drafts",
                                   {"tool": MAIL, "arguments": dict(BLOCKED)}, token=token)
        blocked_id = str(written.get("id") or "")
        status, blocked = request(deny_port, f"/api/drafts/{blocked_id}/send", {}, token=token)
        check("the press is refused by the declared permission, not by the state",
              status == 403 and blocked.get("reason") == "permission_denied",
              f"HTTP {status} {blocked.get('reason')}: {str(blocked.get('error'))[:110]}")
        status, refused_notice = request(deny_port, "/api/telegram/notice",
                                         {"draft_id": blocked_id, "tool": NOTICE,
                                          "updates_tool": UPDATES}, token=token)
        check("even the notice to the owner is refused while sending is denied",
              status == 403 and refused_notice.get("reason") == "permission_denied",
              f"HTTP {status} {refused_notice.get('reason')}")
        check("the transport was never reached: no server was even started",
              calls(deny) == [],
              f"{len(calls(deny))} call(s) reached the demo's servers, "
              f"{len(sends(deny))} of them sends")
    finally:
        code, how = stop(process)
        handle.close()
        check("the second console stopped too", process.poll() is not None,
              f"exit code {code} ({how})")

    # ---------- nothing of the owner's moved ----------
    say()
    say("== what this check left alone ==")
    owner_after = fingerprint(OWNER_ROOT)
    check("the owner's data root is byte-for-byte what it was", owner_after == owner_before,
          f"{len(owner_after)} files, "
          f"{sum(1 for a, b in zip(owner_before, owner_after) if a != b)} differ")
    shared_after = read_stream(shared, "product", 1)
    check("the owner's own graph was read, never written: its product stream is unchanged",
          shared_after == shared_before,
          f"graph {SHARED_PORT}, before: exit {shared_before[0]} "
          f"{shared_before[1][:48]!r} … after: exit {shared_after[0]}")
    say()
    say("== the demo's own subject holds what this check made ==")
    say("        every record is asked for by its own id: a draft's id is the digest of its "
        "call,")
    say("        so editing one raises a second approval beside the first, and both are "
        "here")
    named = [("the letter that arrived", note_id),
             ("the draft that was pressed", draft_id),
             ("the approval it was first raised with", approval_id),
             ("the owner's own grant for the call that went out", grant_id),
             ("the draft the command line wrote", second_id),
             ("the draft that was called off", third_id)]
    records, candidates, why = read_records(STREAM, [record_id for _, record_id in named
                                                     if record_id])
    for what, record_id in named:
        row = records.get(record_id) or {}
        check(f"the demo's own subject holds {what}", bool(row),
              f"{record_id} [{row.get('kind')}] state={row.get('state')}" if row
              else f"{record_id or 'no id'} is not in stream {STREAM}" + (f" ({why})" if why else ""))
    check("the store itself says one draft was sent and the other was called off",
          (records.get(draft_id) or {}).get("state") == "completed"
          and (records.get(third_id) or {}).get("state") == "cancelled"
          and (records.get(grant_id) or {}).get("state") == "completed",
          f"sent={(records.get(draft_id) or {}).get('state')} "
          f"called-off={(records.get(third_id) or {}).get('state')} "
          f"grant={(records.get(grant_id) or {}).get('state')}, "
          f"of {candidates} record(s) the store walks in stream {STREAM}")
    if own_graph:
        say(f"        the demo's graph is taken down now: {stop_private_graph()}")
        check("the demo's own graph is stopped",
              GRAPH_NAME not in subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                               capture_output=True, text=True, timeout=120,
                                               encoding="utf-8", errors="replace").stdout,
              f"container {GRAPH_NAME} stopped; volume {GRAPH_VOLUME} retained as evidence")
    say(f"        the check's own roots stay for inspection: {WORK}")

    say()
    say("== summary ==")
    if RETRIES:
        say(f"  the graph aborted the first attempt of {len(RETRIES)} command(s): "
            f"{', '.join(RETRIES)}; each was run once more and the second answer is the one "
            f"read above")
    for label, ok, detail in RESULTS:
        say(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    say(f"  {passed}/{len(RESULTS)} checks passed")
    say(f"  the mailbox received {len(sends(world))} send(s) all run and the bot "
        f"{len(sends(world, NOTICE))}; {len(calls(world))} call(s) reached the demo's "
        f"two servers, in the demo's own graph (stream {STREAM}), and the owner's graph "
        f"on {SHARED_PORT} was only read")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
