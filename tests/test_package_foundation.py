"""Foundation contracts; no graph, model or account effects."""
from __future__ import annotations

import asyncio
import html
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oneiro import config, i18n, pages
from oneiro.ownership import FileLease, OwnershipError
from oneiro.runtime import Runtime
from oneiro.web import create_app


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ONEIRO_MCP_FILE", str(tmp_path / "mcp.json"))
    # Source-checkout subprocesses do not inherit pytest's sys.path changes.
    # Installed-wheel smoke separately proves no PYTHONPATH is needed.
    monkeypatch.setenv("PYTHONPATH", str(Path(config.__file__).parents[1]))
    for setting in config.SETTINGS:
        if setting.env not in ("ONEIRO_DATA_DIR",):
            monkeypatch.delenv(setting.env, raising=False)
        for alias in setting.aliases:
            monkeypatch.delenv(alias, raising=False)
    # Module-level state outlives a test otherwise: a migration note from one
    # test must not appear in the next one's page.
    monkeypatch.setattr(config, "_migrated_from", "")
    monkeypatch.setattr(config, "_cache", None)


def fake_home(monkeypatch, home: Path) -> None:
    """Point Path.home() at a temporary directory on Windows and POSIX."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))


def _tcp_open() -> bool:
    import socket
    host = str(config.value("graph.host"))
    port = int(config.value("graph.port"))
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


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
        graph = client.get("/api/graph")
        facts = graph.json()
        # The endpoint reports what could actually be read, so its status
        # follows reachability. What must never change: OSTIS is required and
        # there is no substitute store behind either answer.
        assert facts["required"] == "OSTIS"
        assert facts["fallback"] is None
        assert graph.status_code == (200 if facts["reachable"] else 503)
        assert facts["reachable"] == _tcp_open(), "reachability must be measured, not assumed"
        assert client.post("/api/settings", json={"graph.port": 8001}).status_code == 403
        token = client.get("/api/session").json()["csrf"]
        assert client.post("/api/settings", headers={"X-Oneiro-CSRF": token, "Origin": "https://evil.invalid"}, json={"graph.port": 8001}).status_code == 403
        assert client.get("/api/settings", headers={"Host": "evil.invalid"}).status_code == 400
        # An empty body fails validation before any graph or model call. The
        # model-outage 503 path is covered in test_chat_slice.py with a stub.
        assert client.post("/api/message", headers={"X-Oneiro-CSRF": token}).status_code == 400
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


# ------------------------------------------------- one data root, one settings file

def test_settings_and_runtime_share_one_root(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    fake_home(monkeypatch, home)
    monkeypatch.delenv("ONEIRO_SETTINGS_FILE", raising=False)
    monkeypatch.delenv("ONEIRO_DATA_DIR", raising=False)
    root = config.data_root()
    assert root == home / ".oneiro"
    assert config.settings_path() == root / "settings.json"
    # The declared setting and the function the code reads must not drift.
    assert config.path("runtime.data_dir") == root
    assert ".openclaw" not in str(root)
    assert config.describe()["data_root"] == str(root)


def test_legacy_settings_directory_is_migrated_on_first_read(tmp_path, monkeypatch):
    home = tmp_path / "home"
    legacy_dir = home / ".openclaw" / "oneiro"
    legacy_dir.mkdir(parents=True)
    legacy_file = legacy_dir / "settings.json"
    original = '{"graph.port": 8091, "llm.model": "kept-model"}'
    legacy_file.write_text(original, encoding="utf-8")
    (legacy_dir / "settings-history").mkdir()
    (legacy_dir / "settings-history" / "old.json").write_text('{"kept": true}', encoding="utf-8")
    fake_home(monkeypatch, home)
    monkeypatch.delenv("ONEIRO_SETTINGS_FILE", raising=False)
    monkeypatch.delenv("ONEIRO_DATA_DIR", raising=False)
    assert config.value("graph.port") == 8091, "legacy settings must answer before migration"
    migrated = home / ".oneiro" / "settings.json"
    assert migrated.read_text(encoding="utf-8") == original
    assert config.value("llm.model") == "kept-model"
    assert not legacy_file.exists(), "the old copy is moved, never left behind"
    assert (home / ".oneiro" / "settings-history" / "old.json").exists()
    assert not legacy_dir.exists(), "an empty old directory goes; a non-empty one is kept"
    assert config.describe()["migrated_from"].endswith("settings.json")
    # A second read must not migrate again or invent a note.
    assert config.value("graph.port") == 8091


def test_migration_leaves_a_non_empty_old_directory_alone(tmp_path, monkeypatch):
    home = tmp_path / "home"
    legacy_dir = home / ".openclaw" / "oneiro"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "settings.json").write_text('{"graph.port": 8091}', encoding="utf-8")
    (legacy_dir / "runtime.lock").write_bytes(b"0")     # an unknown file must survive
    fake_home(monkeypatch, home)
    monkeypatch.delenv("ONEIRO_SETTINGS_FILE", raising=False)
    monkeypatch.delenv("ONEIRO_DATA_DIR", raising=False)
    assert config.value("graph.port") == 8091
    assert legacy_dir.exists() and (legacy_dir / "runtime.lock").exists()
    assert (home / ".oneiro" / "settings.json").exists()


def test_explicit_settings_path_never_picks_up_the_legacy_directory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    legacy_dir = home / ".openclaw" / "oneiro"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "settings.json").write_text('{"graph.port": 8091}', encoding="utf-8")
    fake_home(monkeypatch, home)
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "explicit.json"))
    assert config.value("graph.port") == 8090, "a test path must not import the owner's settings"
    assert not (home / ".oneiro").exists()
    assert (legacy_dir / "settings.json").exists()


def test_describe_reports_actual_writability(tmp_path, monkeypatch):
    assert config.describe()["writable"] is True
    assert config.describe()["writable_error"] == ""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(blocker / "settings.json"))
    description = config.describe()
    assert description["writable"] is False
    assert "not a directory" in description["writable_error"]


def test_read_only_settings_are_refused_by_save():
    with pytest.raises(ValueError, match="read-only"):
        config.save({"runtime.data_dir": str(Path.home() / "elsewhere")})
    assert not config.settings_path().exists()


# ------------------------------------------------------ page identity on the server

def test_each_route_renders_its_own_page():
    with TestClient(create_app()) as client:
        bodies = {}
        for route, marker in (("/?lang=en", "Conversation"), ("/settings?lang=en", "Oneiro settings"),
                              ("/setup?lang=en", "Setup"), ("/oneiro/?lang=en", "Graph panel")):
            response = client.get(route)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/html")
            bodies[route] = response.text
            assert f"<h2>{marker}</h2>" in response.text, route
        assert len(set(bodies.values())) == 4, "routes must not share one document"
        assert "Graph panel" not in bodies["/?lang=en"]
        assert 'id="message"' in bodies["/?lang=en"], "the chat box is the only conversation control"


def test_settings_form_is_generated_from_the_registry(monkeypatch):
    with TestClient(create_app()) as client:
        page = client.get("/settings").text
    for setting in config.SETTINGS:
        if setting.secret:
            continue
        assert f'name="{setting.key}"' in page, f"{setting.key} is declared but unreachable"
    for key in ("llm.manager_model", "llm.researcher_model", "llm.executor_model", "web.port"):
        assert f'name="{key}"' in page
    # A key is write-only: the control exists, the value never does.
    key_field = page.split('name="llm.api_key"')[0].rsplit("<div", 1)[-1]
    assert "value=" not in key_field
    assert 'id="f-llm.api_key"' in page and 'type="password"' in page
    # The root is answered by the environment, so the control is not editable.
    assert 'id="f-runtime.data_dir"' in page
    readonly = page.split('id="f-runtime.data_dir"')[1].split("</div>")[0]
    assert "disabled" in readonly
    # The interface is loopback-only, so it is not offered as editable either.
    assert 'id="f-web.host"' in page
    assert "disabled" in page.split('id="f-web.host"')[1].split("</div>")[0]
    assert str(config.data_root()) in page
    # A control must carry the current value: an empty number field would post
    # 0 and the whole form would be refused.
    assert 'value="9899"' in page and 'value="8090"' in page


def test_a_refused_save_explains_itself_without_echoing_what_was_typed():
    """A refusal the owner cannot understand is a refusal they cannot fix."""
    with TestClient(create_app()) as client:
        token = client.get("/api/session").json()["csrf"]
        response = client.post("/api/settings", headers={"X-Oneiro-CSRF": token},
                               json={"graph.port": "not-a-port"})
    assert response.status_code == 400
    payload = response.json()
    assert "Nothing was saved" in payload["error"]
    assert any("graph.port" in reason for reason in payload["reasons"]), payload
    assert "not-a-port" not in response.text
    assert config.value("graph.port") == 8090, "a refused write changes nothing"
    assert "unknown settings" in client_messages({"not_a_setting": "x"})


def client_messages(patch: dict) -> str:
    """Post one patch and return everything the client is told about it."""
    with TestClient(create_app()) as client:
        token = client.get("/api/session").json()["csrf"]
        response = client.post("/api/settings", headers={"X-Oneiro-CSRF": token}, json=patch)
    assert response.status_code == 400, response.text
    return response.text


def test_the_page_carries_the_theme_and_language_from_the_settings():
    """W0: the tokens are real — the page names the theme it is painted in."""
    with TestClient(create_app()) as client:
        page = client.get("/settings").text
        tokens = client.get("/console.css")
    assert f'data-theme="{config.value("ui.theme")}"' in page
    assert f'lang="{config.value("ui.language")}"' in page
    # The tokens load before the layout, so no rule can disagree with the theme.
    assert page.index('href="/console.css"') < page.index('href="/style.css"')
    assert tokens.status_code == 200
    assert tokens.headers["content-type"].startswith("text/css")
    assert "[data-theme=" in tokens.text


def _control(page: str, key: str) -> str:
    """The element that carries a setting's name, and what follows it."""
    before, _, after = page.partition(f'id="f-{key}"')
    opening = before.rsplit("<", 1)[-1]
    return opening + after.split("</div>", 1)[0]


def test_a_closed_set_is_a_list_and_a_structure_is_editable_text():
    """Choices and structured values must not be free text boxes."""
    with TestClient(create_app()) as client:
        page = client.get("/settings").text
    # ui.theme: a select carrying exactly the declared options, current one chosen.
    theme = _control(page, "ui.theme")
    assert theme.startswith("select"), theme[:40]
    assert re.findall(r'<option value="([^"]+)"', theme) == \
        list(config._BY_KEY["ui.theme"].choices)
    assert '<option value="night" selected>' in theme
    # A boolean is a closed set too, and both states are visible.
    tray = _control(page, "ui.tray")
    assert '<option value="true"' in tray and '<option value="false" selected>' in tray
    # models.providers is JSON text in a textarea, parsed and checked on write.
    providers = html.unescape(_control(page, "models.providers"))
    assert providers.startswith("textarea")
    assert '"base_url"' in providers and '"key_env"' in providers


def test_every_field_says_which_layer_answered_it():
    """A default must not look like a stored preference (W0 evidence).

    Asked in English: `pages.SOURCES` names a catalog key, and the sentence the page
    renders is that key's text in the language of the request (the product defaults to
    Russian, so the English wording is the one to pin here).
    """
    with TestClient(create_app()) as client:
        page = client.get("/settings?lang=en").text
    described = {row["key"]: row for row in config.describe()["settings"]}
    for key, row in described.items():
        if key == "llm.api_key":
            continue                     # a key reports whether one is in force, not a layer
        said = i18n.t(pages.SOURCES[row["source"]], "en")
        assert f"Value from {said}." in _control(page, key), \
            f"{key} came from {row['source']} but the page does not say so"


def test_a_declared_but_inactive_setting_says_so():
    """`pending` settings are visible and honest about not being in force yet."""
    with TestClient(create_app()) as client:
        page = client.get("/settings?lang=en").text
    assert config._BY_KEY["ui.density"].pending is True
    assert "not in this build yet" in _control(page, "ui.density")
    # A setting already in force carries no such note.
    assert config._BY_KEY["web.port"].pending is False
    assert "not in this build yet" not in _control(page, "web.port")
    # The two keys the honesty pass wired (docs/PROGRESS.md) are in force on the page,
    # and the key the plan never promised carries the label instead of looking wired.
    for key in ("permissions.write_outside", "memory.facts_budget"):
        assert config._BY_KEY[key].pending is False, key
        assert "not in this build yet" not in _control(page, key)
    assert config._BY_KEY["mcp.source"].pending is True
    assert "not in this build yet" in _control(page, "mcp.source")


def _submitted(page: str) -> dict:
    """What a browser would send back from the settings form.

    Only the settings form is read: the same page carries the facts form, and a
    control from there is not part of the settings round trip. Every control
    shape is handled — input, select, textarea, and the disabled control the
    browser would omit entirely.
    """
    form = page.partition('<form id="settings"')[2].partition("</form>")[0]
    assert form, "the settings form is not in the page"
    patch: dict = {}
    for match in re.finditer(r"<(input|select|textarea)\s([^>]*)>", form):
        tag, attributes = match.group(1), match.group(2)
        name = re.search(r'name="([^"]+)"', attributes)
        if not name or "disabled" in attributes:
            continue
        key = name.group(1)
        if tag == "select":
            body = form[match.end():].split("</select>", 1)[0]
            chosen = re.search(r'value="([^"]*)" selected', body)
            raw = chosen.group(1) if chosen else ""
        elif tag == "textarea":
            body = form[match.end():].split("</textarea>", 1)[0]
            raw = html.unescape(body)
        else:
            found = re.search(r'value="([^"]*)"', attributes)
            raw = html.unescape(found.group(1) or "") if found else ""
        patch[key] = int(raw) if key.endswith(".port") else raw
    return patch


def test_every_rendered_field_survives_a_form_round_trip():
    """What the browser sends back must be what the server accepts."""
    with TestClient(create_app()) as client:
        page = client.get("/settings").text
        token = client.get("/api/session").json()["csrf"]
        patch = _submitted(page)
        for setting in config.SETTINGS:
            if not setting.readonly and not setting.secret:
                assert setting.key in patch, f"{setting.key} is rendered but not submittable"
        response = client.post("/api/settings", headers={"X-Oneiro-CSRF": token}, json=patch)
        assert response.status_code == 200, response.text
    assert config.value("web.port") == 9899
    assert config.value("graph.port") == 8090
    assert config.value("llm.manager_model") == "main"


def test_a_settings_post_without_scripts_gets_a_page_and_not_json():
    """§ 6 row 15 on the one path that could still show JSON.

    Measured 2026-10-11 in Chromium with scripting disabled: the settings form's own
    Save button posted to `/api/settings` and the tab rendered
    `{"error": "Cross-origin request refused"}` — raw JSON on a screen, reachable
    without touching the address bar. A refusal is still something a person reads, so a
    browser that accepts HTML gets a page in the active language, while an API client
    that asks for JSON keeps exactly the body it parsed before.
    """
    with TestClient(create_app()) as client:
        as_browser = client.post("/api/settings", data={"ui.language": "en"},
                                 headers={"Accept": "text/html,application/xhtml+xml",
                                          "Origin": "null"})
        assert as_browser.status_code == 403
        assert as_browser.headers["content-type"].startswith("text/html")
        assert 'lang="ru"' in as_browser.text          # the settings' own language
        assert i18n.t("error.refused_title", "ru") in as_browser.text
        assert i18n.t("error.cross_origin", "ru") in as_browser.text
        assert not as_browser.text.lstrip().startswith("{"), as_browser.text[:120]

        as_api = client.post("/api/settings", json={},
                             headers={"Accept": "application/json"})
        assert as_api.status_code == 403
        assert as_api.headers["content-type"].startswith("application/json")
        assert as_api.json() == {"error": "Invalid owner request token"}


def test_adding_a_setting_needs_no_html_edit(monkeypatch):
    probe = config.Setting("audit.probe", "ONEIRO_AUDIT_PROBE", "probe", "Audit probe",
                           "Declared by a test, rendered by the registry.", "Audit")
    monkeypatch.setattr(config, "SETTINGS", config.SETTINGS + (probe,))
    monkeypatch.setattr(config, "_BY_KEY", {**config._BY_KEY, probe.key: probe})
    with TestClient(create_app()) as client:
        page = client.get("/settings").text
    assert 'name="audit.probe"' in page
    assert "Audit probe" in page
    assert "<legend>Audit</legend>" in page
