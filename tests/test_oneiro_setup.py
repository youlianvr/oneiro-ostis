"""The first-run answer is computed from live state: keep that honest offline.

`oneiro_setup` is the module the console's setup page and the chat banner both
ask whether the product is usable. It is stdlib-only on purpose, so these tests
need neither the console nor the panel: the panel is a throwaway HTTP server,
the graph is a bare listening socket, and the provider is another throwaway
server that records what was sent to it.

What matters here is not the plumbing but the judgment: which console configs
count as a usable model, when the product is not ready and why, and that a
provider is asked with the real call the chat makes - address, key and model
together - before the page tells its owner the model is fine.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT / "console" / "overlay" / "channel" / "web" / "oneiro_setup.py"


@pytest.fixture(scope="module")
def setup_module():
    """The module loaded by path: it has no importable name outside the console."""
    spec = importlib.util.spec_from_file_location("oneiro_setup", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ helpers

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Listener:
    """A port something answers on: the cheapest stand-in for sc-machine."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]

    def __enter__(self):
        return self.port

    def __exit__(self, *exc):
        self.sock.close()


class Scripted(BaseHTTPRequestHandler):
    """Answers by path from a table the test sets; records every request."""

    routes: dict = {}
    seen: list = []

    def _answer(self):
        type(self).seen.append({"path": self.path, "method": self.command,
                                "auth": self.headers.get("Authorization", "")})
        status, body = type(self).routes.get(self.path, (404, {"error": "no route"}))
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = _answer
    do_POST = _answer

    def log_message(self, *args):  # silence the test run
        pass


class StubServer:
    def __init__(self, routes: dict):
        self.handler = type("Handler", (Scripted,), {"routes": routes, "seen": []})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def seen(self):
        return self.handler.seen

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def panel_document(**overrides) -> dict:
    """The shape the panel's /api/settings returns, as read from its own code."""
    rows = {
        "llm.base_url": {"key": "llm.base_url", "value": "http://127.0.0.1:20128/v1", "set": True},
        "llm.api_key": {"key": "llm.api_key", "value": "", "set": True, "secret": True},
        "llm.model": {"key": "llm.model", "value": "auto/coding", "set": True},
        "graph.host": {"key": "graph.host", "value": "localhost", "set": False},
        "graph.port": {"key": "graph.port", "value": 8090, "set": False},
    }
    for key, change in overrides.items():
        rows[key] = dict(rows.get(key, {"key": key}), **change)
    return {"path": "/home/user/.openclaw/oneiro/settings.json",
            "settings": list(rows.values())}


# ------------------------------------------------------------------ the console side

def test_an_empty_console_config_has_no_model(setup_module):
    state = setup_module.model_state({})
    assert state["configured"] is False
    assert state["provider_id"] == ""
    assert "ключ" in state["detail"] or "нет ни своего" in state["detail"]


def test_a_complete_custom_provider_is_a_usable_model(setup_module):
    config = {
        "bot_type": "custom:oneiro",
        "custom_providers": [{"id": "oneiro", "name": "Oneiro",
                              "api_base": "http://127.0.0.1:20128/v1",
                              "api_key": "sk-test", "model": "auto/coding"}],
    }
    state = setup_module.model_state(config)
    assert state["configured"] is True
    # The id the console generated, so the page can edit this provider later
    # instead of quietly adding another one with the same name.
    assert state["provider_id"] == "oneiro"
    assert (state["provider"], state["base_url"], state["model"], state["key_set"]) == (
        "Oneiro", "http://127.0.0.1:20128/v1", "auto/coding", True)


@pytest.mark.parametrize("missing", ["api_base", "api_key", "model"])
def test_a_custom_provider_missing_one_part_is_not_usable(setup_module, missing):
    entry = {"id": "oneiro", "name": "Oneiro", "api_base": "http://127.0.0.1:20128/v1",
             "api_key": "sk-test", "model": "auto/coding"}
    entry.pop(missing)
    state = setup_module.model_state({"bot_type": "custom:oneiro", "custom_providers": [entry]})
    assert state["configured"] is False
    russian = {"api_base": "адрес", "api_key": "ключ", "model": "модель"}[missing]
    assert russian in state["detail"]


def test_an_active_custom_provider_that_vanished_is_not_usable(setup_module):
    state = setup_module.model_state({"bot_type": "custom:oneiro"})
    assert state["configured"] is False
    assert "не найден" in state["detail"]


def test_a_builtin_provider_key_counts_and_the_legacy_custom_key_does_not(setup_module):
    builtin = setup_module.model_state({"openai_api_key": "sk-builtin", "custom_api_key": "sk-legacy"})
    assert builtin["configured"] is True and builtin["key_set"] is True
    assert "openai_api_key" in builtin["detail"]

    legacy = setup_module.model_state({"custom_api_key": "sk-legacy"})
    assert legacy["configured"] is False


def test_stored_key_returns_the_key_the_chat_would_use(setup_module):
    custom = {"bot_type": "custom:oneiro",
              "custom_providers": [{"id": "oneiro", "api_key": "sk-custom"}]}
    assert setup_module.stored_key(custom) == "sk-custom"
    assert setup_module.stored_key({"openai_api_key": "sk-builtin"}) == "sk-builtin"
    assert setup_module.stored_key({}) == ""


# ------------------------------------------------------------------ the panel side

def test_panel_base_is_read_from_the_launchers_proxy_spec(setup_module):
    assert setup_module.panel_base("/oneiro=http://127.0.0.1:8130") == "http://127.0.0.1:8130"
    assert setup_module.panel_base("/oneiro=http://127.0.0.1:9999/") == "http://127.0.0.1:9999"
    assert setup_module.panel_base("/other=http://127.0.0.1:1111,/oneiro=http://127.0.0.1:8130") \
        == "http://127.0.0.1:8130"
    assert setup_module.panel_base("") == setup_module.PANEL_FALLBACK


def test_panel_state_reads_rows_and_where_the_settings_live(setup_module):
    with StubServer({"/api/settings": (200, panel_document())}) as stub:
        state = setup_module.panel_state(stub.base)
    assert state["reachable"] is True
    assert state["settings_path"] == "/home/user/.openclaw/oneiro/settings.json"
    assert state["llm"] == {"base_url": True, "api_key": True, "model": True}
    assert state["graph"] == {"host": "localhost", "port": 8090}


def test_panel_state_reports_an_unset_key_instead_of_inventing_one(setup_module):
    document = panel_document(**{"llm.api_key": {"set": False}})
    with StubServer({"/api/settings": (200, document)}) as stub:
        state = setup_module.panel_state(stub.base)
    assert state["llm"]["api_key"] is False
    assert state["llm"]["base_url"] is True


def test_panel_state_with_nobody_home_is_not_reachable(setup_module):
    state = setup_module.panel_state(f"http://127.0.0.1:{free_port()}", timeout=1.0)
    assert state["reachable"] is False
    assert state["base"].startswith("http://127.0.0.1:")
    assert state["detail"]


# ------------------------------------------------------------------ the graph

def test_graph_state_needs_the_machine_port_to_connect(setup_module):
    with Listener() as machine:
        with Listener() as web:
            state = setup_module.graph_state("127.0.0.1", machine, web_port=web)
    assert state["reachable"] is True and state["web_reachable"] is True

    state = setup_module.graph_state("127.0.0.1", free_port(), web_port=free_port())
    assert state["reachable"] is False and state["web_reachable"] is False
    assert "не отвечает" in state["detail"]


def test_graph_state_falls_back_to_the_default_port_on_nonsense(setup_module):
    state = setup_module.graph_state("127.0.0.1", "not a port", web_port=free_port())
    assert state["port"] == 8090


def test_start_graph_without_a_project_directory_says_so(setup_module, tmp_path):
    result = setup_module.start_graph(str(tmp_path / "missing"))
    assert result["ok"] is False
    assert "каталог проекта" in result["detail"]


def test_start_graph_without_docker_says_so(setup_module, monkeypatch):
    def no_docker(*args, **kwargs):
        raise FileNotFoundError("docker")
    monkeypatch.setattr(setup_module.subprocess, "run", no_docker)
    result = setup_module.start_graph(str(PROJECT))
    assert result["ok"] is False
    assert "docker" in result["detail"]


# ------------------------------------------------------------------ the answer

def _state(ready_model=True, ready_graph=True, ready_panel=True) -> dict:
    return {
        "model": {"configured": ready_model, "detail": "модель"},
        "graph": {"reachable": ready_graph, "detail": "граф",
                  "host": "localhost", "port": 8090},
        "panel": {"reachable": ready_panel, "detail": "панель"},
    }


def test_readiness_lists_every_missing_piece_in_order(setup_module):
    answer = setup_module.readiness(_state(False, False, False))
    assert answer["ready"] is False
    assert [item["id"] for item in answer["missing"]] == ["model", "graph", "panel"]
    for item in answer["missing"]:
        assert item["title"] and item["fix"]          # every problem carries a way out


def test_readiness_is_silent_when_everything_answers(setup_module):
    answer = setup_module.readiness(_state())
    assert answer == {"ready": True, "missing": []}


def test_status_composes_the_three_answers(setup_module):
    with StubServer({"/api/settings": (200, panel_document())}) as stub:
        state = setup_module.status({}, f"/oneiro={stub.base}")
    # The panel is the fake; the graph is whatever this machine really has on
    # 8090 and 8000 - so only the panel and model sides are asserted here.
    assert state["panel"]["reachable"] is True
    assert state["panel"]["settings_path"]
    assert state["model"]["configured"] is False
    assert "model" in [item["id"] for item in state["missing"]]
    assert state["ready"] is False


# ------------------------------------------------------------------ verification

def test_verify_model_asks_the_provider_the_way_the_chat_would(setup_module):
    with StubServer({"/v1/chat/completions": (200, {"choices": [{"message": {"content": "p"}}]})}) as stub:
        result = setup_module.verify_model(stub.base + "/v1", "sk-test", "auto/coding")
    assert result["ok"] is True and result["via"] == "chat/completions"
    sent = stub.seen[0]
    assert sent["auth"] == "Bearer sk-test"
    assert sent["path"] == "/v1/chat/completions"


def test_verify_model_accepts_a_provider_that_lists_models_instead(setup_module):
    routes = {"/v1/models": (200, {"data": [{"id": "auto/coding"}]})}
    with StubServer(routes) as stub:
        result = setup_module.verify_model(stub.base + "/v1", "sk-test", "auto/coding")
    assert result["ok"] is True and result["via"] == "models"
    assert "без запроса к модели" in result["detail"]


def test_verify_model_reports_what_the_provider_said(setup_module):
    routes = {"/v1/chat/completions": (401, {"error": {"message": "bad key"}}),
              "/v1/models": (401, {"error": {"message": "bad key"}})}
    with StubServer(routes) as stub:
        result = setup_module.verify_model(stub.base + "/v1", "sk-wrong", "auto/coding")
    assert result["ok"] is False and result["status"] == 401
    assert "bad key" in result["detail"]


def test_verify_model_needs_all_three_parts(setup_module):
    result = setup_module.verify_model("", "", "")
    assert result["ok"] is False
    assert "адрес, ключ и модель" in result["detail"]
