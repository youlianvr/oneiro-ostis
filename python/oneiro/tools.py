"""The tool surface the agent may call, and the policy that bounds it.

This is the reviewed small surface migrated from `native/`, not a generic shell:
no unrestricted command execution, no automatic MCP import, no host process
control. A tool is a name, a JSON schema, an effect vocabulary entry, the roles
allowed to use it and a handler. Nothing here reads a prompt for permission:
`Policy` decides from configuration and role boundaries only, so no model output
and no stored text can widen what may run.

Three properties matter and are tested:

* **Effect vocabulary, not vibes.** Every tool declares one effect from `EFFECTS`
  and `Tool` refuses to exist if that effect is outside the roles that own it.
* **An approval covers one exact call.** `arguments_digest` is computed over
  canonical JSON, so an approval for one file write cannot authorise a different
  write, and a stale approval cannot authorise a new action.
* **Credential material is never exposed.** Secret filenames and key suffixes are
  refused by `readable`, and inside the working folder the internal directories stay
  protected. A path that leaves the folder is *not* refused by the path rule: it is the
  different act `write_outside`, judged by the owner's declared permission for it (which
  asks by default), so the promise the settings page makes about it is one this module
  keeps.
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROLES = ("manager", "researcher", "executor")

EFFECTS = frozenset({"read", "note", "coordinate", "workspace_write", "write_outside",
                     "web_read", "configure", "delete", "database", "sandbox", "install",
                     "publish", "send", "upload", "autostart", "mcp_call"})
SENSITIVE = frozenset({"configure", "delete", "database", "sandbox", "install",
                       "publish", "send", "upload", "mcp_call", "write_outside"})
ROLE_EFFECTS = {
    "manager": {"read", "note", "coordinate", "web_read", "mcp_call"},
    "researcher": {"read", "note", "web_read", "mcp_call"},
    "executor": set(EFFECTS) - {"coordinate", "autostart"},
}

#: Which declared setting the owner's decision about each effect comes from.
#: The table sits next to the effect vocabulary on purpose: an effect acquires a
#: permission by being written down here, and
#: `tests/test_tools.py::test_every_effect_is_governed_or_deliberately_not` fails
#: until the author records that decision.
EFFECT_SETTINGS: dict[str, str] = {
    "web_read": "permissions.web_read",
    # Two effects for one tool: where a write lands decides which permission the
    # owner declared for it, and `write_file` derives that from its own arguments.
    "workspace_write": "permissions.write_workspace",
    "write_outside": "permissions.write_outside",
    "delete": "permissions.delete",
    "install": "permissions.install",
    # An MCP tool is code this product did not write, running in the owner's name,
    # so it is governed by the declared permission for running commands.
    "mcp_call": "permissions.exec",
    "send": "permissions.send_publish",
    "publish": "permissions.send_publish",
    "upload": "permissions.send_publish",
}

#: Effects with no declared setting, and why: local work needs no permission,
#: the sensitive ones ask by the reviewed default below, and autostart is
#: refused outright. A new effect must be added to one list or the other.
EFFECTS_WITHOUT_SETTING = frozenset({"read", "note", "coordinate", "configure",
                                     "database", "sandbox", "autostart"})
DECISIONS = ("allow", "ask", "deny")

SECRET_NAMES = {".env", ".env.local", ".env.production", "credentials",
                "id_rsa", "id_ed25519"}
CONFIG_SUFFIXES = (".ini", ".toml", ".yaml", ".yml")
CONFIG_NAMES = {"settings.json", "config.json", ".mcp.json", "oneiro-tools.json"}
INTERNAL_DIRS = {".git", ".ssh", ".runtime"}


class ToolError(ValueError):
    """A call that cannot be made: bad arguments, or a refusal by the policy.

    Carries a short reason that is safe to show the owner and to hand back to
    the model. Never a credential, never a provider body.

    `uncertain` says something stronger than "it failed": for an effect outside
    this process, the request was already on its way when the answer stopped
    coming, so it may have happened. The caller must then record UNCERTAIN and
    refuse to retry it, exactly as it does for its own timed-out call. A tool that
    cannot tell the difference sets this; one that knows nothing happened does not.
    """

    def __init__(self, message: str, *, uncertain: bool = False) -> None:
        super().__init__(message)
        self.uncertain = uncertain


def arguments_digest(arguments: dict[str, Any]) -> str:
    """A stable digest of exactly these arguments, used to bind an approval.

    Canonical form (sorted keys, no whitespace) so the same call always digests
    the same, and any change of target or payload produces a different digest.
    """
    canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Tool:
    """One callable capability with reviewed metadata."""

    name: str
    description: str
    properties: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    roles: tuple[str, ...] = ROLES
    effect: str = "read"
    handler: Callable[..., Any] | None = None
    #: For a tool whose effect depends on its own arguments (writing inside the
    #: working folder is not the same act as writing outside it). Everything else
    #: declares one effect for every call it ever makes.
    effect_of: Callable[[dict[str, Any]], str] | None = None

    def __post_init__(self) -> None:
        if self.effect not in EFFECTS or not self.roles or set(self.roles) - set(ROLES):
            raise ToolError(f"{self.name}: needs a reviewed effect and known roles")
        if any(self.effect not in ROLE_EFFECTS[role] for role in self.roles):
            raise ToolError(f"{self.name}: violates permanent role boundaries")

    def effect_for(self, arguments: dict[str, Any] | None) -> str:
        """The effect of one exact call.

        A derivation that names something outside `EFFECTS` is a programming error
        and is raised: quietly falling back to the declared effect could turn a
        refused outside write into an allowed inside one.
        """
        if self.effect_of is None:
            return self.effect
        derived = str(self.effect_of(dict(arguments or {})))
        if derived not in EFFECTS:
            raise ToolError(f"{self.name}: {derived!r} is not a declared effect")
        return derived

    def schema(self) -> dict[str, Any]:
        """The OpenAI-compatible function description the model is given."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.properties,
                           "required": list(self.required),
                           "additionalProperties": False}}}

    def validate(self, arguments: Any) -> dict[str, Any]:
        """Check the arguments against the declared schema; returns them back."""
        if not isinstance(arguments, dict):
            raise ToolError(f"{self.name}: arguments must be an object")
        unknown = set(arguments) - set(self.properties)
        missing = set(self.required) - set(arguments)
        if unknown or missing:
            detail = []
            if missing:
                detail.append("missing " + ", ".join(sorted(missing)))
            if unknown:
                detail.append("unexpected " + ", ".join(sorted(unknown)))
            raise ToolError(f"{self.name}: {'; '.join(detail)}")
        types = {"string": str, "integer": int, "boolean": bool,
                 "object": dict, "array": list}
        for name, value in arguments.items():
            expected = self.properties[name].get("type")
            if expected in types and (not isinstance(value, types[expected])
                                      or expected == "integer" and isinstance(value, bool)):
                raise ToolError(f"{self.name}: {name} must be {expected}")
            choices = self.properties[name].get("enum")
            if choices and value not in choices:
                raise ToolError(f"{self.name}: {name} is not one of {', '.join(choices)}")
        return arguments


def role_may(role: str, tool: Tool, effect: str | None = None) -> bool:
    """Whether this role may use this tool at all, whatever the owner configured.

    The permanent boundary, in one place, because two readers need it: the policy
    refuses a call by it, and a caller that offers tools to a model filters by it.
    A tool offered and then refused is a refusal the owner reads about for
    something the model was never allowed to have.

    `effect` is the effect of the exact call being judged, for the tools whose
    effect depends on their arguments; without it the tool's declared effect is used,
    which is what offering a tool means (the model is offered the tool, not a path).
    """
    chosen = tool.effect if effect is None else effect
    return role in tool.roles and chosen in ROLE_EFFECTS.get(role, set())


class Policy:
    """Decides allow, deny or ask for one call, from two inputs only.

    `decisions` is the owner's declared choice per effect, exactly the words the
    settings page shows; `internet_enabled` is whether a network read is possible
    at all. Nothing else takes part, so there is no second vocabulary for the
    same decision and no way for a stored string to widen a rule. An effect with
    no declared decision falls back to the reviewed defaults (:data:`SENSITIVE`
    asks, an unconfirmed outbound URL asks, everything else local is allowed).
    """

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings

    def decision(self, effect: str) -> str:
        """The declared decision for one effect: allow, ask, deny, or empty."""
        decisions = self.settings.get("decisions") or {}
        declared = str(decisions.get(effect, ""))
        return declared if declared in DECISIONS else ""

    def check(self, tool: Tool, role: str, arguments: Any, *,
              approved: bool = False, trusted_url: bool = False) -> tuple[str, str]:
        """Return (decision, reason), decision in allow / deny / ask.

        Denials are permanent boundaries: an unknown role, a tool outside that
        role's effects, a capability switched off, or a declared refusal, which an
        approval cannot open. `ask` means the owner must confirm this exact call;
        the caller records that and does not run it.
        """
        if not role_may(role, tool):
            return "deny", f"the {role} role may not use {tool.effect}"
        tool.validate(arguments)
        # The effect of *this* call: a write inside the working folder and a write
        # outside it are different acts, with different declared decisions, so the
        # permission is looked up for the effect the arguments imply.
        effect = tool.effect_for(arguments)
        if not role_may(role, tool, effect):
            return "deny", f"the {role} role may not use {effect}"
        if effect == "autostart":
            return "deny", "autostart is disabled"
        declared = self.decision(effect)
        if declared == "deny":
            return "deny", f"{effect} is refused by the configured permissions"
        if effect == "web_read" and not self.settings.get("internet_enabled", False):
            return "deny", "internet access is disabled"
        if approved:
            return "allow", "owner approved this exact call"
        if declared == "ask":
            return "ask", f"{effect} needs the owner's confirmation"
        if declared == "allow":
            return "allow", "allowed by the configured permissions"
        if effect in SENSITIVE:
            return "ask", f"{effect} needs the owner's confirmation"
        if effect == "web_read" and not trusted_url:
            return "ask", "confirm this exact outbound URL"
        return "allow", "within the configured local permissions"


def readable(path: str, *, max_bytes: int) -> Path:
    """Resolve a path for reading, refusing credential material."""
    target = Path(path).expanduser().resolve()
    if any(part in SECRET_NAMES or part.lower().endswith((".pem", ".key"))
           or part.lower().startswith(".env.") for part in target.parts):
        raise ToolError("credential files are not exposed to the model")
    return target


def resolves_inside(root: Path, path: Any) -> bool:
    """Whether a path, as written, names something inside the working folder.

    `..` is resolved, not trusted: `sub/../../elsewhere` is outside, and a relative
    path is relative to the folder the agent is allowed to work in. A path that
    cannot be resolved is treated as outside, which is the stricter answer.
    """
    text = str(path or "").strip()
    target = Path(text).expanduser() if text else Path(".")
    base = root.expanduser()
    if not target.is_absolute():
        target = base / target
    try:
        resolved, inside = target.resolve(), base.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == inside or inside in resolved.parents


def declared_write_effect(root: Path | None, path: Any) -> str:
    """Which write effect this exact path asks for."""
    if root is None or not resolves_inside(root, path):
        return "write_outside"
    return "workspace_write"


def write_target(root: Path, path: str, *, effect: str, max_bytes: int) -> Path:
    """Resolve a write target for a call the policy already allowed.

    Credentials are refused wherever the write would land, and inside the folder
    the internal directories stay protected. Outside it, the path is exactly what
    the owner was asked about — an approval is bound to these arguments, so the
    file that gets written is the file the decision covered.
    """
    # A relative write is relative to the working folder, exactly as
    # `resolves_inside` measures it; the process working directory is not that
    # folder, so it must not decide where the file lands.
    text = str(path or "").strip()
    candidate = Path(text).expanduser() if text else Path(".")
    if not candidate.is_absolute():
        candidate = root.expanduser() / candidate
    target = readable(str(candidate), max_bytes=max_bytes)
    if effect == "workspace_write":
        base = root.resolve()
        if target == base:
            raise ToolError("that is the working folder itself, not a file in it")
        if any(part in INTERNAL_DIRS for part in target.relative_to(base).parts):
            raise ToolError("that internal directory is protected")
    return target


def put(target: Path, text: str, *, max_bytes: int) -> dict[str, Any]:
    """Write through a temporary file and replace, so a failure never truncates."""
    raw = text.encode("utf-8")
    if len(raw) > max_bytes:
        raise ToolError(f"the file exceeds the {max_bytes} byte tool limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("." + target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return {"written": str(target), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def public_url(url: str) -> str:
    """Refuse anything that is not an exact public HTTP(S) URL.

    Loopback, private ranges, credentials in the URL, odd ports and fragments are
    refused, so a fetch cannot be pointed at the owner's own machine or services.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ToolError("a public HTTP(S) URL without credentials is required")
    if parts.port not in (None, 80, 443) or parts.fragment:
        raise ToolError("nonstandard ports and fragments are not accepted")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        rows = socket.getaddrinfo(parts.hostname, port)
    except OSError as exc:
        raise ToolError(f"the host cannot be resolved ({exc.__class__.__name__})") from None
    for row in rows:
        if not ipaddress.ip_address(row[4][0]).is_global:
            raise ToolError("private and loopback destinations are blocked")
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is a new destination, so it needs its own decision."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ToolError("a redirect needs a separately confirmed URL: "
                        + urllib.parse.urljoin(req.full_url, newurl))


def fetch_url(url: str, *, max_bytes: int, timeout: float = 25.0) -> dict[str, Any]:
    """Read one public text URL: no cookies, no proxy credentials, no redirects."""
    public_url(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "Oneiro/1.0"})
    try:
        with opener.open(request, timeout=timeout) as response:
            kind = response.headers.get("Content-Type", "")
            if not any(value in kind for value in ("text/", "json", "xml")):
                return {"url": url, "content_type": kind,
                        "note": "not text; the body was not read"}
            raw = response.read(max_bytes + 1)
    except ToolError:
        raise
    except Exception as exc:  # network layer: report the kind, never a body
        raise ToolError(f"the fetch failed ({exc.__class__.__name__})") from None
    text = raw[:max_bytes].decode("utf-8", "replace")
    links = re.findall(r'href=["\']([^"\']+)', text)[:80]
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", text, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return {"url": url, "text": re.sub(r"\s+", " ", text)[:24000],
            "links": [urllib.parse.urljoin(url, link) for link in links],
            "truncated": len(raw) > max_bytes}


def _string(**extra: Any) -> dict[str, Any]:
    return {"type": "string", **extra}


def for_role(registry: dict[str, Tool], role: str) -> dict[str, Tool]:
    """The tools one role may actually use, by the same rule the policy applies."""
    return {name: tool for name, tool in registry.items() if role_may(role, tool)}


def build_registry(workspace: Path | None, *, internet: bool, max_bytes: int,
                   ask: Callable[[str], Any] | None = None,
                   remember: Callable[..., Any] | None = None) -> dict[str, Tool]:
    """The tools available in this runtime, keyed by name.

    `ask` and `remember` are supplied by the runtime that owns records, so this
    module stays free of the record store. A tool whose collaboration is absent
    is simply not offered, rather than offered and failing later.
    """
    root = workspace.resolve() if workspace is not None else None

    def read_file(ctx: dict, args: dict) -> dict:
        target = readable(args["path"], max_bytes=max_bytes)
        with target.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        return {"path": str(target), "text": raw[:max_bytes].decode("utf-8", "replace"),
                "truncated": len(raw) > max_bytes}

    def list_files(ctx: dict, args: dict) -> dict:
        target = readable(args["path"], max_bytes=max_bytes)
        if not target.is_dir():
            raise ToolError("that path is not a directory")
        return {"path": str(target), "entries": sorted(p.name for p in target.iterdir())[:200]}

    def write_file(ctx: dict, args: dict) -> dict:
        # Which effect this write has, and therefore which permission was asked for
        # and granted, is `declared_write_effect` — the same function the tool
        # declares as `effect_of`, so the record and the decision cannot disagree.
        if root is None:
            raise ToolError("no tool workspace is configured, so writing is off")
        effect = declared_write_effect(root, args["path"])
        target = write_target(root, args["path"], effect=effect, max_bytes=max_bytes)
        if target.name in CONFIG_NAMES or target.suffix.lower() in CONFIG_SUFFIXES:
            raise ToolError("configuration files need the owner's own edit")
        return put(target, args["text"], max_bytes=max_bytes)

    def fetch(ctx: dict, args: dict) -> dict:
        if not internet:
            raise ToolError("internet access is disabled")
        return fetch_url(args["url"], max_bytes=max_bytes)

    tools = [
        Tool("read_file", "Read a local text file. Credential files are excluded.",
             {"path": _string()}, ("path",), ROLES, "read", read_file),
        Tool("list_files", "List a directory without changing it.",
             {"path": _string()}, ("path",), ROLES, "read", list_files),
        Tool("fetch_url", "Read one exact public URL. No cookies, redirects or local hosts.",
             {"url": _string()}, ("url",), ROLES, "web_read", fetch),
    ]
    if root is not None:
        # No workspace means no place a write could land, so no write tool is
        # declared at all: a capability that cannot run is not offered.
        tools.append(Tool(
            "write_file",
            "Write one text file. Inside the working folder this is a workspace write; "
            "outside it needs the write-outside permission, which asks you first. "
            "Configuration files are never written.",
            {"path": _string(), "text": _string()}, ("path", "text"), ("executor",),
            "workspace_write", write_file, effect_of=lambda args: declared_write_effect(
                root, args.get("path"))))
    if ask is not None:
        # A coroutine function, so the agent awaits it on the event loop instead
        # of running it in a worker thread: writing a record belongs on the loop.
        async def ask_owner(ctx: dict, args: dict) -> Any:
            return await ask(args["question"])

        tools.append(Tool(
            "ask_owner", "Ask the owner a question and continue with other work; "
                         "asking grants no other permission.",
            {"question": _string()}, ("question",), ("manager",), "coordinate",
            ask_owner))
    if remember is not None:
        async def keep_note(ctx: dict, args: dict) -> Any:
            return await remember(ctx.get("role", "manager"), args["text"],
                                  args.get("sources", []))

        tools.append(Tool(
            "remember", "Keep a research note or lesson, with optional sources.",
            {"text": _string(), "sources": {"type": "array", "items": _string()}},
            ("text",), ROLES, "note", keep_note))
    return {tool.name: tool for tool in tools}
