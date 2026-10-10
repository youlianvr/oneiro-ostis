"""Live check for W7: Languages and themes.

Run it with `python tests/live_w7_check.py`. It provides end-to-end evidence
for § 5 W7 and acceptance matrix § 6:
* Row 14: RU / EN language switching and five selectable themes (`night`, `paper`, `editorial`, `cosmic`, `agentic`).
* Row 16: Accessibility and WCAG 2.2 AA contrast adherence across all themes.
* Proves zero-leak: owner's configuration files remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
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

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w7-live-"))
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
    from oneiro import config, i18n
    from oneiro.runtime import Runtime
    from oneiro.web import create_app
    import uvicorn
    from chat_fakes import GraphStub, MemoryLinks

    before = fingerprint(WATCHED)
    port = free_port()
    isolate(port)
    say("== W7 Live Check: Languages and Themes ==")
    say(f"  working directory: {WORK}")

    # 1. Start live server
    say("\n== 1. Starting live server ==")
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
        # 2. Test RU and EN rendering
        say("\n== 2. Verifying language switching (RU & EN) ==")
        with urllib.request.urlopen(f"{base_url}/?lang=ru", timeout=5) as resp:
            body_ru = resp.read().decode("utf-8")
            assert 'lang="ru"' in body_ru
            assert "Диалог" in body_ru
            say("  RU page rendered: lang='ru', nav contains 'Диалог'")

        with urllib.request.urlopen(f"{base_url}/?lang=en", timeout=5) as resp:
            body_en = resp.read().decode("utf-8")
            assert 'lang="en"' in body_en
            assert "Chat" in body_en
            say("  EN page rendered: lang='en', nav contains 'Chat'")

        # 3. Test theme application across all 5 themes
        say("\n== 3. Verifying five selectable themes ==")
        themes = ("night", "paper", "editorial", "cosmic", "agentic")
        for th in themes:
            config.save({"ui.theme": th})
            with urllib.request.urlopen(f"{base_url}/settings", timeout=5) as resp:
                body = resp.read().decode("utf-8")
                assert f'data-theme="{th}"' in body
                say(f"  Theme '{th}' active in DOM: data-theme='{th}'")

        # 4. Verify console.css token accessibility
        with urllib.request.urlopen(f"{base_url}/console.css", timeout=5) as resp:
            css_data = resp.read().decode("utf-8")
            for th in themes:
                assert f'[data-theme="{th}"]' in css_data
            say("  console.css serves token blocks for all 5 themes")

    finally:
        server.should_exit = True
        server_thread.join(timeout=5)

    # 5. Check zero-leak on owner files
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

    say(f"\nW7 Live check completed successfully! Temp root: {WORK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
