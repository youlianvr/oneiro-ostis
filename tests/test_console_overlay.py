"""The console layer lives in this repository: prove it stays the product's.

Nothing here unpacks CowAgent into its full size. A small stand-in tree is built
in `tmp_path` and the overlay module is pointed at it, because what is being
tested is the contract: a pristine console gets the product's files, an
already-applied one is left alone, and an edit that came from somewhere else is
refused instead of silently overwritten. The real tree is exercised by
`scripts/install.py` from a clean checkout.

One test does read the shipped archive: `console/vendor/cowagent-2.1.9.zip` is
unpacked and checked against the manifest's recorded upstream hashes, so the
archive and the overlay cannot drift apart unnoticed.
"""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
OVERLAY_PATH = PROJECT / "console" / "overlay.py"

UPSTREAM = {
    "channel/web/page.html": "upstream page",
    "channel/web/keep.js": "upstream untouched file",
    "common/i18n.py": "upstream i18n",
}


@pytest.fixture()
def overlay(monkeypatch, tmp_path):
    """The module with its store moved into tmp_path: nothing touches console/."""
    spec = importlib.util.spec_from_file_location("console_overlay", OVERLAY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    monkeypatch.setattr(module, "OVERLAY", tmp_path / "overlay")
    monkeypatch.setattr(module, "MANIFEST", tmp_path / "manifest.json")
    return module


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _pair(tmp_path) -> tuple[Path, Path]:
    """A pristine console and the product's version of it, side by side."""
    pristine = _tree(tmp_path / "pristine", UPSTREAM)
    product = _tree(tmp_path / "vendor", dict(
        UPSTREAM,
        **{"channel/web/page.html": "Oneiro page", "channel/web/new.js": "oneiro new file"},
    ))
    return pristine, product


def test_build_records_only_what_the_product_changed(overlay, tmp_path):
    pristine, product = _pair(tmp_path)
    assert overlay.build(pristine, product) == 0

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    kinds = {entry["path"]: entry["kind"] for entry in manifest["files"]}
    assert kinds == {"channel/web/page.html": "changed", "channel/web/new.js": "new"}
    recorded = (tmp_path / "overlay" / "channel" / "web" / "page.html").read_text(encoding="utf-8")
    assert recorded == "Oneiro page"


def test_apply_puts_the_product_onto_a_pristine_console(overlay, tmp_path):
    pristine, product = _pair(tmp_path)
    overlay.build(pristine, product)
    fresh = _tree(tmp_path / "fresh", UPSTREAM)          # straight from the archive

    assert overlay.apply(fresh, dry_run=False) == 0

    assert (fresh / "channel/web/page.html").read_text(encoding="utf-8") == "Oneiro page"
    assert (fresh / "channel/web/new.js").read_text(encoding="utf-8") == "oneiro new file"
    assert (fresh / "channel/web/keep.js").read_text(encoding="utf-8") == "upstream untouched file"


def test_apply_twice_leaves_the_second_run_nothing_to_do(overlay, tmp_path):
    pristine, product = _pair(tmp_path)
    overlay.build(pristine, product)
    fresh = _tree(tmp_path / "fresh", UPSTREAM)
    overlay.apply(fresh, dry_run=False)
    after_first = (fresh / "channel/web/page.html").read_bytes()

    assert overlay.apply(fresh, dry_run=False) == 0
    assert (fresh / "channel/web/page.html").read_bytes() == after_first


def test_dry_run_reports_without_writing(overlay, tmp_path):
    pristine, product = _pair(tmp_path)
    overlay.build(pristine, product)
    fresh = _tree(tmp_path / "fresh", UPSTREAM)

    assert overlay.apply(fresh, dry_run=True) == 0
    assert (fresh / "channel/web/page.html").read_text(encoding="utf-8") == "upstream page"
    assert not (fresh / "channel/web/new.js").exists()


def test_a_foreign_edit_is_refused_and_left_alone(overlay, tmp_path):
    pristine, product = _pair(tmp_path)
    overlay.build(pristine, product)
    fresh = _tree(tmp_path / "fresh", UPSTREAM)
    (fresh / "channel/web/page.html").write_text("someone else was here", encoding="utf-8")

    assert overlay.apply(fresh, dry_run=False) == 1
    assert (fresh / "channel/web/page.html").read_text(encoding="utf-8") == "someone else was here"


def test_a_recorded_file_that_vanished_is_refused(overlay, tmp_path):
    pristine, product = _pair(tmp_path)
    overlay.build(pristine, product)
    fresh = _tree(tmp_path / "fresh", UPSTREAM)
    (fresh / "channel/web/page.html").unlink()

    assert overlay.apply(fresh, dry_run=False) == 1
    assert not (fresh / "channel/web/page.html").exists()


def test_the_shipped_archive_is_the_release_the_manifest_pins(tmp_path):
    """The archive in console/vendor/ and the manifest must agree, forever.

    This is the invariant a fresh clone depends on: unpack the shipped archive
    and every recorded upstream file must hash to exactly what the manifest
    says, with nothing missing.
    """
    spec = importlib.util.spec_from_file_location("console_installer",
                                                  PROJECT / "scripts" / "install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)

    archive = PROJECT / "console" / "vendor" / f"cowagent-{installer.RELEASE}.zip"
    assert archive.is_file(), f"архив не найден: {archive}"
    assert zipfile.is_zipfile(archive)

    into = tmp_path / "console"
    installer.unpack(archive, into)
    installer.verify_release(into)       # SystemExit on any recorded-file mismatch

    manifest = json.loads((PROJECT / "console" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"], "манифест пуст"
    for entry in manifest["files"]:
        if entry["kind"] == "changed":
            assert (into / entry["path"]).is_file(), entry["path"]
