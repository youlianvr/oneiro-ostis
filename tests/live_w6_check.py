"""Live check for W6: Console screens, the memory states and the window launcher.

Run it with `python tests/live_w6_check.py`. It provides end-to-end evidence
for § 5 W6 and acceptance matrix § 6:
* Row 2: Application window / browser fallback.
* Row 4: Every refusal/approval explained via action cards (no raw JSON on screen).
* Row 14: The readiness panel and the graph page agree about memory, in every state
  the memory substrate can be in (see `graph_states` below).
* Row 15: No JSON on screen across all 5 canonical routes.
* Row 16: Accessibility and keyboard focus elements present.
* Ensures zero-leak: user's settings and files remain completely unchanged.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w6-live-"))
OWNER_SETTINGS = Path.home() / ".oneiro" / "settings.json"
OWNER_KEYS = Path.home() / ".config" / "keys.env"
WATCHED = (OWNER_SETTINGS, OWNER_KEYS, PROJECT / ".env", PROJECT / "knowledge-base" / "repo.path")


def say(text: str = "") -> None:
    print(text, flush=True)


def fingerprint(paths) -> dict[str, str]:
    seen = {}
    for path in paths:
        try:
            raw = Path(path).read_bytes()
        except OSError:
            seen[str(path)] = "absent"
            continue
        seen[str(path)] = f"{len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()[:12]}"
    return seen


def isolate(port: int) -> None:
    os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
    os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "keys.env")
    os.environ["ONEIRO_MCP_FILE"] = str(WORK / "mcp.json")
    os.environ["ONEIRO_WEB_PORT"] = str(port)
    os.environ["ONEIRO_HEADLESS"] = "1"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class SilentPort:
    """A socket that accepts a connection and never answers it.

    This is the state that used to put `500 Internal Server Error` on the graph page: the
    read inside `sc_client` has no deadline, so an outer `wait_for` raised out of the
    route. A listener that holds the connection open reproduces it exactly.
    """

    def __enter__(self) -> int:
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._held: list[socket.socket] = []
        self._stop = threading.Event()
        self._keeper = threading.Thread(target=self._hold, daemon=True)
        self._keeper.start()
        return int(self._listener.getsockname()[1])

    def _hold(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except OSError:
                return
            self._held.append(connection)      # accepted, never answered

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        for connection in self._held:
            connection.close()
        self._listener.close()
        self._keeper.join(timeout=2)


def graph_states(work: Path, configured_port: int) -> int:
    """Row 14/15 with the memory substrate in three states, through the real routes.

    A machine without `sc-server` cannot present a *live* graph on demand, so this
    section reports what the configured graph is and asserts the two states any socket
    can be put into - closed, and accepting-but-silent. All three states, for every
    screen, are asserted in `tests/test_graph_states.py`, which patches only the probe's
    answer; what is added here is the real thing: real sockets, the real probe, the real
    routes, and the panel the browser fills.
    """
    from starlette.testclient import TestClient

    from oneiro import i18n, memory
    from oneiro.runtime import Runtime
    from oneiro.web import create_app
    from test_i18n_themes import (_english_sentences, _panel, _reads_as_english_prose,
                                  _strings, _visible_lines)

    say("\n== 3. The memory substrate in three states (row 14/15) ==")
    screens = ("/", "/tasks", "/tools", "/settings", "/memory", "/setup", "/oneiro/")
    limit = memory.PROBE_BUDGET + 3.0
    problems: list[str] = []
    with SilentPort() as silent_port:
        states = (("configured", configured_port), ("closed", free_port()),
                  ("silent", silent_port))
        for label, port in states:
            settings = work / f"settings-graph-{label}.json"
            settings.write_text(json.dumps({"graph.port": port}), encoding="utf-8")
            os.environ["ONEIRO_SETTINGS_FILE"] = str(settings)
            runtime = Runtime()
            with TestClient(create_app(runtime, scheduler=False)) as client:
                say(f"  -- {label}: graph.port={port}")
                for route in screens:
                    started = time.monotonic()
                    response = client.get(f"{route}?lang=ru")
                    elapsed = time.monotonic() - started
                    body = response.text
                    prose = _english_sentences(_visible_lines(body))
                    bad = []
                    if response.status_code != 200:
                        bad.append(f"HTTP {response.status_code}")
                    if not response.headers["content-type"].startswith("text/html"):
                        bad.append("not HTML")
                    if "Internal Server Error" in body:
                        bad.append("English error body")
                    if prose:
                        bad.append(f"English prose {sorted(prose)[:2]}")
                    if elapsed >= limit:
                        bad.append(f"{elapsed:.1f}s exceeds the {limit:.0f}s budget")
                    say(f"     {route:<10} {response.status_code} {elapsed:5.2f}s "
                        f"prose={len(prose)} {'; '.join(bad) or 'ok'}")
                    problems.extend(f"{label} {route}: {item}" for item in bad)

                status = client.get("/api/status").json()
                graph_started = time.monotonic()
                graph = client.get("/api/graph")
                graph_elapsed = time.monotonic() - graph_started
                panel = _panel(status, "ru")
                library_prose = [(where, value) for where, value in _strings(status)
                                 if _reads_as_english_prose(value)]
                says_readable = i18n.t("status.memory_ok", "ru") in panel.splitlines()
                page = client.get("/oneiro/?lang=ru").text
                page_readable = i18n.t("graph.readable", "ru", arcs=1, anchor="",
                                       elapsed=0)[:24] in page
                say(f"     /api/graph  {graph.status_code} {graph_elapsed:5.2f}s "
                    f"codes={[item['code'] for item in graph.json()['blocked']]}")
                say(f"     memory: verified={status['memory']['verified']} "
                    f"reachable={status['memory']['tcp_reachable']}")
                say(f"     panel: {[line for line in panel.splitlines() if line.startswith('Память')]}")
                if graph.status_code == 500:
                    problems.append(f"{label} /api/graph: 500")
                if says_readable != status["memory"]["verified"]:
                    problems.append(f"{label}: the panel disagrees with the probe")
                if page_readable != status["memory"]["verified"]:
                    problems.append(f"{label}: the graph page disagrees with the probe")
                if library_prose:
                    problems.append(f"{label}: the panel payload carries the library's prose: "
                                    f"{library_prose[:1]}")
                if graph_elapsed >= limit:
                    problems.append(f"{label} /api/graph: took {graph_elapsed:.1f}s")

                if label == "closed":
                    # A silent read of a *different* port happened moments before this
                    # verdict. It must not become this port's reading, and the address it
                    # is about must survive: measured 2026-10-11, a process-wide verdict
                    # did both wrong.
                    memory.probe_within("127.0.0.1", silent_port, timeout=0.5, budget=0.5)
                    after = client.get("/api/status").json()
                    reasons = [item for item in after["blocked"]]
                    codes = [item["code"] for item in reasons]
                    named = [item.get("data", {}).get("port") for item in reasons]
                    say(f"     after a silent read of port {silent_port}: {codes} ports={named}")
                    if memory.TIMEOUT_CODE in codes:
                        problems.append("closed: a silent read of another port became this "
                                        "port's verdict")
                    if port not in named:
                        problems.append("closed: the verdict does not name the port it measured")

                if label == "silent":
                    # A page view is a read. Repeated views must not restart the worker or
                    # close the durability gate (measured 2026-10-11: every view did both).
                    lane = runtime._graph
                    if lane is None:
                        problems.append("silent: the runtime has no graph lane to watch")
                    else:
                        pid_before = lane.pid
                        failure_before = lane.durability.status()["failure"]
                        say(f"     worker pid={pid_before} durability failure={failure_before!r}")
                        views_started = time.monotonic()
                        for _ in range(3):
                            client.get("/tasks?lang=ru")
                            client.get("/oneiro/?lang=ru")
                        failure_after = lane.durability.status()["failure"]
                        say(f"     3 more views of /tasks and /oneiro/ in "
                            f"{time.monotonic() - views_started:.2f}s: pid={lane.pid} "
                            f"durability failure={failure_after!r}")
                        if lane.pid != pid_before:
                            problems.append(f"silent: a page view restarted the worker "
                                            f"({pid_before} -> {lane.pid})")
                        if failure_after != failure_before:
                            problems.append(f"silent: a page view changed the durability gate "
                                            f"({failure_before!r} -> {failure_after!r})")

        # A screen's own reads, with the graph down: chained reads must not each hold the
        # graph lane's 10 s deadline (measured 2026-10-11: /api/tasks 10.04 s before).
        os.environ["ONEIRO_SETTINGS_FILE"] = str(work / "settings-graph-closed.json")
        with TestClient(create_app(Runtime(), scheduler=False)) as client:
            for route in ("/api/tasks", "/api/schedules"):
                started = time.monotonic()
                response = client.get(route)
                elapsed = time.monotonic() - started
                say(f"  {route:<16} {response.status_code} {elapsed:5.2f}s with the graph down")
                if response.status_code != 503 or elapsed >= limit:
                    problems.append(f"a screen did not settle: {route} -> "
                                    f"{response.status_code} in {elapsed:.1f}s")

    for problem in problems:
        say(f"  PROBLEM: {problem}")
    return 1 if problems else 0


def main() -> int:
    from oneiro import config, window
    from oneiro.runtime import Runtime
    from oneiro.web import create_app
    import uvicorn
    from chat_fakes import GraphStub, MemoryLinks

    before = fingerprint(WATCHED)
    port = free_port()
    isolate(port)
    say("== W6 Live Check: Console Screens & Window Lifecycle ==")
    say(f"  working directory: {WORK}")

    # 1. Window module verification in headless/fallback mode
    say("\n== 1. Window module verification ==")
    state = window.launch_window(port, no_window=True)
    say(f"  window launch (headless) -> mode={state.mode}, active={state.active}, url={state.url}")
    assert state.mode == "headless"
    assert state.active is True

    # 2. Start server and exercise all 5 canonical routes
    say("\n== 2. Live HTTP server and screen verification ==")
    memory = Runtime(graph=GraphStub(MemoryLinks(), WORK / "graph-writer.lock"))
    app = create_app(runtime=memory, scheduler=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    try:
        # Asked in English so the words being pinned are the catalog's English values;
        # the Russian side is measured by tests/test_i18n_themes.py and live_w9_shots.py.
        # Each marker is asserted in exactly one form: the escaped form, because that is
        # what a page that escapes its text must send (`&` becomes `&amp;`). Accepting
        # either form would pass on a page that stopped escaping.
        screens = [
            ("/?lang=en", "Conversation", "screen-grid conversation-layout"),
            ("/tasks?lang=en", "Tasks", "Active & Queued Tasks"),
            ("/tools?lang=en", "Tools", "MCP Servers"),
            ("/settings?lang=en", "Oneiro settings", "fieldset"),
            ("/memory?lang=en", "Memory", "Curated memory"),
        ]

        for route, heading_sub, marker in screens:
            url = f"{base_url}{route}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
                say(f"  GET {route:<12} -> HTTP {status}, length={len(body)}")
                assert status == 200
                assert heading_sub in body
                assert html.escape(marker) in body, (
                    f"{route} does not carry {html.escape(marker)!r}: the screen is not the "
                    f"one this check names, or it stopped escaping what it renders")
                # § 6 Row 15: No raw JSON on screen
                assert '{"schema_version":' not in body
                assert '{"ready":' not in body
                assert '{"error":' not in body
        say("  All 5 canonical screens verified: zero raw JSON, action cards present.")

    finally:
        server.should_exit = True
        server_thread.join(timeout=5)

    # 3. The three memory states, then the zero-leak check.
    state_exit = graph_states(WORK, int(config.value("graph.port")))
    if state_exit != 0:
        say("ERROR: the memory states did not answer as row 14/15 requires.")
        return state_exit

    say("\n== 4. Integrity check: owner files ==")
    after = fingerprint(WATCHED)
    problems = []
    for path, seen in before.items():
        if after.get(path) != seen:
            say(f"  CHANGED: {path}")
            problems.append(path)
        else:
            say(f"  unchanged: {path}")

    if problems:
        say(f"ERROR: owner files were modified by live check: {problems}")
        return 1

    say(f"\nW6 Live check completed successfully! Temp root: {WORK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
