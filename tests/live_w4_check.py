"""Live check for W4: models and providers, exercised against the owner's own address.

Run it with `python tests/live_w4_check.py`. It is not a unit test — it is the end-to-end
evidence § 5 W4 asks for, through the surfaces the product really uses:

* the **owner's own provider**, reached the way a shipped install reaches it: the provider
  list the product ships, the pre-registry address and key, a real `GET /models`, and a
  real chat turn, with the model that actually served it named by the provider itself;
* **what was actually probed**: whether the model answered, asked for the offered tool and
  accepted an image — beside what the provider merely advertises;
* **a second model reached through fallback**: a first provider that refuses, then a model
  on the owner's own address, entered only after a real capability probe; and the negative
  case, a fallback that cannot be shown to use tools and is skipped with the reason;
* the **command line in its own process** (`oneiro verify-model`), with the exit status and
  the JSON report it prints;
* the **time one call may take**: `agent.step_timeout` is measured through
  `POST /api/message` against a provider that accepts the connection and never answers,
  because a limit the retries multiply is not the limit the owner set;
* the **HTTP surface** (`/api/status`, `/api/settings`) on a real server on a real port,
  before and after a verification, so "only what was probed" is shown rather than claimed;
* and the owner's own files before and after, because a live check that quietly writes to
  the owner's configuration is worse than no check.

The key is read from the owner's configuration once, read-only, and lives in this process'
environment for the duration of the check; this script never writes it to a file and never
prints it. Everything else it writes lives under its own temporary root.
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

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w4-live-"))
OWNER_SETTINGS = Path.home() / ".oneiro" / "settings.json"
OWNER_KEYS = Path.home() / ".config" / "keys.env"
WATCHED = (OWNER_SETTINGS, OWNER_KEYS, PROJECT / ".env", PROJECT / "knowledge-base" / "repo.path")


def say(text: str = "") -> None:
    print(text, flush=True)


def fingerprint(paths) -> dict[str, str]:
    """What a file looked like, without reading anything secret into the log."""
    seen = {}
    for path in paths:
        try:
            raw = Path(path).read_bytes()
        except OSError:
            seen[str(path)] = "absent"
            continue
        seen[str(path)] = f"{len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()[:12]}"
    return seen


class Refusing(BaseHTTPRequestHandler):
    """A local provider that refuses every call, or (in `words` mode) answers in words.

    Each server carries its own mode: this check runs two of them side by side, one that is
    down and one that can be shown not to call a tool, and they must not share a script.
    """

    def log_message(self, *_: object) -> None:
        return None

    def do_GET(self) -> None:  # noqa: N802
        self._answer(503, {"error": {"message": "no"}})

    def do_POST(self) -> None:  # noqa: N802
        self.server.calls += 1                                   # type: ignore[attr-defined]
        self.rfile.read(int(self.headers.get("content-length") or 0))
        if self.server.mode == "words":                         # type: ignore[attr-defined]
            self._answer(200, {"choices": [{"message": {"role": "assistant",
                                                        "content": "I would rather talk."}}]})
            return
        self._answer(503, {"error": {"message": "no"}})

    def _answer(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class Local:
    """The stub provider on its own loopback port."""

    def __init__(self, mode: str) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Refusing)
        self._server.mode = mode                                  # type: ignore[attr-defined]
        self._server.calls = 0                                    # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    @property
    def calls(self) -> int:
        return int(self._server.calls)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class Wedged(BaseHTTPRequestHandler):
    """A provider that accepts the connection and never answers: the real worst case.

    A refusal is not the same thing as a hang, and only the second one shows whether a
    limit bounds a turn: the call is on the wire and stays there.
    """

    def log_message(self, *_: object) -> None:
        return None

    def do_GET(self) -> None:  # noqa: N802
        self._hold()

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("content-length") or 0))
        self._hold()

    @staticmethod
    def _hold() -> None:
        # Longer than any limit this check sets; the handler runs in a daemon thread, so
        # shutting the server down does not wait for it.
        time.sleep(30)


class Wedge:
    """The wedged provider on its own loopback port."""

    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Wedged)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class Page:
    """Real HTTP against the running application."""

    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def _open(self, request: urllib.request.Request) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:      # a refusal is an answer too
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}")

    def get(self, path: str) -> tuple[int, dict]:
        return self._open(urllib.request.Request(self.base + path))


def owner_credentials() -> tuple[str, str]:
    """The owner's own address and key, read from his configuration and never written back.

    Called before anything points the settings elsewhere, so it answers from the install
    the person actually uses.
    """
    from oneiro import config

    address, address_source = config.resolve("llm.base_url")
    key, key_source = config.resolve("llm.api_key")
    return str(address), str(key), address_source, key_source


def isolate(port: int, owner_address: str, owner_key: str) -> None:
    """Point everything this check writes at its own root, and give it the owner's key.

    The key travels in this process' environment only: `OMNIROUTE_API_KEY` is the name the
    shipped provider record declares for it, so the `key_env` path itself is what is
    exercised, and nothing is written to any file.
    """
    os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
    os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "keys.env")
    os.environ["ONEIRO_MCP_FILE"] = str(WORK / "mcp.json")
    os.environ["ONEIRO_WEB_PORT"] = str(port)
    os.environ["ONEIRO_LLM_BASE_URL"] = owner_address
    os.environ["OMNIROUTE_API_KEY"] = owner_key
    # The local stubs get a key of their own, so the owner's real key never travels to a
    # stub that exists only inside this check.
    os.environ["W4_STUB_KEY"] = "sk-not-a-real-key"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def main() -> int:
    from oneiro import config, models
    from oneiro.runtime import Runtime

    before = fingerprint(WATCHED)
    address, key, address_source, key_source = owner_credentials()
    say("== the owner's own provider ==")
    say(f"  address {address} (from {address_source})")
    say(f"  a key is present: {bool(key)} (from {key_source}); it is never printed and never"
        f" written to a file by this check")
    say()

    port = free_port()
    isolate(port, address, key)
    config.PROJECT_ENV = WORK / "no-project.env"
    say(f"  this check's own root: {WORK} (settings, data root, mcp list)")

    say()
    say("== reached the way a shipped install reaches it: the shipped list, the pre-registry"
        " address and key ==")
    registry = models.Registry()
    providers = registry.providers()
    for provider in providers:
        say(f"  provider {provider.name}: {provider.base_url} key_env={provider.key_env!r} "
            f"key found: {bool(registry.key_for(provider))} discover_models={provider.discover_models}")
    provider = providers[0]
    model = registry.model_for("manager")
    say(f"  the manager's model: {model}  (models.default={config.value('models.default')!r}, "
        f"llm.model={config.value('llm.model')!r})")
    try:
        found = registry.discover(provider)
    except models.ModelError as exc:
        say()
        say(f"BLOCKED: the owner's provider did not answer its model list: {exc}")
        say("  nothing about this address was checked; the check cannot pretend otherwise")
        return 2
    say(f"  discovery: {len(found.models)} models listed (truncated: {found.truncated}); "
        f"the manager's model is listed: {model in found.models}")
    say(f"  the provider advertises about {model}: tools={found.says(model, 'tools')}, "
        f"vision={found.says(model, 'vision')}  (advertised, not measured)")
    aliases = [name for name in found.models if name.startswith("auto/")][:10]
    say(f"  routing aliases it lists: {', '.join(aliases)}")
    say()

    say("== a real call through the registry, and what the provider said about it ==")
    started = time.monotonic()
    try:
        reply = registry.call("manager", [{"role": "system",
                                           "content": "Answer with one short sentence."},
                                          {"role": "user",
                                           "content": "Name the colour of the sky in one word."}],
                              timeout=90)
    except models.ModelError as exc:
        say(f"BLOCKED: the call did not complete: {exc}")
        return 2
    say(f"  asked for {model!r}; the provider says {reply.served or '(nothing)'!r} answered "
        f"(upstream {reply.upstream or 'not named'}) in {time.monotonic() - started:.1f}s")
    say(f"  reply: {reply.content[:200]!r}")
    say(f"  usage as the provider reported it: {json.dumps(reply.usage, ensure_ascii=False)}; "
        f"its own cost: {reply.cost or 'not sent'}")
    entry = registry.report()["entries"][-1]
    say(f"  the ledger line: role {entry['role']}, model {entry['model']}, attempt "
        f"{entry['attempt']}, {entry['outcome']}, {entry['ms']} ms, served "
        f"{entry['served']}, tokens {entry['tokens_in']}/{entry['tokens_out']}")
    say()

    say("== what the model really does, established by real calls ==")
    capability = registry.probe(provider, model, timeout=90)
    say(f"  {provider.name}/{model}: answered={capability.answered} probed={capability.probed} "
        f"tools={capability.says('tools')} vision={capability.says('vision')}")
    for note in capability.notes:
        say(f"    note: {note}")
    say(f"  {len(registry.capabilities())} capability record(s) kept; the ledger holds "
        f"{len(registry.report()['entries'])} call(s)")
    say()

    say("== a fallback is entered only on evidence, and the reason when it is not ==")
    dead = Local("dead")
    words = Local("words")
    try:
        config.save({"models.providers": [
            {"name": "dead", "base_url": dead.base, "key_env": "W4_STUB_KEY"},
            {"name": "words", "base_url": words.base, "key_env": "W4_STUB_KEY"}],
            "models.fallback": ["words/auto/coding"]})
        try:
            registry.call("manager", [{"role": "user", "content": "hello"}],
                          tools=[models.PROBE_TOOL], timeout=5)
            say("  UNEXPECTED: a fallback that cannot be shown to use tools answered")
            return 1
        except models.ModelError as exc:
            say(f"  refused, as it should be: {str(exc)[:220]}")
        asked = [entry for entry in registry.report()["entries"] if entry["provider"] == "words"]
        say(f"  the fallback was asked {words.calls} time(s) to prove itself and never asked "
            f"to do the work; its ledger line says: "
            f"{json.dumps([entry['detail'] for entry in asked])}")
        if words.calls != 1:
            say(f"  UNEXPECTED: the fallback saw {words.calls} request(s), not one probe")
            return 1
    finally:
        dead.close()
        words.close()

    say()
    say("== the same call, served by a second model on the owner's own address ==")
    needs_tools = capability.says("tools") is True
    config.save({"models.providers": [
        {"name": "dead", "base_url": "http://127.0.0.1:9/v1", "key_env": "W4_STUB_KEY"},
        {"name": "owner", "base_url": address, "key_env": "OMNIROUTE_API_KEY"}],
        "models.fallback": [f"owner/{model}"]})
    tools = [models.PROBE_TOOL] if needs_tools else None
    say(f"  the first provider cannot answer; the fallback is owner/{model}, and the call "
        f"{'offers a tool' if tools else 'is plain text'} "
        f"(tools were {'shown' if needs_tools else 'not shown'} to work on this address)")
    try:
        served = registry.call("manager", [{"role": "system", "content": "One short sentence."},
                                           {"role": "user", "content": "Say the word: ready."}],
                               tools=tools, timeout=90)
    except models.ModelError as exc:
        say(f"  BLOCKED: the fallback did not answer either: {exc}")
        return 2
    say(f"  the fallback answered: {served.content[:160]!r} (served by "
        f"{served.served or 'not named'})")
    tail = registry.report()["entries"][-6:]
    for line in tail:
        say(f"    {line['provider']}/{line['model']} attempt {line['attempt']}: "
            f"{line['outcome']} ({line['detail']})")
    say()

    say("== the command line in its own process ==")
    # One provider — the owner's own — with a second model of it as the fallback, so the
    # report has both a primary and a candidate to show verdicts for.
    config.save({"models.providers": [
        {"name": "owner", "base_url": address, "key_env": "OMNIROUTE_API_KEY"}],
        "models.fallback": ["owner/auto/best-coding"]})
    say(f"  the provider list is now: owner -> {address}; fallback: owner/auto/best-coding")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(PROJECT / "python")
    result = subprocess.run([sys.executable, "-m", "oneiro", "verify-model"], cwd=str(PROJECT),
                            env=environment, capture_output=True, text=True, timeout=900)
    say(f"  oneiro verify-model -> exit {result.returncode}")
    if result.returncode not in (0, 1):
        say(f"  stderr: {result.stderr[-400:]}")
        return 1
    report = json.loads(result.stdout)
    say(f"  verified={report['verified']} used_tools={report['used_tools']} "
        f"vision={report['vision']} model={report['model']!r}")
    for described in report["providers"]:
        say(f"    {described['name']}: {described.get('model_list', '(discovery off)')}, "
            f"key found: {described['key_found']}, lists the model: "
            f"{described.get('lists_the_role_model')}, advertises "
            f"{described.get('advertises')}")
    for probe in report["probes"]:
        say(f"    probed {probe['provider']}/{probe['model']}: answered={probe['answered']} "
            f"tools={probe['tools']} vision={probe['vision']}")
    for note in report.get("notes", []):
        say(f"    note: {note}")
    say(f"  accounting: {json.dumps(report['accounting']['totals'], ensure_ascii=False)}")
    say(f"  per call: {len(report['accounting']['entries'])} line(s) for the report above")
    say()

    say("== the HTTP surface: before and after a verification ==")
    import uvicorn                                                          # noqa: E402
    from oneiro.web import create_app                                       # noqa: E402

    runtime = Runtime()
    application = create_app(runtime=runtime, scheduler=False)
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port,
                                           log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    page = Page(port)
    for _ in range(100):
        try:
            if page.get("/api/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.2)
    try:
        status, document = page.get("/api/status")
        said = document["model"]
        say(f"  GET /api/status -> {status}: verified={said['verified']} "
            f"tools={said['used_tools']} vision={said['vision']}")
        say(f"    providers: {[(item['name'], item['base_url'], item['key_found']) for item in said['providers']]}")
        say(f"    roles: {said['roles']}, fallback: {said['fallback']}")
        say(f"    probed so far: {len(said['probed'])}, calls so far: {said['calls']['calls']}")
        say(f"    blocked: {document['blocked']}")

        verified = asyncio.run(runtime.verify_model(timeout=90))
        say(f"  after the runtime verified the model: verified={verified['verified']} "
            f"used_tools={verified['used_tools']} vision={verified['vision']}")
        status, document = page.get("/api/status")
        said = document["model"]
        say(f"  GET /api/status -> {status}: verified={said['verified']} "
            f"tools={said['used_tools']} vision={said['vision']}")
        for probe in said["probed"]:
            say(f"    probed {probe['provider']}/{probe['model']}: answered={probe['answered']} "
                f"tools={probe['tools']} vision={probe['vision']} notes={probe['notes']}")
        say(f"    calls: {json.dumps(said['calls'], ensure_ascii=False)}")
        say(f"    blocked: {document['blocked']}")

        _status, settings = page.get("/api/settings")
        rows = {row["key"]: row for row in settings["settings"]}
        say("  GET /api/settings — the model keys and whether the page still calls them"
            " \"not in this build yet\":")
        for name in ("models.providers", "models.default", "models.roles.manager",
                     "models.roles.researcher", "models.roles.executor", "models.fallback",
                     "models.accounting", "llm.base_url", "llm.api_key", "llm.model"):
            row = rows[name]
            say(f"    {name:<24} pending={row['pending']}  [{row['source']}]")
    finally:
        server.should_exit = True
        thread.join(20)
    say()
    say()

    say("== one call against a provider that never answers, at the limit the owner set ==")
    from chat_fakes import GraphStub, MemoryLinks                           # noqa: E402
    from oneiro import agent                                               # noqa: E402

    wedged = Wedge()
    try:
        config.save({"models.providers": [
            {"name": "wedged", "base_url": wedged.base, "key_env": "W4_STUB_KEY"}]})
        say(f"  the provider list is now: wedged -> {wedged.base}, which accepts the"
            f" connection and never answers")
        say("  the turn runs through the production loop, `oneiro.agent.run_turn`; the memory"
            " it reads is the in-process double the unit tests use, because the subject here"
            " is the model layer and the OSTIS server is not running in this check")
        memory = Runtime(graph=GraphStub(MemoryLinks(), WORK / "graph-writer.lock"))
        for limit in (2, 5):
            config.save({"agent.step_timeout": limit})
            models.registry().records.clear()
            allowed = limit + models.WAIT_SLACK + 1.0
            started = time.monotonic()
            try:
                asyncio.run(agent.run_turn(memory, "are you there?", "live-w4-bound",
                                           "main-chat"))
                refused = "UNEXPECTED: the turn answered"
            except models.ModelError as exc:
                refused = str(exc)
            spent = time.monotonic() - started
            lines = models.registry().report()["entries"]
            say(f"    agent.step_timeout={limit}s -> refused after {spent:.1f}s "
                f"(allowed {allowed:.1f}s), {len(lines)} attempt(s) on the ledger: "
                f"{[entry['outcome'] for entry in lines]}")
            say(f"      it says: {refused[:260]}")
            if spent > allowed or not lines:
                say("    UNEXPECTED: the declared limit did not bound the call")
                return 1
    finally:
        wedged.close()
    say()

    say("== what this check left alone ==")
    after = fingerprint(WATCHED)
    for path, seen in before.items():
        say(f"  {'unchanged' if after.get(path) == seen else 'CHANGED  '} {path}  [{seen}]")
    say(f"  the check's own settings file: {WORK / 'settings.json'} "
        f"({'written' if (WORK / 'settings.json').exists() else 'never written'}); "
        f"the key was never written here")
    say()
    problems = [path for path, seen in before.items() if after.get(path) != seen]
    if problems:
        say(f"the check changed the owner's files: {problems}")
        return 1
    say(f"W4 live check finished; its temporary root is kept at {WORK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
