"""Talk to our MCP server the way the host does, and print what it answers.

    python scripts/mcp-smoke.py            # list tools, read the tail, record one note

This is the evidence that the host's side of the integration really works: a real
MCP client over stdio, a real graph behind it, no mocks.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent.parent
SERVER = HERE / "host" / "ostis_mcp.py"


async def main() -> int:
    print("server:", SERVER)
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])

            tail = await session.call_tool("memory_tail", {"limit": 3})
            print("\n--- memory_tail ---")
            print(_text(tail)[:800])

            search = await session.call_tool("memory_search", {"query": "manager repair candidate"})
            print("\n--- memory_search ---")
            print(_text(search)[:800])

            written = await session.call_tool(
                "memory_record",
                {"text": "the host asked the graph for its tail and got one",
                 "kind": "smoke", "subject": "integration"},
            )
            print("\n--- memory_record ---")
            print(_text(written)[:300])

            again = await session.call_tool("memory_search", {"query": "asked the graph for its tail"})
            print("\n--- memory_search after the write ---")
            print(_text(again)[:500])
    return 0


def _text(result) -> str:
    parts = []
    for item in result.content or []:
        parts.append(getattr(item, "text", str(item)))
    return "\n".join(parts)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
