"""Offline checks for the OpenClaw plugin: its recorder and its command seam.

The live proof (a dev gateway that boots with the plugin loaded and leaves its
lifecycle records in OSTIS) is a run, not a test; these checks keep the seams
honest between runs.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = PROJECT_ROOT / "plugins" / "oneiro-life"


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


def run_node(code: str) -> str:
    """Run one ESM snippet through node, or skip when node is absent."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the plugin command seam cannot be checked")
    result = subprocess.run(
        [node, "--input-type=module", "-e", code],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


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


def test_record_command_is_an_argv_array_not_a_shell_string():
    code = (
        f"const m = await import('{(PLUGIN_DIR / 'command.js').as_uri()}');"
        "console.log(JSON.stringify(m.buildRecordCommand({"
        "recorderPath: 'rec.py', pythonPath: 'py', sessionId: 's1', ostisPort: 18090"
        "}, 'gateway_start', {port: 19001})));"
    )

    built = json.loads(run_node(code))

    assert built["command"] == "py"
    assert built["args"] == [
        "rec.py",
        "--kind", "gateway_start",
        "--session", "s1",
        "--port", "18090",
        "--payload", '{"port":19001}',
    ]


def test_record_command_refuses_without_a_recorder_path():
    code = (
        f"const m = await import('{(PLUGIN_DIR / 'command.js').as_uri()}');"
        "try { m.buildRecordCommand({}, 'gateway_start'); console.log('no-throw'); }"
        "catch (error) { console.log('threw: ' + error.message); }"
    )

    assert run_node(code) == "threw: recorderPath is required"


def test_manifest_and_entry_declare_the_service_and_gateway_hooks():
    manifest = json.loads(
        (PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))
    assert manifest["id"] == "oneiro-life"
    assert manifest["activation"]["onStartup"] is True
    properties = manifest["configSchema"]["properties"]
    assert properties["pythonPath"]["default"] == "python"
    assert properties["ostisPort"]["default"] == 8090

    entry = (PLUGIN_DIR / "index.js").read_text(encoding="utf-8")
    assert "registerService" in entry
    assert '"gateway_start"' in entry and '"gateway_stop"' in entry
    assert "openclaw/plugin-sdk/plugin-entry" in entry
    # Spawning is the acknowledged path now: execFile with an argv array, and
    # no shell string and no second transport anywhere.
    assert 'from "node:child_process"' in entry
    assert "execFile(" in entry
    assert "buildRecordCommand" in entry
    assert "execSync(" not in entry and "exec(" not in entry.replace("execFile(", "")
    assert "fetch(" not in entry

    package = json.loads((PLUGIN_DIR / "package.json").read_text(encoding="utf-8"))
    assert package["openclaw"]["extensions"] == ["./index.js"]
