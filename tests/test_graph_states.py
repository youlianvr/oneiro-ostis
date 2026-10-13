"""The three states a memory substrate can be in, measured through the pages.

Both defects this file closes were found on a live DOM with the owner's real
settings (2026-10-11), and neither was visible to a test that only asked for
healthy or unreachable:

1. With a **live graph** answering and `/oneiro/` showing a successful read, the
   readiness panel printed that memory answered but nothing could be read back,
   because `Runtime._inspect` hardcoded `verified: False`. Panel and page
   contradicted each other in the same moment.
2. With a port that **accepts TCP and never answers**, the outer
   `wait_for(memory.probe, PROBE_TIMEOUT + 2)` raised out of the graph route and
   left `500 text/plain "Internal Server Error"` on screen. `/tasks?lang=ru` also
   failed to settle, because each read behind it held the graph lane's own 10 s
   deadline (measured: /api/tasks 10.04 s, /api/schedules 9.11 s).

So the states are tested as states: the page is asked what it answers, and a
silent socket is a real socket in this file, not a patched function.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chat_fakes import MemoryLinks, isolate, make_app
from oneiro import config, i18n, memory

#: The screens a person can open, and the bound each must answer within.
SCREENS = ("/", "/drafts", "/tasks", "/tools", "/settings", "/memory", "/setup", "/oneiro/")
ANSWER_BUDGET = 5.0

#: What a probe can come back with, one entry per state.
LIVE = memory.GraphFacts(reachable=True, verified=True, arcs_found=1,
                         identifiers=("concept_oneiro",),
                         anchor=memory.ANCHOR_RELATION)
CLOSED = memory.GraphFacts(blocked=({"code": "blocked.graph_unreachable",
                                     "data": {"host": "127.0.0.1", "port": 8090}},))
SILENT = memory.GraphFacts(reachable=True, verified=False, blocked=(
    {"code": memory.TIMEOUT_CODE, "data": {"seconds": memory.PROBE_BUDGET}},))
STATES = {"live": LIVE, "closed": CLOSED, "silent": SILENT}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def _facts_of(page_or_status: str, lang: str) -> str:
    return page_or_status


@pytest.mark.parametrize("state", sorted(STATES))
def test_every_screen_answers_with_a_page_in_each_graph_state(state, tmp_path, monkeypatch):
    """All three states, every screen: HTML, bounded, and no English prose."""
    monkeypatch.setattr(memory, "probe_within", lambda *a, **k: STATES[state])
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        for route in SCREENS:
            started = time.monotonic()
            response = client.get(f"{route}?lang=ru")
            elapsed = time.monotonic() - started
            assert response.status_code == 200, f"{state} {route}: {response.status_code}"
            assert response.headers["content-type"].startswith("text/html"), route
            assert elapsed < ANSWER_BUDGET, f"{state} {route} took {elapsed:.1f}s"
            assert "Internal Server Error" not in response.text
            assert _english_prose_5(response.text) == set(), (
                f"{state} {route} shows English prose: {sorted(_english_prose_5(response.text))[:3]}")

        # The JSON a screen reads is bounded too. 503 is this API's documented answer for
        # a graph it cannot read; 500 is the server admitting it did not catch something.
        for route in ("/api/status", "/api/graph", "/api/tasks", "/api/schedules",
                      "/api/conversations", "/api/memory/facts"):
            started = time.monotonic()
            response = client.get(route)
            elapsed = time.monotonic() - started
            assert response.status_code != 500, f"{state} {route}: 500"
            assert elapsed < ANSWER_BUDGET, f"{state} {route} took {elapsed:.1f}s"


def _english_prose_5(markup: str) -> set[str]:
    """The project's rule, imported rather than copied."""
    from test_i18n_themes import _english_sentences, _visible_lines
    return _english_sentences(_visible_lines(markup))


@pytest.mark.parametrize("state", sorted(STATES))
def test_the_panel_and_the_graph_page_agree(state, tmp_path, monkeypatch):
    """Row 14's other half: the panel must not contradict the page it links to.

    If the panel says memory is readable, the graph page says readable; if it says
    the read is not confirmed, the panel names a memory reason and the page does not
    claim a read. That is the invariant that failed with the owner's live graph.
    """
    monkeypatch.setattr(memory, "probe_within", lambda *a, **k: STATES[state])
    from test_i18n_themes import _panel
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        status = client.get("/api/status").json()
        graph_page = client.get("/oneiro/?lang=ru").text
        english = client.get("/oneiro/?lang=en").text

    assert status["memory"]["verified"] == STATES[state].verified
    assert status["memory"]["tcp_reachable"] == STATES[state].reachable
    panel = _panel(status, "ru")
    says_readable = i18n.t("status.memory_ok", "ru") in panel.splitlines()
    # The graph page has three verdicts: readable, unverified, unreachable.
    page_readable = i18n.t("graph.readable", "ru", arcs=1, anchor="", elapsed=0)[:24] in graph_page
    page_not_claimed = (i18n.t("graph.unverified", "ru") in graph_page
                        or i18n.t("graph.unreachable", "ru") in graph_page)
    assert says_readable == STATES[state].verified, "the panel disagrees with the probe"
    assert page_readable == STATES[state].verified, "the page disagrees with the probe"
    assert page_not_claimed or page_readable
    if not says_readable:
        memory_reasons = [item["code"] for item in status["blocked"] if isinstance(item, dict)]
        assert any(code.startswith("blocked.graph") or code == "blocked.client_absent"
                   for code in memory_reasons), (
            f"the panel says the read is unconfirmed without naming a memory reason: "
            f"{memory_reasons}")
    assert _english_prose_5(graph_page) == set()
    assert _english_prose_5(english) != set(), "the English page has no prose to compare with"


def test_a_silent_graph_is_reported_not_raised(tmp_path, monkeypatch):
    """`probe_within` returns facts inside its budget and never raises.

    The read itself has no deadline of its own, so this blocks the real `probe`:
    the call must come back with the timeout code, and the next call must not start
    a second stuck worker.
    """
    release = threading.Event()
    monkeypatch.setattr(memory, "probe", lambda *a, **k: release.wait(30) or LIVE)
    monkeypatch.setattr(memory, "_SILENT", {})

    started = time.monotonic()
    facts = memory.probe_within("127.0.0.1", 8090, timeout=0.5, budget=0.4)
    waited = time.monotonic() - started
    assert waited < 2.0, f"probe_within waited {waited:.1f}s for a budget of 0.4s"
    assert facts.verified is False
    assert [item["code"] for item in facts.blocked] == [memory.TIMEOUT_CODE]

    # The second call still measures reachability, so it pays one TCP check - but it must
    # not pay the budget again: the silent worker is not joined a second time.
    started = time.monotonic()
    again = memory.probe_within("127.0.0.1", 8090, timeout=0.5, budget=5.0)
    assert time.monotonic() - started < 1.0, "a stuck worker must not be joined again"
    assert [item["code"] for item in again.blocked] == [memory.TIMEOUT_CODE]
    release.set()


def test_a_note_does_not_outlive_its_window(tmp_path, monkeypatch):
    """A verdict must not outlive its evidence.

    Measured 2026-10-11 against a shim client that had started answering again: the note
    left by one stuck read kept returning `blocked.probe_timeout` in 0.018 s and never
    dialled, so the panel and the graph page called a recovered graph unreadable. The
    window is what makes the next reading a real one.
    """
    monkeypatch.setattr(memory, "_SILENT", {})
    monkeypatch.setattr(memory, "SILENT_SECONDS", 0.5)
    monkeypatch.setattr(memory, "_tcp_reachable", lambda host, port, timeout: True)
    stuck = threading.Event()
    reads: list[float] = []

    def probe(host: str, port: int, *, timeout: float = memory.PROBE_TIMEOUT) -> memory.GraphFacts:
        reads.append(time.monotonic())
        if len(reads) == 1:
            # The first read never comes back and stays stuck: a wedged socket does not
            # heal. A graph that answers again is a graph that answers *new* reads.
            stuck.wait(30)
        return LIVE

    monkeypatch.setattr(memory, "probe", probe)
    try:
        first = memory.probe_within("127.0.0.1", 8090, budget=0.1)
        assert [item["code"] for item in first.blocked] == [memory.TIMEOUT_CODE]
        inside = memory.probe_within("127.0.0.1", 8090, budget=5.0)
        assert [item["code"] for item in inside.blocked] == [memory.TIMEOUT_CODE]
        assert len(reads) == 1, "a fresh note must not start a second read"

        time.sleep(0.6)                         # the window passes
        recovered = memory.probe_within("127.0.0.1", 8090, budget=0.5)
        assert len(reads) == 2, "a note outlived its window and stood in for a real reading"
        assert recovered.verified is True and recovered.blocked == ()
    finally:
        stuck.set()


def test_a_recovered_graph_is_reported_readable_again(tmp_path, monkeypatch):
    """Both surfaces have to believe a graph that answers again.

    The same window, measured through the routes: a panel that stands by a verdict after
    the graph came back is the defect, not the caution that produced it.
    """
    monkeypatch.setattr(memory, "_SILENT", {})
    monkeypatch.setattr(memory, "SILENT_SECONDS", 0.5)
    monkeypatch.setattr(memory, "_tcp_reachable", lambda host, port, timeout: True)
    wedged = threading.Event()
    reads: list[float] = []

    def probe(host: str, port: int, *, timeout: float = memory.PROBE_TIMEOUT) -> memory.GraphFacts:
        reads.append(time.monotonic())
        if len(reads) == 1:
            wedged.wait(30)                     # the read that never comes back
        return LIVE

    monkeypatch.setattr(memory, "probe", probe)
    try:
        with TestClient(make_app(tmp_path, MemoryLinks())) as client:
            stuck = memory.probe_within("127.0.0.1", 8090, budget=0.1)
            assert [item["code"] for item in stuck.blocked] == [memory.TIMEOUT_CODE]
            down = client.get("/api/status").json()
            assert down["memory"]["verified"] is False
            assert "blocked.graph_unreadable" in [item["code"] for item in down["blocked"]]
            assert len(reads) == 1, "a fresh note must stand for the reading, not a second read"

            time.sleep(0.6)                     # the window passes
            after = client.get("/api/status").json()
            page = client.get("/oneiro/?lang=ru").text
        assert len(reads) >= 2, "a note outlived its window and stood in for a reading"
        assert after["memory"]["verified"] is True, "a recovered graph is still called unreadable"
        assert i18n.t("graph.readable", "ru", arcs=1, anchor="", elapsed=0)[:24] in page
    finally:
        wedged.set()


def test_a_verdict_names_the_target_it_was_derived_from(tmp_path, monkeypatch):
    """A silent read of one graph is not another target's verdict.

    Measured 2026-10-11: after one read of a silent-but-accepting port, a probe for a
    merely closed port answered `blocked.probe_timeout` instead of
    `blocked.graph_unreachable`, and the panel rendered an address-less "unreadable"
    verdict for a port that was not even listening.
    """
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        closed_port = int(spare.getsockname()[1])
    silent_port = 1          # never dialled: the probe is held open for it below
    released = threading.Event()
    real_probe = memory.probe

    def fake_probe(host: str, port: int, *, timeout: float = memory.PROBE_TIMEOUT) -> memory.GraphFacts:
        if port == silent_port:
            released.wait(30)                # the read that never comes back
            return LIVE
        return real_probe(host, port, timeout=timeout)

    monkeypatch.setattr(memory, "probe", fake_probe)
    monkeypatch.setattr(memory, "_SILENT", {})
    try:
        silent = memory.probe_within("127.0.0.1", silent_port, timeout=0.5, budget=0.4)
        assert [item["code"] for item in silent.blocked] == [memory.TIMEOUT_CODE]

        # A budget roomy enough for the first real probe of this process (the import of
        # the client is the slow part); what matters is which verdict comes back.
        facts = memory.probe_within("127.0.0.1", closed_port, timeout=0.5, budget=3.0)
        codes = [item["code"] for item in facts.blocked]
        assert codes == ["blocked.graph_unreachable"], (
            f"a silent read of {silent_port} became the verdict for {closed_port}: {codes}")
        assert facts.blocked[0]["data"] == {"host": "127.0.0.1", "port": closed_port}
        assert memory.panel_reasons(facts) == [
            {"code": "blocked.graph_unreachable",
             "data": {"host": "127.0.0.1", "port": closed_port}}]
    finally:
        released.set()


def test_the_panel_payload_never_carries_the_library_prose(tmp_path, monkeypatch):
    """The graph page may quote the dependency; the panel may not.

    `blocked.probe_failed` interpolates the library's own sentence, and the panel is
    on every screen, so the panel reports the verdict as `blocked.graph_unreadable`
    (machine data only) while the graph page keeps the diagnosis.
    """
    failed = memory.GraphFacts(reachable=True, blocked=(
        {"code": "blocked.probe_failed",
         "data": {"exception": "ConnectionAbortedError: Sc-server takes a long time to respond"}},))
    monkeypatch.setattr(memory, "probe_within", lambda *a, **k: failed)
    with TestClient(make_app(tmp_path, MemoryLinks())) as client:
        status = client.get("/api/status").json()
        page = client.get("/oneiro/?lang=ru").text

    codes = [item["code"] for item in status["blocked"]]
    assert "blocked.probe_failed" not in codes and "blocked.graph_unreadable" in codes
    assert "Sc-server" not in json.dumps(status, ensure_ascii=False)
    assert "Sc-server takes a long time to respond" in page, (
        "the graph page is where the dependency's own text belongs")


def test_a_silent_port_does_not_put_500_on_screen(tmp_path, monkeypatch):
    """The defect, end to end: a socket that accepts and never answers.

    Either the dependency gives up first (`blocked.probe_failed`) or the budget runs
    out (`blocked.probe_timeout`); both mean the same thing to a reader, and neither may
    become a 500 or an English body.
    """
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = int(listener.getsockname()[1])
    holding: list[socket.socket] = []
    stop = threading.Event()

    def hold() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            holding.append(connection)          # accepted, never answered

    keeper = threading.Thread(target=hold, daemon=True)
    keeper.start()
    (tmp_path / "settings.json").write_text(json.dumps({"graph.port": port}),
                                            encoding="utf-8")
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(memory, "_SILENT", {})
    try:
        assert config.value("graph.port") == port
        with TestClient(make_app(tmp_path, MemoryLinks())) as client:
            started = time.monotonic()
            page = client.get("/oneiro/?lang=ru")
            elapsed = time.monotonic() - started
            assert page.status_code == 200, f"the graph page answered {page.status_code}"
            assert page.headers["content-type"].startswith("text/html")
            assert "Internal Server Error" not in page.text
            assert elapsed < memory.PROBE_BUDGET + 3, f"the graph page took {elapsed:.1f}s"
            assert _english_prose_5(page.text) == set()
            assert i18n.t("graph.unverified", "ru") in page.text

            graph = client.get("/api/graph")
            assert graph.status_code != 500, f"/api/graph answered {graph.status_code}"
            codes = [item["code"] for item in graph.json()["blocked"]]
            assert set(codes) & {memory.TIMEOUT_CODE, "blocked.probe_failed"}, codes
            assert graph.json()["verified"] is False

            # The panel never carries the dependency's own sentence: it reports the
            # verdict, and the page above holds the diagnosis.
            status = client.get("/api/status").json()
            panel_codes = [item["code"] for item in status["blocked"]]
            assert "blocked.probe_failed" not in panel_codes, panel_codes
            assert "Sc-server" not in json.dumps(status, ensure_ascii=False)
    finally:
        stop.set()
        for connection in holding:
            connection.close()
        listener.close()
        keeper.join(timeout=2)


def test_a_screen_settles_while_the_graph_is_unreachable(tmp_path, monkeypatch):
    """The `/tasks` hang: chained reads each holding the graph lane's own 10 s deadline.

    This drives the *real* lane, not the in-memory stub the other tests use: with an
    unreachable graph the screen's reads must answer inside the page budget instead of
    taking 10 s each (measured 2026-10-11: /api/tasks 10.04 s, /api/schedules 9.11 s).
    """
    from oneiro.runtime import Runtime
    from oneiro.web import create_app

    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    dead_port = int(closed.getsockname()[1])
    closed.close()
    (tmp_path / "settings.json").write_text(json.dumps({"graph.port": dead_port}),
                                            encoding="utf-8")
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    with TestClient(create_app(Runtime())) as client:
        for route in ("/api/tasks", "/api/schedules"):
            started = time.monotonic()
            response = client.get(route)
            elapsed = time.monotonic() - started
            assert response.status_code == 503, f"{route}: {response.status_code}"
            assert elapsed < 8.0, f"{route} took {elapsed:.1f}s with an unreachable graph"
            assert response.headers["content-type"].startswith("application/json")
