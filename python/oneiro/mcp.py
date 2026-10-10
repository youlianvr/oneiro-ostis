"""MCP: the services Oneiro did not write, taken rather than rebuilt.

The server list is **ours** — `mcp.file` (`~/.oneiro/mcp.json`) — in the dictionary
other clients already use, so a list can be read and written by hand and no other
program's configuration is ever modified:

    {"mcp": {"<name>": {"type": "local", "command": ["npx", "-y", "thing"],
                        "environment": {}, "enabled": true},
             "<other>": {"type": "remote", "url": "https://host/mcp", "enabled": false}}}

`mcp.servers` and a bare `mcpServers` map are accepted **on read**, because those are
what the owner's other clients write; keys this build does not understand are kept and
written back. Importing from another client is a read of that client's file and a write
of ours, never the other way round: `survey()` only looks, `preview()` says what would be
added, and `save()` is the only thing that writes.

Two transports, one discipline:

* **local** — a child process speaking line-delimited JSON-RPC over stdio;
* **remote** — JSON-RPC over HTTP, with plain-JSON and event-stream replies both read.

**Every call is bounded and every failure is named.** A server that cannot start is a
recorded failure with its own stderr tail, not a hanging turn; a call that times out
comes back as a refusal naming the server and the method; a server that exits mid-call is
reported as closed. Nothing here invents a result.

**A tool is a tool.** Each MCP tool becomes an ordinary `Tool` named `<server>.<tool>`
with the effect `mcp_call`, which `permissions.exec` governs — so an MCP call goes
through the same `Policy`, the same approval flow and the same `Action` record as a
built-in tool, and it can be refused or confirmed exactly like one.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from oneiro import config
from oneiro.tools import ROLES, Tool, ToolError

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "oneiro"
CLIENT_VERSION = "1.0"
LOCAL = "local"
REMOTE = "remote"
#: The one effect every MCP tool declares. `permissions.exec` governs it.
EFFECT = "mcp_call"

#: A local server may have to fetch its package on first start, so starting is
#: generous; a request inside a running session is not, because a turn waits for it.
START_TIMEOUT = 40.0
REQUEST_TIMEOUT = 30.0
MAX_TOOLS = 200
OBSERVATION_CHARS = 4000
FAILURE_CHARS = 300
STDERR_LINES = 40
NAME_CHARS = 64
CLOSE_GRACE = 5.0


class McpError(RuntimeError):
    """A configuration or transport problem, with a reason worth reading."""


class McpUncertain(McpError):
    """The request was sent and the answer never came.

    For a tool call this is the difference between "it did not happen" and "it may
    have happened": the server may have carried it out before it stopped answering.
    Only a call, never a start or a listing, can be uncertain, because nothing is
    asked of the other side before a call."""


def tool_key(server: str, tool: str) -> str:
    """The name the model sees and the record keeps: ``<server>.<tool>``."""
    return f"{server}.{tool}"


def split_tool_key(key: str) -> tuple[str, str]:
    """`<server>.<tool>` back into its two parts, or a named refusal."""
    server, dot, tool = str(key).partition(".")
    if not dot or not server or not tool:
        raise McpError(f"{key!r} is not an mcp tool name; write it as server.tool")
    return server, tool


# ---------- the product's own list ----------


@dataclass(frozen=True)
class Server:
    """One server as this build understands it, with everything else kept."""

    name: str
    kind: str = LOCAL
    command: tuple[str, ...] = ()
    url: str = ""
    enabled: bool = True
    environment: tuple[tuple[str, str], ...] = ()
    cwd: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> str:
        """How this server is reached, for a surface to show."""
        return self.url if self.kind == REMOTE else " ".join(self.command)

    def to_dict(self) -> dict[str, Any]:
        """The OpenCode shape, with the keys this build did not use written back."""
        entry: dict[str, Any] = dict(self.extra)
        if self.kind == REMOTE:
            entry.update({"type": REMOTE, "url": self.url})
        else:
            entry.update({"type": LOCAL, "command": list(self.command)})
            if self.environment:
                entry["environment"] = dict(self.environment)
            if self.cwd:
                entry["cwd"] = self.cwd
        entry["enabled"] = self.enabled
        return entry

    def with_enabled(self, enabled: bool) -> "Server":
        return Server(self.name, self.kind, self.command, self.url, enabled,
                      self.environment, self.cwd, dict(self.extra))


def _name_ok(name: str) -> str:
    """A server name this build can use in a tool name, or a named refusal."""
    text = str(name or "").strip()
    if not text or len(text) > NAME_CHARS:
        raise McpError("a server name is 1..64 characters")
    if any(character in text for character in "./\\ "):
        raise McpError(f"the server name {text!r} may not contain a dot, slash or space")
    return text


def _entry_to_server(name: str, raw: Any) -> Server:
    """One config entry in any shape the ecosystem writes, or a named refusal."""
    if not isinstance(raw, dict):
        raise McpError("a server entry must be an object")
    kind = str(raw.get("type") or "").strip().lower()
    command = raw.get("command")
    args = raw.get("args")
    argv: list[str] = []
    if isinstance(command, list):
        argv = [str(item) for item in command]
    elif isinstance(command, str) and command.strip():
        argv = [command.strip(), *[str(item) for item in (args or [])]]
    url = str(raw.get("url") or "").strip()
    if kind in ("http", "sse", "streamable-http", "remote"):
        kind = REMOTE
    elif kind in ("stdio", "local", ""):
        kind = LOCAL if argv else (REMOTE if url else "")
    else:
        raise McpError(f"unknown server type {raw.get('type')!r}")
    if kind == REMOTE and not url:
        raise McpError("a remote server needs a url")
    if kind == LOCAL and not argv:
        raise McpError("a local server needs a command")
    environment = raw.get("environment") if isinstance(raw.get("environment"), dict) else raw.get("env")
    kept = {key: value for key, value in raw.items()
            if key not in ("type", "command", "args", "url", "enabled",
                           "environment", "env", "cwd")}
    return Server(
        name=_name_ok(name), kind=kind, command=tuple(argv), url=url,
        enabled=bool(raw.get("enabled", True)),
        environment=tuple((str(key), str(value))
                          for key, value in (environment or {}).items()),
        cwd=str(raw.get("cwd") or ""), extra=kept)


def _block(document: dict[str, Any]) -> dict[str, Any]:
    """The server map inside a document, whichever spelling the file uses."""
    mcp = document.get("mcp")
    if isinstance(mcp, dict):
        servers = mcp.get("servers")
        if isinstance(servers, dict):
            return servers
        return {key: value for key, value in mcp.items() if key != "servers"}
    for key in ("mcpServers", "servers"):
        found = document.get(key)
        if isinstance(found, dict):
            return found
    return {}


@dataclass
class Document:
    """`mcp.json` as it is on disk, plus what this build could read out of it."""

    path: Path
    data: dict[str, Any] = field(default_factory=dict)
    servers: dict[str, Server] = field(default_factory=dict)
    #: Every entry exactly as the file wrote it, including the ones this build
    #: could not read. They are written back untouched, so a save can never eat
    #: an entry a newer client understood and this build did not.
    raw_entries: dict[str, Any] = field(default_factory=dict)
    problems: tuple[dict[str, str], ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "error": self.error,
                "servers": {name: server.to_dict() for name, server in self.servers.items()},
                "problems": list(self.problems)}

    def save(self, changes: dict[str, Server] | None = None,
             removals: Iterable[str] = ()) -> dict[str, Any]:
        """Write the list atomically: only the `mcp` map changes, nothing else.

        A file this build could not read is **not** overwritten: an unreadable list
        is reported and left alone, because replacing it would destroy entries
        nobody has looked at. A `mcpServers` block that was already in the file is
        kept exactly as it is, so pointing `mcp.file` at another client's file
        cannot silently eat that client's own list.
        """
        if self.error:
            raise McpError(f"{self.path} cannot be read ({self.error}), so it is not "
                           f"overwritten")
        dropped = {str(name) for name in removals}
        block = {name: value for name, value in self.raw_entries.items() if name not in dropped}
        servers = dict(self.servers)
        servers.update(changes or {})
        for name in dropped:
            servers.pop(name, None)
        for name, server in servers.items():
            block[name] = server.to_dict()
        document = {**self.data, "mcp": block}
        raw = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name("." + self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temp.write_text(raw, encoding="utf-8")
            temp.replace(self.path)
        finally:
            temp.unlink(missing_ok=True)
        self.data, self.servers = document, servers
        return {"path": str(self.path), "written": sorted(changes or {}),
                "removed": sorted(dropped), "bytes": len(raw.encode("utf-8"))}


def configured_path() -> Path:
    """Where the owner's list lives, as declared in the settings."""
    return config.path("mcp.file")


def load(path: Path | str | None = None) -> Document:
    """Read the list. A file that is not there is an empty list, not an error."""
    target = Path(path) if path is not None else configured_path()
    if not target.is_file():
        return Document(path=target)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Document(path=target, error=f"the mcp list cannot be read ({type(exc).__name__})")
    if not isinstance(raw, dict):
        return Document(path=target, error="the mcp list must be a JSON object")
    servers: dict[str, Server] = {}
    problems: list[dict[str, str]] = []
    for name, entry in _block(raw).items():
        try:
            servers[str(name)] = _entry_to_server(str(name), entry)
        except McpError as exc:
            problems.append({"name": str(name), "reason": str(exc)})
    return Document(path=target, data=raw, servers=servers,
                    raw_entries={str(name): entry for name, entry in _block(raw).items()},
                    problems=tuple(problems))


# ---------- what the owner's other clients declare (read only) ----------

CLIENTS = (
    ("OpenCode", Path.home() / ".config" / "opencode" / "opencode.json", "opencode"),
    ("OpenClaw", Path.home() / ".openclaw" / "workspace" / ".mcp.json", "mcpServers"),
    ("Claude Desktop", Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
     / "Claude" / "claude_desktop_config.json", "mcpServers"),
    ("Cursor", Path.home() / ".cursor" / "mcp.json", "mcpServers"),
    ("VS Code", Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
     / "Code" / "User" / "mcp.json", "vscode"),
    ("Windsurf", Path.home() / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers"),
)


@dataclass(frozen=True)
class Found:
    """One client config: what it is, whether it is there, and what it declares."""

    client: str
    path: str
    found: bool = False
    servers: tuple[Server, ...] = ()
    problems: tuple[dict[str, str], ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"client": self.client, "path": self.path, "found": self.found,
                "servers": [{"name": server.name, "kind": server.kind,
                             "source": server.source, "enabled": server.enabled}
                            for server in self.servers],
                "problems": list(self.problems), "error": self.error}


def survey(clients: Iterable[tuple[str, Path, str]] = CLIENTS) -> list[Found]:
    """What each known client declares. Reads only; nothing is written anywhere."""
    reports: list[Found] = []
    for label, path, _shape in clients:
        if not path.is_file():
            reports.append(Found(client=label, path=str(path)))
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            block = _block(document) if isinstance(document, dict) else {}
        except (OSError, ValueError) as exc:
            reports.append(Found(client=label, path=str(path), found=True,
                                 error=f"unreadable ({type(exc).__name__})"))
            continue
        servers: list[Server] = []
        problems: list[dict[str, str]] = []
        for name, entry in block.items():
            try:
                servers.append(_entry_to_server(str(name), entry))
            except McpError as exc:
                problems.append({"name": str(name), "reason": str(exc)})
        reports.append(Found(client=label, path=str(path), found=True,
                             servers=tuple(servers), problems=tuple(problems)))
    return reports


def preview(document: Document, reports: list[Found] | None = None,
            only: Iterable[str] = ()) -> dict[str, Any]:
    """What an import would add, without writing anything.

    A name the product's own list already has is never overwritten: the owner's
    own entry wins, and the collision is named instead.
    """
    wanted = {str(name) for name in only}
    add: dict[str, Server] = {}
    already: list[str] = []
    refused: list[dict[str, str]] = []
    for report in reports if reports is not None else survey():
        for problem in report.problems:
            refused.append({**problem, "from": report.client})
        for server in report.servers:
            if wanted and server.name not in wanted:
                continue
            if server.name in document.servers:
                already.append(server.name)
                continue
            add.setdefault(server.name, server)
    return {"add": {name: server.to_dict() for name, server in sorted(add.items())},
            "already": sorted(set(already)), "refused": refused,
            "path": str(document.path), "sources": [report.to_dict() for report in
                                                    (reports if reports is not None else survey())]}


def apply_import(document: Document, reports: list[Found] | None = None,
                 only: Iterable[str] = ()) -> dict[str, Any]:
    """Add the surveyed servers to **our** file and to no other file."""
    plan = preview(document, reports, only)
    added = {name: _entry_to_server(name, entry) for name, entry in plan["add"].items()}
    if not added:
        return {**plan, "written": []}
    written = document.save(changes=added)
    return {**plan, "written": written["written"], "bytes": written["bytes"]}


# ---------- transports ----------


class Session(Protocol):
    """One live conversation with one server, however it is carried."""

    name: str

    def start(self) -> None: ...
    def list_tools(self) -> list[dict[str, Any]]: ...
    def call(self, tool: str, arguments: dict[str, Any]) -> str: ...
    def close(self) -> None: ...


class LocalSession:
    """A child process speaking line-delimited JSON-RPC over stdio."""

    def __init__(self, server: Server, *, request_timeout: float = REQUEST_TIMEOUT,
                 start_timeout: float = START_TIMEOUT) -> None:
        self.server = server
        self.name = server.name
        self.request_timeout = request_timeout
        self.start_timeout = start_timeout
        self.process: subprocess.Popen[str] | None = None
        self.calls = 0
        self._inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr: list[str] = []
        self._next_id = 0
        self._write_lock = threading.Lock()

    def argv(self) -> list[str]:
        """The spawn command, through cmd.exe when it is a `.cmd` shim.

        On Windows an npm-installed server is a `.cmd` wrapper that CreateProcess
        cannot start directly, which is why the shim is resolved here.
        """
        first, *rest = self.server.command
        found = shutil.which(first) or first
        if found.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", found, *rest]
        return [found, *rest]

    def start(self) -> None:
        if self.process is not None:
            return
        environment = dict(os.environ, **dict(self.server.environment))
        self.process = subprocess.Popen(
            self.argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=environment,
            cwd=self.server.cwd or None)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            self._request("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                         "capabilities": {},
                                         "clientInfo": {"name": CLIENT_NAME,
                                                        "version": CLIENT_VERSION}},
                          timeout=self.start_timeout)
        except McpError as exc:
            self.close()
            raise McpError(str(exc)) from None
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.terminate()
            process.wait(timeout=CLOSE_GRACE)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    def _read_stdout(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue        # a server printing prose is not a protocol error
            if isinstance(message, dict) and "id" in message:
                self._inbox.put(message)
        self._inbox.put({"__eof__": True})

    def _read_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr.append(line.strip())
            del self._stderr[:-STDERR_LINES]

    def _tail(self) -> str:
        return " | ".join(self._stderr[-3:])[:FAILURE_CHARS]

    def _send(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise McpError(f"{self.name}: the server is not running")
        with self._write_lock:
            try:
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise McpError(f"{self.name}: writing to the server failed "
                               f"({type(exc).__name__})") from None

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any], *,
                 timeout: float | None = None, uncertain: bool = False) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.time() + (timeout if timeout is not None else self.request_timeout)
        kind = McpUncertain if uncertain else McpError
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                tail = self._tail()
                raise kind(f"{self.name}: {method} did not answer within "
                           f"{timeout if timeout is not None else self.request_timeout:.0f}s"
                           + (f" (server said: {tail})" if tail else ""))
            try:
                message = self._inbox.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("__eof__"):
                detail = self._tail()
                self.process = None
                raise kind(f"{self.name}: the server stopped"
                           + (f" during {method}" if method != "initialize" else " while starting")
                           + (f" (it said: {detail})" if detail else ""))
            if message.get("id") != request_id:
                continue        # a late answer to a request already given up on
            if "error" in message:
                error = message.get("error") or {}
                raise McpError(f"{self.name}: {method} was refused by the server: "
                               f"{str(error.get('message') or error)[:FAILURE_CHARS]}")
            result = message.get("result")
            return result if isinstance(result, dict) else {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        return [tool for tool in tools if isinstance(tool, dict) and tool.get("name")]

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.calls += 1
        # `uncertain`: an answer that never comes to a call may mean the tool ran.
        result = self._request("tools/call", {"name": tool, "arguments": arguments or {}},
                               uncertain=True)
        return content_to_text(result, result.get("isError"))


class RemoteSession:
    """JSON-RPC over HTTP: one POST per request, plain JSON or event-stream back."""

    def __init__(self, server: Server, *, request_timeout: float = REQUEST_TIMEOUT,
                 start_timeout: float = START_TIMEOUT) -> None:
        self.server = server
        self.name = server.name
        self.request_timeout = request_timeout
        self.start_timeout = start_timeout
        self.calls = 0
        self.session_id = ""
        self._next_id = 0

    def start(self) -> None:
        self._request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                     "clientInfo": {"name": CLIENT_NAME,
                                                    "version": CLIENT_VERSION}},
                      timeout=self.start_timeout)
        self._notify("notifications/initialized", {})

    def close(self) -> None:
        """Nothing is held open: an HTTP server is not this process's child."""

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params}, expect_reply=False)
        except McpError:
            # A notification that could not be delivered is not a failed session:
            # the next request says for itself whether the server is there.
            return

    def _post(self, message: dict[str, Any], *, expect_reply: bool,
              timeout: float | None = None, uncertain: bool = False) -> dict[str, Any]:
        body = json.dumps(message).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        request = urllib.request.Request(self.server.url, data=body, headers=headers, method="POST")
        limit = timeout if timeout is not None else self.request_timeout
        try:
            with urllib.request.urlopen(request, timeout=limit) as response:
                raw = response.read(OBSERVATION_CHARS * 8)
                content_type = response.headers.get("Content-Type", "")
                returned = response.headers.get("Mcp-Session-Id", "")
        except urllib.error.HTTPError as exc:
            # A reply came back, so the server is there and the call was refused.
            raise McpError(f"{self.name}: the server answered HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # The body was already sent: a timeout here means the call may have run,
            # while a refused connection means it never left this machine.
            kind = McpUncertain if uncertain else McpError
            raise kind(f"{self.name}: unreachable at {self.server.url} "
                       f"({type(exc).__name__})") from None
        if returned:
            self.session_id = returned
        if not expect_reply:
            return {}
        return _decode_body(self.name, content_type, raw)

    def _request(self, method: str, params: dict[str, Any], *,
                 timeout: float | None = None, uncertain: bool = False) -> dict[str, Any]:
        self._next_id += 1
        answer = self._post({"jsonrpc": "2.0", "id": self._next_id, "method": method,
                             "params": params}, expect_reply=True, timeout=timeout,
                            uncertain=uncertain)
        if "error" in answer:
            error = answer.get("error") or {}
            raise McpError(f"{self.name}: {method} was refused by the server: "
                           f"{str(error.get('message') or error)[:FAILURE_CHARS]}")
        result = answer.get("result")
        return result if isinstance(result, dict) else {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        return [tool for tool in tools if isinstance(tool, dict) and tool.get("name")]

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.calls += 1
        result = self._request("tools/call", {"name": tool, "arguments": arguments or {}},
                               uncertain=True)
        return content_to_text(result, result.get("isError"))


def _decode_body(name: str, content_type: str, raw: bytes) -> dict[str, Any]:
    """A reply that may be one JSON object or an event stream carrying it."""
    text = raw.decode("utf-8", "replace").strip()
    if "text/event-stream" in content_type or text.startswith("event:") or "\ndata:" in text:
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                message = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(message, dict):
                return message
        raise McpError(f"{name}: the event stream carried no reply")
    try:
        message = json.loads(text)
    except ValueError:
        raise McpError(f"{name}: the server's reply is not JSON") from None
    return message if isinstance(message, dict) else {}


def content_to_text(result: dict[str, Any], is_error: Any = False) -> str:
    """MCP answers carry a content list; keep the text and name the rest."""
    parts: list[str] = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        kind = item.get("type")
        if kind == "text":
            parts.append(str(item.get("text") or ""))
        elif kind == "image":
            parts.append(f"[image {item.get('mimeType') or 'unknown'}]")
        elif kind == "resource":
            resource = item.get("resource") or {}
            parts.append(str(resource.get("text") or resource.get("uri") or "[resource]"))
        else:
            parts.append(f"[{kind or 'content'}]")
    if not parts and result.get("structuredContent") is not None:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    text = "\n".join(parts).strip() or "[no content]"
    if is_error:
        text = f"the server reported an error: {text}"
    if len(text) > OBSERVATION_CHARS:
        text = text[:OBSERVATION_CHARS] + f"\n... [{len(text) - OBSERVATION_CHARS} characters truncated]"
    return text


def session_for(server: Server, *, request_timeout: float = REQUEST_TIMEOUT,
                start_timeout: float = START_TIMEOUT) -> Session:
    """The transport this server's kind asks for."""
    if server.kind == REMOTE:
        return RemoteSession(server, request_timeout=request_timeout,
                             start_timeout=start_timeout)
    return LocalSession(server, request_timeout=request_timeout, start_timeout=start_timeout)


def _start_and_list(session: Session) -> list[dict[str, Any]]:
    """Blocking work for opening one server: start it and ask for its tools."""
    session.start()
    return session.list_tools()[:MAX_TOOLS]


# ---------- the open servers of this process ----------


def tool_for(server: str, description: dict[str, Any]) -> Tool:
    """One MCP tool as an ordinary tool, so the policy and the record apply."""
    name = tool_key(server, str(description["name"]))
    schema = description.get("inputSchema")
    schema = schema if isinstance(schema, dict) else {}
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    required = tuple(str(item) for item in (schema.get("required") or ())
                     if isinstance(item, str))
    text = str(description.get("description") or "").strip()

    async def handler(_context: dict[str, Any], arguments: dict[str, Any]) -> Any:
        outcome = await hub().call(name, arguments)
        if outcome["state"] == "uncertain":
            # The call was on the wire and the answer never came: for an effect
            # outside this process that means the tool may have run, so the turn is
            # told exactly that and the call is never simply repeated.
            raise ToolError(str(outcome["reason"]), uncertain=True)
        if not outcome["ok"]:
            # A failed call is a failed call: the reason goes back, and no result
            # is invented for the model to build on.
            raise ToolError(str(outcome["reason"]))
        return {"server": server, "tool": str(description["name"]),
                "text": outcome["text"]}

    return Tool(name, (f"{server}: {text}"[:1000] or f"the {server} MCP tool {name}."),
                properties, required, ROLES, EFFECT, handler)


class Hub:
    """The servers this process has open, and the tools they offer.

    Nothing is offered until a server is actually open, so a turn is never handed
    a tool whose server is down — a dead shelf is a named failure on a surface,
    not a call that hangs while the owner waits.
    """

    def __init__(self, path: Path | str | None = None, *,
                 request_timeout: float = REQUEST_TIMEOUT,
                 start_timeout: float = START_TIMEOUT) -> None:
        self.path = Path(path) if path is not None else None
        self.request_timeout = request_timeout
        self.start_timeout = start_timeout
        self.sessions: dict[str, Session] = {}
        #: Sessions that are being started right now. Kept apart from `sessions`
        #: so nothing offers tools of a server whose catalogue has not arrived, and
        #: still closed on shutdown — a child process left behind by a start that
        #: was interrupted must not outlive the process that started it.
        self.starting: dict[str, Session] = {}
        self.catalogs: dict[str, list[dict[str, Any]]] = {}
        self.failures: dict[str, str] = {}
        self.opened_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def document(self) -> Document:
        return load(self.path) if self.path is not None else load()

    async def open(self, name: str) -> dict[str, Any]:
        """Start one server and read its tools. A failure is recorded, not raised."""
        document = self.document()
        server = document.servers.get(name)
        if server is None:
            reason = (f"no server named {name} in {document.path}"
                      if not document.error else document.error)
            self.failures[name] = reason
            return {"opened": False, "name": name, "reason": reason}
        if not server.enabled:
            # The switch is authoritative: a server the owner turned off is not
            # started by any surface, whatever asks. This is not a failure of the
            # server, so it is not recorded as one — the state stays `disabled`.
            return {"opened": False, "name": name,
                    "reason": (f"the server {name} is turned off in {document.path}; "
                               f"turn it on before opening it")}
        with self._lock:
            if name in self.sessions:
                return {"opened": True, "name": name,
                        "tools": len(self.catalogs.get(name, []))}
        session = session_for(server, request_timeout=self.request_timeout,
                              start_timeout=self.start_timeout)
        with self._lock:
            self.starting[name] = session
        try:
            catalog = await asyncio.to_thread(_start_and_list, session)
        except (McpError, OSError) as exc:
            with self._lock:
                self.starting.pop(name, None)
            self.failures[name] = str(exc)[:FAILURE_CHARS]
            session.close()
            return {"opened": False, "name": name, "reason": self.failures[name]}
        with self._lock:
            self.starting.pop(name, None)
            self.sessions[name] = session
            self.catalogs[name] = catalog
            self.opened_at[name] = time.time()
            self.failures.pop(name, None)
        return {"opened": True, "name": name, "tools": len(catalog)}

    async def open_enabled(self, *, only: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Open every enabled server, or the named ones. Nothing else is touched."""
        document = self.document()
        wanted = [str(name) for name in only] or [name for name, server
                                                 in document.servers.items() if server.enabled]
        reports = []
        for name in wanted:
            reports.append(await self.open(name))
        return reports

    def registry(self) -> dict[str, Tool]:
        """The tools of the servers that are open right now, and no others."""
        tools: dict[str, Tool] = {}
        for name, catalog in self.catalogs.items():
            for description in catalog:
                tool = tool_for(name, description)
                tools[tool.name] = tool
        return tools

    async def call(self, key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call one tool and say what happened: text on success, a reason otherwise."""
        try:
            server, tool = split_tool_key(key)
        except McpError as exc:
            return {"ok": False, "state": "failed", "reason": str(exc), "text": ""}
        with self._lock:
            session = self.sessions.get(server)
        if session is None:
            reason = (self.failures.get(server)
                      or f"the server {server} is not open in this process")
            return {"ok": False, "state": "failed", "text": "", "server": server,
                    "reason": f"{key} did not run: {reason}"}
        try:
            text = await asyncio.to_thread(session.call, tool, dict(arguments or {}))
        except McpUncertain as exc:
            self.failures[server] = str(exc)[:FAILURE_CHARS]
            return {"ok": False, "state": "uncertain", "text": "", "server": server,
                    "reason": (f"{key} was sent and {exc}; whether the tool ran is "
                               f"unknown, so it is not repeated")}
        except (McpError, OSError) as exc:
            self.failures[server] = str(exc)[:FAILURE_CHARS]
            return {"ok": False, "state": "failed", "text": "", "server": server,
                    "reason": f"{key} did not run: {exc}"}
        return {"ok": True, "state": "completed", "reason": "the server answered",
                "text": text, "server": server, "tool": tool}

    def disconnect(self, name: str) -> dict[str, Any]:
        """Stop offering one server's tools and let the server go.

        Turning a server off has to take effect where the owner can see it: a
        server that is off must not keep answering turns until the next launch only
        because it happened to be open when the switch was flipped.
        """
        with self._lock:
            session = self.sessions.pop(name, None)
            interrupted = self.starting.pop(name, None)
            self.catalogs.pop(name, None)
            self.opened_at.pop(name, None)
            self.failures.pop(name, None)
        for live in (session, interrupted):
            if live is None:
                continue
            try:
                live.close()
            except OSError:
                pass
        return {"name": name, "closed": session is not None or interrupted is not None}

    def states(self, document: Document | None = None) -> list[dict[str, Any]]:
        """Every declared server with its state, for a surface to show honestly."""
        found = document if document is not None else self.document()
        rows = []
        for name, server in sorted(found.servers.items()):
            open_now = name in self.sessions
            rows.append({
                "name": name, "kind": server.kind, "source": server.source,
                "enabled": server.enabled, "open": open_now,
                "tools": len(self.catalogs.get(name, [])) if open_now else 0,
                "opened_at": (time.strftime("%Y-%m-%dT%H:%M:%S",
                                            time.localtime(self.opened_at[name]))
                              if name in self.opened_at else ""),
                "failure": self.failures.get(name, ""),
                "state": ("open" if open_now else
                          ("failed" if name in self.failures else
                           ("closed" if server.enabled else "disabled"))),
            })
        return rows

    def close(self) -> None:
        with self._lock:
            sessions = {**self.starting, **self.sessions}
            self.sessions, self.starting = {}, {}
        for session in sessions.values():
            try:
                session.close()
            except OSError:
                pass
        self.catalogs.clear()


_HUB: Hub | None = None
_HUB_LOCK = threading.Lock()


def hub() -> Hub:
    """The one hub of this process. Creating it opens nothing."""
    global _HUB
    with _HUB_LOCK:
        if _HUB is None:
            _HUB = Hub()
        return _HUB


def set_hub(replacement: Hub | None) -> None:
    """Install a hub (tests, and a process that wants its own path). Closes the old one."""
    global _HUB
    with _HUB_LOCK:
        previous, _HUB = _HUB, replacement
    if previous is not None and previous is not replacement:
        previous.close()


def registry() -> dict[str, Tool]:
    """The MCP tools this process may offer the agent right now."""
    return hub().registry()
