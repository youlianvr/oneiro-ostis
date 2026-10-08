"""Same-origin foundation; chat and graph remain explicitly unavailable."""
from __future__ import annotations

import asyncio
import json
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from oneiro import config, memory, pages, recall
from oneiro.chat import ChatError, chat_reply
from oneiro.records import ConversationMessage, Provenance, State
from oneiro.runtime import Runtime
from oneiro.query import GraphQueryError, _check_limit

STATIC = Path(__file__).parent / "static"
CHAT_CONVERSATION = "main"
CHAT_MAX_CHARS = 4000
CHAT_BODY_LIMIT = 16000
_CLIENT_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
_FACT_ID = re.compile(r"fact-[A-Za-z0-9-]{8,64}")
FACT_BODY_LIMIT = 8000


class _ChatRefused(Exception):
    """A chat request the slice declines, carrying the status it should return."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


async def _json_object(request: Request, limit: int) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """A bounded JSON object from the body, or the refusal to return instead."""
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > limit:
            return None, JSONResponse({"error": f"Body exceeds {limit} bytes"}, status_code=413)
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return None, JSONResponse({"error": "Body must be a JSON object"}, status_code=400)
    return body, None


async def _chat_turn(owner: Runtime, text: str, client_id: str) -> dict[str, Any]:
    """One owner message and one model reply, each published at most once.

    Record IDs derive from the client's ID, so a retry after a lost response or
    a restart finds what was already published and does not publish it again.
    The model is called only when no reply for this ID is stored yet.
    """
    user_id, reply_id = "msg-" + client_id, "reply-" + client_id
    user = await owner.memory_entity(user_id)
    if user is None:
        record = ConversationMessage(id=user_id, conversation_id=CHAT_CONVERSATION, role="owner",
                                     text=text, provenance=Provenance.OWNER_INSTRUCTION)
        await owner.chat_append(record.to_dict(), user_id)
        user = record.to_dict()
    elif user.get("text") != text:
        raise _ChatRefused(409, "this client_id already carries a different message")
    reply = await owner.memory_entity(reply_id)
    context: dict[str, Any] | None = None
    if reply is None:
        # Read memory before the model is called. A failed read does not stop the
        # reply; the report says what the reply could not use.
        messages, context = await recall.reply_context(
            owner, CHAT_CONVERSATION, exclude_id=user_id,
            history_limit=int(config.value("chat.history_messages")),
            char_budget=int(config.value("chat.context_chars")))
        messages.append({"role": "user", "content": text})
        try:
            answer = await asyncio.to_thread(
                chat_reply, messages,
                base_url=str(config.value("llm.base_url")),
                api_key=str(config.value("llm.api_key")),
                model=str(config.value("llm.model")),
            )
        except ChatError as exc:
            # The owner's message stays stored; no reply is invented in its place.
            raise _ChatRefused(503, str(exc)) from None
        record = ConversationMessage(id=reply_id, conversation_id=CHAT_CONVERSATION, role="manager",
                                     text=answer, provenance=Provenance.MODEL_CLAIM)
        await owner.chat_append(record.to_dict(), reply_id)
        reply = record.to_dict()
    return {"user": user, "reply": reply, "context": context}


def create_app(runtime: Runtime | None = None) -> FastAPI:
    owner = runtime or Runtime()
    csrf = secrets.token_urlsafe(32)
    # One owner, one process: fact writes check a budget before publishing, so
    # two writes must not interleave between that check and the publication.
    facts_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await owner.start()
        try:
            yield
        finally:
            await owner.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = owner
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def same_origin(request: Request, call_next: Any) -> Any:
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or parsed.netloc != request.headers.get("host"):
                return JSONResponse({"error": "Cross-origin request refused"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not secrets.compare_digest(request.headers.get("x-oneiro-csrf", ""), csrf):
                return JSONResponse({"error": "Invalid owner request token"}, status_code=403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    async def serve(page: str) -> HTMLResponse:
        """One route, one page. `web.py` names it; `pages` renders it."""
        description = config.describe()
        facts = None
        if page == "graph":
            host = str(config.value("graph.host"))
            port = int(config.value("graph.port"))
            facts = await asyncio.wait_for(
                asyncio.to_thread(memory.probe, host, port),
                timeout=memory.PROBE_TIMEOUT + 2)
        return HTMLResponse(pages.render(page, description, error=description["error"],
                                        facts=facts))

    @app.get("/", response_class=HTMLResponse)
    async def chat() -> HTMLResponse:
        return await serve("chat")

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page() -> HTMLResponse:
        return await serve("settings")

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page() -> HTMLResponse:
        return await serve("setup")

    @app.get("/oneiro/", response_class=HTMLResponse)
    async def graph_page() -> HTMLResponse:
        return await serve("graph")

    @app.get("/app.js")
    async def script() -> FileResponse:
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @app.get("/style.css")
    async def styles() -> FileResponse:
        return FileResponse(STATIC / "style.css", media_type="text/css")

    @app.get("/api/session")
    async def session() -> dict[str, str]:
        return {"csrf": csrf}

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"http": "ready", "assistant_ready": False, "instance_id": owner.instance_id}

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
            import json
            import asyncio
            patch = json.loads(raw)
            # Cross-process lease and backups belong to the shared config module.
            result = await asyncio.to_thread(config.save, patch)
            await owner.status(refresh=True)
            return JSONResponse(result)
        except (ValueError, TypeError, OSError):
            # Never reflect request values or exception text that may carry keys.
            return JSONResponse({"error": "Invalid settings or settings file unavailable; existing data preserved"}, status_code=400)

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
        if not isinstance(text, str) or not text.strip() or len(text) > CHAT_MAX_CHARS:
            return JSONResponse({"error": f"text must be 1..{CHAT_MAX_CHARS} characters"}, status_code=400)
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return JSONResponse({"error": "client_id must be 8..64 letters, digits or hyphens"}, status_code=400)
        try:
            return JSONResponse(await _chat_turn(owner, text, client_id))
        except _ChatRefused as exc:
            return JSONResponse({"error": exc.message}, status_code=exc.status)
        except GraphQueryError as exc:
            return JSONResponse({"error": exc.code, "reason": exc.reason}, status_code=503)

    def unavailable(exc: GraphQueryError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "reason": exc.reason, "fallback": None},
                            status_code=503)

    def refused(status: int, error: str, **extra: Any) -> JSONResponse:
        return JSONResponse({"error": error, **extra}, status_code=status)

    @app.get("/api/memory/facts")
    async def facts() -> JSONResponse:
        try:
            return JSONResponse((await recall.current_facts(owner)).to_dict())
        except GraphQueryError as exc:
            return unavailable(exc)

    @app.post("/api/memory/facts")
    async def add_fact(request: Request) -> JSONResponse:
        body, refusal = await _json_object(request, FACT_BODY_LIMIT)
        if refusal is not None:
            return refusal
        text, client_id = body.get("text"), body.get("client_id")
        if (error := recall.fact_text_error(text)) is not None:
            return refused(400, error)
        if not isinstance(client_id, str) or not _CLIENT_ID.fullmatch(client_id):
            return refused(400, "client_id must be 8..64 letters, digits or hyphens")
        fact_id = "fact-" + client_id
        async with facts_lock:
            try:
                found = await recall.current_facts(owner)
                for existing in found.facts:
                    if existing["id"] == fact_id:      # a retry of a stored fact
                        return JSONResponse({"fact": existing, "duplicate": True})
                if not found.complete or found.skipped:
                    return refused(503, "Curated memory could not be fully read, so its limit cannot be checked. Nothing was saved.")
                if (error := recall.budget_error(found.used_chars, 0, text)) is not None:
                    return refused(422, error, used_chars=found.used_chars, limit_chars=recall.CURATED_CHARS)
                result = await owner.publish(recall.new_fact(fact_id, text).to_dict(), fact_id)
            except GraphQueryError as exc:
                return unavailable(exc)
        return JSONResponse({"fact": result["record"], "duplicate": result["duplicate"]})

    @app.post("/api/memory/facts/{fact_id}/edit")
    async def edit_fact(fact_id: str, request: Request) -> JSONResponse:
        if not _FACT_ID.fullmatch(fact_id):
            return refused(404, "no such fact")
        body, refusal = await _json_object(request, FACT_BODY_LIMIT)
        if refusal is not None:
            return refusal
        text, client_id, revision = body.get("text"), body.get("client_id"), body.get("revision")
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
                found = await recall.current_facts(owner)
                if not found.complete or found.skipped:
                    return refused(503, "Curated memory could not be fully read, so its limit cannot be checked. Nothing was saved.")
                # `current` is already in `used_chars`, so it is what this edit replaces.
                if (error := recall.budget_error(found.used_chars, len(current["text"]), text)) is not None:
                    return refused(422, error, used_chars=found.used_chars, limit_chars=recall.CURATED_CHARS)
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
        body, refusal = await _json_object(request, FACT_BODY_LIMIT)
        if refusal is not None:
            return refusal
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

    @app.get("/api/memory/records")
    async def memory_records(cursor: str | None = None, limit: str | None = None) -> JSONResponse:
        try:
            page = await owner.memory_page(cursor=cursor, limit=_check_limit(limit))
        except GraphQueryError as exc:
            invalid = exc.code in ("bad_cursor", "bad_limit", "bad_scan_limit")
            return JSONResponse({"error": exc.code, "reason": exc.reason, "fallback": None},
                                status_code=400 if invalid else 503)
        return JSONResponse({"required": "OSTIS", "fallback": None,
                             "order": "publication_newest_first", **page})

    @app.get("/api/memory/records/{record_id}")
    async def memory_entity(record_id: str) -> JSONResponse:
        try:
            record = await owner.memory_entity(record_id)
        except GraphQueryError as exc:
            return JSONResponse({"error": exc.code, "reason": exc.reason, "fallback": None}, status_code=503)
        return JSONResponse({"record": record}, status_code=200 if record is not None else 404)

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
        facts = await asyncio.wait_for(asyncio.to_thread(memory.probe, host, port),
                                       timeout=memory.PROBE_TIMEOUT + 2)
        return JSONResponse(facts.to_dict(), status_code=200 if facts.reachable else 503)

    return app
