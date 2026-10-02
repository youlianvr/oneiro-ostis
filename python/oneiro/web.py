"""Same-origin foundation; chat and graph remain explicitly unavailable."""
from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from oneiro import config, memory, pages
from oneiro.runtime import Runtime

STATIC = Path(__file__).parent / "static"


def create_app(runtime: Runtime | None = None) -> FastAPI:
    owner = runtime or Runtime()
    csrf = secrets.token_urlsafe(32)

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
    async def not_integrated() -> JSONResponse:
        return JSONResponse({"error": "The agent runtime is not integrated yet", "ready": False}, status_code=503)

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
