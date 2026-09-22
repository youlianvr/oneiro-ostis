"""Point the host at our MCP server, in the host's own config format.

    python scripts/host-wire.py            # show what would change
    python scripts/host-wire.py --apply    # merge our entry into ~/cow/mcp.json

The host reads ``<workspace>/mcp.json`` with an ``mcpServers`` map, the same shape
every other tool on this machine uses. This script only adds (or refreshes) our one
entry and prints the file, so a person can see exactly what the host will run.
Anything already in that file is left alone.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SERVER = HERE / "host" / "ostis_mcp.py"
DEFAULT_WORKSPACE = Path(os.environ.get("COW_WORKSPACE", Path.home() / "cow"))
NAME = "oneiro"


def our_entry() -> dict:
    return {
        "command": sys.executable,
        "args": [str(SERVER)],
        "env": {
            "ONEIRO_HOST": os.environ.get("ONEIRO_HOST", "localhost"),
            "ONEIRO_PORT": os.environ.get("ONEIRO_PORT", "8090"),
        },
    }


def load(path: Path) -> dict:
    if not path.is_file():
        return {"mcpServers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON ({exc}); fix it before wiring")
    data.setdefault("mcpServers", {})
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    args = parser.parse_args()

    workspace = Path(args.workspace)
    path = workspace / "mcp.json"
    if not SERVER.is_file():
        raise SystemExit(f"our server is missing: {SERVER}")

    data = load(path)
    before = json.dumps(data.get("mcpServers", {}).get(NAME))
    data["mcpServers"][NAME] = our_entry()
    after = json.dumps(data["mcpServers"][NAME])
    print(f"config: {path}")
    print(f"servers in it: {sorted(data['mcpServers'])}")
    print("changed" if before != after else "already current")

    if not args.apply:
        print(json.dumps({NAME: our_entry()}, indent=2))
        print("\nrun again with --apply to write it")
        return 0

    workspace.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = path.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(path, backup)
        print(f"backup: {backup}")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written: {path}")
    print(json.dumps(data["mcpServers"][NAME], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
