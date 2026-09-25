"""The proxy is the seam between one address and two processes: keep it tested.

Nothing here needs the panel or the console. The upstream is a throwaway HTTP
server on a free port, so the tests stay offline and deterministic and still
exercise the real forwarding path rather than a mock of it.
"""

from __future__ import annotations

import http.server
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import oneiro_proxy  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Upstream(http.server.BaseHTTPRequestHandler):
    """Records what arrived and answers with what the test asked for."""

    seen: list = []

    def _answer(self):
        body = json.dumps({"path": self.path, "method": self.command}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *args):  # silence the test run
        pass


class _UpstreamServer:
    def __init__(self):
        self.port = _free_port()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), _Upstream)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def _call(app, path, query="", method="GET", body=b""):
    """Run one request through a WSGI app and collect status, headers, body."""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "80",
        "wsgi.input": __import__("io").BytesIO(body),
        "CONTENT_LENGTH": str(len(body)),
    }
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    chunks = app(environ, start_response)
    payload = b"".join(chunks)
    if hasattr(chunks, "close"):
        chunks.close()
    return captured["status"], captured["headers"], payload


def _fallback(environ, start_response):
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"not a mount"]


def test_redirects_bare_prefix_to_the_trailing_slash():
    """The page resolves its API paths relative to itself, so the slash matters."""
    app = oneiro_proxy.wrap(_fallback, "/oneiro=http://127.0.0.1:1")
    status, headers, _ = _call(app, "/oneiro")
    assert status.startswith("301")
    assert headers["Location"] == "/oneiro/"


def test_paths_outside_the_mount_stay_with_the_console():
    app = oneiro_proxy.wrap(_fallback, "/oneiro=http://127.0.0.1:1")
    status, _, body = _call(app, "/chat")
    assert status.startswith("404")
    assert body == b"not a mount"


def test_the_prefix_is_dropped_so_the_panel_is_portable():
    """The panel serves /api/state on its own; it must never learn about /oneiro."""
    with _UpstreamServer() as upstream:
        app = oneiro_proxy.wrap(_fallback, f"/oneiro={upstream}")
        status, _, body = _call(app, "/oneiro/api/state", query="subject=abc")
        assert status.startswith("200")
        assert json.loads(body) == {"path": "/api/state?subject=abc", "method": "GET"}


def test_a_dead_panel_says_so_instead_of_hanging():
    app = oneiro_proxy.wrap(_fallback, f"/oneiro=http://127.0.0.1:{_free_port()}")
    status, _, body = _call(app, "/oneiro/api/settings")
    assert status.startswith("502")
    assert "недоступна".encode("utf-8") in body


@pytest.mark.parametrize("spec", ["/oneiro", "/oneiro=ftp://host", "/oneiro=not a url"])
def test_a_broken_spec_is_refused_rather_than_guessed(spec):
    """A typo in a configuration line must be loud: the console logs it."""
    with pytest.raises(ValueError):
        oneiro_proxy.wrap(_fallback, spec)
