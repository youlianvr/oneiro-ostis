"""Live check for W3: skills inside the product, exercised the way they are used.

Run it with `python tests/live_w3_check.py`. It is not a unit test — it is the
end-to-end evidence § 6 row 7 asks for, reached through the surfaces the product
actually exposes:

* the **catalog that ships with the product**, searched with no skill folder on the
  machine at all, so "the catalog travels with the product" is shown rather than
  claimed;
* **`skills.paths` really searched**: two skills written by hand into a folder, found
  by description, and one of them opened as the same `SKILL.md` a person would open;
* the **command line in its own process** (`oneiro skills list|search|show`), with the
  exit status and the words it prints;
* the **HTTP surface** (`/api/skills`, `/api/skills/search`, `/api/skills/{name}`) on a
  real server on a real port, including the refusals: an unknown name, a reviewed name
  whose contract is not installed, and a catalog that is not valid JSON;
* the **turn**: a stub model asks for `find_skills`, reads the candidate it was given
  with `read_skill`, and answers with a line it can only have from the contract — with
  the calls, their effect and their outcome recorded in the memory;
* **parity** with the module the ranking came from, over the reviewed workspace catalog;
* and a comparison of the owner's own files before and after, because a live check that
  quietly writes to the owner's settings is worse than no check.

The stubs are the model provider (a real HTTP server on loopback answering the
chat-completions shape) and the graph (the real `RecordStore` over an in-memory link
graph, in the worker's exact result shapes). Settings, data root and keys all live in a
temporary folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(PROJECT / "python"))

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w3-live-"))
SKILLS = WORK / "skills"
OWNER_SETTINGS = Path.home() / ".oneiro" / "settings.json"
OWNER_SKILLS = Path.home() / "skills"
WORKSPACE_CATALOG = Path.home() / ".openclaw" / "workspace" / "knowledge" / "wiki" \
    / "skills-catalog.json"
MARKER = "MARKER-W3-RELEASE-NOTES"

RELEASE_NOTES = f"""---
name: release-notes
description: Write release notes for a shipped version, in the house changelog style.
---

# Release notes

{MARKER}

Write one line per change, grouped as Added, Changed and Fixed. Name the module each
change touched. Never invent a change that is not in the diff.
"""

HOUSE_STYLE = """---
name: house-style
description: Keep prose in the house voice: short sentences, no filler, no emoji.
---

# House style

Prefer the concrete noun. Cut every sentence that only warms the page up.
"""


class Provider(BaseHTTPRequestHandler):
    """The stub model: search the catalog, open the candidate, answer from the contract."""

    offered: list[list[str]] = []

    def log_message(self, *_: object) -> None:
        return None

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages") or []
        Provider.offered.append([str(tool["function"]["name"])
                                 for tool in (body.get("tools") or [])])
        results = [str(item.get("content") or "") for item in messages
                   if item.get("role") == "tool"]
        # A tool result carries no name; what the model has is its own earlier calls.
        asked_before = [item for item in messages
                        if item.get("role") == "assistant" and item.get("tool_calls")]
        last_call = (asked_before[-1]["tool_calls"][-1]["function"]["name"]
                     if asked_before else "")
        if not asked_before:
            message = self._tool_call("find_skills",
                                      {"query": "write release notes for a release"})
        elif last_call == "find_skills":
            # A model would use the candidate it was handed; here it is read out of the
            # result, which also proves the search really returned a name to use.
            candidate = self._candidate(results[0])
            message = self._tool_call("read_skill", {"name": candidate, "chars": 2000})
        else:
            found = re.search(rf"{MARKER}|Prefer the concrete noun",
                              self._result_text(results[-1]))
            quote = found.group(0) if found else "(nothing to quote)"
            message = {"role": "assistant",
                       "content": f"applied the skill; the contract says: {quote}"}
        payload = json.dumps({"choices": [{"message": message}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    @staticmethod
    def _tool_call(name: str, arguments: dict) -> dict:
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": f"call-{name}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(arguments)}}]}

    @staticmethod
    def _result_text(result: str) -> str:
        """A tool's own text, out of the record the call is sent as.

        The model is told `<tool> returned: <result>`, where the result is the tool's own
        record; it reads the words inside that, so the stub decodes it too instead of
        matching against escape sequences. An empty answer is a real answer here: it
        becomes a refusal the check then reports.
        """
        payload = result.split(" returned: ", 1)[-1]
        try:
            decoded = json.loads(payload)
        except ValueError:
            return payload
        if isinstance(decoded, dict):
            return str(decoded.get("text") or "")
        return payload

    @classmethod
    def _candidate(cls, result: str) -> str:
        """The name the search ranked first, as the model would read it."""
        match = re.search(r"^([A-Za-z0-9:._\-/]+)\s+\(match ", cls._result_text(result), re.M)
        return match.group(1) if match else ""


class Browser:
    """Real HTTP against the running application."""

    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.token = self.get("/api/session")["csrf"]

    def _open(self, request: urllib.request.Request) -> tuple[int, dict]:
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:      # a refusal is an answer too
            raw = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"error": raw[:200]}

    def get(self, path: str) -> dict:
        _status, body = self._open(urllib.request.Request(self.base + path))
        return body

    def status_get(self, path: str) -> tuple[int, dict]:
        return self._open(urllib.request.Request(self.base + path))

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Oneiro-CSRF": self.token},
            method="POST")
        return self._open(request)


def say(line: str = "") -> None:
    print(line, flush=True)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fingerprint(paths: list[Path]) -> dict[str, str]:
    prints: dict[str, str] = {}
    for path in paths:
        if path.is_file():
            prints[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        elif path.is_dir():
            entries = sorted(item.name for item in path.iterdir())
            prints[str(path)] = f"dir with {len(entries)} entries"
        else:
            prints[str(path)] = "(not there)"
    return prints


def cli(*arguments: str) -> tuple[int, str]:
    """One real process of the command line, seeing the settings in force right now.

    The environment is read at the moment of the call, not captured once, because the
    check changes `skills.paths` and `skills.catalog` between calls and a child that
    never saw the change would answer about a build that no longer exists.
    """
    done = subprocess.run([sys.executable, "-m", "oneiro", *arguments],
                          cwd=str(PROJECT),
                          env={**os.environ, "PYTHONPATH": str(PROJECT / "python"),
                               "PYTHONIOENCODING": "utf-8"},
                          capture_output=True, text=True, timeout=180,
                          encoding="utf-8", errors="replace")
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def main() -> int:
    SKILLS.mkdir(parents=True, exist_ok=True)
    (SKILLS / "release-notes").mkdir()
    (SKILLS / "release-notes" / "SKILL.md").write_text(RELEASE_NOTES, encoding="utf-8")
    (SKILLS / "house-style").mkdir()
    (SKILLS / "house-style" / "SKILL.md").write_text(HOUSE_STYLE, encoding="utf-8")

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()

    # Nothing of the owner's is touched: settings, data root and keys live in the
    # temporary folder, and the folders this check searches are its own.
    os.environ["ONEIRO_SETTINGS_FILE"] = str(WORK / "settings.json")
    os.environ["ONEIRO_DATA_DIR"] = str(WORK / "runtime")
    os.environ["ONEIRO_KEYS_FILE"] = str(WORK / "no-keys.env")
    os.environ["ONEIRO_LLM_BASE_URL"] = f"http://127.0.0.1:{provider.server_port}/v1"
    os.environ["ONEIRO_LLM_API_KEY"] = "live-check-key"
    os.environ["ONEIRO_LLM_MODEL"] = "stub/live-check"
    os.environ["ONEIRO_MCP_FILE"] = str(WORK / "mcp.json")
    os.environ["ONEIRO_MCP_AUTOSTART"] = "false"

    import uvicorn                                                  # noqa: E402
    from chat_fakes import GraphStub, MemoryLinks                    # noqa: E402
    from oneiro import skills, web                                   # noqa: E402
    from oneiro.runtime import Runtime                               # noqa: E402

    watched = [OWNER_SETTINGS, OWNER_SKILLS, WORKSPACE_CATALOG]
    before = fingerprint(watched)

    links = MemoryLinks()
    stub = GraphStub(links, WORK / "graph-writer.lock")
    runtime = Runtime(graph=stub)
    app = web.create_app(runtime=runtime, scheduler=False)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
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

    say(f"Oneiro on http://127.0.0.1:{port} (temporary root {WORK})")
    say(f"stub provider on http://127.0.0.1:{provider.server_port}/v1")
    say(f"skills.paths will point at {SKILLS}")
    say()

    # ---------- the catalog that travels with the product ----------
    say("== the catalog that ships with the product, and no skill folder at all ==")
    overview = browser.get("/api/skills")
    say(f"  GET /api/skills -> catalog {overview['catalog']}")
    say(f"      source: {overview['catalog_source']}, "
        f"{overview['skills']} contracts ({overview['routes']} reviewed + "
        f"{overview['parts']} parts), {overview['on_disk']} found in folders")
    for root in overview["roots"]:
        say(f"      folder: {root['path']}  [{root['named_by']}, "
            f"{'there' if root['exists'] else 'not there'}]")
    status, found = browser.status_get(
        "/api/skills/search?q=" + urllib.parse.quote("take a screenshot of a page"))
    say(f"  GET /api/skills/search -> {status}, best: "
        + ", ".join(f"{row['name']} ({row['score']})" for row in found["skills"][:3]))
    status, refused = browser.status_get("/api/skills/find-skills")
    say(f"  GET /api/skills/find-skills -> {status}")
    say(f"      {refused.get('error', '')[:150]}")
    say()

    say("== the command line, in its own process ==")
    for arguments in (("skills", "list"), ("skills", "search", "review a pull request"),
                      ("skills", "show", "find-skills")):
        code, output = cli(*arguments)
        first = " | ".join(line.strip() for line in output.strip().splitlines()[:2])
        say(f"  oneiro {' '.join(arguments)} -> exit {code}: {first[:160]}")
    say()

    # ---------- the folders the owner names ----------
    say("== skills.paths: folders that are really searched ==")
    os.environ["ONEIRO_SKILLS_PATHS"] = json.dumps([str(SKILLS)])
    found = browser.get("/api/skills/search?q=" + urllib.parse.quote(
        "write release notes for a release"))
    for row in found["skills"][:3]:
        say(f"  {row['name']:<34} match {row['score']:<3} review {row['confidence']:<4} "
            f"{row['status']}")
    status, contract = browser.status_get("/api/skills/release-notes")
    say(f"  GET /api/skills/release-notes -> {status}, {len(contract.get('text', ''))} "
        f"characters from {contract.get('path', '')}")
    say(f"      the marker line is in the contract: {MARKER in contract.get('text', '')}")
    status, unknown = browser.status_get("/api/skills/no-such-skill")
    say(f"  GET /api/skills/no-such-skill -> {status}: {unknown.get('error', '')[:90]}")
    code, output = cli("skills", "search", "write release notes for a release")
    say(f"  oneiro skills search -> exit {code}: "
        + " | ".join(line.strip() for line in output.strip().splitlines()[:2])[:160])
    code, output = cli("skills", "show", "release-notes", "--chars", "400")
    say(f"  oneiro skills show release-notes -> exit {code}, "
        f"first line: {output.strip().splitlines()[0][:100]}")
    say()

    say("== a catalog that cannot be read is named, not skipped ==")
    broken = WORK / "broken-catalog.json"
    broken.write_text("{not json", encoding="utf-8")
    os.environ["ONEIRO_SKILLS_CATALOG"] = str(broken)
    status, payload = browser.status_get("/api/skills")
    say(f"  GET /api/skills -> {status}: {payload.get('error', '')[:120]}")
    code, output = cli("skills", "list")
    say(f"  oneiro skills list -> exit {code}: {output.strip().splitlines()[0][:120]}")
    os.environ.pop("ONEIRO_SKILLS_CATALOG", None)
    say()

    # ---------- the turn ----------
    say("== a turn: the model searches, reads the contract, and answers from it ==")
    status, turn = browser.post("/api/message",
                                {"text": "prepare the release notes for this version",
                                 "client_id": "live-w3-turn"})
    say(f"  POST /api/message -> {status}")
    if status != 200:
        say(f"      {turn}")
        return 1
    say(f"  reply: {turn['reply']['text'][:160]}")
    for step in turn["steps"]:
        say(f"    step {step['index']}: {step['tool']} decision {step['decision']} "
            f"effect {step['effect']} state {step['state']} "
            f"args {json.dumps(step['arguments'])[:70]}")
        if step["state"] != "completed":
            say(f"        {str(step.get('result') or step['reason'])[:160]}")
    offered = [row for row in Provider.offered if row]
    say(f"  the model was offered, on its first call: "
        f"{', '.join(sorted(row for row in offered[0] if row.startswith(('find_', 'read_'))))}")
    from oneiro import skills as skills_module                        # noqa: E402
    try:
        catalog = skills_module.load()
    except skills_module.CatalogError:
        catalog = None
    tally = skills_module.evidence(
        [{"tool": step["tool"], "args": step["arguments"],
          "observation": step.get("result") or ""} for step in turn["steps"]], catalog)
    say(f"  the catalog gave this turn: {tally['lookups']} lookup(s), "
        f"{tally['contracts_read']} contract(s) read, {tally['observation_chars']} "
        f"characters of observation")
    say(f"  the reply quotes the contract: {MARKER in turn['reply']['text']}")
    say()

    say("== parity with the module the ranking came from, over the reviewed catalog ==")
    if WORKSPACE_CATALOG.is_file():
        import skills_index                                           # noqa: E402
        old = skills_index.load()
        new = skills_module.load(catalog_path=skills_module.ASSET, roots=[], cached=False)
        queries = ["take a screenshot of a page", "send a message to telegram",
                   "write release notes", "audit accessibility with wcag",
                   "review a pull request", "to be or not"]
        mismatches = [query for query in queries
                      if [(hit.name, hit.score) for hit in new.search(query, 5)]
                      != [(hit.name, hit.score) for hit in old.search(query, 5)]]
        say(f"  {old.size} contracts addressable in both; {len(queries)} queries, "
            f"{len(mismatches)} mismatch(es)")
    else:
        say(f"  no reviewed catalog at {WORKSPACE_CATALOG}: parity not checked here "
            f"(tests/test_skills.py checks it where the file exists)")
    say()

    # ---------- nothing of the owner's moved ----------
    say("== what this check left alone ==")
    after = fingerprint(watched)
    for path, seen in before.items():
        same = after.get(path) == seen
        say(f"  {'unchanged' if same else 'CHANGED  '} {path}  [{seen}]")
    say(f"  the check's own settings file: {WORK / 'settings.json'} "
        f"({'written' if (WORK / 'settings.json').exists() else 'never written'})")
    say()

    server.should_exit = True
    provider.shutdown()
    stub.store.close()
    problems = [path for path, seen in before.items() if after.get(path) != seen]
    if problems:
        say(f"the check changed the owner's files: {problems}")
        return 1
    say(f"W3 live check finished; its temporary root is kept at {WORK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
