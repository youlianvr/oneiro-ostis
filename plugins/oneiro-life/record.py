"""Write one lifecycle record into OSTIS through the project bridge.

    python plugins/oneiro-life/record.py --kind gateway_start --payload '{"port": 19001}'

The OpenClaw plugin runs inside the gateway (Node) and the graph is written by
Python; this recorder is the one seam between them. The plugin shells out, the
bridge owns the graph. A failure exits non-zero and never pretends a record was
made.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from bridge import OneiroBridge  # noqa: E402  (import after sys.path is set)


def write_record(bridge, *, kind: str, session: str, role: str, payload: dict) -> None:
    """The only write this script makes: one verified, system-origin record."""
    bridge.record_organization_event(
        session_id=session,
        role=role,
        kind=kind,
        payload=payload,
        origin="rule",
        verified=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record one Oneiro lifecycle event")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--session", default="oneiro-gateway")
    parser.add_argument("--role", default="gateway")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--payload", default="{}")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        print(f"payload is not JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("payload must be a JSON object", file=sys.stderr)
        return 2

    bridge = OneiroBridge(host=args.host, port=args.port)
    bridge.connect()
    try:
        write_record(bridge, kind=args.kind, session=args.session, role=args.role,
                     payload=payload)
    finally:
        bridge.close()
    print(f"recorded {args.kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
