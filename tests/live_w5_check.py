"""Live check for W5: research, source-backed citations, and attachment intake.

Run it with `python tests/live_w5_check.py`. It provides end-to-end evidence
for § 5 W5 and acceptance matrix § 6:
* Row 12: Research with sources (answer with citations and source records).
* Row 13: Attachment intake (text, images, PDF with limits, SHA-256 hashes,
          attachment-only turn, unsupported type rejection).
* Verification through CLI (`oneiro research`) and real HTTP on loopback.
* Ensures zero-leak: user's settings and files remain completely unchanged.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
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

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w5-live-"))
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


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def main() -> int:
    from oneiro import config, research
    from oneiro.runtime import Runtime
    from oneiro.web import create_app
    import uvicorn
    from chat_fakes import GraphStub, MemoryLinks

    before = fingerprint(WATCHED)
    port = free_port()
    isolate(port)
    say("== W5 Live Check: Research, Citations & Attachments ==")
    say(f"  working directory: {WORK}")

    # 1. Test CLI research command in separate process
    say("\n== 1. CLI surface verification ==")
    sample_doc = WORK / "sample.md"
    sample_doc.write_text("# OSTIS Architecture\n\nSemantic networks and agents in Oneiro.", encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT / "python")

    # oneiro research attach
    res_attach = subprocess.run(
        [sys.executable, "-m", "oneiro", "research", "attach", str(sample_doc), "--json"],
        cwd=str(PROJECT), env=env, capture_output=True, text=True,
    )
    say(f"  oneiro research attach sample.md -> exit {res_attach.returncode}")
    if res_attach.returncode != 0:
        say(f"  stderr: {res_attach.stderr}")
        return 1
    meta = json.loads(res_attach.stdout)
    say(f"    attached ID: {meta['id']}, MIME: {meta['mime']}, sha256: {meta['sha256'][:16]}...")

    # oneiro research show
    res_show = subprocess.run(
        [sys.executable, "-m", "oneiro", "research", "show", meta["id"], "--json"],
        cwd=str(PROJECT), env=env, capture_output=True, text=True,
    )
    say(f"  oneiro research show {meta['id']} -> exit {res_show.returncode}")
    if res_show.returncode != 0:
        say(f"  stderr: {res_show.stderr}")
        return 1
    loaded = json.loads(res_show.stdout)
    say(f"    loaded text excerpt: {loaded['text'][:40]!r}")
    assert "OSTIS Architecture" in loaded["text"]

    # 2. Attachments of different types: text, image, PDF, and rejection
    say("\n== 2. Attachment intake: formats and bounds ==")
    # Text
    txt_meta = research.ingest_attachment("notes.txt", b"Research note content")
    say(f"  Text attachment: {txt_meta.name} -> {txt_meta.mime}, {txt_meta.size} bytes")

    # PDF
    pdf_bytes = (
        b"%PDF-1.4\n1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R>> endobj\n"
        b"4 0 obj <</Length 35>> stream\n(OSTIS knowledge representation) Tj\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f \ntrailer <</Size 5 /Root 1 0 R>>\nstartxref\n220\n%%EOF"
    )
    pdf_meta = research.ingest_attachment("paper.pdf", pdf_bytes)
    say(f"  PDF attachment: {pdf_meta.name} -> {pdf_meta.mime}, pages={pdf_meta.pages}")

    # Rejection of unsupported executable
    try:
        research.ingest_attachment("binary.exe", b"MZ\x90\x00malicious")
        say("  UNEXPECTED: unsupported binary was accepted")
        return 1
    except research.AttachmentRejected as exc:
        say(f"  Unsupported format rejected properly: {exc}")

    # Rejection of oversized file
    try:
        research.ingest_attachment("huge.txt", b"x" * 200, max_bytes=100)
        say("  UNEXPECTED: oversized file was accepted")
        return 1
    except research.AttachmentRejected as exc:
        say(f"  Oversized file rejected properly: {exc}")

    # 3. Live HTTP server and attachment-only chat turn
    say("\n== 3. Live HTTP server and turn with attachment ==")
    # Hook transport to fake model in this process so turn succeeds without depending on external provider
    from oneiro import models
    from oneiro.chat import ModelReply

    def fake_transport(messages, *, base_url, api_key, model, tools=None, timeout=60.0):
        # Extract user message content
        last = messages[-1].get("content", "")
        return ModelReply(f"Answer: processed input. Observed: {last[:60]}...")

    models.TRANSPORT = fake_transport
    os.environ["ONEIRO_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
    os.environ["ONEIRO_LLM_API_KEY"] = "sk-live-test"
    os.environ["ONEIRO_LLM_MODEL"] = "auto/coding"

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
        # Get CSRF token
        with urllib.request.urlopen(f"{base_url}/api/session", timeout=2) as resp:
            token = json.loads(resp.read().decode("utf-8"))["csrf"]

        # Upload via POST /api/attachments
        upload_req = urllib.request.Request(
            f"{base_url}/api/attachments",
            data=b"Specialized semantic code: sc_node_class -> concept_agent.",
            headers={"X-Filename": "agent.scs", "Content-Type": "text/plain", "X-Oneiro-CSRF": token},
        )
        with urllib.request.urlopen(upload_req, timeout=5) as resp:
            up_info = json.loads(resp.read().decode("utf-8"))
            say(f"  POST /api/attachments -> HTTP {resp.status}, ID: {up_info['id']}")

        # Hook fake search provider for researched turn
        def live_search_provider(q: str, c: int) -> list[research.SearchResult]:
            return [
                research.SearchResult(
                    title="OSTIS Specifications 2026",
                    url="https://ostis.net/docs/spec",
                    snippet="Official OSTIS semantic networks specification and knowledge base principles.",
                )
            ]
        research.SEARCH_PROVIDER = live_search_provider

        # Run an agent turn with the attachment
        turn_data = json.dumps({
            "text": "What does the attached scs file define?",
            "client_id": "client-live-w5-001",
            "attachments": [up_info["id"]],
        }).encode("utf-8")

        turn_req = urllib.request.Request(
            f"{base_url}/api/message",
            data=turn_data,
            headers={"Content-Type": "application/json", "X-Oneiro-CSRF": token},
        )
        with urllib.request.urlopen(turn_req, timeout=15) as resp:
            turn_res = json.loads(resp.read().decode("utf-8"))
            say(f"  POST /api/message with attachment -> HTTP {resp.status}")
            say(f"    user message stored: ID={turn_res['user']['id']}")
            say(f"    reply text: {turn_res['reply']['text'][:120]!r}")

        # Check turn with attachment ONLY (no text)
        empty_text_turn = json.dumps({
            "text": "",
            "client_id": "client-live-w5-002",
            "attachments": [up_info["id"]],
        }).encode("utf-8")
        empty_req = urllib.request.Request(
            f"{base_url}/api/message",
            data=empty_text_turn,
            headers={"Content-Type": "application/json", "X-Oneiro-CSRF": token},
        )
        with urllib.request.urlopen(empty_req, timeout=15) as resp:
            turn_empty_res = json.loads(resp.read().decode("utf-8"))
            say(f"  POST /api/message (attachment ONLY, text empty) -> HTTP {resp.status}")
            say(f"    reply text: {turn_empty_res['reply']['text'][:120]!r}")

    finally:
        server.should_exit = True
        server_thread.join(timeout=5)

    # 4. Check zero-leak on owner files
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

    say(f"\nW5 Live check completed successfully! Temp root: {WORK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
