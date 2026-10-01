"""Standalone entrypoint. No ambient install, browser launch or autostart."""
from __future__ import annotations

import argparse
import asyncio
import json
import socket

from oneiro import config
from oneiro.ownership import OwnershipError
from oneiro.runtime import Runtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Oneiro standalone rewrite")
    parser.add_argument("command", choices=("doctor", "serve"))
    args = parser.parse_args(argv)
    listener: socket.socket | None = None
    try:
        if args.command == "doctor":
            # Read-only: no runtime lease or graph writes.
            result = asyncio.run(Runtime().status())
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 1
        host, port = str(config.value("web.host")), int(config.value("web.port"))
        listener = socket.socket()
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, port))
        listener.listen(128)
        listener.setblocking(False)
        import uvicorn
        from oneiro.web import create_app
        server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port,
                                             access_log=False, log_level="warning"))
        print(f"Oneiro foundation: http://{host}:{port}; assistant integration pending", flush=True)
        server.run(sockets=[listener])
        return 0 if server.started else 2
    except (ValueError, OSError, OwnershipError):
        print("Oneiro cannot start: check configuration, runtime ownership and port availability.")
        return 2
    finally:
        if listener is not None:
            listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
