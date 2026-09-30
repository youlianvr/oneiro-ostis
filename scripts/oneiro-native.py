#!/usr/bin/env python3
"""Run the native Oneiro, without CowAgent/OpenClaw. No automatic installation."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "python"))

from native.memory import GraphMemory
from native.service import Oneiro, Busy
from native.telegram import Telegram
from native.web import NativeServer


def diagnostics():
    return {"python": sys.version.split()[0],
            "dependencies": {name: importlib.util.find_spec(name) is not None
                             for name in ("sc_client", "sc_kpm", "websocket")},
            "docker": bool(shutil.which("docker")),
            "keys": {name: bool(os.environ.get(name)) for name in (
                "ONEIRO_LLM_API_KEY", "OMNIROUTE_API_KEY", "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_CHAT_ID", "VIRUSTOTAL_API_KEY", "ONEIRO_WEB_TOKEN")},
            "memory": "OSTIS required; no production fallback", "autostart": "disabled"}


def main():
    parser = argparse.ArgumentParser(description="Native Oneiro: one product, one control plane")
    # A platform-injected PORT means the port is proxied, so bind every interface;
    # a plain local run stays loopback-only by default.
    default_host = os.environ.get("ONEIRO_WEB_HOST") or (
        "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT") or "9899"))
    parser.add_argument("--check", action="store_true", help="Report local prerequisites without starting anything")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(diagnostics(), indent=2))
        return 0
    token = os.environ.get("ONEIRO_WEB_TOKEN", "")
    if args.host not in ("127.0.0.1", "localhost", "::1") and len(token) < 24:
        # A proxied port without a configured owner token is still reachable by
        # URL, so generate a one-time access token and print it once. This is a
        # fresh runtime token, not a stored secret: it changes every start.
        token = secrets.token_urlsafe(32)
        print("ONEIRO_WEB_TOKEN is not set: generated a one-time access token for this run.", flush=True)
        print(f"Oneiro access token (changes every start): {token}", flush=True)
    service = Oneiro(GraphMemory())
    stop = threading.Event()
    telegram = None
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        telegram = Telegram(service, os.environ["TELEGRAM_BOT_TOKEN"], int(os.environ["TELEGRAM_CHAT_ID"]))

    def scheduler():
        recovered = False
        while not stop.is_set():
            try:
                if not recovered:
                    service.recover()
                    recovered = True
                service.step()
                service.last_error = ""
            except Busy:
                pass
            except Exception as exc:
                service.last_error = f"{type(exc).__name__}: affected work is paused; inspect prerequisites and retry."
            stop.wait(2 if not service.last_error else 15)

    def phone():
        while not stop.is_set():
            try:
                telegram.poll()
                telegram.flush()
            except Exception:
                service.last_error = "Telegram unavailable; incoming offset advances only after persistence."
            stop.wait(3)

    server = NativeServer((args.host, args.port), service, access_token=token)
    threading.Thread(target=scheduler, daemon=True).start()
    if telegram:
        threading.Thread(target=phone, daemon=True).start()
    print(f"Oneiro HTTP listening on {args.host}:{args.port}; integration state is shown in the workspace.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        service.memory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
