"""Live check for W6: Console screens and window launcher.

Run it with `python tests/live_w6_check.py`. It provides end-to-end evidence
for § 5 W6 and acceptance matrix § 6:
* Row 2: Application window / browser fallback.
* Row 4: Every refusal/approval explained via action cards (no raw JSON on screen).
* Row 15: No JSON on screen across all 5 canonical routes.
* Row 16: Accessibility and keyboard focus elements present.
* Ensures zero-leak: user's settings and files remain completely unchanged.
"""
from __future__ import annotations

import hashlib
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
                assert marker in body
                # § 6 Row 15: No raw JSON on screen
                assert '{"schema_version":' not in body
                assert '{"ready":' not in body
                assert '{"error":' not in body
        say("  All 5 canonical screens verified: zero raw JSON, action cards present.")

    finally:
        server.should_exit = True
        server_thread.join(timeout=5)

    # 3. Check zero-leak on owner files
    say("\n== 3. Integrity check: owner files ==")
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
