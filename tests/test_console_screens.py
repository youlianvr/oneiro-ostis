"""Unit and integration tests for the 5 canonical console screens and window launcher."""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, isolate, make_app
from oneiro import config, window


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_five_canonical_screens_render_without_raw_json(tmp_path):
    """§ 3 and § 6 row 15: Every canonical screen renders HTML, zero raw JSON on screen."""
    routes = ["/", "/tasks", "/tools", "/settings", "/memory"]
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        for route in routes:
            res = client.get(route)
            assert res.status_code == 200, f"route {route} failed with {res.status_code}"
            assert res.headers["content-type"].startswith("text/html")
            text = res.text

            # Check for absence of unescaped/raw JSON payload dumps on screen
            assert '{"schema_version":' not in text
            assert '{"ready":' not in text
            assert '{"status":' not in text

            # Check that screen has title, nav, and body
            assert "<nav>" in text
            assert "</nav>" in text
            assert "<main>" in text


def test_conversation_screen_has_three_zones_and_action_feed(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        res = client.get("/")
        text = res.text
        assert 'class="screen-grid conversation-layout"' in text
        assert 'class="panel-left"' in text
        assert 'class="panel-center"' in text
        assert 'class="panel-right"' in text
        assert 'id="approvals"' in text
        assert 'id="questions"' in text
        assert 'id="transcript"' in text


def test_tasks_screen_has_split_view_for_tasks_and_schedules(tmp_path):
    # The words are asserted in English, because the words are catalog text: the
    # default language is Russian, so the screen is asked for in the language whose
    # sentences are being pinned here. The Russian side is measured in
    # test_i18n_themes.py.
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        res = client.get("/tasks?lang=en")
        text = res.text
        assert "Active &amp; Queued Tasks" in text or "Active & Queued Tasks" in text
        assert "Standing Schedules" in text
        assert 'id="task-list"' in text
        assert 'id="schedule-list"' in text


def test_tools_screen_has_three_tabs(tmp_path):
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        res = client.get("/tools?lang=en")
        text = res.text
        assert "MCP Servers" in text
        assert "Skills Catalog" in text
        assert "Local Safe Tools" in text
        assert 'id="tab-mcp"' in text
        assert 'id="tab-skills"' in text
        assert 'id="tab-local"' in text


def test_window_launcher_headless_mode(monkeypatch):
    monkeypatch.setenv("ONEIRO_HEADLESS", "1")
    state = window.launch_window(9899, no_window=True)
    assert state.mode == "headless"
    assert state.active is True
    assert "9899" in state.url


def test_window_launcher_browser_preference(monkeypatch):
    opened = []
    monkeypatch.setattr(window.webbrowser, "open", lambda url: opened.append(url))
    config.save({"ui.window": "browser"})
    state = window.launch_window(9899)
    assert state.mode == "browser"
    assert state.active is True
    assert len(opened) == 1
    assert "9899" in opened[0]
