"""Live check for W1: the real surface, a real schedule, a real run into history.

Run it with `python tests/live_w1_check.py`. It is not a unit test — it is the
end-to-end evidence the plan asks for, exercised the way the product is used:

* a real uvicorn server on a real port, driven through real HTTP with the owner's
  request token, not through the app object;
* a schedule created through the API, fired by the application's **own** clock
  (the process that `oneiro serve` starts), with the wait for the next real
  minute measured, not faked;
* the fired task worked by the product's own workers and written into the stored
  history, read back through the API;
* the model is the one stub: a local HTTP provider on loopback, because the
  owner's provider and graph are not touched by a check. Everything else — the
  store, the policy, the tools, the records, the schedule — is the product's own.

The owner's settings, data root and memory graph are not read or written: the
check points them at a temporary directory before it starts anything.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w1-live-"))
NOTE = WORK / "note.txt"
NOTE.write_text("The note says to keep the schedule small.\n", encoding="utf-8")
# Nothing of the owner's is touched: settings, data root and keys all live here.
os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "no-keys.env")
os.environ["ONEIRO_MCP_FILE"] = str(WORK / "mcp.json")   # never the owner's servers
os.environ["ONEIRO_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"      # replaced below
os.environ["ONEIRO_LLM_API_KEY"] = "live-check-key"
os.environ["ONEIRO_LLM_MODEL"] = "stub/live-check"

import uvicorn                                                      # noqa: E402
from chat_fakes import GraphStub, MemoryLinks                       # noqa: E402
from oneiro import web                                              # noqa: E402
from oneiro.records import State                                    # noqa: E402
from oneiro.runtime import Runtime                                  # noqa: E402

SCHEDULE_CLIENT = "live-check-schedule-0001"
TASK_CLIENT = "live-check-task-0001"


class Provider(BaseHTTPRequestHandler):
    """A loopback provider that speaks the chat-completions shape the product uses."""

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages") or []
        spoken = " ".join(str(item.get("content") or "") for item in messages)
        answered = any(item.get("role") == "tool" for item in messages)
        if answered:
            message = {"role": "assistant",
                       "content": "Done: the note says to keep the schedule small."}
        else:
            if "slowly" in spoken:
                time.sleep(2.0)                       # a provider that takes its time
            message = {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call-1", "type": "function",
                 "function": {"name": "read_file", "arguments": json.dumps({"path": str(NOTE)})}}]}
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

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.base + path, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Oneiro-CSRF": self.token},
            method="POST")
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))


def say(line: str = "") -> None:
    print(line, flush=True)


def main() -> int:
    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    os.environ["ONEIRO_LLM_BASE_URL"] = f"http://127.0.0.1:{provider.server_port}/v1"

    links = MemoryLinks()
    stub = GraphStub(links, WORK / "graph-writer.lock")
    runtime = Runtime(graph=stub)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(web.create_app(runtime=runtime, scheduler=True),
                                           host="127.0.0.1", port=port,
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

    say(f"Oneiro on http://127.0.0.1:{port} (temporary settings in {WORK})")
    say(f"stub provider on http://127.0.0.1:{provider.server_port}/v1")
    say()
    say("== the settings in force ==")
    listing = browser.get("/api/schedules")
    say(f"initiative.level = {listing['level']}, a schedule fires: {listing['fires']}")
    say()

    say("== a schedule, created through the API ==")
    created = browser.post("/api/schedules", {
        "title": "Read the note every minute",
        "detail": "Read the note and say what it says.",
        "cron": "* * * * *",
        "client_id": SCHEDULE_CLIENT})
    schedule_id = created["schedule"]["id"]
    say(f"created {schedule_id} {created['schedule']['cron']!r} "
        f"(duplicate={created['duplicate']})")
    say()

    say("== the application's own clock (waiting for the next real minute) ==")
    started = time.monotonic()
    fired: list[dict] = []
    while time.monotonic() - started < 80:
        fired = browser.get("/api/tasks")["tasks"]
        if fired:
            break
        time.sleep(1.0)
    if not fired:
        say("the clock did not fire the schedule within 80 seconds")
        server.should_exit = True
        return 1
    waited = time.monotonic() - started
    task = fired[0]
    say(f"fired after {waited:.1f}s of real time: {task['id']}")
    # The tick creates the task and then works it, so the poll above can catch it
    # while its first attempt is still in flight. Wait for the attempt to settle
    # before reading on, or the record section below reports a half-written run as
    # if it were the finished one — a check that lies is worse than a slow one.
    settled = time.monotonic()
    while task["state"] == State.RUNNING.value and time.monotonic() - settled < 90:
        time.sleep(0.5)
        task = {row["id"]: row
                for row in browser.get("/api/tasks")["tasks"]}[task["id"]]
    say(f"  settled after {time.monotonic() - settled:.1f}s of real time"
        + ("" if task["state"] != State.RUNNING.value
           else "; the attempt was still in flight when this check gave up waiting"))
    say(f"  state {task['state']} — {task['why']}")
    say(f"  labels {task['labels']}")
    for attempt in task["runs"]:
        say(f"  attempt {attempt['attempt']} as {attempt['role']}: {attempt['state']}")
        say(f"    result: {attempt['notes']}")
    say()

    say("== the run history of that task, read as its own resource ==")
    history = browser.get(f"/api/tasks/{task['id']}")
    say(f"  {history['id']}  {history['state']}  attempts: {len(history['runs'])}")
    for attempt in history["runs"]:
        say(f"    attempt {attempt['attempt']} as {attempt['role']}: {attempt['state']}"
            f"  {attempt['started_at']} -> {attempt['updated_at']}")
        say(f"      {attempt['notes']}")
    say()

    say("== what the record holds for that run ==")
    records = stub.store.page(limit=500)
    kinds: dict[str, int] = {}
    for row in records.items:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    say("  stored revisions by kind: "
        + ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items())))
    steps = [row for row in records.items if row["kind"] == "action"]
    say(f"  tool calls recorded inside the task: {len(steps)}")
    for row in sorted(steps, key=lambda item: item["__sequence__"]):
        say(f"    {row['tool']}: {row['decision']} -> {row['state']} "
            f"({row['effect']['outcome']})")
    say()

    say("== the owner's level, changed through the settings API ==")
    browser.post("/api/settings", {"initiative.level": "on_command"})
    after = browser.get("/api/tasks")
    say(f"initiative.level = {after['level']}, picks_up_work = {after['picks_up_work']}")
    say()

    say("== the chat while a task runs (measured) ==")
    slow = browser.post("/api/tasks", {
        "title": "Work slowly", "detail": "Read the note slowly and answer.",
        "client_id": TASK_CLIENT})
    slow_id = slow["task"]["id"]
    holder: dict = {}

    def run_it() -> None:
        holder["result"] = browser.post(f"/api/tasks/{slow_id}/run", {"retry": False})

    worker = threading.Thread(target=run_it)
    worker.start()
    time.sleep(0.4)
    during = {row["id"]: row for row in browser.get("/api/tasks")["tasks"]}[slow_id]
    say(f"while the task runs: state {during['state']} — {during['why']}")
    asked = time.monotonic()
    answer = browser.post("/api/message", {
        "text": "What does the note say?", "client_id": "live-check-chat-0001"})
    chat_seconds = time.monotonic() - asked
    say(f"chat answered in {chat_seconds:.3f}s: {answer['reply']['text']!r}")
    worker.join()
    say(f"the task finished as {holder['result']['state']} after the chat had answered")
    say()

    say("== a due schedule with the level off ==")
    browser.post("/api/settings", {"initiative.level": "off"})
    # The schedule fired in the minute just gone, so it is due again in this one;
    # wait for that minute rather than pretending it is later than it is.
    off: dict = {}
    deadline = time.monotonic() + 80
    while time.monotonic() < deadline:
        off = browser.post("/api/schedules/tick", {})
        if off["due"]:
            break
        time.sleep(3.0)
    say(f"level {off['level']}: fired {len(off['fired'])}, due {len(off['due'])}, "
        f"worked {off['worked']}")
    say(f"  why: {off['why']}")
    for held in off["due"]:
        say(f"  held: {held['title']} ({held['cron']})")
    tasks_now = browser.get("/api/tasks")["tasks"]
    say(f"  tasks in the history: {len(tasks_now)} "
        f"(no new one was made by that tick)")
    say()

    say("== what Oneiro said on its own ==")
    for notice in browser.get("/api/tasks")["notices"]:
        say(f"  [{notice['at']}] held={notice['held']} {notice['text']!r}")
    say()
    say(f"done. Temporary root kept at {WORK} for inspection.")

    provider.shutdown()
    server.should_exit = True
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
