"""Offline fakes shared by the chat, memory and search tests.

The graph is the real RecordStore over an in-memory link graph, and the stub
answers operations the way the graph worker answers them (same result shapes,
same error codes), so the behaviour under test is the production path. The model
is a stub at the `chat_reply` seam.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from oneiro import config, web
from oneiro.chat import ChatError
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
    """Point settings, data and keys at the test's directory; no real secrets read."""
    monkeypatch.setenv("ONEIRO_SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setenv("ONEIRO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("ONEIRO_KEYS_FILE", str(tmp_path / "no-keys.env"))
    monkeypatch.setattr(config, "PROJECT_ENV", tmp_path / "no-project.env")
    monkeypatch.setenv("ONEIRO_LLM_API_KEY", SECRET)
    monkeypatch.setenv("ONEIRO_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("ONEIRO_LLM_MODEL", "auto/coding")
    for name in ("ONEIRO_API_KEY", "OMNIROUTE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class Model:
    """Replaces the provider call; records each invocation and can be made to fail."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[str] = []
        self.messages: list[list[dict]] = []
        self.failure: str | None = None
        monkeypatch.setattr(web, "chat_reply", self._reply)

    def _reply(self, messages, *, base_url, api_key, model, timeout=60.0):
        self.calls.append(messages[-1]["content"])
        self.messages.append(list(messages))
        if self.failure:
            raise ChatError(self.failure)
        return f"answer:{messages[-1]['content']}"


def make_app(tmp_path: Path, links: MemoryLinks, *, scan_limit: int = 500) -> FastAPI:
    stub = GraphStub(links, tmp_path / "graph-writer.lock", scan_limit=scan_limit)
    return web.create_app(runtime=Runtime(graph=stub))


def stored_page(client: TestClient, limit: int = 500) -> dict:
    """The live store's newest page, read through the app's own graph lane."""
    return asyncio.run(client.app.state.runtime._graph.call("page", limit=limit))


def csrf_of(client: TestClient) -> str:
    return client.get("/api/session").json()["csrf"]


def post(client: TestClient, path: str, body, csrf: str):
    return client.post(path, json=body, headers={"X-Oneiro-CSRF": csrf})
