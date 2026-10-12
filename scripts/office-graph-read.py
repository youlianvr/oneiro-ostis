"""Read one stream back through the owned graph worker.

This is the independent half of W1's evidence: the office job reports its own
records, and this reads them out of the graph again, so a job cannot claim work
the graph does not hold. It also makes the negative check possible — `--stream
product` shows the owner's own stream as untouched by the demo.

    python scripts/office-graph-read.py --stream demo
    python scripts/office-graph-read.py --stream product --limit 5

Run it with the same `ONEIRO_DATA_DIR` the job used.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from oneiro import config                       # noqa: E402
from oneiro.graph_worker import GraphWorker     # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="office-graph-read")
    parser.add_argument("--stream", default="demo")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    url = f"ws://{config.value('graph.host')}:{config.value('graph.port')}/ws_json"
    worker = GraphWorker(url, args.stream, config.data_root() / f"{args.stream}-read.lock")

    async def run() -> int:
        try:
            page = await worker.call("page", limit=args.limit)
            print(f"stream {args.stream}: {json.dumps(page, ensure_ascii=False, default=str)[:1200]}")
            return 0
        except Exception as exc:                # noqa: BLE001 - the diagnosis is the output
            print(f"stream {args.stream}: read FAILED {type(exc).__name__}: {exc}")
            return 1
        finally:
            await worker.close()

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
