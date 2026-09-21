"""Offline checks for the OpenClaw plugin: the Python seam, manifest, entry.

The live proof (a dev gateway that boots with the plugin and leaves its
lifecycle records in OSTIS) is a run, not a test; these checks keep the seam
honest between runs.
"""

import importlib.util
import json
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "oneiro-life"


class FakeBridge:
    def __init__(self):
        self.calls = []

    def record_organization_event(self, **event):
        self.calls.append(event)


def load_recorder():
    spec = importlib.util.spec_from_file_location("oneiro_life_record",
                                                  PLUGIN_DIR / "record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recorder_writes_one_verified_rule_record():
    recorder = load_recorder()
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
    recorder = load_recorder()

    assert recorder.main(["--kind", "gateway_start", "--payload", "[1,2]"]) == 2
    assert "must be a JSON object" in capsys.readouterr().err


def test_manifest_and_entry_declare_the_service_and_gateway_hooks():
    manifest = json.loads(
        (PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "oneiro-life"
    assert manifest["activation"]["onStartup"] is True
    assert manifest["configSchema"]["properties"]["autostart"]["default"] is False

    entry = (PLUGIN_DIR / "index.js").read_text(encoding="utf-8")
    assert "registerService" in entry
    assert '"gateway_start"' in entry and '"gateway_stop"' in entry
    assert "openclaw/plugin-sdk/plugin-entry" in entry

    package = json.loads((PLUGIN_DIR / "package.json").read_text(encoding="utf-8"))
    assert package["openclaw"]["extensions"] == ["./index.js"]
