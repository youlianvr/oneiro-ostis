"""Point the host at our MCP server and at the machine's own tools.

    python scripts/host-wire.py                     # show what would change
    python scripts/host-wire.py --apply             # merge into ~/cow/mcp.json
    python scripts/host-wire.py --include playwright,sqlite-mcp --apply

The host reads ``<workspace>/mcp.json`` with an ``mcpServers`` map, the same shape
every other tool on this machine uses. This script adds (or refreshes) our own entry
and copies the chosen servers out of the workspace's ``.mcp.json`` verbatim: their
commands, arguments and environment are their own, and mistranslating them would be
the easiest way to break something that already works.

Anything already in the target file that we are not touching is left alone.

The default set is deliberately local: tools that keep working when the network is
gone. Servers that can send things outward (Telegram, mail) are not included until
the approval rule is wired into them, because on this host an outgoing message must
not happen without the owner's press.
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
SOURCE_CONFIG = Path(os.environ.get(
    "ONEIRO_MCP_SOURCE",
    Path.home() / ".openclaw" / "workspace" / ".mcp.json",
))
NAME = "oneiro"

# Local first: a tool that only reads and writes this machine, and that works
# without the network. Outward-capable servers come later, once every send has to
# pass the approval channel.
DEFAULT_INCLUDE = (
    "memora",          # the owner's own memory store, with hybrid search built in
    "knowledge-rag",   # the workspace knowledge base
    "searchmcp",       # web search
    "playwright",      # a browser that acts, not just fetches
)
# Left out on purpose, each after a real attempt (see docs/HOST.md): chroma
# spends 200+ MB of downloads to duplicate memora's search, and the rest need
# credentials or a display we have not set up for this host.


def read_source() -> dict:
    if not SOURCE_CONFIG.is_file():
        raise SystemExit(f"no server list to copy from: {SOURCE_CONFIG}")
    data = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    return data.get("mcpServers") or data.get("servers") or data


def resolve_command(cfg: dict) -> tuple[dict, str]:
    """A bare command name is a guess about PATH; an absolute path is not.

    The host starts in whatever environment it was launched from, and on this
    machine every ``npx`` server died with ``WinError 2`` for exactly that reason.
    """
    entry = json.loads(json.dumps(cfg))
    command = str(entry.get("command") or "")
    if not command or os.path.isabs(command) or "/" in command or "\\" in command:
        return entry, "already absolute"
    found = shutil.which(command)
    if not found and os.name == "nt":
        found = shutil.which(command + ".cmd") or shutil.which(command + ".exe")
    if not found:
        return entry, f"NOT FOUND on PATH ({command})"
    entry["command"] = found
    env = dict(entry.get("env") or {})
    path = env.get("PATH") or env.get("Path") or os.environ.get("PATH", "")
    env["PATH"] = os.pathsep.join(
        [os.path.dirname(found), path] if path else [os.path.dirname(found)]
    )
    entry["env"] = env
    return entry, f"resolved to {found}"


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
    parser.add_argument("--include", default=",".join(DEFAULT_INCLUDE),
                        help="comma separated server names to copy; 'none' for ours only")
    args = parser.parse_args()

    workspace = Path(args.workspace)
    path = workspace / "mcp.json"
    if not SERVER.is_file():
        raise SystemExit(f"our server is missing: {SERVER}")

    wanted = [] if args.include.strip().lower() == "none" else [
        name.strip() for name in args.include.split(",") if name.strip()
    ]

    data = load(path)
    before = json.dumps(data.get("mcpServers", {}), sort_keys=True)
    data["mcpServers"][NAME] = our_entry()

    copied, missing, notes = [], [], []
    if wanted:
        source = read_source()
        for name in wanted:
            if name in source:
                entry, note = resolve_command(source[name])
                data["mcpServers"][name] = entry
                copied.append(name)
                notes.append(f"  {name}: {note}")
            else:
                missing.append(name)

    # Drop entries we put there earlier and no longer choose. Only names that also
    # exist in the source list are ours to remove; anything else in the file was
    # written by a person or another tool and stays.
    pruned = []
    if wanted:
        source = read_source()
        for name in list(data["mcpServers"]):
            if name != NAME and name in source and name not in wanted:
                data["mcpServers"].pop(name)
                pruned.append(name)

    after = json.dumps(data.get("mcpServers", {}), sort_keys=True)
    print(f"config: {path}")
    if pruned:
        print(f"removed (no longer chosen): {pruned}")
    print(f"copied from {SOURCE_CONFIG.name}: {copied or 'nothing'}")
    for line in notes:
        print(line)
    if missing:
        print(f"not in the source list: {missing}")
    print(f"servers in the target: {sorted(data['mcpServers'])}")
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
