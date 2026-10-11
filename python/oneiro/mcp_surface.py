"""The MCP surface: how the owner reads, imports, opens and calls servers.

`web.py` and `cli.py` are already over the plan's size guideline, so this module
owns the whole MCP surface and they only hand it over: `add_routes(app, owner)`
from the application, `mcp_command(argv)` from the command line.

Three things this surface refuses to blur:

* **Our file, nobody else's.** Servers are read from `mcp.file` and written only
  there. The other clients' configurations are surveyed, never changed; an import
  copies what they declare into our list and says what it found first.
* **What is shown is what is true now.** A server is `open` only while this process
  holds a live session, `failed` with the reason the server itself gave, otherwise
  `closed` or `disabled`. Nothing is reported as working because it is configured.
* **A call is decided, run and recorded like any other.** The decision comes from
  the same `Policy` the agent uses, the effect is `mcp_call`, and the call is
  published as an `Action` with the same fields as a step of a turn. A call typed
  here is the owner's own word, so it is treated as confirmed — a declared `deny`
  still refuses it, because a refusal is a boundary, not a default.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from oneiro import agent, config, mcp
from oneiro.records import Action, Effect, EffectOutcome, Provenance, State
from oneiro.runtime import Runtime
from oneiro.tools import Policy, ToolError

_NAME = re.compile(r"[A-Za-z0-9-]{1,64}")
BODY_LIMIT = 8000


def _digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


def request_id(key: str, arguments: dict[str, Any]) -> str:
    """A stable id for one call, so asking twice in a minute is one record."""
    canonical = json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True, default=str)
    minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    return "mcp-" + _digest(key, canonical, minute)


# ---------- reading ----------


def overview(document: mcp.Document | None = None) -> dict[str, Any]:
    """Everything the surface shows: our list, its state, and what others declare."""
    found = document if document is not None else mcp.load()
    states = mcp.hub().states(found)
    return {"file": str(found.path), "error": found.error,
            "problems": list(found.problems), "servers": states,
            "autostart": bool(config.value("mcp.autostart")),
            "sources": [report.to_dict() for report in mcp.survey()],
            "nothing_declared": (not found.servers and not found.error),
            "note": ("no MCP servers are declared yet. `mcp sources` shows what the other "
                     "clients on this machine declare, and `mcp import --write` copies them "
                     "into Oneiro's own list") if not found.servers and not found.error else ""}


class ImportUnnamed(mcp.McpError):
    """A write was asked for without saying which servers to take."""


def import_servers(*, write: bool = False, only: tuple[str, ...] = (), take_all: bool = False,
                   document: mcp.Document | None = None) -> dict[str, Any]:
    """Show what an import would add; with `write`, add it to our list only.

    A write has to say what it takes: `only` names the servers, `take_all` takes
    everything the clients declare. Importing every server another program ever
    configured, without the owner naming one, would fill the list — and start
    them all at the next launch — which is not a decision to make on their behalf.
    """
    found = document if document is not None else mcp.load()
    if write and not only and not take_all:
        raise ImportUnnamed("a write needs to know what to take: name the servers with "
                            "--only, or take everything with --all")
    if not write:
        plan = mcp.preview(found, None, only)
        plan["written"] = []
        return plan
    return mcp.apply_import(found, None, only)


def set_enabled(name: str, enabled: bool,
                document: mcp.Document | None = None) -> dict[str, Any]:
    """Turn one server on or off in our list, and make it so in this process.

    Writing the list is not the whole switch. Turning a server **off** also lets go
    of the session it had, so its tools stop being offered to the next turn instead
    of surviving until the next launch. Turning one **on** starts nothing by itself:
    the entry is on, the server opens when it is asked to or at the next launch, and
    a failure recorded before the switch is dropped so the next attempt judges it.
    """
    found = document if document is not None else mcp.load()
    server = found.servers.get(name)
    if server is None:
        raise mcp.McpError(f"no server named {name} in {found.path}")
    written = found.save(changes={name: server.with_enabled(enabled)})
    closed = mcp.hub().disconnect(name)["closed"] if not enabled else False
    mcp.hub().failures.pop(name, None)
    return {"name": name, "enabled": enabled, "file": str(found.path),
            "closed": closed, "bytes": written["bytes"]}


def is_declared(name: str) -> bool:
    """Whether our own list has this server at all, which a 404 turns on."""
    return name in mcp.load().servers


async def open_server(name: str) -> dict[str, Any]:
    """Start one server now and read its tools, or say why it did not come up."""
    declared = is_declared(name)
    report = await mcp.hub().open(name)
    row = next((item for item in mcp.hub().states() if item["name"] == name), None)
    return {**report, "declared": declared, "server": row}


async def tools_of(name: str) -> dict[str, Any]:
    """The tools of one server, starting it first if it is not open."""
    hub = mcp.hub()
    declared = is_declared(name)
    if declared and name not in hub.sessions:
        report = await hub.open(name)
        if not report["opened"]:
            return {"server": name, "declared": True, "opened": False,
                    "reason": report["reason"], "tools": []}
    if not declared and name not in hub.sessions:
        return {"server": name, "declared": False, "opened": False,
                "reason": f"no server named {name} in {mcp.load().path}", "tools": []}
    catalog = hub.catalogs.get(name, [])
    return {"server": name, "declared": declared, "opened": True, "reason": "", "tools": [
        {"key": mcp.tool_key(name, str(item.get("name"))),
         "description": str(item.get("description") or "")[:400],
         "schema": item.get("inputSchema") or {}} for item in catalog]}


# ---------- calling ----------


async def call_tool(owner: Any, key: str, arguments: dict[str, Any], *,
                    client_id: str = "", role: str = "manager",
                    policy: Policy | None = None) -> dict[str, Any]:
    """Decide, record and only then run one MCP call.

    The order is the rule: the `Action` is published **before** the call, in state
    RUNNING, and revised with what happened afterwards. A call whose record cannot
    be written is therefore not made — a tool that ran with nothing to show for it
    is exactly the kind of thing this product refuses to do. A refusal is recorded
    just as carefully, because a call that did not happen is information too.
    """
    hub = mcp.hub()
    action_id = "act-" + _digest(client_id or request_id(key, arguments), key)
    try:
        server, tool = mcp.split_tool_key(key)
    except mcp.McpError as exc:
        return await _refused(owner, action_id, key, {}, "", "", str(exc))

    report = await hub.open(server) if server not in hub.sessions else {"opened": True}
    tool_object = hub.registry().get(key)
    if not report.get("opened", True) or tool_object is None:
        reason = str(report.get("reason") or f"the server {server} did not come up")
        if report.get("opened", True):
            offered = ", ".join(sorted(hub.registry())) or "none"
            reason = (f"the server {server} does not offer a tool named {tool}; "
                      f"it offers: {offered}")
        return await _refused(owner, action_id, key, arguments, server, tool, reason)

    decided = policy if policy is not None else agent.default_policy()
    try:
        decision, decision_reason = decided.check(tool_object, role, arguments, approved=True)
    except ToolError as exc:
        decision, decision_reason = "deny", str(exc)
    if decision != "allow":
        return await _refused(owner, action_id, key, arguments, server, tool,
                              decision_reason)

    in_flight = _action(action_id, key, server, tool, arguments, decision="allow",
                        outcome=EffectOutcome.NONE, state=State.RUNNING,
                        provenance=Provenance.SYSTEM,
                        result=f"{decision_reason}\n(the call is in flight)")
    try:
        published = await owner.publish(in_flight.to_dict(), action_id)
    except Exception as exc:            # the store is the reason to refuse, and it is named
        return {"key": key, "server": server, "tool": tool, "decision": "deny",
                "reason": (f"the call was not made: its record could not be written "
                           f"({type(exc).__name__})"), "ok": False,
                "state": State.FAILED.value, "effect": mcp.EFFECT,
                "outcome": EffectOutcome.NONE.value, "text": "", "action_id": action_id,
                "may_retry": False, "recorded": False}

    outcome = await hub.call(key, arguments)
    state, effect = _outcome_of(outcome)
    ok = bool(outcome["ok"])
    text = str(outcome.get("text") or "")
    final = _action(action_id, key, server, tool, arguments, decision="allow", outcome=effect,
                    state=state, provenance=(Provenance.VERIFIED_TOOL_OUTCOME if ok
                                             else Provenance.SYSTEM),
                    result=(f"{decision_reason}\n{text}" if ok
                            else f"allow: {outcome.get('reason') or 'it did not finish'}"),
                    effect_target=server)
    recorded = True
    try:
        await owner.publish(final.to_dict(), f"{action_id}-done",
                            expected_revision=int(published.get("revision") or 0))
    except Exception:                   # the call happened; say so instead of hiding it
        recorded = False
    return {"key": key, "server": server, "tool": tool, "decision": "allow",
            "reason": str(outcome.get("reason") or ""), "ok": ok, "state": state.value,
            "effect": mcp.EFFECT, "outcome": effect.value, "text": text,
            "action_id": action_id, "may_retry": effect.permits_blind_retry,
            "recorded": recorded}


def _outcome_of(outcome: dict[str, Any]) -> tuple[State, EffectOutcome]:
    if outcome["ok"]:
        return State.COMPLETED, EffectOutcome.SUCCEEDED
    if outcome.get("state") == "uncertain":
        return State.UNCERTAIN, EffectOutcome.UNCERTAIN
    return State.FAILED, EffectOutcome.FAILED


def _action(action_id: str, key: str, server: str, tool: str, arguments: dict[str, Any], *,
            decision: str, outcome: EffectOutcome, state: State, provenance: Provenance,
            result: str, effect_target: str = "") -> Action:
    """One Action in the same shape a step of a turn records."""
    return Action(id=action_id, run_id="mcp-" + action_id[4:], tool=key, arguments=arguments,
                  effect=Effect(kind=mcp.EFFECT, target=effect_target or server,
                                outcome=outcome),
                  decision=decision, result=result[:4000], state=state, provenance=provenance,
                  labels=tuple(label for label in
                               ("mcp", f"server:{server}" if server else "",
                                f"tool:{tool}" if tool else "") if label))


async def _refused(owner: Any, action_id: str, key: str, arguments: dict[str, Any],
                   server: str, tool: str, reason: str) -> dict[str, Any]:
    """A call that did not run, recorded exactly as a refusal."""
    action = _action(action_id, key, server, tool, arguments, decision="deny",
                     outcome=EffectOutcome.NONE, state=State.FAILED,
                     provenance=Provenance.SYSTEM, result=f"deny: {reason}")
    await owner.publish(action.to_dict(), action_id)
    return {"key": key, "server": server, "tool": tool, "decision": "deny",
            "reason": reason, "ok": False, "state": State.FAILED.value, "effect": mcp.EFFECT,
            "outcome": EffectOutcome.NONE.value, "text": "", "action_id": action_id,
            "may_retry": False, "recorded": True}


# ---------- the command line ----------


def _with_runtime(action: Callable[[Runtime], Coroutine[Any, Any, Any]]) -> Any:
    """Hold a runtime for one command and let it go, whatever the command did."""

    async def runner() -> Any:
        runtime = Runtime()
        await runtime.start()
        try:
            return await action(runtime)
        finally:
            await runtime.close()

    return asyncio.run(runner())


def _say(line: str = "") -> None:
    print(line, flush=True)


def mcp_command(argv: list[str]) -> int:
    """`oneiro mcp` — the servers, what they offer, and a call when it is wanted."""
    parser = argparse.ArgumentParser(prog="oneiro mcp",
                                     description="MCP servers: list, sources, import, "
                                                 "enable, disable, open, tools, call")
    parser.add_argument("action", nargs="?", default="list",
                        choices=("list", "sources", "import", "enable", "disable",
                                 "open", "tools", "call"))
    parser.add_argument("name", nargs="?", help="the server, or server.tool for a call")
    parser.add_argument("arguments", nargs="?", default="",
                        help="a JSON object with the call's arguments")
    parser.add_argument("--write", action="store_true",
                        help="an import writes the list; without it nothing is written")
    parser.add_argument("--only", nargs="*", metavar="NAME",
                        help="import only these servers")
    parser.add_argument("--all", action="store_true",
                        help="take every server the other clients declare")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        if args.action == "list":
            return _print_list(args.json)
        if args.action == "sources":
            return _print_sources(args.json)
        if args.action == "import":
            found = import_servers(write=args.write, only=tuple(args.only or ()),
                                   take_all=args.all)
            if args.json:
                _say(json.dumps(found, ensure_ascii=False, indent=2))
                return 0
            for name, entry in found["add"].items():
                _say(f"would add {name}: {_entry_source(entry)}")
            if not found["add"]:
                _say("nothing new to add")
            for name in found["already"]:
                _say(f"already in the list, left alone: {name}")
            for item in found["refused"]:
                _say(f"could not read {item['name']} from {item['from']}: {item['reason']}")
            if args.write:
                _say(f"wrote {len(found['written'])} server(s) to {found['path']}")
            else:
                _say("nothing was written. Add the ones you want with: "
                     "oneiro mcp import --write --only NAME ...")
            return 0
        if args.action in ("enable", "disable"):
            if not args.name:
                _say(f"error: a server name is required to {args.action} one")
                return 2
            result = set_enabled(args.name, args.action == "enable")
            if args.json:
                _say(json.dumps(result, ensure_ascii=False, indent=2))
                return 0
            _say(f"{result['name']}: {'enabled' if result['enabled'] else 'disabled'} "
                 f"in {result['file']}")
            return 0
        if args.action in ("open", "tools"):
            if not args.name:
                _say(f"error: a server name is required to {args.action} it")
                return 2
            found = (asyncio.run(open_server(args.name)) if args.action == "open"
                     else asyncio.run(tools_of(args.name)))
            if args.json:
                _say(json.dumps(found, ensure_ascii=False, indent=2))
                return 0 if found["opened"] else (1 if found.get("declared", True) else 2)
            if not found.get("declared", True):
                _say(f"error: no server named {args.name} is declared in our list")
                return 2
            if not found["opened"]:
                _say(f"{args.name}: did not come up — {found['reason']}")
                return 1
            if args.action == "open":
                _say(f"{args.name}: open with {found['tools']} tool(s)")
                return 0
            for row in found["tools"]:
                _say(f"{row['key']}  {row['description']}")
            if not found["tools"]:
                _say(f"{args.name}: it is open and offers no tools")
            return 0
        return _call_from_command_line(args)
    except mcp.McpError as exc:
        _say(f"error: {exc}")
        return 2


def _entry_source(entry: dict[str, Any]) -> str:
    if str(entry.get("type")) == mcp.REMOTE:
        return str(entry.get("url") or "")
    command = entry.get("command")
    if isinstance(command, list):
        return " ".join(str(item) for item in command)
    return str(command or "")


def _call_from_command_line(args: argparse.Namespace) -> int:
    if not args.name:
        _say("error: a tool name is required, written as server.tool")
        return 2
    arguments: dict[str, Any] = {}
    if args.arguments.strip():
        try:
            parsed = json.loads(args.arguments)
        except ValueError:
            _say("error: the arguments must be a JSON object")
            return 2
        if not isinstance(parsed, dict):
            _say("error: the arguments must be a JSON object")
            return 2
        arguments = parsed
    client_id = request_id(args.name, arguments)
    result = _with_runtime(lambda owner: call_tool(owner, args.name, arguments,
                                                  client_id=client_id))
    if args.json:
        _say(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result["ok"] else 1
    _say(f"{result['key']}: {result['decision']} — {result['reason']}")
    if result["decision"] == "allow":
        _say(f"  outcome {result['outcome']}, recorded as {result['action_id']}")
        if result["text"]:
            _say(result["text"])
    else:
        _say(f"  nothing ran; recorded as {result['action_id']}")
    return 0 if result["ok"] else 1


def _print_list(machine: bool) -> int:
    payload = overview()
    if machine:
        _say(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    _say(f"file: {payload['file']}")
    if payload["error"]:
        _say(f"error: {payload['error']}")
    _say(f"autostart: {'on' if payload['autostart'] else 'off'}")
    for item in payload["servers"]:
        _say(f"{item['name']:<24} {item['kind']:<7} "
             f"{'on' if item['enabled'] else 'off':<4} {item['state']:<9} "
             f"{item['tools']:>2} tool(s)  {item['source']}")
        if item["failure"]:
            _say(f"    why: {item['failure']}")
    for item in payload["problems"]:
        _say(f"could not read {item['name']}: {item['reason']}")
    if payload["nothing_declared"]:
        _say(payload["note"])
    return 0


def _print_sources(machine: bool) -> int:
    reports = [report.to_dict() for report in mcp.survey()]
    if machine:
        _say(json.dumps(reports, ensure_ascii=False, indent=2, default=str))
        return 0
    for report in reports:
        if not report["found"]:
            looked = "; ".join(report.get("paths") or [report["path"]])
            _say(f"{report['client']:<16} (no such file here — looked in {looked})")
            continue
        if report["error"]:
            _say(f"{report['client']:<16} {report['path']}  {report['error']}")
            continue
        declared = ", ".join(f"{row['name']} ({row['kind']})" for row in report["servers"])
        _say(f"{report['client']:<16} {report['path']}  {declared or 'declares no servers'}")
        for problem in report["problems"]:
            _say(f"    could not read {problem['name']}: {problem['reason']}")
    return 0


# ---------- the HTTP surface ----------


async def _body(request: Request) -> dict[str, Any] | JSONResponse:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > BODY_LIMIT:
            return JSONResponse({"error": f"Body exceeds {BODY_LIMIT} bytes"}, status_code=413)
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except ValueError:
        return JSONResponse({"error": "Body must be a JSON object"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object"}, status_code=400)
    return body


def add_routes(app: FastAPI, owner: Runtime) -> None:
    """The MCP routes, added to the application by `web.create_app`."""

    def unknown(name: str) -> JSONResponse:
        return JSONResponse({"error": "no such MCP server", "name": name}, status_code=404)

    @app.get("/api/mcp")
    async def mcp_overview() -> JSONResponse:
        return JSONResponse(overview())

    @app.post("/api/mcp/import")
    async def mcp_import(request: Request) -> JSONResponse:
        body = await _body(request)
        if isinstance(body, JSONResponse):
            return body
        only = body.get("only") or []
        if not isinstance(only, list) or any(not isinstance(item, str) for item in only):
            return JSONResponse({"error": "only must be a list of server names"}, status_code=400)
        try:
            return JSONResponse(import_servers(write=bool(body.get("write", False)),
                                               only=tuple(only),
                                               take_all=bool(body.get("all", False))))
        except mcp.McpError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)

    @app.post("/api/mcp/{name}/enable")
    async def mcp_enable(name: str) -> JSONResponse:
        return _toggle(name, True)

    @app.post("/api/mcp/{name}/disable")
    async def mcp_disable(name: str) -> JSONResponse:
        return _toggle(name, False)

    def _toggle(name: str, enabled: bool) -> JSONResponse:
        if not _NAME.fullmatch(name):
            return unknown(name)
        try:
            return JSONResponse(set_enabled(name, enabled))
        except mcp.McpError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @app.post("/api/mcp/{name}/open")
    async def mcp_open(name: str) -> JSONResponse:
        if not _NAME.fullmatch(name) or not is_declared(name):
            return unknown(name)
        report = await open_server(name)
        # 503 for a declared server that did not come up, 404 for one we do not have.
        return JSONResponse(report, status_code=200 if report["opened"] else 503)

    @app.get("/api/mcp/{name}/tools")
    async def mcp_tools(name: str) -> JSONResponse:
        if not _NAME.fullmatch(name) or not is_declared(name):
            return unknown(name)
        found = await tools_of(name)
        return JSONResponse(found, status_code=200 if found["opened"] else 503)

    @app.post("/api/mcp/{name}/call")
    async def mcp_call(name: str, request: Request) -> JSONResponse:
        if not _NAME.fullmatch(name):
            return unknown(name)
        body = await _body(request)
        if isinstance(body, JSONResponse):
            return body
        tool = body.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            return JSONResponse({"error": "tool must be a non-empty string"}, status_code=400)
        # `None` means "no arguments"; an empty list is a wrong shape, not an absence.
        arguments = body.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return JSONResponse({"error": "arguments must be a JSON object"}, status_code=400)
        client_id = body.get("client_id") or request_id(f"{name}.{tool}", arguments)
        if not isinstance(client_id, str) or not client_id.strip():
            return JSONResponse({"error": "client_id must be a string"}, status_code=400)
        try:
            result = await call_tool(owner, mcp.tool_key(name, tool.strip()), arguments,
                                     client_id=client_id)
        except Exception as exc:            # a store that cannot be written is a refusal
            return JSONResponse({"error": f"the call could not be recorded ({type(exc).__name__})"},
                                status_code=503)
        status = 200 if result["decision"] == "allow" else 403
        return JSONResponse(result, status_code=status)


def main(argv: list[str] | None = None) -> int:
    """Used by the tests and by `python -m oneiro.mcp_surface`."""
    try:
        return mcp_command(list(argv if argv is not None else sys.argv[1:]))
    except BrokenPipeError:                 # a closed pipe is not an error worth a traceback
        return 0
