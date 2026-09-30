"""Native local-first web application; a channel adapter over Oneiro."""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from native.memory import MemoryUnavailable
from native.service import Busy

WEB_ROOT = Path(__file__).resolve().parents[2] / "interface" / "native"


class NativeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, *, access_token=""):
        self.service = service
        self.access_token = access_token
        self.sessions = {}
        self.session_lock = threading.Lock()
        self.local_only = address[0] in ("127.0.0.1", "localhost", "::1")
        super().__init__(address, NativeHandler)


class NativeHandler(BaseHTTPRequestHandler):
    server_version = "Oneiro/1"

    def log_message(self, *args):
        pass  # URLs, cookies and tokens never enter access logs.

    def reply(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        for name, value in {"Content-Type": content_type, "Content-Length": str(len(raw)),
                            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                            "Referrer-Policy": "no-referrer",
                            "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
                            **(headers or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 200000:
            raise ValueError("Request body must contain 1..200000 bytes")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("An object body is required")
        return value

    def session(self):
        cookie = self.headers.get("Cookie", "")
        sid = next((part.strip().split("=", 1)[1] for part in cookie.split(";")
                    if part.strip().startswith("oneiro_session=")), "")
        with self.server.session_lock:
            data = self.server.sessions.get(sid)
            if data and data["expires"] > time.time():
                return data
        return None

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme in ("http", "https") and parsed.netloc == self.headers.get("Host")

    def authenticate(self, *, write=False):
        data = self.session()
        if not data:
            self.reply(401, {"error": "Sign in to this Oneiro instance"})
            return False
        if write and (not self.same_origin() or not hmac.compare_digest(
                self.headers.get("X-Oneiro-CSRF", ""), data["csrf"])):
            self.reply(403, {"error": "Invalid same-origin owner request"})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            # Readiness proves the HTTP service is running, not that integrations work.
            return self.reply(200, {"product": "Oneiro", "http": "ready"})
        if path == "/api/session":
            data = self.session()
            return self.reply(200, {"authenticated": bool(data), "csrf": data["csrf"] if data else "",
                                   "token_required": not self.server.local_only})
        if path.startswith("/api/"):
            if not self.authenticate():
                return
            try:
                if path == "/api/state":
                    return self.reply(200, self.server.service.snapshot())
                return self.reply(404, {"error": "Unknown API route"})
            except MemoryUnavailable as exc:
                return self.reply(503, {"error": str(exc), "memory": "unavailable"})
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path not in files:
            return self.reply(404, {"error": "Not found"})
        filename, kind = files[path]
        return self.reply(200, (WEB_ROOT / filename).read_bytes(), kind)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            body = self.body()
            if path == "/api/login":
                if not self.same_origin():
                    return self.reply(403, {"error": "Cross-origin login is refused"})
                token = str(body.get("token", ""))
                local = self.server.local_only and self.client_address[0] in ("127.0.0.1", "::1")
                host = self.headers.get("Host", "").split(":")[0]
                if local and host not in ("127.0.0.1", "localhost", "[", "::1"):
                    return self.reply(403, {"error": "Untrusted host header"})
                if not local and (not self.server.access_token or not hmac.compare_digest(token, self.server.access_token)):
                    return self.reply(401, {"error": "A valid ONEIRO_WEB_TOKEN is required for remote access"})
                sid = secrets.token_urlsafe(32)
                data = {"csrf": secrets.token_urlsafe(32), "expires": time.time() + 12 * 3600}
                with self.server.session_lock:
                    self.server.sessions = {k: v for k, v in self.server.sessions.items() if v["expires"] > time.time()}
                    if len(self.server.sessions) > 100:
                        return self.reply(429, {"error": "Session limit reached"})
                    self.server.sessions[sid] = data
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                return self.reply(200, {"csrf": data["csrf"]}, headers={
                    "Set-Cookie": f"oneiro_session={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200" + secure})
            if not self.authenticate(write=True):
                return
            service = self.server.service
            if path == "/api/message":
                return self.reply(202, service.message(body["text"], reply_to=body.get("reply_to", "")))
            if path == "/api/decision":
                return self.reply(200, service.decide(body["id"], body["approved"]))
            if path == "/api/answer":
                return self.reply(202, service.answer(body["id"], body["text"]))
            if path == "/api/settings":
                return self.reply(200, service.update_settings(body))
            if path == "/api/soul":
                return self.reply(200, {"text": service.update_soul(body["role"], body["text"])})
            if path == "/api/retry":
                return self.reply(202, service.retry(body["kind"], body["id"]))
            return self.reply(404, {"error": "Unknown API route"})
        except MemoryUnavailable as exc:
            return self.reply(503, {"error": str(exc)})
        except Busy as exc:
            return self.reply(409, {"error": str(exc)})
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply(400, {"error": str(exc)[:500]})
        except Exception:
            return self.reply(500, {"error": "Native service failed; no success is being claimed"})
