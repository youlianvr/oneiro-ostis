"""Live check for W2: the webhook contract, through the console that serves it.

Run it with `python tests/live_hooks_check.py`. It is not a unit test; it is the evidence
the plan asks for, exercised the way the product is used:

* a real console process on a free port, with its own data root and its own **explicitly
  named** graph port, stopped at the end — with the exit code read from the process;
* real HTTP: one signed POST that creates a task, and four wrong POSTs, each refused with
  its own code and its own sentence;
* the task read back twice, independently of the console's own answer: the raw record out
  of the graph, and the owner's own reader script as a separate process with its exit
  code; and the product stream read before and after, to show the owner's own stream was
  not written to;
* the console's log checked for the secret's value, which must appear nowhere;
* the owner's data root fingerprinted before and after: the live directory is read only.

The task id is the digest of the body, so the same delivery twice is one task: a run
without `--marker` is therefore the delivery of the previous run as well, and the console
answers that it already has it. Pass `--marker <word>` to make this run's delivery its own.

Records it creates go to the `demo` stream — the separate subject of experience the owner
decided demo records live in — of the running graph. The owner's memory, settings, data
root and console are never started and never written.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
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

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

from oneiro import config                                     # noqa: E402
from oneiro.graph_worker import GraphWorker                   # noqa: E402

#: The owner's own data root, read from this process's environment: only ever hashed.
OWNER_ROOT = config.data_root()
#: Where this check keeps everything of its own.
WORK = Path(tempfile.mkdtemp(prefix="oneiro-w2-live-"))
#: The graph is named explicitly. With an isolated root the default is 8090, where
#: nothing answers (found and written down in W1); the running graph is published on 8096.
GRAPH_PORT = int(os.environ.get("ONEIRO_LIVE_GRAPH_PORT", "8096"))
GRAPH_URL = f"ws://127.0.0.1:{GRAPH_PORT}/ws_json"
PAYLOAD = {"title": "Мониторинг: диск почти полон", "detail": "83% занято", "host": "db-1"}
STRANGER = b"a-key-that-is-not-the-one-in-force"
OTHER_BODY = json.dumps({"title": "Другое дело"}, ensure_ascii=False).encode("utf-8")
RESULTS: list[tuple[str, bool, str]] = []


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


def request(port: int, path: str, *, body: bytes | None = None,
            headers: dict[str, str] | None = None) -> tuple[int, str]:
    """One real HTTP call, answering with the status even when it is a refusal."""
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body,
                                  headers=headers or {},
                                  method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(call, timeout=120) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def hook_post(port: int, body: bytes, *, name: str = "monitor",
              secret: bytes | None = None, sign_body: bytes | None = None,
              header: str | None = None) -> tuple[int, str]:
    """POST the exact bytes, signed with a key, over other bytes, or not signed at all."""
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["X-Oneiro-Signature"] = header
    elif secret is not None:
        headers["X-Oneiro-Signature"] = hmac.new(
            secret, body if sign_body is None else sign_body, hashlib.sha256).hexdigest()
    return request(port, f"/api/hooks/{name}", body=body, headers=headers)


def isolated_env(web_port: int) -> dict[str, str]:
    """Everything of the owner's pointed somewhere else, and the graph named explicitly."""
    env = dict(os.environ)
    env.update({
        "ONEIRO_DATA_DIR": str(WORK / "runtime"),
        "ONEIRO_SETTINGS_FILE": str(WORK / "settings.json"),
        "ONEIRO_MCP_FILE": str(WORK / "mcp.json"),          # never the owner's servers
        "ONEIRO_KEYS_FILE": str(WORK / "no-keys.env"),
        "ONEIRO_WEB_HOST": "127.0.0.1",
        "ONEIRO_WEB_PORT": str(web_port),
        "ONEIRO_PORT": str(GRAPH_PORT),
        # The owner's provider is not called by a check.
        "ONEIRO_LLM_BASE_URL": "http://127.0.0.1:9/v1",
        "ONEIRO_LLM_API_KEY": "live-check-key",
        "ONEIRO_LLM_MODEL": "stub/live-check",
    })
    for name in ("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"):
        env.pop(name, None)
    return env


def fingerprint(root: Path) -> list[str]:
    """A digest per file, so "nothing was written" is a comparison and not a claim."""
    if not root.is_dir():
        return []
    return [f"{path.relative_to(root)} {hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in sorted(root.rglob("*")) if path.is_file()]


def read_stream(env: dict[str, str], stream: str, limit: int) -> tuple[int, str]:
    """The owner's own reader, as a separate process: its exit code is the answer."""
    finished = subprocess.run(
        [sys.executable, str(PROJECT / "scripts" / "office-graph-read.py"),
         "--stream", stream, "--limit", str(limit)],
        cwd=str(PROJECT), env=env, capture_output=True, text=True, timeout=300)
    return finished.returncode, (finished.stdout or "").strip()


def raw_record(stream: str, record_id: str) -> dict | None:
    """The stored record itself, read through a worker of this check's own."""
    worker = GraphWorker(GRAPH_URL, stream, WORK / "check-read.lock")

    async def run() -> dict | None:
        try:
            page = await worker.call("page", limit=20)
        finally:
            await worker.close()
        return next((row for row in page["items"] if row["id"] == record_id), None)

    return asyncio.run(run())


def listener(pid: int, port: int) -> tuple[str | None, str]:
    """The address the console listens on, from this machine's table. Read-only."""
    command = ["netstat", "-ano"] if os.name == "nt" else ["ss", "-ltnp"]
    try:
        # The table is not UTF-8 on every machine (measured here: 0x80 mid-line), and the
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
        return process.wait(timeout=30), "asked to stop"
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.wait(timeout=20), "terminated after 30 s without stopping"
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait(timeout=20), "killed after two waits without stopping"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="live_hooks_check")
    parser.add_argument("--marker", default="",
                        help="a word that makes this run's delivery a new one: an unmarked "
                             "run is the delivery of the last run too, and is answered as "
                             "already recorded")
    args = parser.parse_args(argv)
    # The task id is the digest of the body, so this shape is the delivery of this run:
    # without a marker it is the same one as last time, and the console answers that it
    # already has it instead of writing a second task.
    if args.marker:
        PAYLOAD["detail"] = f"{PAYLOAD['detail']} ({args.marker})"
    body = json.dumps(PAYLOAD, ensure_ascii=False).encode("utf-8")

    (WORK / "runtime").mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = isolated_env(port)
    before_owner = fingerprint(OWNER_ROOT)
    product_before = read_stream(env, "product", 1)
    log_path = WORK / "console.log"
    handle = log_path.open("w", encoding="utf-8")
    creation = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, str(TESTS / "live_hooks_serve.py"), "--stream", "demo"],
        cwd=str(PROJECT), env=env, stdout=handle, stderr=subprocess.STDOUT,
        creationflags=creation)
    say(f"Oneiro: console pid {process.pid} on http://127.0.0.1:{port}, "
        f"data root {env['ONEIRO_DATA_DIR']}")
    say(f"        graph named explicitly: ONEIRO_PORT={env['ONEIRO_PORT']} ({GRAPH_URL})")
    say(f"        the owner's data root is {OWNER_ROOT} ({len(before_owner)} files, read only)")

    secret: bytes | None = None
    try:
        say()
        say("== the console comes up ==")
        ready = False
        started = time.monotonic()
        while time.monotonic() - started < 120 and process.poll() is None:
            try:
                if request(port, "/api/session")[0] == 200:
                    ready = True
                    break
            except OSError:
                pass
            time.sleep(0.25)
        if not check("the console answered on its own port", ready,
                     f"{time.monotonic() - started:.1f}s after start"):
            say(log_path.read_text(encoding="utf-8", errors="replace")[-1500:])
            return 1

        status, text = request(port, "/api/graph")
        facts = json.loads(text) if text.strip().startswith("{") else {}
        check("the explicitly named graph is the one in use", facts.get("verified") is True,
              f"/api/graph {status}: reachable={facts.get('reachable')} "
              f"verified={facts.get('verified')} arcs={facts.get('arcs_found')} "
              f"in {facts.get('elapsed_ms')} ms")

        key_path = Path(env["ONEIRO_DATA_DIR"]) / "hooks.secret"
        for _ in range(40):                      # the console makes it during startup
            if key_path.is_file():
                break
            time.sleep(0.25)
        check("the console generated the secret in its own data root", key_path.is_file(),
              f"{key_path} ({key_path.stat().st_size if key_path.is_file() else 0} bytes)")
        if not key_path.is_file():
            return 1
        secret = key_path.read_bytes()

        say()
        say("== a signed delivery becomes a task ==")
        status, text = hook_post(port, body, secret=secret, name="monitor")
        answer = json.loads(text)
        check("a signed POST is accepted", status == 202, f"HTTP {status} {text[:200]}")
        task_id = str(answer.get("task_id", ""))
        check("the answer names the task it created", task_id.startswith("task-hook-monitor-"),
              f"task_id={task_id!r} duplicate={answer.get('duplicate')} "
              f"title={answer.get('title')!r}")

        status, text = request(port, f"/api/tasks/{task_id}")
        history = json.loads(text) if status == 200 else {}
        check("the console reads it back as a queued task", history.get("state") == "queued"
              and history.get("runs") == [],
              f"HTTP {status} state={history.get('state')!r} attempts={len(history.get('runs') or [])}")

        record = raw_record("demo", task_id)
        check("the task is in the graph, as a task record", bool(record)
              and record.get("kind") == "task" and record.get("state") == "queued"
              and record.get("provenance") == "owner_instruction",
              f"kind={record.get('kind')} state={record.get('state')} "
              f"provenance={record.get('provenance')} title={record.get('title')!r}"
              if record else "the record was not found")

        code, output = read_stream(env, "demo", 1)
        check("the owner's own reader finds it as the newest demo record", code == 0
              and task_id in output, f"exit {code}: {output[:220]}")

        product_after = read_stream(env, "product", 1)
        check("the owner's own stream was not written to",
              product_after == product_before and task_id not in product_after[1],
              f"before: exit {product_before[0]} {product_before[1][:60]!r} … "
              f"after: exit {product_after[0]}")

        say()
        say("== the same delivery again is not a second task ==")
        status, text = hook_post(port, body, secret=secret, name="monitor")
        again = json.loads(text)
        check("a repeated delivery is answered, not duplicated", status == 202
              and again.get("duplicate") is True and again.get("task_id") == task_id,
              f"HTTP {status} duplicate={again.get('duplicate')}")
        status, text = request(port, "/api/tasks")
        count = len([row for row in json.loads(text).get("tasks", [])
                     if row["id"] == task_id])
        check("the store holds that one task once", count == 1, f"{count} task(s) with that id")

        say()
        say("== every wrong delivery is refused with its own reason ==")
        wrong = [
            ("no signature at all", hook_post(port, body, name="monitor"),
             401, "signature_absent"),
            ("a stranger's signature", hook_post(port, body, name="monitor", secret=STRANGER),
             401, "signature_mismatch"),
            ("a signature over other bytes",
             hook_post(port, body, name="monitor", secret=secret, sign_body=OTHER_BODY),
             401, "signature_mismatch"),
            ("a broken body that is signed",
             hook_post(port, b'{"title": "broken', secret=secret, name="monitor"),
             400, "body_not_json"),
            ("an unknown hook name", hook_post(port, body, secret=secret, name="Monitor-2"),
             400, "unknown_hook"),
        ]
        for what, (status, text), expected, code in wrong:
            body = json.loads(text)
            check(f"{what}: HTTP {status} {body.get('code')}", status == expected
                  and body.get("code") == code,
                  f"reason: {body.get('error')}")
        status, text = request(port, "/api/tasks", body=b"{}",
                               headers={"Content-Type": "application/json"})
        check("every other write still needs the page token", status == 403,
              f"POST /api/tasks without the token: HTTP {status} {text[:80]}")

        address, why = listener(process.pid, port)
        check("the console listens on loopback only", address is not None
              and address.startswith("127.0.0.1:"), f"{address or 'not reported'} ({why})")
    finally:
        say()
        say("== the console stops ==")
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
        free = False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                free = False
        except OSError:
            free = True
        check("the console stopped and its port is free", free,
              f"exit code {code} ({how}); the socket no longer answers")
        if secret is not None:
            check("the secret's value appears nowhere in the console's log",
                  secret.decode() not in log_text,
                  f"{len(log_text)} characters of log; fingerprints only")
        printed = [line for line in log_text.splitlines() if "webhook secret" in line]
        check("the log names the secret by fingerprint, not by value",
              bool(printed) and all(len(line) < 200 for line in printed),
              printed[0] if printed else "no line about the secret was logged")

    say()
    say("== nothing of the owner's was written ==")
    after_owner = fingerprint(OWNER_ROOT)
    check("the owner's data root is byte-for-byte what it was",
          after_owner == before_owner,
          f"{len(after_owner)} files, {sum(1 for a, b in zip(before_owner, after_owner) if a != b)} "
          f"differ")
    say()
    say("== summary ==")
    for label, ok, detail in RESULTS:
        say(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail else ""))
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    say(f"  {passed}/{len(RESULTS)} checks passed")
    say(f"  the check's own root stays for inspection: {WORK}")
    say("  one task record went to the demo stream of the running graph;"
        " the product stream is unchanged")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
