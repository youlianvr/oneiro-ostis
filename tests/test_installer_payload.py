"""Tests for installer payload packaging, manifest integrity, and Inno Setup configuration."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_installer_payload import build_payload, generate_sha256_manifest


def test_build_payload_creates_manifest_and_required_files(tmp_path):
    target = tmp_path / "staging_payload"
    res = build_payload(target)
    assert res.exists()
    assert (res / "manifest.json").exists()
    assert (res / "app" / "python" / "oneiro").exists()
    assert (res / "app" / "python" / "oneiro" / "assets" / "skills-catalog.json").exists()
    assert (res / "app" / "python" / "oneiro" / "static" / "page.html").exists()
    assert (res / "oneiro.cmd").exists()

    manifest = json.loads((res / "manifest.json").read_text(encoding="utf-8"))
    assert "oneiro.cmd" in manifest
    assert "app/python/oneiro/__init__.py" in manifest
    assert len(manifest) > 20


def test_the_payload_carries_the_licence_and_the_notice(tmp_path):
    """docs/DECISIONS-v1.md 1.6: the installer payload carries NOTICE.

    An installed copy that names nobody is a licence problem that no test would
    otherwise catch, so the payload, its manifest and both builders are pinned
    here: a dropped copy fails instead of shipping quietly.
    """
    project = Path(__file__).resolve().parents[1]
    res = build_payload(tmp_path / "payload")

    for document in ("NOTICE", "LICENSE"):
        assert (project / document).is_file(), f"{document} is missing from the project root"
        assert (res / document).is_file(), f"{document} did not reach the payload"

    manifest = json.loads((res / "manifest.json").read_text(encoding="utf-8"))
    for document in ("NOTICE", "LICENSE"):
        assert document in manifest, f"{document} is not in the payload manifest"
        on_disk = res / document
        assert manifest[document] == __import__("hashlib").sha256(on_disk.read_bytes()).hexdigest()

    # The real payload builder (powershell) must copy the same two files, and the
    # Inno Setup script must ship the payload root, or the attribution never
    # reaches the installed program.
    ps1 = (project / "installer" / "build-payload.ps1").read_text(encoding="utf-8")
    assert "NOTICE" in ps1, "build-payload.ps1 does not copy NOTICE into the payload"
    iss = (project / "installer" / "oneiro.iss").read_text(encoding="utf-8")
    assert 'Source: "payload\\*"' in iss, "oneiro.iss does not ship the payload root"

    # The notice must actually name the sources the borrowing audit recorded.
    notice = (project / "NOTICE").read_text(encoding="utf-8")
    for source in ("CowAgent 2.1.9", "ostis-example-app", "Design-systems library",
                   "OpenCode", "Hermes", "ims.ostis.kb"):
        assert source in notice, f"NOTICE does not name {source}"


def test_inno_setup_script_respects_data_safety_rules():
    iss_file = Path(__file__).resolve().parents[1] / "installer" / "oneiro.iss"
    content = iss_file.read_text(encoding="utf-8")

    # Privileges must be lowest (per-user, no root/admin required)
    assert "PrivilegesRequired=lowest" in content
    # Application directory in localappdata
    assert "{localappdata}\\Programs\\Oneiro" in content
    # Docker Desktop prerequisite check
    assert "docker info" in content
    # Container stop on uninstall without deleting database volume
    assert "docker stop" in content
    assert "oneiro-graph-kb-v1" in content
    # No deletion of .oneiro user data
    assert ".oneiro" in content
    assert "leaves the memory in place" in content.lower()
