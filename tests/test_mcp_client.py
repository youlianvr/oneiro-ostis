"""The MCP layer: what it reads, what it sends, and how it fails.

Every test here runs a real child process speaking the real protocol; the
server is ours only because a real one would need the network and a key.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "python"))

import mcp_client  # noqa: E402

FAKE_SERVER = r'''
import json, sys

TOOLS = [
    {"name": "echo", "description": "Repeat the text back.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "boom", "description": "Always fails.",
     "inputSchema": {"type": "object", "properties": {}}},
]

def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"],
              "result": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "serverInfo": {"name": "fake", "version": "1"}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") == "boom":
            send({"jsonrpc": "2.0", "id": request["id"],
                  "result": {"content": [{"type": "text", "text": "exploded"}],
                             "isError": True}})
        else:
            text = (params.get("arguments") or {}).get("text", "")
            send({"jsonrpc": "2.0", "id": request["id"],
                  "result": {"content": [{"type": "text", "text": "echo: " + text}]}})
'''

DEAD_SERVER = r'''
import sys
sys.stderr.write("no credentials for the fake service\n")
raise SystemExit(3)
'''


@pytest.fixture()
def config(tmp_path: Path) -> Path:
    """A mcp.json shaped exactly like the workspace one."""
    (tmp_path / "fake_server.py").write_text(FAKE_SERVER, encoding="utf-8")
    (tmp_path / "dead_server.py").write_text(DEAD_SERVER, encoding="utf-8")
    path = tmp_path / ".mcp.json"
    path.write_text(json.dumps({
        "mcpServers": {
            "fake": {"command": sys.executable,
                     "args": [str(tmp_path / "fake_server.py")],
                     "env": {"FAKE_TOKEN": "yes"}},
            "dead": {"command": sys.executable,
                     "args": [str(tmp_path / "dead_server.py")]},
            "remote": {"type": "http", "url": "http://127.0.0.1:9/mcp"},
        }
    }), encoding="utf-8")
    return path


def test_reads_the_same_config_openclaw_reads(config: Path):
    servers = mcp_client.load_servers(config)
    assert set(servers) == {"fake", "dead"}         # the http entry is not ours
    assert servers["fake"].env == {"FAKE_TOKEN": "yes"}
    assert servers["fake"].argv()[1].endswith("fake_server.py")


def test_tool_keys_round_trip():
    key = mcp_client.tool_key("telegram-mcp-bot", "send_message")
    assert key == "mcp__telegram-mcp-bot__send_message"
    assert mcp_client.split_tool_key(key) == ("telegram-mcp-bot", "send_message")
    with pytest.raises(mcp_client.McpError):
        mcp_client.split_tool_key("read_file")


def test_a_session_initializes_lists_and_calls(config: Path):
    hub = mcp_client.McpHub(mcp_client.load_servers(config), ("fake",))
    schemas = hub.tools()
    names = {schema["function"]["name"] for schema in schemas}
    assert names == {"mcp__fake__echo", "mcp__fake__boom"}

    assert hub.call("mcp__fake__echo", {"text": "hi"}) == "echo: hi"
    failed = hub.call("mcp__fake__boom", {})
    assert "exploded" in failed and failed.startswith("[tool reported an error]")
    assert hub.evidence()["calls"] == 2
    hub.close()


def test_a_dead_server_is_a_named_failure_not_a_dead_episode(config: Path):
    hub = mcp_client.McpHub(mcp_client.load_servers(config), ("fake", "dead"),
                            request_timeout=20.0)
    names = {schema["function"]["name"] for schema in hub.tools()}
    assert "mcp__fake__echo" in names           # the living shelf still opens
    evidence = hub.evidence()
    assert evidence["servers_opened"] == ["fake"]
    assert evidence["failures"] and evidence["failures"][0]["server"] == "dead"
    assert "credentials" in evidence["failures"][0]["error"]
    hub.close()


def test_a_server_that_is_not_open_is_refused_by_name(config: Path):
    hub = mcp_client.McpHub(mcp_client.load_servers(config), ("fake",))
    answer = hub.call("mcp__telegram-mcp-bot__send_message", {"text": "x"})
    assert answer.startswith("[refused: server telegram-mcp-bot is not part of this run")
    hub.close()


def test_a_missing_server_is_reported_by_name(config: Path):
    hub = mcp_client.McpHub(mcp_client.load_servers(config), ("fake", "nowhere"))
    assert hub.evidence()["servers_missing_from_config"] == ["nowhere"]
    assert hub.names == ("fake",)


def test_observation_is_bounded():
    assert mcp_client._clip("x" * 100, 10).endswith("[90 characters truncated]")
    assert mcp_client._clip("short", 10) == "short"


def test_content_shapes_are_named_not_dropped():
    result = {"content": [{"type": "text", "text": "a"},
                          {"type": "image", "mimeType": "image/png"},
                          {"type": "resource", "resource": {"uri": "file:///x"}}]}
    assert mcp_client._content_to_text(result) == "a\n[image image/png]\nfile:///x"
    assert mcp_client._content_to_text({}) == "[no content]"


def test_config_missing_is_a_clear_error(tmp_path: Path):
    with pytest.raises(mcp_client.McpError):
        mcp_client.load_servers(tmp_path / "nope.json")
