"""Unit and integration tests for the 5 canonical console screens and window launcher."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, isolate, make_app
from oneiro import config, i18n, window

STATIC = Path(__file__).resolve().parents[1] / "python" / "oneiro" / "static"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_five_canonical_screens_render_without_raw_json(tmp_path):
    """§ 3 and § 6 row 15: Every canonical screen renders HTML, zero raw JSON on screen."""
    routes = ["/", "/drafts", "/tasks", "/tools", "/settings", "/memory"]
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


def test_drafts_screen_carries_the_press_and_the_revision_field(tmp_path):
    """§ 6 W3: a draft is seen in the tab, and the press is the owner's.

    The screen serves a skeleton on purpose: the drafts come from `/api/drafts`, because
    that read walks the graph and a page must answer whatever the substrate is doing
    (`test_graph_states.py` pins that for every screen). So this pins the places the
    page's own script fills — the two lists and the status line — and the words that
    name them, which live in the page's i18n block rather than in `static/app.js`: a
    sentence written in the script could only ever be one language.
    """
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        res = client.get("/drafts?lang=en")
        text = res.text
        assert res.status_code == 200, res.status_code
        assert res.headers["content-type"].startswith("text/html")
        assert "Waiting for your press" in text
        assert "Settled drafts" in text
        for element in ("draft-list", "draft-settled", "draft-meter"):
            assert f'id="{element}"' in text, element
        assert i18n.t("draft.revision_label", "en") in text
        assert i18n.t("btn.send_draft", "en") in text
        assert i18n.t("btn.save_revision", "en") in text
        # Every screen links to the tab, and the tab is one of the screens the nav names.
        assert 'href="/drafts"' in text
        assert i18n.t("nav.drafts", "en") in text
        # The press and the revision are the same routes the command line uses.
        script = (STATIC / "app.js").read_text(encoding="utf-8")
        assert '"/send"' in script and '"/revise"' in script and '"/discard"' in script


@pytest.fixture(scope="module")
def browser():
    # Use the existing browser driver also used by live_drafts_check.py; a missing
    # installation is a failed check, not a silently skipped regression.
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        launched = play.chromium.launch()
        try:
            yield launched
        finally:
            launched.close()


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("case", ["sent", "failed", "uncertain", "uncertain-effect",
                                  "unrecorded", "malformed", "refresh-failed"])
def test_draft_click_reports_delivery_not_http_success(tmp_path, monkeypatch, browser, lang, case):
    """Run the shipped script in Chromium against the real HTTP routes.

    Only the send/listing boundary is scripted: no mailbox, bot, model or graph server
    is contacted. A POST still goes through Oneiro's token middleware and send handler.
    """
    from oneiro import drafts
    from oneiro.query import GraphQueryError

    waiting = {"id": "draft-browser-test", "tool": "testmail.send_message",
               "arguments": {"to": "test@example.org", "body": "local test only"},
               "target": "test@example.org", "state": "waiting",
               "effect": {"outcome": "none"}}
    calls = []
    answer = {"ok": True, "state": "completed", "effect": "succeeded", "recorded": True}
    if case == "failed":
        answer.update(ok=False, state="failed", effect="failed", reason="transport_failed")
    elif case == "uncertain":
        answer.update(ok=False, state="uncertain", effect="uncertain")
    elif case == "uncertain-effect":
        answer["effect"] = "uncertain"
    elif case == "unrecorded":
        answer["recorded"] = False
    elif case == "malformed":
        answer = {}

    async def press(_owner, draft_id):
        calls.append(draft_id)
        return answer

    async def listing(_owner):
        if calls and case == "refresh-failed":
            raise GraphQueryError("server_unreachable", "local test failure")
        settled = {**waiting, "state": answer.get("state", "running"),
                   "effect": {"outcome": answer.get("effect", "none")}}
        return {"drafts": [] if calls else [waiting], "settled": [settled] if calls else [],
                "waiting": 0 if calls else 1, "complete": True, "scanned": 1}

    monkeypatch.setattr(drafts, "press", press)
    monkeypatch.setattr(drafts, "listing", listing)
    errors = []
    page = browser.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        def route(request_route):
            request = request_route.request
            from urllib.parse import urlsplit
            url = urlsplit(request.url)
            response = client.request(request.method, url.path + ("?" + url.query if url.query else ""),
                                      content=request.post_data_buffer,
                                      headers={"X-Oneiro-CSRF": request.headers.get("x-oneiro-csrf", "")})
            request_route.fulfill(status=response.status_code, body=response.content,
                                  content_type=response.headers.get("content-type", ""))

        page.route("**/*", route)
        try:
            page.goto(f"http://127.0.0.1:32123/drafts?lang={lang}")
            page.locator(".draft-send").wait_for(state="visible")
            assert calls == [], "opening the page must not send"
            page.locator(".draft-send").click()
            expected = {"sent": "draft.sent", "failed": "draft.send_failed",
                        "uncertain": "draft.send_uncertain", "uncertain-effect": "draft.send_uncertain",
                        "unrecorded": "draft.send_unrecorded", "malformed": "draft.send_unknown",
                        "refresh-failed": "draft.load_failed"}[case]
            # Look for the exact catalog sentence, not a source-code pattern or HTTP 200.
            page.get_by_text(i18n.t(expected, lang), exact=True).wait_for(state="visible", timeout=5000)
            assert calls == [waiting["id"]], "one click must not retry the send"
            if case != "sent":
                assert page.get_by_text(i18n.t("draft.sent", lang), exact=True).count() == 0
            assert errors == []
        finally:
            page.close()


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_memory_screen_shows_each_fact_with_its_source_and_the_value_it_replaced(
        tmp_path, browser, lang):
    """Run the shipped script in Chromium against the real HTTP routes.

    The curated list is not asserted in the page skeleton: it is fetched, so the check
    is a real run of `app.js` against `/api/memory/facts`, an edit that replaced a
    value, and the add form the screen carries. A page that prints the fact but hides
    what it replaced would fail here.
    """
    from chat_fakes import csrf_of, post

    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        token = csrf_of(client)
        added = post(client, "/api/memory/facts",
                     {"text": "Владелец пишет по-русски.", "client_id": "fact-screen-0001"},
                     token)
        assert added.status_code == 200, added.text
        fact_id = added.json()["fact"]["id"]
        assert post(client, f"/api/memory/facts/{fact_id}/edit",
                    {"text": "Владелец пишет по-русски и по-английски.",
                     "client_id": "fact-edit-screen-0001", "revision": 1},
                    token).status_code == 200

        def route(request_route):
            from urllib.parse import urlsplit
            request = request_route.request
            url = urlsplit(request.url)
            response = client.request(request.method,
                                      url.path + ("?" + url.query if url.query else ""),
                                      content=request.post_data_buffer,
                                      headers={"X-Oneiro-CSRF": request.headers.get("x-oneiro-csrf", "")})
            request_route.fulfill(status=response.status_code, body=response.content,
                                  content_type=response.headers.get("content-type", ""))

        errors = []
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        try:
            page.goto(f"http://127.0.0.1:32123/memory?lang={lang}")
            page.locator(".fact-card").first.wait_for(state="visible")
            page.get_by_text("Владелец пишет по-русски и по-английски.", exact=True).wait_for()
            # The source and the dates are shown with the fact, not only its text.
            card = page.locator(".fact-card").first
            meta = card.locator(".fact-meta").inner_text()
            assert i18n.t("facts.source.owner_instruction", lang) in meta, meta
            assert i18n.t("facts.recorded", lang) in meta and i18n.t("facts.updated", lang) in meta
            # The value the edit replaced stays readable, with its own source and date.
            earlier = card.locator(".fact-earlier")
            assert earlier.count() == 1
            assert earlier.locator(".fact-older-text").inner_text() == "Владелец пишет по-русски."
            earlier_meta = earlier.locator(".fact-older small").first.inner_text()
            assert i18n.t("facts.source.owner_instruction", lang) in earlier_meta, earlier_meta
            assert i18n.t("facts.earlier", lang) in earlier.inner_text()
            # The form on the screen writes: a new fact appears without a reload.
            page.fill("#fact-text", "Ещё один факт.")
            page.click("#fact-add button[type=submit]")
            page.get_by_text("Ещё один факт.", exact=True).wait_for(timeout=5000)
            page.get_by_text(i18n.t("facts.added", lang), exact=True).wait_for(timeout=5000)
            assert page.locator(".fact-card").count() == 2
            assert errors == []
        finally:
            page.close()


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
