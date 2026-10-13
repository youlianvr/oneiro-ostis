"""Live check for curated memory: the fact list, its source, and the value it replaced.

Run it with `python tests/live_memory_check.py`. It is not a unit test; it is the
evidence the plan asks for, exercised the way the product is used:

* a real console process on a free port, with its own data root, its own settings file
  and its own **explicitly named** graph, stopped at the end with its exit code read
  from the process;
* real HTTP: a fact written, then edited, then read back through `/api/memory/facts` —
  so what is asserted is the answer the screen itself receives, not a call into the
  module;
* the **earlier value** the edit replaced, with its own date and source, present in that
  answer; and the panel page carrying the containers the client script fills and the
  sentences it renders (both languages), so an empty screen cannot pass for a working one;
* `history_complete`, so a walk that stopped at its bound cannot be read as a full history;
* the owner's data root fingerprinted before and after: the live directory is read only.

Records go to the `demo` stream — the separate subject of experience the owner decided
demo records live in. The graph is either the one published at `ONEIRO_LIVE_GRAPH_PORT`
(pass a port to use that) or a container of this check's own, from the shipped image,
which is stopped and its volume retained at the end. The owner's memory, settings, data
root and console are never started and never written.
"""
from __future__ import annotations

import argparse
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

from oneiro import config, i18n                                 # noqa: E402

#: The owner's own data root, read from this process's environment: only ever hashed.
OWNER_ROOT = config.data_root()
#: Where this check keeps everything of its own.
(PROJECT / "_tmp").mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="oneiro-mem-live-", dir=PROJECT / "_tmp"))
#: 0 means "bring up a graph of its own"; a port means "use the one already there".
GRAPH_PORT = int(os.environ.get("ONEIRO_LIVE_GRAPH_PORT", "0") or 0)
GRAPH_IMAGE = "oneiro-rewrite-machine:checkpoint"
GRAPH_NAME = "oneiro-mem-" + WORK.name.removeprefix("oneiro-mem-live-")
GRAPH_VOLUME = GRAPH_NAME + "-kb"
#: The subject of experience this check writes in, through the declared setting.
STREAM = "demo"

#: Two facts of this run's own. A fact's id is the digest of the client id it arrived
#: with, so without a marker a second run would read the previous run's facts and would
#: be measuring them; `--marker` says what this run is about.
MARKER = ""
FIRST = ""
SECOND = ""
EDITED = ""

STEPS: list[dict[str, Any]] = []
FAILURES: list[str] = []


def _this_run(marker: str) -> None:
    global MARKER, FIRST, SECOND, EDITED
    MARKER = marker
    FIRST = f"Владелец пишет по-русски. [{marker}]"
    SECOND = f"Отчёты готовятся к пятнице. [{marker}]"
    EDITED = f"Владелец пишет по-русски и по-английски. [{marker}]"


_this_run(os.environ.get("ONEIRO_LIVE_MARKER", "") or
          time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(os.urandom(8)).hexdigest()[:6])


def say(text: str) -> None:
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


def use_graph(port: int) -> None:
    global GRAPH_PORT
    GRAPH_PORT = port


def start_private_graph(port: int) -> tuple[bool, str]:
    """A graph of this check's own, from the shipped image, on a free host port."""
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
    stopped = subprocess.run(["docker", "stop", "--timeout", "20", GRAPH_NAME], capture_output=True,
                             text=True, timeout=180, encoding="utf-8", errors="replace")
    return (stopped.stdout or stopped.stderr or "").strip()[:80]


def _request_once(port: int, path: str, body: Any = None, *, token: str = "") -> tuple[int, Any]:
    headers: dict[str, str] = {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        if token:
            headers["X-Oneiro-CSRF"] = token
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                  headers=headers, method="POST" if data else "GET")
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


def request(port: int, path: str, body: Any = None, *, token: str = "",
            tries: int = 6) -> tuple[int, Any]:
    """One real HTTP call; a 503 (nothing could be read just now) is asked again."""
    for attempt in range(1, tries + 1):
        status, payload = _request_once(port, path, body, token=token)
        if status != 503 or attempt == tries:
            return status, payload
        say(f"  [note] the graph answered 503 on {path}; asking again (attempt {attempt + 1})")
        time.sleep(1.0 + attempt)
    return status, payload


def fingerprint(root: Path) -> list[str]:
    """A digest per file, so "nothing was written" is a comparison and not a claim."""
    if not root.is_dir():
        return []
    return [f"{path.relative_to(root)} {hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in sorted(root.rglob("*")) if path.is_file()]


def prepare() -> dict[str, Any]:
    """A console's own world: its root, its settings file and its MCP list."""
    root = WORK
    (root / "runtime").mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text("{}", encoding="utf-8")
    (root / "mcp.json").write_text(json.dumps({"mcp": {}}), encoding="utf-8")
    return {"root": root}


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
        "ONEIRO_STREAM": STREAM,
        "ONEIRO_LLM_BASE_URL": "http://127.0.0.1:9/v1",
        "ONEIRO_LLM_API_KEY": "live-check-key",
        "ONEIRO_LLM_MODEL": "stub/live-check",
        "ONEIRO_MCP_AUTOSTART": "false",
    })
    for name in ("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"):
        env.pop(name, None)
    return env


def start_console(world: dict[str, Any], port: int) -> tuple[subprocess.Popen, Path]:
    log_path: Path = world["root"] / "console.log"
    handle = log_path.open("w", encoding="utf-8")
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, str(TESTS / "live_hooks_serve.py"), "--stream", STREAM],
        cwd=str(PROJECT), env=base_env(world, web_port=port), stdout=handle,
        stderr=subprocess.STDOUT, creationflags=creation)
    return process, log_path


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
            if request(port, "/api/session", tries=1)[0] == 200:
                return True, f"{time.monotonic() - started:.1f}s after start"
        except OSError:
            pass
        time.sleep(0.25)
    return False, f"no answer within {seconds:.0f}s"


def csrf_of(port: int) -> str:
    status, payload = request(port, "/api/session")
    if status != 200 or not isinstance(payload, dict):
        return ""
    return str(payload.get("csrf") or "")


def check_listing(port: int, language: str) -> dict[str, Any]:
    """Everything the fact answer must carry, measured against the answer itself."""
    status, listing = request(port, "/api/memory/facts")
    step("facts are read back over HTTP", status == 200, f"GET /api/memory/facts -> {status}")
    if status != 200 or not isinstance(listing, dict):
        return {}
    facts = listing.get("facts") or []
    texts = [fact.get("text") for fact in facts]
    # The two facts *in force*: the edited value of the first, and the second one.
    # (The value the first fact replaced is history, and is asserted below under
    # `superseded` — this list is what a reply would be given.)
    step("both facts in force are listed", texts == [EDITED, SECOND], f"texts={texts}")
    edited = next((fact for fact in facts if fact.get("text") == EDITED), {})
    step("a fact carries its source", edited.get("provenance") == "owner_instruction",
         f"provenance={edited.get('provenance')!r}")
    step("a fact carries both dates",
         bool(edited.get("created_at")) and bool(edited.get("updated_at")),
         f"created={edited.get('created_at')} updated={edited.get('updated_at')}")
    earlier = edited.get("superseded") or []
    step("the value the edit replaced is kept, with its own date and source",
         len(earlier) == 1 and earlier[0].get("text") == FIRST
         and earlier[0].get("revision") == 1
         and earlier[0].get("provenance") == "owner_instruction"
         and bool(earlier[0].get("updated_at")),
         f"superseded={json.dumps(earlier, ensure_ascii=False)}")
    step("the read says whether the history was read in full",
         listing.get("history_complete") is True,
         f"history_complete={listing.get('history_complete')!r}")
    step("the budget counts the facts in force",
         listing.get("used_chars") == len(EDITED) + len(SECOND),
         f"used_chars={listing.get('used_chars')} expected={len(EDITED) + len(SECOND)}")
    # The page the owner opens: it must carry what the client script fills, and the
    # sentences it renders, in the language it was asked for.
    page_status, page = request(port, f"/memory?lang={language}")
    containers = all(f'id="{element}"' in str(page)
                     for element in ("facts-list", "facts-meter", "facts-error", "fact-add"))
    step(f"the panel page carries the list and the form ({language})",
         page_status == 200 and containers, f"GET /memory?lang={language} -> {page_status}")
    for key in ("facts.earlier", "facts.source", "facts.source.owner_instruction",
                "facts.added", "facts.load_failed"):
        said = i18n.t(key, language)
        step(f"the page carries {key} in {language}", said in str(page), f"{key}={said!r}")
    return listing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-port", type=int, default=GRAPH_PORT,
                        help="use an already running graph on this port")
    parser.add_argument("--language", default="ru", choices=("ru", "en"))
    args = parser.parse_args(argv)

    say(f"curated-memory live check: marker {MARKER}")
    say(f"  own root: {WORK}")
    before = fingerprint(OWNER_ROOT)
    world = prepare()
    owned_graph = False
    if args.graph_port:
        use_graph(args.graph_port)
        say(f"  graph: already running at 127.0.0.1:{GRAPH_PORT}")
    else:
        port = free_port()
        started, detail = start_private_graph(port)
        step("a graph of this check's own came up", started, f"container {GRAPH_NAME}: {detail}")
        if not started:
            return 1
        owned_graph = True
        use_graph(port)
        say(f"  graph: container {GRAPH_NAME} on 127.0.0.1:{GRAPH_PORT}")

    web_port = free_port()
    process, log_path = start_console(world, web_port)
    exit_code: int | None = None
    try:
        ready, detail = wait_ready(process, web_port)
        step("the console answered", ready, f"http://127.0.0.1:{web_port}/api/session: {detail}")
        if not ready:
            return 1
        token = csrf_of(web_port)
        step("a session token was issued", bool(token), "GET /api/session")
        if not token:
            return 1

        status, answer = request(web_port, "/api/memory/facts",
                                 {"text": FIRST, "client_id": f"fact-live-first-{MARKER}"},
                                 token=token)
        step("a fact is written over HTTP", status == 200,
             f"POST /api/memory/facts -> {status} {json.dumps(answer, ensure_ascii=False)[:160]}")
        if status != 200:
            return 1
        fact_id = str((answer.get("fact") or {}).get("id") or "")
        step("the fact answers with its own id", fact_id.startswith("fact-"), f"id={fact_id}")

        status, answer = request(web_port, f"/api/memory/facts/{fact_id}/edit",
                                 {"text": EDITED, "client_id": f"fact-live-edit-{MARKER}",
                                  "revision": 1}, token=token)
        step("the fact is edited over HTTP", status == 200,
             f"POST .../edit -> {status} {json.dumps(answer, ensure_ascii=False)[:160]}")

        status, answer = request(web_port, "/api/memory/facts",
                                 {"text": SECOND, "client_id": f"fact-live-second-{MARKER}"},
                                 token=token)
        step("a second fact is written", status == 200, f"POST /api/memory/facts -> {status}")

        listing = check_listing(web_port, args.language)
        (WORK / "facts.json").write_text(json.dumps(listing, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        say(f"  evidence: {WORK / 'facts.json'}")
    finally:
        exit_code, how = stop(process)
        step("the console stopped on request", exit_code == 0, f"exit {exit_code}, {how}")
        if owned_graph:
            say(f"  graph stop: {stop_private_graph()} (volume {GRAPH_VOLUME} retained)")

    after = fingerprint(OWNER_ROOT)
    step("the owner's data root was not written", before == after,
         f"{len(before)} files fingerprinted before and after")

    (WORK / "summary.json").write_text(json.dumps({
        "marker": MARKER, "graph_port": GRAPH_PORT, "web_port": web_port, "stream": STREAM,
        "console_exit": exit_code, "console_log": str(log_path), "steps": STEPS,
        "failures": FAILURES}, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"  summary: {WORK / 'summary.json'}")
    say(f"  console log: {log_path}")
    if FAILURES:
        say(f"FAILED: {len(FAILURES)} step(s): " + "; ".join(FAILURES[:4]))
        return 1
    say(f"OK: {len(STEPS)} steps, curated memory reads back with its source and its replaced value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
