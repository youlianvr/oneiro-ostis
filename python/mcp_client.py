"""MCP client: the agent's hands for services this project did not write.

Owner decision (2026-09-22): integrations are taken, not rebuilt. A whole
shelf of services already runs beside this project (Telegram, Google
Workspace, a browser, databases, Obsidian), each speaking the Model Context
Protocol. Re-implementing them inside Oneiro would be a duplicate of working
software.

Compatibility is the point of this module, so deliberately:

* the server list is read from the **same** ``.mcp.json`` that OpenClaw reads,
  not from a file of our own;
* the transport is the same stdio JSON-RPC the whole ecosystem speaks;
* a tool the agent calls here is the same tool a person gets in OpenClaw.

What this module adds on top of a bare client is the discipline the rest of
the project lives by: every call is bounded in time and in size, a server that
fails to start is reported as a named failure instead of hanging the episode,
and what came back can be recorded verbatim.

Nothing here decides *which* servers the agent may use; that is a caller's
allowlist, so a run can be measured with and without the shelf.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "oneiro-ostis"

START_TIMEOUT = 90.0        # npx has to fetch a package on a cold machine
REQUEST_TIMEOUT = 60.0
OBSERVATION_CHARS = 4000    # what a tool may return into the trajectory
STDERR_CHARS = 2000         # kept for diagnosing a failed start

DEFAULT_CONFIG_SEARCH = (
    Path(".openclaw") / "workspace" / ".mcp.json",
    Path(".mcp.json"),
)

# Servers this project is allowed to open by default. Kept short on purpose:
# every opened server is a process, and an episode must stay bounded.
DEFAULT_SERVERS = ("telegram-mcp-bot",)


class McpError(RuntimeError):
    """A protocol or transport failure that survived the bounded wait."""


@dataclass
class ServerConfig:
    """One server entry from ``mcp.json``, ready to be spawned."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)
    cwd: Optional[str] = None

    def argv(self) -> list[str]:
        """The spawn command, routed through cmd.exe when it is a wrapper.

        On Windows an npm-installed tool is a ``.cmd`` shim that CreateProcess
        cannot launch directly; the same fix the opencode runner uses.
        """
        found = shutil.which(self.command) or self.command
        if found.lower().endswith((".cmd", ".bat")):
            return ["cmd", "/c", found, *self.args]
        return [found, *self.args]


def find_config(path: Optional[Path] = None) -> Path:
    """The ``mcp.json`` to read: an explicit path, or the usual locations."""
    if path is not None:
        candidate = Path(path)
        if not candidate.is_file():
            raise McpError(f"no mcp config at {candidate}")
        return candidate
    for relative in DEFAULT_CONFIG_SEARCH:
        for base in (Path.cwd(), *Path.cwd().parents, Path.home()):
            candidate = (base / relative) if not relative.is_absolute() else relative
            if candidate.is_file():
                return candidate
    raise McpError("no mcp.json found; pass the path explicitly")


def load_servers(path: Optional[Path] = None) -> dict[str, ServerConfig]:
    """Every server the config declares, in the config's own shape."""
    config_path = find_config(path)
    data = json.loads(config_path.read_text(encoding="utf-8"))
    block = data.get("mcpServers") or data
    servers: dict[str, ServerConfig] = {}
    for name, entry in block.items():
        if not isinstance(entry, dict) or "command" not in entry:
            continue  # http/sse servers are reached differently; not this unit
        servers[name] = ServerConfig(
            name=name,
            command=str(entry["command"]),
            args=[str(a) for a in (entry.get("args") or [])],
            env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
            cwd=entry.get("cwd"),
        )
    return servers


def tool_key(server: str, tool: str) -> str:
    """The name the model sees: ``mcp__<server>__<tool>``."""
    return f"mcp__{server}__{tool}"


def split_tool_key(key: str) -> tuple[str, str]:
    """Inverse of :func:`tool_key`; raises when the key is not ours."""
    parts = str(key).split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp" or not parts[1] or not parts[2]:
        raise McpError(f"not an mcp tool key: {key}")
    return parts[1], parts[2]


class McpSession:
    """One live stdio conversation with one server."""

    def __init__(self, config: ServerConfig, request_timeout: float = REQUEST_TIMEOUT,
                 observation_chars: int = OBSERVATION_CHARS):
        self.config = config
        self.request_timeout = request_timeout
        self.observation_chars = observation_chars
        self.process: Optional[subprocess.Popen] = None
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._stderr: list[str] = []
        self._next_id = 0
        self._lock = threading.Lock()
        self.started_at = 0.0
        self.calls = 0

    # -- lifecycle --

    def start(self) -> None:
        if self.process is not None:
            return
        env = dict(os.environ, **self.config.env)
        self.process = subprocess.Popen(
            self.config.argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            bufsize=1, env=env, cwd=self.config.cwd,
        )
        self.started_at = time.time()
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": CLIENT_NAME, "version": "1"},
        }, timeout=START_TIMEOUT)
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
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    # -- protocol --

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
            except json.JSONDecodeError:
                continue  # a server that prints prose is not a protocol error
            if isinstance(message, dict) and "id" in message:
                self._inbox.put(message)
        self._inbox.put({"__eof__": True})

    def _read_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr.append(line.strip())
            del self._stderr[:-40]

    def send(self, message: dict) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise McpError(f"{self.config.name}: session is not running")
        with self._lock:
            try:
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
            except (OSError, ValueError) as exc:
                raise McpError(f"{self.config.name}: write failed: {exc}") from exc

    def _notify(self, method: str, params: dict) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict,
                 timeout: Optional[float] = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method,
                   "params": params})
        deadline = time.time() + (timeout or self.request_timeout)
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                tail = " | ".join(self._stderr[-3:])
                raise McpError(f"{self.config.name}: {method} timed out"
                               + (f" (stderr: {tail})" if tail else ""))
            try:
                message = self._inbox.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("__eof__"):
                detail = " | ".join(self._stderr[-3:])
                if method == "initialize":
                    raise McpError(
                        f"{self.config.name}: server exited during startup"
                        + (f" (stderr: {detail})" if detail else "")
                    )
                self.process = None
                raise McpError(f"{self.config.name}: server closed the connection"
                               + (f" (stderr: {detail})" if detail else ""))
            if message.get("id") != request_id:
                continue  # a late answer to something we already gave up on
            if "error" in message:
                error = message["error"] or {}
                raise McpError(f"{self.config.name}: {method} failed: "
                               f"{error.get('message') or error}")
            return message.get("result") or {}

    # -- the two useful calls --

    def list_tools(self) -> list[dict]:
        """Every tool this server offers, with its schema."""
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        return [t for t in tools if isinstance(t, dict) and t.get("name")]

    def call(self, tool: str, arguments: dict) -> str:
        """Call one tool and return its text, bounded."""
        self.calls += 1
        result = self._request("tools/call",
                               {"name": tool, "arguments": arguments or {}})
        text = _content_to_text(result)
        if result.get("isError"):
            text = f"[tool reported an error] {text}"
        return _clip(text, self.observation_chars)

    # -- evidence --

    def status(self) -> dict:
        return {"server": self.config.name, "calls": self.calls,
                "started": bool(self.started_at),
                "start_seconds": round(self.started_at, 3) if self.started_at else 0.0}


def _content_to_text(result: dict) -> str:
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
    return "\n".join(parts).strip() or "[no content]"


def _clip(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit] + f"\n... [{len(text) - limit} characters truncated]"
    return text


class McpHub:
    """The open servers of one episode, and the tools they expose."""

    def __init__(self, servers: dict[str, ServerConfig], names: tuple[str, ...],
                 request_timeout: float = REQUEST_TIMEOUT,
                 observation_chars: int = OBSERVATION_CHARS):
        self.available = servers
        self.names = tuple(name for name in names if name in servers)
        self.missing = tuple(name for name in names if name not in servers)
        self.request_timeout = request_timeout
        self.observation_chars = observation_chars
        self.sessions: dict[str, McpSession] = {}
        self.failures: list[dict] = []
        self.opened: list[str] = []

    def _session(self, name: str) -> McpSession:
        if name in self.sessions:
            return self.sessions[name]
        session = McpSession(self.available[name], self.request_timeout,
                             self.observation_chars)
        session.start()
        self.sessions[name] = session
        self.opened.append(name)
        return session

    def tools(self) -> list[dict]:
        """OpenAI-shaped tool schemas for every tool of every server.

        Servers that cannot start are recorded as failures and skipped: one
        dead shelf must not cost the episode its whole toolbox.
        """
        schemas: list[dict] = []
        for name in self.names:
            try:
                session = self._session(name)
                catalog = session.list_tools()
            except (McpError, OSError) as exc:
                self.failures.append({"server": name, "error": str(exc)[:300]})
                continue
            for tool in catalog:
                schemas.append({
                    "type": "function",
                    "function": {
                        "name": tool_key(name, tool["name"]),
                        "description": (tool.get("description") or "")[:1024],
                        "parameters": tool.get("inputSchema")
                        or {"type": "object", "properties": {}},
                    },
                })
        return schemas

    def call(self, key: str, arguments: dict) -> str:
        """Route one tool call to its server, reporting refusals as text."""
        try:
            server, tool = split_tool_key(key)
        except McpError as exc:
            return f"[refused: {exc}]"
        if server not in self.names:
            return (f"[refused: server {server} is not part of this run; "
                    f"open ones are {', '.join(self.names) or 'none'}]")
        try:
            return self._session(server).call(tool, arguments)
        except (McpError, OSError) as exc:
            self.failures.append({"server": server, "tool": tool, "error": str(exc)[:300]})
            return f"[mcp failure: {server}/{tool}: {exc}]"

    def close(self) -> None:
        for session in self.sessions.values():
            session.close()
        self.sessions.clear()

    def evidence(self) -> dict:
        return {
            "servers_requested": list(self.names),
            "servers_missing_from_config": list(self.missing),
            "servers_opened": list(self.opened),
            "failures": list(self.failures),
            "calls": sum(s.calls for s in self.sessions.values()),
        }
