"""Same-origin HTTP surface: chat, tasks, memory, settings and conversations.

Every route here is loopback-only and behind the owner's request token, with one
deliberate exception: an inbound webhook (`POST /api/hooks/<name>`) authenticates
its own caller with the body's HMAC signature, because a machine caller cannot hold
a token minted for the page. The chat and task routes hand the work to
`oneiro.agent` and `oneiro.tasks`; this module owns transport, not policy. The
clock can run here as well, so that the standalone process that serves the pages
also keeps the schedules: shutting it down stops the clock with it.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from oneiro import (agent, config, drafts, hooks, mcp, memory, pages, recall, schedule, skills,
                    tasks)
from oneiro import mcp_surface
from oneiro.agent import TurnConflict
from oneiro.chat import ChatError
from oneiro.graph_worker import page_budget
from oneiro.records import State
from oneiro.runtime import Runtime
from oneiro.query import GraphQueryError, _check_limit
from oneiro.schedule import ScheduleError
from oneiro.tasks import TaskError

STATIC = Path(__file__).parent / "static"
CHAT_CONVERSATION = "main"
CHAT_MAX_CHARS = 4000
CHAT_BODY_LIMIT = 16000

#: The deadline a *page-facing* read gets, set on the graph lane while the page's own
#: reads run. A screen issues several of these, and one of them holding the lane's own
#: 10 s deadline each is how `/tasks` failed to settle for more than 30 s with an
#: unreachable graph (measured 2026-10-11: /api/tasks 10.04 s, /api/schedules 9.11 s,
#: /api/conversations 8.98 s). Writes keep the lane's own, longer deadline. The number is
#: a product decision; what the lane owes either way is a bounded answer that costs no
#: worker and no durability.
PAGE_READ_BUDGET = 3.0
_CLIENT_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
_FACT_ID = re.compile(r"fact-[A-Za-z0-9-]{8,64}")
FACT_BODY_LIMIT = 8000
_CONVERSATION = re.compile(r"[A-Za-z0-9-]{1,64}")
_RECORD_ID = re.compile(r"[A-Za-z0-9-]{1,96}")
SEARCH_LIMIT = 50
SEARCH_CHARS = 200
SEARCH_WORDS = 6

#: The one prefix that authenticates itself. Its callers are scripts, not a page, so
#: they cannot carry the token the page is given; the HMAC signature over the exact
#: body, with a secret that never leaves the data root, is what stands in its place.
#: The exemption is this prefix and `POST` only, and the route below verifies the
#: signature before it reads the payload, writes anything or creates a task.
SIGNED_PREFIX = "/api/hooks/"


class _ChatRefused(Exception):
    """A chat request the slice declines, carrying the status it should return."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _message_out(row: dict[str, Any]) -> dict[str, Any]:
    """The public shape of one stored conversation message."""
    return {"id": row["id"], "conversation_id": row["conversation_id"], "role": row["role"],
            "text": row["text"], "created_at": row["created_at"]}


async def _json_object(request: Request, limit: int) -> dict[str, Any] | JSONResponse:
    """A bounded JSON object from the body, or the refusal to return instead."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            return JSONResponse({"error": f"Body exceeds {limit} bytes"}, status_code=413)
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return JSONResponse({"error": "Body must be a JSON object"}, status_code=400)
    return body


async def _chat_turn(owner: Runtime, text: str, client_id: str,
                     conversation_id: str = CHAT_CONVERSATION,
                     attachments: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """One owner message and one assistant reply, published at most once each.

    The turn itself - tool steps, permission decisions and the reply - belongs to
    `oneiro.agent`; this wrapper only turns its failures into HTTP statuses. The
    owner's message stays stored when the provider fails, and no reply is
    invented in its place.
    """
    try:
        return await agent.run_turn(owner, text, client_id, conversation_id, attachments=attachments)
    except ChatError as exc:
        raise _ChatRefused(503, str(exc)) from None
    except TurnConflict as exc:
        raise _ChatRefused(409, str(exc)) from None


def _report_tick_failure(exc: Exception) -> None:
    """A scheduler tick that failed is said out loud; a silent loop is a lie."""

    print(f"Oneiro: a scheduler tick failed ({type(exc).__name__}: {exc})",
          file=sys.stderr, flush=True)


def _facts_budget() -> int:
    """The curated-facts budget the owner declared, in characters.

    Read at each use rather than cached, so a change in the settings window takes
    effect on the next fact that is saved instead of at the next restart.
    """
    return int(config.value("memory.facts_budget"))


def _report_mcp_failure(report: dict) -> None:
    """A server that did not come up is named in the log, not discovered later."""

    print(f"Oneiro: the MCP server {report['name']} did not come up: {report['reason']}",
          file=sys.stderr, flush=True)


def create_app(runtime: Runtime | None = None, *, scheduler: bool = False) -> FastAPI:
    """The HTTP surface. `scheduler` starts the clock inside this process.

    Off by default because the clock belongs to the process that owns the
    runtime: `oneiro serve` is that process, and a host that embeds this app says
    for itself whether it wants a clock. An app that is handed a store for one
    test must not start one behind its back.
    """
    owner = runtime or Runtime()
    csrf = secrets.token_urlsafe(32)
    # One owner, one process: fact writes check a budget before publishing, so
    # two writes must not interleave between that check and the publication.
    facts_lock = asyncio.Lock()

    async def _start_servers() -> None:
        """Open the enabled MCP servers, in the background, failures named."""
        for report in await mcp.hub().open_enabled():
            if not report.get("opened"):
                _report_mcp_failure(report)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await owner.start()
        # The webhook secret belongs to the process that owns the data root. It is made
        # once, on the first start, so an integration has a key to be signed with, and
        # the line names its fingerprint and path and never the value.
        key = hooks.ensure_secret()
        if key["created"]:
            print(f"Oneiro: webhook secret created at {key['path']} "
                  f"(fingerprint {key['fingerprint']})", flush=True)
        ticker = (asyncio.create_task(schedule.loop(owner, on_error=_report_tick_failure))
                  if scheduler else None)
        # `mcp.autostart` decides whether the enabled servers are started with the
        # process. It runs in the background: a server that is slow to start must
        # not hold the window shut, and one that does not start is named in the log.
        servers = asyncio.create_task(_start_servers()) if bool(config.value("mcp.autostart")) \
            else None
        try:
            yield
        finally:
            for task in (ticker, servers):
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            mcp.hub().close()
            await owner.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = owner
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    # A refusal is read by a person as well as by a parser. A browser that never ran
    # JavaScript posts the settings form straight at `/api/settings`, and a JSON body
    # would be what the tab shows; it gets the shell, in the active language, instead.
    # The two shapes refuse the same thing, so an API client keeps the JSON it parses.
    refusals = {"error.cross_origin": "Cross-origin request refused",
                "error.bad_token": "Invalid owner request token"}

    def refuse(request: Request, key: str) -> Any:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and "application/json" not in accept:
            return HTMLResponse(pages.render_error(key), status_code=403)
        return JSONResponse({"error": refusals[key]}, status_code=403)

    @app.middleware("http")
    async def same_origin(request: Request, call_next: Any) -> Any:
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or parsed.netloc != request.headers.get("host"):
                return refuse(request, "error.cross_origin")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            signed = (request.method == "POST"
                      and request.url.path.startswith(SIGNED_PREFIX))
            if not signed and not secrets.compare_digest(
                    request.headers.get("x-oneiro-csrf", ""), csrf):
                return refuse(request, "error.bad_token")
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    async def serve(page: str, request: Request | None = None) -> HTMLResponse:
        """One route, one page. `web.py` names it; `pages` renders it."""
        description = config.describe()
        facts = None
        lang = request.query_params.get("lang") if request else None
        if page == "graph":
            host = str(config.value("graph.host"))
            port = int(config.value("graph.port"))
            # Bounded inside the probe, not by a `wait_for` around the thread: an outer
            # deadline raises out of this handler and leaves `500 Internal Server Error`
            # (measured 2026-10-11 against a port that accepted TCP and never answered),
            # while `probe_within` returns the facts that say the read did not finish.
            facts = await asyncio.to_thread(memory.probe_within, host, port,
                                            budget=memory.PROBE_BUDGET)
        return HTMLResponse(pages.render(page, description, error=description["error"],
                                        facts=facts, lang=lang))

    @app.get("/", response_class=HTMLResponse)
    async def chat(request: Request) -> HTMLResponse:
        return await serve("chat", request)

    @app.get("/drafts", response_class=HTMLResponse)
    async def drafts_page(request: Request) -> HTMLResponse:
        """The screen the owner presses from. Every write it makes is a route below."""
        return await serve("drafts", request)

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(request: Request) -> HTMLResponse:
        return await serve("tasks", request)

    @app.get("/tools", response_class=HTMLResponse)
    async def tools_page(request: Request) -> HTMLResponse:
        return await serve("tools", request)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        return await serve("settings", request)

    @app.get("/memory", response_class=HTMLResponse)
    async def memory_page(request: Request) -> HTMLResponse:
        return await serve("memory", request)

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request) -> HTMLResponse:
        return await serve("setup", request)

    @app.get("/oneiro/", response_class=HTMLResponse)
    async def graph_page(request: Request) -> HTMLResponse:
        return await serve("graph", request)

    @app.get("/app.js")
    async def script() -> FileResponse:
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @app.get("/console.css")
    async def tokens(request: Request) -> FileResponse:
        """The theme tokens, served first so the layout can only use them."""
        # Ensure ui.theme is read and active
        _ = config.value("ui.theme")
        return FileResponse(STATIC / "console.css", media_type="text/css")

    @app.get("/style.css")
    async def styles() -> FileResponse:
        return FileResponse(STATIC / "style.css", media_type="text/css")

    @app.get("/api/session")
    async def session() -> dict[str, str]:
        return {"csrf": csrf}

    # The MCP surface lives in its own module; this app only hands it the runtime. The
    # skills surface does too, and needs nothing handed to it: a search and a contract
    # read change nothing, so no route of it records anything.
    mcp_surface.add_routes(app, owner)
    skills.add_routes(app)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        # `assistant_ready` means a real model capability check passed in this
        # process, not that a key is present. It stays false until then.
        return {"http": "ready", "assistant_ready": owner.model_verified,
                "instance_id": owner.instance_id}

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        return await owner.status()

    @app.get("/api/settings")
    async def settings() -> dict[str, Any]:
        return config.describe()

    @app.post("/api/settings")
    async def update_settings(request: Request) -> JSONResponse:
        # Bound request buffering even when Transfer-Encoding is chunked.
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 64000:
                return JSONResponse({"error": "Settings body exceeds 64000 bytes"}, status_code=413)
        try:
            patch = json.loads(raw)
        except ValueError:
            return JSONResponse({"error": "The request body was not valid JSON."}, status_code=400)
        try:
            # Cross-process lease and backups belong to the shared config module.
            result = await asyncio.to_thread(config.save, patch)
            await owner.status(refresh=True)
            return JSONResponse(result)
        except config.SettingsRejected as exc:
            # The settings layer's reasons name the keys and what was expected of
            # them, never a submitted value, so they are safe to show. A refusal
            # the owner cannot understand is a refusal they cannot fix.
            return JSONResponse({"error": "Nothing was saved. One setting needs a different value."
                                          if len(exc.reasons) == 1 else
                                          "Nothing was saved. Some settings need a different value.",
                                 "reasons": list(exc.reasons)}, status_code=400)
        except (TypeError, OSError, ValueError):
            # Anything else may carry a path or a provider body: say nothing about it.
            return JSONResponse({"error": "Nothing was saved. The settings file could not be written."}, status_code=400)

    @app.post("/api/message")
    async def message(request: Request) -> JSONResponse:
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > CHAT_BODY_LIMIT:
                return JSONResponse({"error": f"Message body exceeds {CHAT_BODY_LIMIT} bytes"}, status_code=413)
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return JSONResponse({"error": "Body must be a JSON object"}, status_code=400)
        text, client_id = body.get("text"), body.get("client_id")
        attachments = body.get("attachments") or []
        if not isinstance(attachments, list) or any(not isinstance(a, str) for a in attachments):
            return JSONResponse({"error": "attachments must be a list of attachment ids"}, status_code=400)
        text_str = str(text or "")
        if not text_str.strip() and not attachments:
            return JSONResponse({"error": f"text must be 1..{CHAT_MAX_CHARS} characters or attachments provided"}, status_code=400)
        if text_str and len(text_str) > CHAT_MAX_CHARS:
            return JSONResponse({"error": f"text must be 1..{CHAT_MAX_CHARS} characters"}, status_code=400)
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return JSONResponse({"error": "client_id must be 8..64 letters, digits or hyphens"}, status_code=400)
        conversation = body.get("conversation_id", CHAT_CONVERSATION)
        if not isinstance(conversation, str) or not _CONVERSATION.fullmatch(conversation):
            return JSONResponse({"error": "conversation_id must be 1..64 letters, digits or hyphens"}, status_code=400)
        try:
            return JSONResponse(await _chat_turn(owner, text_str, client_id, conversation, attachments=attachments))
        except _ChatRefused as exc:
            return JSONResponse({"error": exc.message}, status_code=exc.status)
        except GraphQueryError as exc:
            return JSONResponse({"error": exc.code, "reason": exc.reason}, status_code=503)

    @app.post("/api/attachments")
    async def upload_attachment(request: Request) -> JSONResponse:
        """Upload and validate an attachment with bounds and SHA-256 verification."""
        from oneiro import research

        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            try:
                form = await request.form()
            except Exception as exc:
                return JSONResponse({"error": f"Invalid multipart form data: {exc}"}, status_code=400)
            upload_file = form.get("file")
            filename = getattr(upload_file, "filename", "unnamed.bin")
            read_fn = getattr(upload_file, "read", None)
            if not callable(read_fn):
                return JSONResponse({"error": "file field is required in form"}, status_code=400)
            data = await upload_file.read()  # type: ignore[union-attr]
        else:
            # Direct binary or json base64 body
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                max_bytes = int(config.value("attachments.max_bytes") or research.DEFAULT_MAX_BYTES)
                if len(raw) > max_bytes + 1024:
                    return JSONResponse({"error": f"Attachment exceeds limit of {max_bytes} bytes"}, status_code=413)
            filename = request.headers.get("x-filename", "attachment.bin")
            data = bytes(raw)

        try:
            meta = research.ingest_attachment(filename, data)
        except research.AttachmentRejected as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status)

        return JSONResponse(meta.to_dict())

    @app.get("/api/attachments/{attachment_id}")
    async def get_attachment(attachment_id: str) -> JSONResponse:
        from oneiro import research

        try:
            content = research.read_attachment_content(attachment_id)
            return JSONResponse(content)
        except research.AttachmentRejected as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status)

    def unavailable(exc: GraphQueryError) -> JSONResponse:
        """A memory read that failed, said in words rather than in wires.

        "resolve_keynodes failed" is not an answer to anything the owner asked,
        so the sentence is what the screen shows; the technical string travels as
        `detail` for a log or a bug report, and nothing is claimed to have run.
        """
        return JSONResponse({"error": "Nothing could be read from the memory graph just now. "
                                      "Nothing was changed.",
                             "detail": f"{exc.code}: {exc.reason}", "fallback": None},
                            status_code=503)

    def refused(status: int, error: str, **extra: Any) -> JSONResponse:
        return JSONResponse({"error": error, **extra}, status_code=status)

    async def page_read(work: Callable[[], Awaitable[Any]], *,
                        budget: float = PAGE_READ_BUDGET) -> Any:
        """One bounded graph read for a page, bounded on the lane, not by cancelling it.

        `asyncio.wait_for` here would cancel the call, and a cancellation lands in the
        worker's stop path: the owned worker dies and the durability gate closes because
        somebody looked at a page (measured 2026-10-11: every view of a silent graph
        respawned the worker). The lane gives up by itself within the budget and raises
        `graph_timeout`, which the routes below answer as `unavailable`.

        `work` is a thunk because the budget has to be set before the coroutines exist:
        `asyncio.gather` turns what it is given into tasks immediately, and a task made
        before this block keeps the context it was made in (measured 2026-10-11: the
        `/api/tasks` reads ran on the lane's own 10 s deadline instead of this one).
        """
        with page_budget(budget):
            return await work()

    @app.get("/api/memory/facts")
    async def facts() -> JSONResponse:
        try:
            found = await page_read(lambda: recall.current_facts(owner, limit_chars=_facts_budget()))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(found.to_dict())

    @app.post("/api/memory/facts")
    async def add_fact(request: Request) -> JSONResponse:
        body = await _json_object(request, FACT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        text, client_id = body.get("text"), body.get("client_id")
        if not isinstance(text, str):
            return refused(400, "text must be a non-empty string")
        if (error := recall.fact_text_error(text)) is not None:
            return refused(400, error)
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        fact_id = "fact-" + client_id
        async with facts_lock:
            try:
                found = await recall.current_facts(owner, limit_chars=_facts_budget())
                for existing in found.facts:
                    if existing["id"] == fact_id:      # a retry of a stored fact
                        return JSONResponse({"fact": existing, "duplicate": True})
                if not found.complete or found.skipped:
                    return refused(503, "Curated memory could not be fully read, so its limit cannot be checked. Nothing was saved.")
                if (error := recall.budget_error(found.used_chars, 0, text,
                                                 _facts_budget())) is not None:
                    return refused(422, error, used_chars=found.used_chars,
                                   limit_chars=_facts_budget())
                result = await owner.publish(recall.new_fact(fact_id, text).to_dict(), fact_id)
            except GraphQueryError as exc:
                return unavailable(exc)
        return JSONResponse({"fact": result["record"], "duplicate": result["duplicate"]})

    @app.post("/api/memory/facts/{fact_id}/edit")
    async def edit_fact(fact_id: str, request: Request) -> JSONResponse:
        if not _FACT_ID.fullmatch(fact_id):
            return refused(404, "no such fact")
        body = await _json_object(request, FACT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        text, client_id, revision = body.get("text"), body.get("client_id"), body.get("revision")
        if not isinstance(text, str):
            return refused(400, "text must be a non-empty string")
        if (error := recall.fact_text_error(text)) is not None:
            return refused(400, error)
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        if type(revision) is not int or revision < 1:
            return refused(400, "revision must be the revision you read")
        async with facts_lock:
            try:
                current = await recall.latest_fact(owner, fact_id)
                if current is None:
                    return refused(404, "no such fact")
                if current["state"] != State.COMPLETED.value:
                    return refused(409, "this fact was removed")
                found = await recall.current_facts(owner, limit_chars=_facts_budget())
                if not found.complete or found.skipped:
                    return refused(503, "Curated memory could not be fully read, so its limit cannot be checked. Nothing was saved.")
                # `current` is already in `used_chars`, so it is what this edit replaces.
                if (error := recall.budget_error(found.used_chars, len(current["text"]), text,
                                                 _facts_budget())) is not None:
                    return refused(422, error, used_chars=found.used_chars,
                                   limit_chars=_facts_budget())
                updated = recall.new_fact(fact_id, text, created_at=current["created_at"])
                result = await owner.publish(updated.to_dict(), "factedit-" + client_id,
                                             expected_revision=revision)
            except GraphQueryError as exc:
                if exc.code == "revision_conflict":
                    return refused(409, "this fact changed since you read it; reload the list")
                return unavailable(exc)
            except ValueError as exc:
                return refused(503, f"Stored memory is not readable: {exc}")
        return JSONResponse({"fact": result["record"], "duplicate": result["duplicate"]})

    @app.post("/api/memory/facts/{fact_id}/remove")
    async def remove_fact(fact_id: str, request: Request) -> JSONResponse:
        if not _FACT_ID.fullmatch(fact_id):
            return refused(404, "no such fact")
        body = await _json_object(request, FACT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        client_id, revision = body.get("client_id"), body.get("revision")
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        if type(revision) is not int or revision < 1:
            return refused(400, "revision must be the revision you read")
        async with facts_lock:
            try:
                current = await recall.latest_fact(owner, fact_id)
                if current is None:
                    return refused(404, "no such fact")
                if current["state"] != State.COMPLETED.value:
                    # Already removed: a retry after a lost response lands here.
                    return JSONResponse({"id": fact_id, "removed": True, "duplicate": True})
                removed = recall.new_fact(fact_id, current["text"], created_at=current["created_at"],
                                          state=State.CANCELLED)
                result = await owner.publish(removed.to_dict(), "factdel-" + client_id,
                                             expected_revision=revision)
            except GraphQueryError as exc:
                if exc.code == "revision_conflict":
                    return refused(409, "this fact changed since you read it; reload the list")
                return unavailable(exc)
            except ValueError as exc:
                return refused(503, f"Stored memory is not readable: {exc}")
        return JSONResponse({"id": fact_id, "removed": True, "duplicate": result["duplicate"]})

    @app.get("/api/conversations")
    async def conversations() -> JSONResponse:
        try:
            listed = await page_read(lambda: recall.conversation_list(owner))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(listed)

    @app.post("/api/conversations")
    async def new_conversation() -> JSONResponse:
        # Nothing is stored yet: a conversation exists once its first message does.
        return JSONResponse({"conversation_id": uuid.uuid4().hex})

    @app.get("/api/conversations/{conversation_id}/messages")
    async def conversation_messages(conversation_id: str, limit: str | None = None) -> JSONResponse:
        if not _CONVERSATION.fullmatch(conversation_id):
            return refused(400, "conversation_id must be 1..64 letters, digits or hyphens")
        try:
            async def read_messages() -> tuple[recall.Scan, dict[str, list[dict[str, Any]]]]:
                found = await recall.history(owner, conversation_id, limit=_check_limit(limit))
                steps = await agent.turn_steps_for(owner, {
                    row["id"] for row in found.rows if row["id"].startswith("reply-")})
                return found, steps

            found, steps = await page_read(read_messages)
        except GraphQueryError as exc:
            if exc.code == "bad_limit":
                return refused(400, exc.reason)
            return unavailable(exc)
        return JSONResponse({"conversation_id": conversation_id,
                             "messages": [{**_message_out(row), "steps": steps.get(row["id"], [])}
                                          for row in found.rows],
                             "complete": found.complete, "scanned": found.scanned,
                             "skipped": found.skipped})

    @app.get("/api/search")
    async def search(q: str | None = None) -> JSONResponse:
        words = (q or "").split()
        if (not words or len(q or "") > SEARCH_CHARS or len(words) > SEARCH_WORDS
                or any(len(word) > 64 for word in words)):
            return refused(400, f"query must be 1..{SEARCH_CHARS} characters, at most {SEARCH_WORDS} words")
        try:
            found = await page_read(lambda: recall.search_messages(owner, words,
                                                                  limit=SEARCH_LIMIT))
        except GraphQueryError as exc:
            return unavailable(exc)
        results = [{**_message_out(row), "snippet": recall.snippet(row["text"], words[0])}
                   for row in found.rows]
        # The note says what was covered. "No match" is claimed only for a complete read.
        if results and found.complete:
            note = f"{len(results)} matching messages in all {found.scanned} stored records."
        elif results:
            note = f"Showing {len(results)} newest matches; there may be more."
        elif found.complete:
            note = f"No match in all {found.scanned} stored records."
        else:
            note = (f"No match in the first {found.scanned} stored records; the search did not "
                    "cover the whole history.")
        if found.skipped:
            note += f" {found.skipped} stored records could not be read."
        return JSONResponse({"query": " ".join(words), "results": results, "note": note,
                             "scanned": found.scanned, "complete": found.complete,
                             "skipped": found.skipped})

    @app.get("/api/memory/records")
    async def memory_records(cursor: str | None = None, limit: str | None = None) -> JSONResponse:
        try:
            page = await page_read(lambda: owner.memory_page(cursor=cursor,
                                                             limit=_check_limit(limit)))
        except GraphQueryError as exc:
            invalid = exc.code in ("bad_cursor", "bad_limit", "bad_scan_limit")
            return JSONResponse({"error": exc.code, "reason": exc.reason, "fallback": None},
                                status_code=400 if invalid else 503)
        return JSONResponse({"required": "OSTIS", "fallback": None,
                             "order": "publication_newest_first", **page})

    @app.get("/api/memory/records/{record_id}")
    async def memory_entity(record_id: str) -> JSONResponse:
        try:
            record = await page_read(lambda: owner.memory_entity(record_id))
        except GraphQueryError as exc:
            return JSONResponse({"error": exc.code, "reason": exc.reason, "fallback": None}, status_code=503)
        return JSONResponse({"record": record}, status_code=200 if record is not None else 404)

    @app.get("/api/tasks")
    async def task_list() -> JSONResponse:
        """The owner's tasks, what Oneiro said on its own, and what it may start."""
        level = tasks.level()
        try:
            found, spoken, offered = await page_read(lambda: asyncio.gather(
                tasks.view(owner), tasks.notices(owner), tasks.suggestions(owner)))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse({**found.to_dict(), "level": level,
                             "level_error": tasks.settings_error(),
                             "picks_up_work": tasks.picks_up_work(level),
                             "notices": spoken["notices"], "quiet_hours": spoken["quiet_hours"],
                             "suggestions": offered["suggestions"], "suggests_why": offered["why"]})

    @app.get("/api/tasks/{task_id}")
    async def task_history(task_id: str) -> JSONResponse:
        """One task with every attempt it made, newest first: the run history.

        A task that is not stored is a 404 carrying the reason, not an empty task
        that would read like one that has never run.
        """
        if not _RECORD_ID.fullmatch(task_id):
            return refused(404, "no such task")
        try:
            history = await page_read(lambda: tasks.history(owner, task_id))
        except TaskError as exc:
            return refused(404, str(exc))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(history)

    @app.post("/api/tasks")
    async def task_create(request: Request) -> JSONResponse:
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        title, client_id = body.get("title"), body.get("client_id")
        if not isinstance(title, str) or not title.strip():
            return refused(400, "title must be a non-empty string")
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        blocked = body.get("blocked_by") or []
        if not isinstance(blocked, list) or any(not isinstance(item, str) for item in blocked):
            return refused(400, "blocked_by must be a list of task ids")
        role = body.get("role", "executor")
        if not isinstance(role, str):
            return refused(400, "role must be a string")
        try:
            result = await tasks.create(owner, title=title, detail=str(body.get("detail") or ""),
                                        role=role, blocked_by=blocked, client_id=client_id)
        except TaskError as exc:
            return refused(400, str(exc))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(result)

    @app.post("/api/tasks/{task_id}/run")
    async def task_run(task_id: str, request: Request) -> JSONResponse:
        """Begin one attempt because the owner asked for it, and run it here."""
        if not _RECORD_ID.fullmatch(task_id):
            return refused(404, "no such task")
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        retry = body.get("retry", False)
        if not isinstance(retry, bool):
            return refused(400, "retry must be true or false")
        try:
            result = await tasks.run_now(owner, task_id, retry=retry)
        except TaskError as exc:
            return refused(404, str(exc))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(result)

    @app.post("/api/hooks/{name}")
    async def hook_deliver(name: str, request: Request) -> JSONResponse:
        """One signed delivery from outside the conversation, turned into a task.

        The body is authenticated exactly as it arrived: re-serialising it would check a
        signature over bytes the caller never sent. Every refusal carries its own code
        and sentence, because "400 Bad Request" tells an integrator nothing about which
        half of their script is wrong. The answer is 202: the task is recorded and its
        work has not run — the same thing `tasks.create` did when the owner typed it.
        """
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > hooks.MAX_BODY:
                return refused(413, f"the body exceeds {hooks.MAX_BODY} bytes",
                               code="body_too_large", hook=name)
        try:
            result = await hooks.deliver(owner, bytes(raw),
                                         request.headers.get(hooks.HEADER), name=name)
        except hooks.HookError as exc:
            return refused(exc.status, exc.reason, code=exc.code, hook=name)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse({"hook": result["hook"], "client_id": result["client_id"],
                             "title": result["title"], "task_id": result["task_id"],
                             "duplicate": result["duplicate"]}, status_code=202)

    # ---- drafts: a reply that goes out only when the owner presses send ----
    #
    # A draft is written here, read here and released here, and the release is this
    # process's own act on the owner's behalf. The refusal statuses are the module's
    # reasons: `not_pressed` and `already_settled` are conflicts (the request is fine,
    # the state is not), `permission_denied` is a boundary, a missing tool or draft is a
    # 404, and a bot that has never been written to is a 503 with its own words.
    DRAFT_STATUS = {"unknown_draft": 404, "unknown_tool": 404, "bad_arguments": 400,
                    "not_pressed": 409, "already_settled": 409, "permission_denied": 403,
                    "not_the_owner": 403, "no_chat": 503}

    def draft_refused(exc: drafts.DraftError) -> JSONResponse:
        return refused(DRAFT_STATUS.get(exc.reason, 400), str(exc), reason=exc.reason)

    def draft_input(body: dict[str, Any]) -> tuple[str, dict[str, Any]] | JSONResponse:
        """The tool key and the exact arguments, checked before anything is written."""
        tool, arguments = body.get("tool"), body.get("arguments")
        if not isinstance(tool, str) or "." not in tool:
            return refused(400, "tool must be the key of a declared MCP tool, "
                                "such as server.tool")
        if not isinstance(arguments, dict):
            return refused(400, "arguments must be an object: the exact call the draft makes")
        return tool, arguments

    @app.get("/api/drafts")
    async def draft_list() -> JSONResponse:
        """The drafts waiting for the owner, and what became of the last few that are not."""
        try:
            listed = await page_read(lambda: drafts.listing(owner))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(listed)

    @app.get("/api/drafts/{draft_id}")
    async def draft_show(draft_id: str) -> JSONResponse:
        if not _RECORD_ID.fullmatch(draft_id):
            return refused(404, "no such draft")
        try:
            found = await page_read(lambda: drafts.get(owner, draft_id))
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(found)

    @app.post("/api/mail/read")
    async def mail_read(request: Request) -> JSONResponse:
        """Ask a declared mailbox tool for the newest incoming mail and keep it."""
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        asked = draft_input({**body, "arguments": body.get("arguments") or {}})
        if isinstance(asked, JSONResponse):
            return asked
        limit = body.get("limit", 10)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            return refused(400, "limit must be a whole number between 1 and 50")
        try:
            read = await drafts.read_incoming(owner, tool=asked[0], arguments=asked[1],
                                              limit=limit)
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(read)

    @app.post("/api/drafts")
    async def draft_create(request: Request) -> JSONResponse:
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        asked = draft_input(body)
        if isinstance(asked, JSONResponse):
            return asked
        labels = body.get("labels") or []
        if not isinstance(labels, list) or any(not isinstance(item, str) for item in labels):
            return refused(400, "labels must be a list of words")
        try:
            created = await drafts.create(owner, tool=asked[0], arguments=asked[1],
                                          labels=tuple(labels),
                                          source_id=str(body.get("source_id") or ""))
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(created, status_code=201)

    @app.post("/api/drafts/{draft_id}/revise")
    async def draft_revise(draft_id: str, request: Request) -> JSONResponse:
        """Edit a pending draft. The edited call has not been pressed, so it waits again."""
        if not _RECORD_ID.fullmatch(draft_id):
            return refused(404, "no such draft")
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        arguments = body.get("arguments")
        if not isinstance(arguments, dict):
            return refused(400, "arguments must be the object to replace the draft with")
        try:
            revised = await drafts.revise(owner, draft_id, arguments=arguments)
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(revised)

    @app.post("/api/drafts/{draft_id}/discard")
    async def draft_discard(draft_id: str, request: Request) -> JSONResponse:
        if not _RECORD_ID.fullmatch(draft_id):
            return refused(404, "no such draft")
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        try:
            discarded = await drafts.discard(owner, draft_id, reason=str(body.get("reason") or ""))
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(discarded)

    @app.post("/api/drafts/{draft_id}/send")
    async def draft_send(draft_id: str, request: Request) -> JSONResponse:
        """The owner's press: the decision and the send, in that order.

        `dry_run` asks the same question the press answers and sends nothing — a screen
        needs to know whether the button is live without pressing it.
        """
        if not _RECORD_ID.fullmatch(draft_id):
            return refused(404, "no such draft")
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        dry_run = body.get("dry_run", False)
        if not isinstance(dry_run, bool):
            return refused(400, "dry_run must be true or false")
        try:
            if dry_run:
                return JSONResponse(await drafts.send(owner, draft_id, actor="owner",
                                                      dry_run=True))
            result = await drafts.press(owner, draft_id)
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(result)

    @app.post("/api/telegram/notice")
    async def telegram_notice(request: Request) -> JSONResponse:
        """Tell the owner, in their own chat, that a draft is waiting.

        The text is composed here from the draft itself and the address is discovered
        from the bot's own inbox, so neither is a parameter: this route cannot be used
        to send anything to anybody else, whatever is posted to it.
        """
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        draft_id, tool = body.get("draft_id"), body.get("tool")
        updates_tool = body.get("updates_tool")
        if not isinstance(draft_id, str) or not _RECORD_ID.fullmatch(draft_id):
            return refused(400, "draft_id must name a draft")
        for name, value in (("tool", tool), ("updates_tool", updates_tool)):
            if not isinstance(value, str) or "." not in value:
                return refused(400, f"{name} must be the key of a declared MCP tool")
        try:
            found = await drafts.get(owner, draft_id)
            sent = await drafts.notify(owner, drafts.notice_for(owner, found),
                                       tool=str(tool), updates_tool=str(updates_tool))
        except drafts.DraftError as exc:
            return draft_refused(exc)
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse({**sent, "draft_id": draft_id})

    @app.get("/api/schedules")
    async def schedule_list() -> JSONResponse:
        try:
            listed = await page_read(lambda: schedule.listing(owner))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(listed)

    @app.post("/api/schedules")
    async def schedule_create(request: Request) -> JSONResponse:
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        title, cron, client_id = body.get("title"), body.get("cron"), body.get("client_id")
        if not isinstance(title, str) or not title.strip():
            return refused(400, "title must be a non-empty string")
        if not isinstance(cron, str) or not cron.strip():
            return refused(400, "cron must be an expression such as '0 9 * * *'")
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        role = body.get("role", "executor")
        if not isinstance(role, str):
            return refused(400, "role must be a string")
        try:
            result = await schedule.add(owner, title=title, cron=cron,
                                        detail=str(body.get("detail") or ""), role=role,
                                        client_id=client_id)
        except ScheduleError as exc:
            return refused(400, str(exc))
        except GraphQueryError as exc:
            return unavailable(exc)
        return JSONResponse(result)

    @app.post("/api/schedules/{schedule_id}/remove")
    async def schedule_remove(schedule_id: str, request: Request) -> JSONResponse:
        if not _RECORD_ID.fullmatch(schedule_id):
            return refused(404, "no such schedule")
        body = await _json_object(request, CHAT_BODY_LIMIT)
        if isinstance(body, JSONResponse):
            return body
        client_id = body.get("client_id")
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        try:
            result = await schedule.remove(owner, schedule_id, client_id=client_id)
        except ScheduleError as exc:
            return refused(404, str(exc))
        except GraphQueryError as exc:
            if exc.code == "revision_conflict":
                return refused(409, "this schedule changed since you read it; reload the list")
            return unavailable(exc)
        return JSONResponse(result)

    @app.post("/api/schedules/tick")
    async def schedule_tick() -> JSONResponse:
        """Look at the clock now instead of waiting for the next minute."""
        try:
            return JSONResponse(await schedule.tick(owner))
        except GraphQueryError as exc:
            return unavailable(exc)

    @app.get("/api/graph")
    async def graph() -> JSONResponse:
        """What the memory substrate can actually be read for, right now.

        The probe blocks on a socket and a graph traversal, so it runs off the
        request thread and is bounded: an unresponsive graph must not hold the
        page open. There is no substitute store, so an unreachable graph is a
        503 carrying the reason, never an empty graph that reads like success.
        """
        host = str(config.value("graph.host"))
        port = int(config.value("graph.port"))
        facts = await asyncio.to_thread(memory.probe_within, host, port,
                                        budget=memory.PROBE_BUDGET)
        return JSONResponse(facts.to_dict(), status_code=200 if facts.reachable else 503)

    return app
