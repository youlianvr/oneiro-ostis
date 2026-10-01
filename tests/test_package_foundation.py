"""Foundation contracts; no graph, model or account effects."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oneiro import config
from oneiro.ownership import FileLease, OwnershipError
from oneiro.runtime import Runtime
from oneiro.web import create_app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path / "runtime"))
    # Source-checkout subprocesses do not inherit pytest's sys.path changes.
    # Installed-wheel smoke separately proves no PYTHONPATH is needed.
    monkeypatch.setenv("PYTHONPATH", str(Path(config.__file__).parents[1]))
    for setting in config.SETTINGS:
        if setting.env not in ("ONEIRO_DATA_DIR",):
            monkeypatch.delenv(setting.env, raising=False)
        for alias in setting.aliases:
            monkeypatch.delenv(alias, raising=False)


def test_legacy_import_is_same_settings_owner():
    from config import save, settings
    assert save is config.save
    assert settings is config.settings


def test_settings_cache_is_scoped_to_path(tmp_path, monkeypatch):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text('{"graph.port": 8001}', encoding="utf-8")
    second.write_text('{"graph.port": 8002}', encoding="utf-8")
    import os
    stamp = first.stat().st_mtime_ns
    os.utime(second, ns=(stamp, stamp))
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(first))
    assert config.value("graph.port") == 8001
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(second))
    assert config.value("graph.port") == 8002


def test_corrupt_settings_are_preserved_on_write(tmp_path):
    target = config.settings_path()
    target.write_text('{"secret": "do-not-echo",', encoding="utf-8")
    with pytest.raises(ValueError, match="preserved"):
        config.save({"graph.port": 8001})
    assert "do-not-echo" in target.read_text()
    assert "do-not-echo" not in json.dumps(config.describe())


def test_overrides_unknown_data_and_history_survive(tmp_path):
    target = config.settings_path()
    original = '{"future.setting": "keep", "graph.port": 8090}'
    target.write_text(original, encoding="utf-8")
    config.save({"graph.port": 8001})
    assert json.loads(target.read_text())["future.setting"] == "keep"
    backups = list((tmp_path / "settings-history").glob("*.json"))
    assert len(backups) == 1 and backups[0].read_text() == original


@pytest.mark.parametrize("patch", [{"graph.port": 0}, {"web.port": 65536},
    {"web.host": "0.0.0.0"}, {"llm.base_url": "http://user:key@localhost/v1"},
    {"llm.base_url": "https://localhost:bad"}, {"llm.api_key": {"nested": "secret"}}])
def test_invalid_settings_do_not_write(patch):
    with pytest.raises(ValueError):
        config.save(patch)
    assert not config.settings_path().exists()


def test_threaded_writes_do_not_lose_updates():
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(config.save, ({"graph.port": 8001}, {"world.seed": "kept"})))
    assert config.value("graph.port") == 8001
    assert config.value("world.seed") == "kept"


def test_competing_process_lease_and_crash_recovery(tmp_path):
    lease = FileLease(tmp_path / "runtime.lock")
    lease.acquire()
    code = "from pathlib import Path; from oneiro.ownership import FileLease; FileLease(Path(__import__('sys').argv[1])).acquire()"
    result = subprocess.run([sys.executable, "-c", code, str(lease.path)], capture_output=True, timeout=10)
    assert result.returncode != 0
    lease.release()
    # Child exits without explicit release: OS releases kernel lock.
    result = subprocess.run([sys.executable, "-c", code, str(lease.path)], capture_output=True, timeout=10)
    assert result.returncode == 0
    lease.acquire()
    lease.release()
    assert lease.path.exists()


def test_two_runtime_owners_cannot_start():
    async def check():
        first, second = Runtime(), Runtime()
        await first.start()
        try:
            with pytest.raises(OwnershipError):
                await second.start()
        finally:
            await first.close()
        await second.start()
        await second.close()
    asyncio.run(check())


def test_lifespan_same_origin_and_honest_health():
    runtime = Runtime()
    with TestClient(create_app(runtime)) as client:
        assert runtime.started_at is not None
        for route in ("/", "/settings", "/setup", "/oneiro/", "/app.js", "/style.css"):
            response = client.get(route)
            assert response.status_code == 200
            assert "access-control-allow-origin" not in response.headers
        assert client.get("/api/health").json()["assistant_ready"] is False
        status = client.get("/api/status").json()
        assert status["memory"]["fallback"] is None
        assert status["runtime_connected"] is False
        assert client.get("/api/graph").status_code == 503
        assert client.post("/api/settings", json={"graph.port": 8001}).status_code == 403
        token = client.get("/api/session").json()["csrf"]
        assert client.post("/api/settings", headers={"X-Oneiro-CSRF": token, "Origin": "https://evil.invalid"}, json={"graph.port": 8001}).status_code == 403
        assert client.get("/api/settings", headers={"Host": "evil.invalid"}).status_code == 400
        assert client.post("/api/message", headers={"X-Oneiro-CSRF": token}).status_code == 503
    assert runtime.started_at is None


def test_settings_secrets_and_size_are_not_reflected():
    with TestClient(create_app()) as client:
        token = client.get("/api/session").json()["csrf"]
        headers = {"X-Oneiro-CSRF": token}
        response = client.post("/api/settings", headers=headers, json={"llm.api_key": "do-not-reflect"})
        assert response.status_code == 200
        assert "do-not-reflect" not in response.text
        assert "do-not-reflect" not in client.get("/api/settings").text
        response = client.post("/api/settings", headers=headers, content="x" * 64001)
        assert response.status_code == 413


def test_doctor_does_not_create_runtime_or_fake_readiness():
    result = subprocess.run([sys.executable, "-m", "oneiro", "doctor"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert json.loads(result.stdout)["ready"] is False
    assert not config.path("runtime.data_dir").exists()
