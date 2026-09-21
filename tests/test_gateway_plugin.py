"""Offline checks for the OpenClaw plugin: its two write seams and its manifest.

The live proof (a dev gateway that boots with the plugin loaded and leaves its
lifecycle records in OSTIS) is a run, not a test; these checks keep the seams
honest between runs.
"""

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "oneiro-life"
DASHBOARD_SERVER = PROJECT_ROOT / "dashboard" / "server.py"


class FakeBridge:
    def __init__(self):
        self.calls = []

    def record_organization_event(self, **event):
        self.calls.append(event)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_dashboard_server():
    return load_module("oneiro_dashboard_server_for_test", DASHBOARD_SERVER)


def test_recorder_writes_one_verified_rule_record():
    recorder = load_module("oneiro_life_record", PLUGIN_DIR / "record.py")
    bridge = FakeBridge()

    recorder.write_record(bridge, kind="gateway_start", session="oneiro-gateway",
                          role="gateway", payload={"port": 19001})

    assert bridge.calls == [{
        "session_id": "oneiro-gateway",
        "role": "gateway",
        "kind": "gateway_start",
        "payload": {"port": 19001},
        "origin": "rule",
        "verified": True,
    }]


def test_recorder_rejects_a_payload_that_is_not_an_object(capsys):
    recorder = load_module("oneiro_life_record_again", PLUGIN_DIR / "record.py")

    assert recorder.main(["--kind", "gateway_start", "--payload", "[1,2]"]) == 2
    assert "must be a JSON object" in capsys.readouterr().err


def test_dashboard_endpoint_writes_one_verified_record():
    server = load_dashboard_server()
    server._bridge_conn = FakeBridge()
    client = server.app.test_client()

    response = client.post("/api/gateway-record", json={
        "kind": "gateway_start", "session": "oneiro-gateway",
        "payload": {"port": 19001},
    })

    assert response.status_code == 200
    assert server._bridge_conn.calls == [{
        "session_id": "oneiro-gateway",
        "role": "gateway",
        "kind": "gateway_start",
        "payload": {"port": 19001},
        "origin": "rule",
        "verified": True,
    }]


def test_dashboard_endpoint_refuses_unknown_kinds_and_big_payloads():
    server = load_dashboard_server()
    server._bridge_conn = FakeBridge()
    client = server.app.test_client()

    refused_kind = client.post("/api/gateway-record", json={"kind": "not_a_kind"})
    refused_payload = client.post("/api/gateway-record", json={
        "kind": "gateway_start", "payload": {"blob": "x" * 5_000},
    })

    assert refused_kind.status_code == 400
    assert refused_payload.status_code == 400
    assert server._bridge_conn.calls == []


def test_manifest_and_entry_declare_the_service_and_gateway_hooks():
    manifest = json.loads(
        (PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "oneiro-life"
    assert manifest["activation"]["onStartup"] is True
    assert (manifest["configSchema"]["properties"]["dashboardUrl"]["default"]
            == "http://127.0.0.1:8130")

    entry = (PLUGIN_DIR / "index.js").read_text(encoding="utf-8")
    assert "registerService" in entry
    assert '"gateway_start"' in entry and '"gateway_stop"' in entry
    assert "openclaw/plugin-sdk/plugin-entry" in entry
    # The host's install scan blocks plugins that spawn processes; the plugin
    # must stay installable without an acknowledgment.
    assert "child_process" not in entry

    package = json.loads((PLUGIN_DIR / "package.json").read_text(encoding="utf-8"))
    assert package["openclaw"]["extensions"] == ["./index.js"]
