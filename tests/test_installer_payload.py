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
