"""Offline fakes shared by the chat, memory and search tests.

The graph is the real RecordStore over an in-memory link graph, and the stub
answers operations the way the graph worker answers them (same result shapes,
same error codes), so the behaviour under test is the production path. The model
is a stub at the registry's transport seam, so everything between the turn and the
provider — which model a role uses, the retries, the accounting — is the real one.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from oneiro import agent, config, models, web
from oneiro.chat import ChatError, ModelReply, ToolCall
from oneiro.records import decode
from oneiro.runtime import Runtime
from oneiro.store import RecordStore

SECRET = "sk-chat-slice-secret-value"


class MemoryLinks:
    """The LinkGraph protocol the store needs, held in a dict that outlives an app."""

    def __init__(self) -> None:
        self.links: dict[str, str] = {}
        self.addresses: dict[str, int] = {}
        self.relations: set[tuple[str, str, str]] = set()
        self.classes: set[tuple[str, str]] = set()

    def read(self, name: str) -> str | None:
        return self.links.get(name)

    def write(self, name: str, text: str) -> None:
        self.links[name] = text

    def address(self, name: str) -> int:
        return self.addresses.setdefault(name, len(self.addresses) + 1)

    def relate(self, source: str, target: str, relation: str) -> None:
        self.relations.add((source, target, relation))

    def classify(self, name: str, kind: str) -> None:
        self.classes.add((name, kind))

    def checkpoint(self) -> dict:
        return {"saved": True}


class GraphStub:
    """Answers the graph worker's operations over a real RecordStore."""

    def __init__(self, links: MemoryLinks, lease_path: Path, *, scan_limit: int = 500) -> None:
        self.store = RecordStore(links, "oneiro", lease_path, scan_limit=scan_limit)
        self.store.__enter__()

    async def call(self, operation: str, **arguments):
        if operation == "append":
            publication = self.store.append(
                decode(arguments["record"]), arguments["operation_id"],
                expected_revision=arguments.get("expected_revision", 0))
            return {"entry": publication.entry, "address": publication.address,
                    "sequence": publication.sequence, "revision": publication.revision,
                    "record": publication.record.to_dict(), "duplicate": publication.duplicate,
                    "durable": publication.durable}
        if operation == "entity":
            record = self.store.entity(arguments["record_id"])
            return record.to_dict() if record is not None else None
        if operation == "page":
            # The worker's exact shape: asdict(QueryPage), cursor included.
            return asdict(self.store.page(cursor=arguments.get("cursor"),
                                          limit=arguments.get("limit")))
        raise AssertionError(f"unexpected graph operation {operation}")

    async def close(self) -> None:
        self.store.close()


def isolate(tmp_path: Path, monkeypatch) -> None:
    """Point settings, data, keys and the MCP list at the test's directory."""
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ONEIRO_KEYS_FILE", str(tmp_path / "no-keys.env"))
    # The MCP list is the owner's, and an enabled server there is started at launch:
    # a test must never spawn the owner's servers, so the list points at nothing here.
    monkeypatch.setenv("ONEIRO_MCP_FILE", str(tmp_path / "mcp.json"))
    monkeypatch.setattr(config, "PROJECT_ENV", tmp_path / "no-project.env")
    monkeypatch.setenv("ONEIRO_LLM_API_KEY", SECRET)
    monkeypatch.setenv("ONEIRO_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("ONEIRO_LLM_MODEL", "auto/coding")
    for name in ("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class Model:
    """Replaces the provider call; records each invocation and can be made to fail.

    The stub sits at the registry's transport seam (`oneiro.models.TRANSPORT`), so the turn
    under test is the production one: the same provider list, the same model per role, the
    same bounded retries, the same records and the same accounting. Each call also keeps
    the tool declarations it was offered, which is how a test can assert what the model was
    actually allowed to ask for.

    A failure raised here is a `ChatError` with `retryable` unset, so it is the kind a
    provider answers once: a test that wants the retry path raises one with `retryable=True`
    or uses a real stub server.
    """

    def __init__(self, monkeypatch, replies: list | None = None) -> None:
        self.calls: list[str] = []
        self.messages: list[list[dict]] = []
        self.offered: list[list[dict] | None] = []
        self.models: list[str] = []
        self.failure: str | None = None
        self.replies = list(replies or [])
        monkeypatch.setattr(models, "TRANSPORT", self._call)

    def _call(self, messages, *, base_url, api_key, model, tools=None, timeout=60.0):
        self.calls.append(messages[-1]["content"])
        self.messages.append(list(messages))
        self.offered.append(tools)
        self.models.append(model)
        if self.failure:
            raise ChatError(self.failure)
        if self.replies:
            item = self.replies.pop(0)
            if isinstance(item, Exception):      # scripted mid-turn provider failure
                raise item
            return item
        return ModelReply(f"answer:{messages[-1]['content']}")

    @staticmethod
    def tool(name: str, arguments: dict, call_id: str = "call-1") -> ModelReply:
        """One scripted tool request, with no assistant text."""
        return ModelReply("", (ToolCall(call_id, name, arguments),))


def make_app(tmp_path: Path, links: MemoryLinks, *, scan_limit: int = 500) -> FastAPI:
    """The app under test, with the background clock off.

    A scheduler that ticks while a test is asserting makes the suite depend on
    timing; the clock is started by the product's own entrypoint and is tested
    where it belongs, in `test_schedule.py`.
    """
    stub = GraphStub(links, tmp_path / "graph-writer.lock", scan_limit=scan_limit)
    return web.create_app(runtime=Runtime(graph=stub), scheduler=False)


def stored_page(client: TestClient, limit: int = 500) -> dict:
    """The live store's newest page, read through the app's own graph lane."""
    return asyncio.run(client.app.state.runtime._graph.call("page", limit=limit))


def csrf_of(client: TestClient) -> str:
    return client.get("/api/session").json()["csrf"]


def post(client: TestClient, path: str, body, csrf: str):
    return client.post(path, json=body, headers={"X-Oneiro-CSRF": csrf})
