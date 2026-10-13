"""Live check for the proactive moments: the real clock, the real graph, real HTTP.

Run it with `python tests/live_proactive_check.py`. It is not a unit test — it is the
end-to-end evidence the plan asks for, exercised the way the product is used:

* a graph of this check's own, from the shipped image, on a free host port, so neither
  the owner's graph nor the stream their own work lives in is touched;
* a data root, a settings file and an MCP list of the check's own in a temporary
  directory, with `initiative.quiet_hours` set to a window that ends a few minutes from
  now — a window nobody has to wait until 09:00 for;
* the product's own application, served by uvicorn with **its own clock**
  (`create_app(scheduler=True)`), so every moment below is decided by `schedule.tick`
  and never by this check calling a function directly;
* the model is the one stub: a local HTTP provider on loopback that refuses on purpose
  when the owner's own words ask it to. Neither the owner's provider nor a live channel
  is touched by a check.

What it measures, each step with the artifact it left:

1. a task created by a schedule during the quiet hours, worked by the application's own
   clock, its outcome notice **held** for the quiet window;
2. an item whose attempt fails, reminded **once** while nobody answers it — the reminder
   held too — and nothing more once the item is finished;
3. the digest at the end of the quiet window, read back over HTTP from the notice list
   **and** from the conversation it was said in, which is the transport a channel would
   carry: no live channel is enabled here;
4. `POST /api/schedules/tick` afterwards, showing the tick's own report — the digest is
   already said, with the reason, rather than said twice;
5. the owner's own data root, hashed before and after: nothing of it was written.
"""
from __future__ import annotations

import argparse
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
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

import uvicorn                                                       # noqa: E402
from oneiro import config, web                                       # noqa: E402
from oneiro.graph_worker import GraphWorker                          # noqa: E402
from oneiro.runtime import Runtime                                   # noqa: E402

#: Where this check keeps everything of its own. Under the project's own `_tmp`, which
#: is ignored by Git, so the evidence can be inspected afterwards.
(PROJECT / "_tmp").mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="oneiro-pro-live-", dir=PROJECT / "_tmp"))
#: The owner's own data root, read from this process's environment: only ever hashed.
OWNER_ROOT = config.data_root()
#: 0 means "bring up a graph of its own"; a port means "use the one already there".
GRAPH_PORT = int(os.environ.get("ONEIRO_LIVE_GRAPH_PORT", "0") or 0)
GRAPH_IMAGE = "oneiro-rewrite-machine:checkpoint"
SUFFIX = WORK.name.removeprefix("oneiro-pro-live-")
GRAPH_NAME = "oneiro-pro-" + SUFFIX
GRAPH_VOLUME = GRAPH_NAME + "-kb"
#: The subject of experience this check writes in: the demo's own, never the owner's.
STREAM = "demo"
#: How long the quiet window set up below lasts. Long enough that everything meant to
#: happen inside it does — a scheduled task firing, a failing item, and its reminder —
#: with slack for the tick that works one task at a time, and short enough to wait for
#: its end afterwards. Measured at 3 minutes this check's reminder landed one tick late,
#: outside the window, which is the product behaving correctly and the check assuming
#: too much: 5 minutes is the slack that measurement bought.
WINDOW_MINUTES = 5
#: The words that make the stub provider refuse, so one item can be left unfinished.
REFUSE = "live-proactive-refuse"
SCHEDULE_CLIENT = "live-pro-active-schedule-0001"
ITEM_CLIENT = "live-pro-active-item-0001"

STEPS: list[dict[str, Any]] = []
FAILURES: list[str] = []
#: The stub provider's own switch: it refuses while the check wants an unfinished item,
#: and serves once that item is being handled.
PROVIDER: dict[str, Any] = {"refuse": True, "calls": 0}


def say(text: str = "") -> None:
    print(text, flush=True)


def step(what: str, ok: bool, detail: str, **extra: Any) -> None:
    """One measured step, recorded whether it passed or not."""
    STEPS.append({"step": what, "ok": ok, "detail": detail, **extra})
    say(f"{'ok  ' if ok else 'FAIL'} {what}: {detail}")
    if not ok:
        FAILURES.append(f"{what}: {detail}")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fingerprint(root: Path) -> list[str]:
    """A digest per file, so \"nothing was written\" is a comparison, not a claim."""
    if not root.is_dir():
        return []
    return [f"{path.relative_to(root)} {hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in sorted(root.rglob("*")) if path.is_file()]


# ---------- the provider the product's own workers call ----------


class Provider(BaseHTTPRequestHandler):
    """A loopback provider that speaks the chat-completions shape the product uses.

    It refuses when the words it is given carry the marker and the check is still asking
    for an unfinished item, and answers otherwise. Nothing else about it is special: the
    product's registry, retries, roles and records are its own.
    """

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        spoken = " ".join(str(item.get("content") or "") for item in body.get("messages") or [])
        PROVIDER["calls"] += 1
        if PROVIDER["refuse"] and REFUSE in spoken:
            payload = json.dumps({"error": {"message": "the provider refused this call"}}
                                 ).encode("utf-8")
            self.send_response(500)
        else:
            payload = json.dumps({"choices": [
                {"message": {"role": "assistant",
                             "content": "done: the note was read and it says to keep "
                                        "the schedule small."}}]}).encode("utf-8")
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: object) -> None:
        return None


# ---------- the graph, of this check's own ----------


def start_private_graph(port: int) -> tuple[bool, str]:
    """A graph of this check's own, from the shipped image, on a free host port.

    Each run has its own container and its own retained volume. No existing container
    or data is removed, and stopping preserves the evidence for later inspection.
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
    stopped = subprocess.run(["docker", "stop", "--timeout", "20", GRAPH_NAME],
                             capture_output=True, text=True, timeout=180,
                             encoding="utf-8", errors="replace")
    return (stopped.stdout or stopped.stderr or "").strip()[:80]


# ---------- real HTTP, the way the console does it ----------


def _once(port: int, path: str, body: Any = None, *, token: str = "",
          method: str | None = None) -> tuple[int, Any]:
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        if token:
            headers["X-Oneiro-CSRF"] = token
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                  headers=headers, method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(call, timeout=120) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, {"error": raw[:200]}


def request(port: int, path: str, body: Any = None, *, token: str = "",
            method: str | None = None, tries: int = 5) -> tuple[int, Any]:
    """One real HTTP call. A 503 — nothing could be read just now — is asked again.

    The graph is a service that warms up and occasionally aborts a fresh connection while
    it does, so a 503 is asked again and counted rather than read as a product failure.
    Every other answer, refusals included, is passed on untouched.
    """
    for attempt in range(1, tries + 1):
        status, payload = _once(port, path, body, token=token, method=method)
        if status != 503 or attempt == tries:
            return status, payload
        say(f"  [note] the graph answered 503 on {path}; asking again "
            f"(attempt {attempt + 1} of {tries})")
        time.sleep(1.0 + attempt)
    return status, payload


def csrf_of(port: int) -> str:
    status, payload = request(port, "/api/session")
    if status != 200 or not isinstance(payload, dict):
        return ""
    return str(payload.get("csrf") or "")


def notices_of(port: int) -> list[dict[str, Any]]:
    status, payload = request(port, "/api/tasks")
    if status != 200 or not isinstance(payload, dict):
        return []
    return list(payload.get("notices") or [])


def task_of(port: int, task_id: str) -> dict[str, Any]:
    status, payload = request(port, f"/api/tasks/{task_id}")
    return payload if status == 200 and isinstance(payload, dict) else {}


def listed_tasks(port: int) -> list[dict[str, Any]]:
    """The task list as the page reads it."""
    status, payload = request(port, "/api/tasks")
    if status != 200 or not isinstance(payload, dict):
        return []
    return list(payload.get("tasks") or [])


def wait_until(seconds: float, probe: Any, *, every: float = 2.0) -> tuple[bool, Any]:
    """Poll a probe until it answers yes, or the time is up. Bounded, never open-ended."""
    started = time.monotonic()
    answer: Any = None
    while time.monotonic() - started < seconds:
        ok, answer = probe()
        if ok:
            return True, answer
        time.sleep(every)
    return False, answer


# ---------- the run of this check ----------


def prepare(root: Path) -> dict[str, Any]:
    """The check's own world: a settings file, a quiet window, and the server's ports."""
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    end = now + timedelta(minutes=WINDOW_MINUTES)
    if end.day != now.day:                      # never a window that wraps at midnight
        end = now.replace(hour=23, minute=59)
        now = end - timedelta(minutes=WINDOW_MINUTES)
    window = f"{now:%H:%M}-{end:%H:%M}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(json.dumps({
        "initiative.level": "proactive",
        "initiative.quiet_hours": window,
        "initiative.digest": True,
        "initiative.reminders": True,
        "initiative.reminder_after": 1,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "mcp.json").write_text(json.dumps({"servers": []}), encoding="utf-8")
    return {"root": root, "window": window, "end": end}


def base_env(world: dict[str, Any], *, web_port: int, provider_port: int) -> dict[str, str]:
    """This process's own environment: the check's root, its graph, its stub provider."""
    root: Path = world["root"]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "ONEIRO_DATA_DIR": str(root / "runtime"),
           "ONEIRO_SETTINGS_FILE": str(root / "settings.json"),
           "ONEIRO_MCP_FILE": str(root / "mcp.json"),
           "ONEIRO_KEYS_FILE": str(root / "no-keys.env"),
           "ONEIRO_WEB_HOST": "127.0.0.1",
           "ONEIRO_WEB_PORT": str(web_port),
           "ONEIRO_HOST": "127.0.0.1",
           "ONEIRO_PORT": str(GRAPH_PORT),
           "ONEIRO_STREAM": STREAM,
           "ONEIRO_LLM_BASE_URL": f"http://127.0.0.1:{provider_port}/v1",
           "ONEIRO_LLM_API_KEY": "live-check-key",
           "ONEIRO_LLM_MODEL": "stub/live-check",
           "ONEIRO_MCP_AUTOSTART": "false"}
    for name in ("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"):
        env.pop(name, None)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-port", type=int, default=GRAPH_PORT,
                        help="use an already running graph on this port")
    args = parser.parse_args(argv)

    started_at = time.monotonic()
    world = prepare(WORK / "root")
    say(f"proactive live check: quiet window {world['window']}, "
        f"ending {world['end']:%H:%M}")
    say(f"  own root: {world['root']}")
    before = fingerprint(OWNER_ROOT)

    owned_graph = False
    port = args.graph_port or free_port()
    if args.graph_port:
        say(f"  graph: already running at 127.0.0.1:{port}")
    else:
        started, detail = start_private_graph(port)
        step("a graph of this check's own came up", started,
             f"container {GRAPH_NAME}: {detail}")
        if not started:
            return 1
        owned_graph = True
        say(f"  graph: container {GRAPH_NAME} on 127.0.0.1:{port}")
    globals()["GRAPH_PORT"] = port

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    web_port = free_port()
    for name, value in base_env(world, web_port=web_port,
                                provider_port=int(provider.server_port)).items():
        os.environ[name] = value

    # The product's own application, on the product's own server, with its own clock.
    # `scheduler=True` is the whole point: every proactive moment in this check is
    # decided by the application's tick, not by a call this check makes.
    worker = GraphWorker(f"ws://127.0.0.1:{GRAPH_PORT}/ws_json", STREAM,
                         Path(os.environ["ONEIRO_DATA_DIR"]) / "graph-writer.lock")
    server = uvicorn.Server(uvicorn.Config(
        web.create_app(runtime=Runtime(graph=worker), scheduler=True),
        host="127.0.0.1", port=web_port, access_log=False, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    say(f"  console: http://127.0.0.1:{web_port}  (stream {STREAM}, "
        f"stub provider on {provider.server_port})")

    exit_code: int | None = None
    try:
        ready, _ = wait_until(60, lambda: (request(web_port, "/api/session", tries=1)[0] == 200,
                                          None), every=0.25)
        step("the console answered", ready, f"GET /api/session -> {'200' if ready else 'no answer'}")
        if not ready:
            return 1
        token = csrf_of(web_port)
        step("a session token was issued", bool(token), "GET /api/session")
        if not token:
            return 1
        up, _ = wait_until(300, lambda: (request(web_port, "/api/tasks")[0] == 200, None))
        step("the memory answered through the console", up,
             f"GET /api/tasks -> {'200' if up else 'no answer within 300s'}")
        if not up:
            return 1
        # A graph that has just come up answers slowly for a while, and a slow read and a
        # slow tick are the same load on this machine. Three reads are timed here so a run
        # that stalls later can be read against the graph it was given rather than guessed
        # at: measured 2026-10-13, one run stalled inside a tick while the graph was warming.
        warm: list[float] = []
        for _ in range(3):
            reading = time.monotonic()
            request(web_port, "/api/tasks")
            warm.append(round(time.monotonic() - reading, 2))
            time.sleep(1.0)
        say(f"  the memory answers a task list in {warm} s (three reads, one second apart)")

        status, listed = request(web_port, "/api/tasks")
        step("the settings this check declared are in force",
             listed.get("level") == "proactive" and listed.get("picks_up_work") is True
             and listed.get("quiet_hours") == world["window"],
             f"level={listed.get('level')!r} picks_up_work={listed.get('picks_up_work')!r} "
             f"quiet_hours={listed.get('quiet_hours')!r}")

        # 1. A schedule that fires inside the quiet window, worked by the app's own clock.
        fire_at = (datetime.now().astimezone().replace(second=0, microsecond=0)
                   + timedelta(minutes=1))
        cron = f"{fire_at:%M %H} * * *"
        status, created = request(web_port, "/api/schedules",
                                  {"title": "Read the note during the quiet hours",
                                   "detail": "Read the note and say what it says.",
                                   "cron": cron, "client_id": SCHEDULE_CLIENT}, token=token)
        step("a schedule is created through the API", status == 200,
             f"POST /api/schedules {cron!r} -> {status}")
        if status != 200:
            return 1
        schedule_id = str((created.get("schedule") or {}).get("id") or "")

        def its_task() -> tuple[bool, Any]:
            """The task this schedule made, once the clock has made it."""
            made = next((str(row["id"]) for row in listed_tasks(web_port)
                         if f"schedule:{schedule_id}" in (row.get("labels") or ())), None)
            return made is not None, made

        fired, task_id = wait_until(WINDOW_MINUTES * 60 + 90, its_task)
        step("the application's own clock fired it during the quiet hours", fired,
             f"the task the schedule made: {task_id}")
        if not fired:
            return 1
        # Bounded by the window itself: the clock works one task per tick, and a graph
        # that has just come up can make one tick long. An open window is the honest
        # bound, with a minute of slack for the tick that reads the result.
        settled, task = wait_until(WINDOW_MINUTES * 60 + 120, lambda: (
            task_of(web_port, task_id).get("state") not in (None, "", "running"),
            task_of(web_port, task_id)))
        step("its attempt was worked by the product and finished", settled
             and task.get("state") == "completed",
             f"state={task.get('state')!r} notes={str(task.get('last_result'))[:60]!r}")
        held = [row for row in notices_of(web_port)
                if row["conversation_id"] == f"task-{task_id}"]
        notice: dict[str, Any] = held[0] if held else {}
        step("its outcome notice is held for the quiet window",
             bool(held) and notice.get("held") is True
             and "Read the note during the quiet hours" in str(notice.get("text") or ""),
             f"{len(held)} notice(s): {str(notice.get('text'))[:60]!r} "
             f"held={notice.get('held')}")

        # 2. An item that stays unfinished: refused by the provider, reminded once.
        status, made = request(web_port, "/api/tasks",
                               {"title": "Fix the report",
                                "detail": f"{REFUSE}: this one is left unfinished on purpose.",
                                "client_id": ITEM_CLIENT}, token=token)
        item_id = str((made.get("task") or {}).get("id") or "")
        step("an item is created through the API", status == 200 and bool(item_id),
             f"POST /api/tasks -> {status} id={item_id}")
        if not item_id:
            return 1
        status, ran = request(web_port, f"/api/tasks/{item_id}/run", {"retry": False},
                              token=token)
        step("the owner's own run of it fails, and it stays unfinished",
             status == 200 and ran.get("state") == "failed",
             f"POST /api/tasks/{item_id}/run -> {status} state={ran.get('state')!r} "
             f"{str(ran.get('text'))[:60]!r}")
        reminded, rows = wait_until(WINDOW_MINUTES * 60, lambda: (
            (found := [row for row in notices_of(web_port)
                       if row["conversation_id"] == f"task-{item_id}"
                       and row["text"].startswith("Still unfinished:")]) != [], found))
        step("one reminder is said about it while nobody answers", reminded,
             f"{len(rows)} reminder(s): {rows[0]['text'][:70]!r} held="
             f"{rows[0]['held'] if rows else None}")
        step("the reminder respects the quiet window (held, not hidden)",
             bool(rows) and rows[0]["held"] is True, f"held={rows[0]['held'] if rows else None}")
        first_id = rows[0]["id"] if rows else ""
        time.sleep(75)                          # one more tick of the product's own clock
        again_reminders = [row for row in notices_of(web_port)
                           if row["conversation_id"] == f"task-{item_id}"
                           and row["text"].startswith("Still unfinished:")]
        step("a later tick says nothing more about it", len(again_reminders) == 1
             and again_reminders[0]["id"] == first_id,
             f"{len(again_reminders)} reminder(s) after another tick")

        # 3. Handled: the owner's retry carries it, and the reminder stops.
        PROVIDER["refuse"] = False
        status, carried = request(web_port, f"/api/tasks/{item_id}/run", {"retry": True},
                                  token=token)
        # A started attempt answers with the run it worked; only a refusal carries
        # `started: false` and the reason, so the key's absence is the good case.
        say(f"  the owner's retry: HTTP {status} started={carried.get('started', True)} "
            f"state={carried.get('state')!r} {str(carried.get('why') or '')[:80]}")
        done, task = wait_until(180, lambda: (
            task_of(web_port, item_id).get("state") == "completed", task_of(web_port, item_id)))
        step("the item is finished by the owner's own retry", done,
             f"state={task.get('state')!r} attempts={len(task.get('runs') or [])}")
        time.sleep(75)                          # one more tick after it was handled
        later_reminders = [row for row in notices_of(web_port)
                           if row["conversation_id"] == f"task-{item_id}"
                           and row["text"].startswith("Still unfinished:")]
        step("nothing more is said about it once it is finished",
             len(later_reminders) == 1 and later_reminders[0]["id"] == first_id,
             f"{len(later_reminders)} reminder(s) after the item was finished")

        # 4. The digest, at the end of the quiet window, read back as a notice and as a
        #    message in the conversation a channel would carry.
        left = max(0.0, (world["end"] - datetime.now().astimezone()).total_seconds())
        say(f"  waiting {left:.0f}s for the quiet window to end, then for the tick after it")
        seen, found_digests = wait_until(left + 120, lambda: (
            (found := [row for row in notices_of(web_port)
                       if row["conversation_id"] == "main"
                       and row["text"].startswith("While you were quiet")]) != [], found))
        digest_rows: list[dict[str, Any]] = list(found_digests or [])
        step("the digest is said when the quiet hours end", seen,
             f"{len(digest_rows)} digest(s): {(digest_rows[0]['text'].splitlines()[0] if digest_rows else '')!r}")
        if digest_rows:
            text = digest_rows[0]["text"]
            step("it names what finished inside the window",
                 "- done: Read the note during the quiet hours" in text,
                 f"lines: {len(text.splitlines())}")
            step("it is said outside the quiet window, so it is not held",
                 digest_rows[0]["held"] is False, f"held={digest_rows[0]['held']}")
            say("  the digest, as the owner reads it:")
            for line in text.splitlines():
                say(f"    | {line}")

        status, carried = request(web_port, "/api/conversations/main/messages?limit=20")
        messages = list((carried or {}).get("messages") or []) if status == 200 else []
        same = [row for row in messages
                if row["text"].startswith("While you were quiet")
                and digest_rows and row["id"] == digest_rows[0]["id"]]
        step("the digest reached the conversation, which is the transport", bool(same),
             f"GET /api/conversations/main/messages -> {status}, {len(messages)} message(s), "
             f"{len(same)} of them the digest")

        status, tick = request(web_port, "/api/schedules/tick", {}, token=token)
        spoken = (tick or {}).get("proactive") or {}
        said = (spoken or {}).get("digest") or {}
        step("the next tick reports it as already said, with the reason",
             status == 200 and said.get("already") is True and "already reported" in str(said.get("why")),
             f"POST /api/schedules/tick -> {status} "
             f"digest={json.dumps({key: said.get(key) for key in ('said', 'already', 'at')}, ensure_ascii=False)}")
        (WORK / "tick.json").write_text(json.dumps(tick, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
        (WORK / "notices.json").write_text(
            json.dumps(notices_of(web_port), ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        provider.shutdown()
        stopping = time.monotonic()
        server.should_exit = True
        thread.join(timeout=90)
        exit_code = 0 if not thread.is_alive() else 1
        step("the console stopped on request", exit_code == 0,
             (f"stopped in {time.monotonic() - stopping:.1f}s, asked to stop" if exit_code == 0
              else f"still serving after 90 s (asked at {stopping - started_at:.0f}s into the run)"))
        if owned_graph:
            say(f"  graph stop: {stop_private_graph()} (volume {GRAPH_VOLUME} retained)")

    after = fingerprint(OWNER_ROOT)
    step("the owner's data root was not written", before == after,
         f"{len(before)} files fingerprinted before and after")

    (WORK / "summary.json").write_text(json.dumps({
        "window": world["window"], "graph_port": GRAPH_PORT, "stream": STREAM,
        "provider_calls": PROVIDER["calls"], "steps": STEPS, "failures": FAILURES},
        ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"  summary: {WORK / 'summary.json'}")
    if FAILURES:
        say(f"FAILED: {len(FAILURES)} step(s): " + "; ".join(FAILURES[:4]))
        return 1
    say(f"OK: {len(STEPS)} steps; the digest and the reminder were said by the "
        f"application's own clock and read back over HTTP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
