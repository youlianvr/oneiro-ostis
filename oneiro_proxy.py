"""One address for the product: the console owns it, the panel lives under it.

The console and the panel cannot share one interpreter. The panel needs the
project's modules by their bare names (`config`, `bridge`, `replay`), and the
console has its own modules under those very names - `config` is imported by
the console before anything else runs, so a panel imported into that process
would be handed the console's settings module, and whichever side loses the
name collision fails quietly instead of loudly. Keeping the panel in its own
process is what makes the two safe to run at once.

What the owner asked for is one program and one address, and that is what this
module gives: the console serves the only origin the browser sees, and hands
`/oneiro/` to the panel underneath. The settings page therefore talks to
`/oneiro/api/settings` on its own origin - no port hunting, no CORS.

Two deliberate properties:

  - **Standard library only.** This code is imported inside the console
    process, so anything it imported from the project would drag the project's
    module names in with it - the exact collision the split exists to avoid.
  - **Streaming, not buffering.** The panel's `/api/events` is a
    server-sent-events stream that stays open while the page is open. The
    response is forwarded chunk by chunk as it arrives; reading it whole first
    would turn a live log into a page that never updates.

Run it standalone to check the wiring without the console:

    python oneiro_proxy.py 8134 http://127.0.0.1:8133
"""

from __future__ import annotations

import http.client
import sys
from urllib.parse import urlsplit

# Headers that describe a single connection rather than the message. Copying
# them across would make the two servers argue about framing.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
})

CHUNK = 64 * 1024


class _Mount:
    """Forward one URL prefix upstream; leave every other path to `app`."""

    def __init__(self, app, prefix: str, host: str, port: int, timeout: float):
        self.app = app
        self.prefix = "/" + prefix.strip("/")
        self.host = host
        self.port = port
        self.timeout = timeout

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        if path == self.prefix:
            # The panel's page resolves its API paths relative to the page, so
            # it must be reached with the trailing slash. Without this the
            # browser would resolve them against the console root instead.
            query = environ.get("QUERY_STRING", "")
            location = self.prefix + "/" + (f"?{query}" if query else "")
            start_response("301 Moved Permanently", [
                ("Location", location),
                ("Content-Length", "0"),
            ])
            return [b""]
        if not path.startswith(self.prefix + "/"):
            return self.app(environ, start_response)
        return self._forward(environ, start_response)

    def _forward(self, environ, start_response):
        # The mount prefix is dropped: the panel serves /api/state, not
        # /oneiro/api/state, so it stays usable on its own without the console.
        path = (environ.get("PATH_INFO") or "/")[len(self.prefix):] or "/"
        query = environ.get("QUERY_STRING", "")
        target = f"{path}?{query}" if query else path

        headers = {}
        for key, value in environ.items():
            if not key.startswith("HTTP_"):
                continue
            name = key[5:].replace("_", "-")
            if name.lower() not in HOP_BY_HOP:
                headers[name] = value
        if environ.get("CONTENT_TYPE"):
            headers["Content-Type"] = environ["CONTENT_TYPE"]
        headers["Host"] = f"{self.host}:{self.port}"

        body = None
        length = environ.get("CONTENT_LENGTH")
        if length:
            try:
                body = environ["wsgi.input"].read(int(length))
            except (ValueError, OSError):
                body = b""

        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(environ.get("REQUEST_METHOD", "GET"), target, body=body, headers=headers)
            response = connection.getresponse()
        except (OSError, http.client.HTTPException) as exc:
            # The console must survive a panel that is down: the chat and the
            # settings page are still served, and this says plainly what is
            # missing instead of leaving the browser to guess.
            start_response("502 Bad Gateway", [("Content-Type", "text/plain; charset=utf-8")])
            return [f"Панель Oneiro недоступна: {exc}".encode("utf-8")]

        start_response(
            f"{response.status} {response.reason}",
            [(k, v) for k, v in response.getheaders() if k.lower() not in HOP_BY_HOP],
        )
        return self._stream(response)

    @staticmethod
    def _stream(response):
        # read1, not read: a plain read(n) on a chunked response keeps pulling
        # until n bytes are collected, which for a stream that sends one small
        # line every fifteen seconds means the client sees nothing at all.
        # read1 returns whatever has arrived, which is the whole point here.
        read = getattr(response, "read1", None) or response.read
        try:
            while True:
                chunk = read(CHUNK)
                if not chunk:
                    return
                yield chunk
        finally:
            response.close()


def wrap(app, spec: str, timeout: float = 300.0):
    """Mount every `prefix=base_url` entry in `spec` in front of `app`.

    Longer prefixes are mounted first so a specific path wins over a general
    one; `spec` is the shape `ONEIRO_PROXY` uses, e.g.
    ``/oneiro=http://127.0.0.1:8130``.
    """
    mounts = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        prefix, sep, url = item.partition("=")
        if not sep:
            raise ValueError(f"нет знака '=' в записи прокси: {item!r}")
        parts = urlsplit(url.strip())
        if parts.scheme != "http" or not parts.hostname:
            raise ValueError(f"ожидается http://хост:порт в записи прокси: {item!r}")
        mounts.append(_Mount(app, prefix, parts.hostname,
                             parts.port or 80, timeout))
    for mount in sorted(mounts, key=lambda m: len(m.prefix), reverse=True):
        app = mount
    return app


def main(argv):
    """A standalone run, for checking the proxy without starting the console."""
    if len(argv) < 3:
        print("Как пользоваться: python oneiro_proxy.py <порт> <адрес панели>")
        return 2
    import wsgiref.simple_server

    def nothing(environ, start_response):
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"only the mount (default /oneiro) is served in this check mode"]

    port = int(argv[1])
    app = wrap(nothing, f"/oneiro={argv[2]}")
    with wsgiref.simple_server.make_server("127.0.0.1", port, app) as server:
        print(f"прокси слушает http://127.0.0.1:{port}/oneiro/ -> {argv[2]}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
