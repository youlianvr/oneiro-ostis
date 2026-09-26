"""The installer's offline steps: unpack, verify, seed a config, name failures.

`scripts/install.py` is the one-click door from a fresh clone to a working
product, and it was walked end to end on a clean checkout. These tests pin the
pieces a change could quietly break: the archive loses its top directory, an
archive that is not the recorded release is named as such instead of surfacing
as a dozen "someone edited our files" refusals, and the console config is
seeded once and never overwritten with one machine's defaults.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
INSTALL_PATH = PROJECT / "scripts" / "install.py"


@pytest.fixture()
def install():
    """The installer module, loaded by path; HERE stays the real project."""
    spec = importlib.util.spec_from_file_location("oneiro_installer", INSTALL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unpack_drops_the_archive_top_directory(install, tmp_path):
    archive = tmp_path / "cowagent.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("zhayujie-CowAgent-be1782c/app.py", "print('console')")
        bundle.writestr("zhayujie-CowAgent-be1782c/channel/web/page.html", "page")
    target = tmp_path / "console"

    install.unpack(archive, target)

    assert (target / "app.py").is_file()
    assert (target / "channel" / "web" / "page.html").is_file()
    assert not (target / "zhayujie-CowAgent-be1782c").exists()


def test_unpack_refuses_an_archive_without_a_single_root(install, tmp_path):
    archive = tmp_path / "flat.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("app.py", "print('no root directory')")
    with pytest.raises(SystemExit):
        install.unpack(archive, tmp_path / "console")


def test_seed_config_takes_the_template_and_turns_on_the_web_channel(install, monkeypatch, tmp_path):
    monkeypatch.setattr(install, "DATA_DIR", tmp_path / "instance")
    into = tmp_path / "console"
    into.mkdir()
    (into / "config-template.json").write_text(
        json.dumps({"channel_type": "cli", "custom": 1}), encoding="utf-8")

    install.seed_config(into)

    data = json.loads((tmp_path / "instance" / "config.json").read_text(encoding="utf-8"))
    assert data["channel_type"] == "web"
    assert data["cow_lang"] == "ru"
    assert data["web_host"] == "127.0.0.1"
    assert data["web_port"] == 9899
    assert data["custom"] == 1


def test_seed_config_never_overwrites_an_existing_conversation(install, monkeypatch, tmp_path):
    monkeypatch.setattr(install, "DATA_DIR", tmp_path / "instance")
    config = tmp_path / "instance" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"channel_type": "telegram", "custom": 2}), encoding="utf-8")
    into = tmp_path / "console"
    into.mkdir()
    (into / "config-template.json").write_text(json.dumps({"channel_type": "cli"}), encoding="utf-8")

    install.seed_config(into)

    assert json.loads(config.read_text(encoding="utf-8")) == {"channel_type": "telegram", "custom": 2}


def test_verify_release_names_the_wrong_archive(install, monkeypatch, tmp_path):
    home = tmp_path / "project"
    (home / "console").mkdir(parents=True)
    (home / "console" / "manifest.json").write_text(json.dumps({
        "upstream": {"name": "cowagent", "release": "2.1.9"},
        "files": [{"path": "a.py", "kind": "changed",
                   "pristine_sha256": "00", "product_sha256": "11"}],
    }), encoding="utf-8")
    monkeypatch.setattr(install, "HERE", home)
    tree = tmp_path / "console"
    tree.mkdir()
    (tree / "a.py").write_text("who is this?", encoding="utf-8")

    with pytest.raises(SystemExit) as failure:
        install.verify_release(tree)

    message = str(failure.value)
    assert "a.py" in message and "2.1.9" in message


def test_verify_release_accepts_the_recording_tree(install, monkeypatch, tmp_path):
    home = tmp_path / "project"
    (home / "console").mkdir(parents=True)
    good = tmp_path / "console"
    good.mkdir()
    (good / "a.py").write_text("as recorded", encoding="utf-8")
    digest = hashlib.sha256(b"as recorded").hexdigest()
    (home / "console" / "manifest.json").write_text(json.dumps({
        "upstream": {"name": "cowagent", "release": "2.1.9"},
        "files": [{"path": "a.py", "kind": "changed",
                   "pristine_sha256": digest, "product_sha256": "11"}],
    }), encoding="utf-8")
    monkeypatch.setattr(install, "HERE", home)

    install.verify_release(good)         # no exception


def test_the_repository_carries_the_archive_before_the_network(install):
    """A clone must install with nothing but itself; the archive is shipped."""
    assert install.LOCAL_ARCHIVES[0].is_file()
    assert install.LOCAL_ARCHIVES[0].name == f"cowagent-{install.RELEASE}.zip"
