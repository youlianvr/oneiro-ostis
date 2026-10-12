"""The console the W2 live check drives: the product's app, on a temporary data root.

`oneiro serve` always writes as the `product` stream, which holds the owner's own work,
and this check must not add demo records to it. So the app is still the product's app
(`oneiro.web.create_app`) on the product's server (uvicorn), with the one thing the
check chooses for itself: the stream the memory is written in, and the port it listens
on. Everything else — routes, middleware, store, records — is the product's own.

    ONEIRO_DATA_DIR=<temp> ONEIRO_PORT=8096 ONEIRO_WEB_PORT=<free> \
        python tests/live_hooks_serve.py [--stream demo]

It prints where it listens and then serves until it is stopped. The check starts it as a
separate process and reads its exit code, so this file has no knowledge of the check.
"""
from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "python"))

import uvicorn                                                       # noqa: E402
from oneiro import config, web                                       # noqa: E402
from oneiro.graph_worker import GraphWorker                          # noqa: E402
from oneiro.runtime import Runtime                                   # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="live_hooks_serve",
                                     description="Oneiro for the W2 live check")
    parser.add_argument("--stream", default="demo",
                        help="the subject of experience the memory is written in")
    args = parser.parse_args(argv)

    host, port = str(config.value("web.host")), int(config.value("web.port"))
    graph = f"ws://{config.value('graph.host')}:{config.value('graph.port')}/ws_json"
    worker = GraphWorker(graph, args.stream, config.data_root() / "graph-writer.lock")
    print(f"Oneiro: http://{host}:{port}  stream {args.stream}  graph {graph}", flush=True)

    server = uvicorn.Server(uvicorn.Config(web.create_app(runtime=Runtime(graph=worker),
                                                          scheduler=False),
                                           host=host, port=port, access_log=False,
                                           log_level="warning"))
    # uvicorn installs its own handler for SIGINT and SIGTERM; on Windows the check asks
    # it to stop with a break event, which nobody handles by default — a handler that sets
    # what uvicorn's own handler sets is the difference between a graceful stop and a
    # killed process, and the check reads this very exit code.
    for name in ("SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name),
                          lambda *_: setattr(server, "should_exit", True))
    server.run()
    return 0 if server.started else 2


if __name__ == "__main__":
    raise SystemExit(main())
