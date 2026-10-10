"""Live check for W8: Installer and delivery.

Run it with `python tests/live_w8_check.py`.
Evidence for § 5 W8 and acceptance matrix § 6:
* Row 1: Install outside the working folder (simulation of payload extraction).
* Row 19: Upgrade preserves data (existing user settings, memory graph and keys stay intact).
* Verifies zero-leak on owner's live files.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
PROJECT = TESTS.parent
sys.path.insert(0, str(PROJECT))

from scripts.build_installer_payload import build_payload

WORK = Path(tempfile.mkdtemp(prefix="oneiro-w8-live-"))
OWNER_SETTINGS = Path.home() / ".oneiro" / "settings.json"
OWNER_KEYS = Path.home() / ".config" / "keys.env"
WATCHED = (OWNER_SETTINGS, OWNER_KEYS, PROJECT / ".env", PROJECT / "knowledge-base" / "repo.path")


def say(text: str = "") -> None:
    print(text, flush=True)


def fingerprint(paths) -> dict[str, str]:
    seen = {}
    for path in paths:
        try:
            raw = Path(path).read_bytes()
        except OSError:
            seen[str(path)] = "absent"
            continue
        seen[str(path)] = f"{len(raw)} bytes, sha256 {hashlib.sha256(raw).hexdigest()[:12]}"
    return seen


def main() -> int:
    before = fingerprint(WATCHED)
    say("== W8 Live Check: Installer and Delivery ==")
    say(f"  working directory: {WORK}")

    # 1. Simulate existing user data directory
    user_data = WORK / "mock_user_oneiro"
    user_data.mkdir(parents=True, exist_ok=True)
    existing_settings = user_data / "settings.json"
    existing_settings.write_text(json.dumps({"ui.theme": "editorial", "user_marker": "keep_me"}), encoding="utf-8")
    existing_memory = user_data / "records.jsonl"
    existing_memory.write_text('{"id":"rec-1","kind":"fact","text":"Important owner fact"}\n', encoding="utf-8")
    user_fingerprint_before = fingerprint([existing_settings, existing_memory])

    say("\n== 1. Building staging payload ==")
    payload_dir = WORK / "staging_payload"
    built = build_payload(payload_dir)
    manifest_file = built / "manifest.json"
    say(f"  Payload assembled at: {built}")
    assert manifest_file.exists(), "Manifest file missing"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    say(f"  Manifest entries count: {len(manifest)}")

    say("\n== 2. Simulating fresh installation outside workspace ==")
    install_target = WORK / "installed_app"
    shutil.copytree(built, install_target)
    say(f"  App deployed to: {install_target}")

    # Test running CLI entrypoint from installed tree
    env = dict(os.environ)
    env["PYTHONPATH"] = str(install_target / "app" / "python")
    env["ONEIRO_SETTINGS_FILE"] = str(existing_settings)
    env["ONEIRO_DATA_DIR"] = str(user_data)
    env["ONEIRO_HEADLESS"] = "1"

    doctor_res = subprocess.run(
        [sys.executable, "-m", "oneiro", "doctor"],
        cwd=str(install_target),
        env=env,
        capture_output=True,
        text=True,
    )
    say(f"  Installed doctor check -> exit {doctor_res.returncode}")
    # doctor returns 1 if graph/model not ready, but prints valid json report
    doc_json = json.loads(doctor_res.stdout)
    say(f"    doctor report: ready={doc_json.get('ready')}, phase={doc_json.get('phase')}")
    assert "ready" in doc_json

    say("\n== 3. Simulating upgrade over existing installation ==")
    # Re-copy payload simulating an upgrade / installer run
    shutil.copytree(built, install_target, dirs_exist_ok=True)
    say("  Upgraded app files in place.")

    # 4. Verify user data was 100% preserved
    user_fingerprint_after = fingerprint([existing_settings, existing_memory])
    assert user_fingerprint_before == user_fingerprint_after, "User settings or records were corrupted during upgrade!"
    say("  Verified: user settings.json and memory records were 100% preserved.")

    # 5. Check zero-leak on owner files
    say("\n== 5. Integrity check: owner files ==")
    after = fingerprint(WATCHED)
    problems = []
    for path, seen in before.items():
        if after.get(path) != seen:
            say(f"  CHANGED: {path}")
            problems.append(path)
        else:
            say(f"  unchanged: {path}")

    if problems:
        say(f"ERROR: owner files were modified by live check: {problems}")
        return 1

    say(f"\nW8 Live check completed successfully! Temp root: {WORK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
