"""Build standalone installer payload and distribution package for Oneiro.

Assembles staging payload under installer/payload or target directory:
- Oneiro python package and entry points
- Assets (skills-catalog.json, web static files)
- Pinned runtime configuration
- Deterministic SHA-256 integrity manifest
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer"


def generate_sha256_manifest(folder: Path) -> dict[str, str]:
    """Calculate SHA-256 for all files in folder."""
    manifest = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(folder)).replace("\\", "/")
            raw = p.read_bytes()
            manifest[rel] = hashlib.sha256(raw).hexdigest()
    return manifest


def build_payload(destination: Path | None = None) -> Path:
    """Assemble the payload directory for installer packaging."""
    out = destination or (INSTALLER / "payload")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 1. Copy application python package
    app_dir = out / "app" / "python"
    app_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ROOT / "python" / "oneiro",
        app_dir / "oneiro",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    # 2. Copy launcher scripts
    for launcher in ("start-oneiro.cmd", "start-oneiro.ps1"):
        src = INSTALLER / launcher
        if src.exists():
            shutil.copy2(src, out / launcher)

    # 3. Ship the licence and the attribution notice beside the program.
    # docs/DECISIONS-v1.md 1.6 and docs/MASTER-PLAN.md 1.12 require the payload to
    # carry NOTICE, so a copy of the installed program states where its material came
    # from. A missing file is an error, not a warning: an installer without the
    # attribution would be a silent licence problem.
    for document in ("NOTICE", "LICENSE"):
        src = ROOT / document
        if not src.is_file():
            raise FileNotFoundError(f"{document} is required in the payload but is missing at {src}")
        shutil.copy2(src, out / document)

    # 4. Create launcher batch command for terminal usage
    cmd_file = out / "oneiro.cmd"
    cmd_file.write_text(
        "@echo off\r\n"
        "\"%~dp0python\\python.exe\" -m oneiro %*\r\n",
        encoding="ascii",
    )

    # 5. Generate deterministic manifest
    manifest = generate_sha256_manifest(out)
    manifest_file = out / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    res = build_payload(target)
    print(f"Payload assembled at: {res}")
