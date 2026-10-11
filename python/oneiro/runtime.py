"""Application lifecycle and prerequisites, not a fake substitute agent."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import socket
import time
import uuid
from typing import Any

from oneiro import __version__
from oneiro import config, models
from oneiro.ownership import FileLease
from oneiro.graph_worker import GraphWorker
from oneiro.query import GraphQueryError


class Runtime:
    def __init__(self, graph: GraphWorker | None = None) -> None:
        self.instance_id = uuid.uuid4().hex
        self.started_at: float | None = None
        #: Set only by a real provider call that came back. `assistant_ready`
        #: and `model.verified` read this, so neither can claim a capability
        #: that was never exercised.
        self.model_verified = False
        self.model_used_tools = False
        #: Set only by a probe that showed the model accepted an image.
        self.model_vision = False
        self.model_verification: dict[str, Any] | None = None
        self._lease: FileLease | None = None
        self._probe_lock = asyncio.Lock()
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._graph = graph

    async def start(self) -> None:
        if self._lease is not None:
            raise RuntimeError("Runtime already started")
        lease = FileLease(config.data_root() / "runtime.lock")
        lease.acquire()
        self._lease = lease
        try:
            if self._graph is None:
                host, port = str(config.value("graph.host")), int(config.value("graph.port"))
                self._graph = GraphWorker(f"ws://{host}:{port}/ws_json", "product",
                                          config.data_root() / "graph-writer.lock")
        except BaseException:
            lease.release()
            self._lease = None
            raise
        self.started_at = time.time()

    async def close(self) -> None:
        if self._graph is not None:
            await self._graph.close()
            self._graph = None
        if self._lease is not None:
            self._lease.release()
            self._lease = None
        self.started_at = None

    async def memory_page(self, *, cursor: str | None = None, limit: int | None = None) -> dict[str, Any]:
        if self._graph is None:
            raise GraphQueryError("store_closed", "runtime is not started")
        return await self._graph.call("page", cursor=cursor, limit=limit)

    async def memory_entity(self, record_id: str) -> dict[str, Any] | None:
        if self._graph is None:
            raise GraphQueryError("store_closed", "runtime is not started")
        return await self._graph.call("entity", record_id=record_id)

    async def chat_append(self, record: dict[str, Any], operation_id: str) -> dict[str, Any]:
        """Publish a new conversation record once per operation ID."""
        return await self.publish(record, operation_id)

    async def publish(self, record: dict[str, Any], operation_id: str, *,
                      expected_revision: int = 0) -> dict[str, Any]:
        """Publish one revision once per operation ID; updates must name the prior revision.

        The store answers a repeated operation with its original publication and
        refuses a stale expected revision, so callers may retry safely.
        """
        if self._graph is None:
            raise GraphQueryError("store_closed", "runtime is not started")
        return await self._graph.call("append", record=record, operation_id=operation_id,
                                      expected_revision=expected_revision)

    async def status(self, *, refresh: bool = False) -> dict[str, Any]:
        async with self._probe_lock:
            if self._cached is None or refresh or time.monotonic() - self._cached_at > 5:
                self._cached = await asyncio.to_thread(self._inspect)
                self._cached_at = time.monotonic()
            model = dict(self._cached["model"])
            model["verified"] = self.model_verified
            model["used_tools"] = self.model_used_tools
            model["vision"] = self.model_vision
            # The ledger lives with the process, so the count is current even though the
            # rest of the document is cached for a few seconds.
            model["calls"] = models.registry().report()["totals"]
            if self.model_verified:
                model.pop("reason_code", None)
            blocked = list(self._cached["blocked"])
            if not self.model_verified:
                blocked.append({"code": "blocked.model_unverified"})
            return {**self._cached, "model": model, "blocked": blocked,
                    "instance_id": self.instance_id,
                    "running": self._lease is not None, "version": __version__}

    async def verify_model(self, *, role: str = "manager",
                           timeout: float = 60.0) -> dict[str, Any]:
        """Ask the providers what they list and the models what they can really do.

        This is the only thing that may set `model_verified`, and everything it reports
        was observed in this call: the model list each provider gave, whether the model
        the role uses answered, asked for the offered tool and accepted an image, and
        whether each fallback could serve a call that offers tools. What a provider
        *advertises* about its models is printed beside what was seen, never instead.

        A model that answers but asks for no tool proves that conversation works and
        leaves tool use unproven; both are said, and `verified` follows the answer alone.
        """
        registry = models.registry()
        report: dict[str, Any] = {"role": role, "providers": [], "fallback": [],
                                  "tools_offered": [models.PROBE_TOOL["function"]["name"]]}
        try:
            providers = registry.providers()
        except models.ModelError as exc:
            report.update({"verified": False, "answered": False, "used_tools": False,
                           "vision": False, "reason": str(exc)})
            self._remember(report)
            return report

        model = registry.model_for(role)
        report["model"] = model
        for provider in providers:
            # One renderer for what a provider declares, shared with `/api/status`, so the
            # two surfaces cannot describe the same provider differently.
            described = registry.describe(provider)
            if provider.discover_models:
                try:
                    found = await asyncio.to_thread(registry.discover, provider,
                                                    timeout=min(models.DISCOVER_TIMEOUT,
                                                                timeout))
                except models.ModelError as exc:
                    described["model_list"] = f"could not be read: {exc}"
                else:
                    described["model_list"] = f"{len(found.models)} models"
                    described["lists_the_role_model"] = model in found.models
                    described["advertises"] = {
                        need: found.says(model, need) for need in models.CAPABILITIES}
            report["providers"].append(described)

        try:
            provider, name = registry.resolve(model)
        except models.ModelError as exc:
            report.update({"verified": False, "answered": False, "used_tools": False,
                           "vision": False, "reason": str(exc)})
            self._remember(report)
            return report

        # The same probes the fallback rule uses, on the model the role uses: the report
        # and the call path must not be able to disagree about what a model was seen to do.
        capability = await asyncio.to_thread(
            registry.probe, provider, name, needs=models.CAPABILITIES,
            timeout=min(models.PROBE_TIMEOUT, timeout))
        report["used_tools"] = bool(capability.says("tools"))
        report["vision"] = bool(capability.says("vision"))
        report["answered"] = capability.answered
        report["verified"] = capability.answered
        report["probes"] = [capability.to_dict()]
        if capability.notes:
            report["notes"] = list(capability.notes)

        try:
            entries = list(config.value("models.fallback") or [])
        except ValueError as exc:                    # a hand-edited list that cannot be read
            entries = []
            report["fallback"] = [{"reference": "", "usable_for_tools": False,
                                   "why": f"models.fallback cannot be read: {exc}"}]
        for entry in entries[:models.MAX_FALLBACK]:
            try:
                other, other_model = registry.resolve(str(entry))
            except models.ModelError as exc:
                report["fallback"].append({"reference": str(entry),
                                           "usable_for_tools": False,
                                           "why": f"it cannot be resolved: {exc}"})
                continue
            why = await asyncio.to_thread(registry.verdict, other, other_model, ("tools",),
                                          timeout=min(models.PROBE_TIMEOUT, timeout))
            report["fallback"].append({"reference": str(entry),
                                       "provider": other.name, "model": other_model,
                                       "usable_for_tools": not why,
                                       "why": why or "a real call showed it can call tools"})
            probed = next((item for item in registry.capabilities()
                           if item.provider == other.name and item.model == other_model), None)
            if probed is not None and probed.to_dict() not in report["probes"]:
                report["probes"].append(probed.to_dict())

        report["accounting"] = registry.report()
        self._remember(report)
        return report

    def _remember(self, report: dict[str, Any]) -> None:
        """Keep the verification for `/api/status`, and claim only what it shows."""
        self.model_verified = bool(report.get("verified"))
        self.model_used_tools = bool(report.get("used_tools"))
        self.model_vision = bool(report.get("vision"))
        self.model_verification = report

    @staticmethod
    def _inspect() -> dict[str, Any]:
        # A TCP probe proves reachability only. It does not validate vocabulary,
        # graph persistence, provider authorization, model tools or vision.
        host = str(config.value("graph.host"))
        port = int(config.value("graph.port"))
        try:
            with socket.create_connection((host, port), timeout=0.5):
                reachable = True
        except OSError:
            reachable = False
        dependencies = {name: importlib.util.find_spec(name) is not None
                        for name in ("sc_client", "sc_kpm", "websocket")}
        # The registry knows the providers, the model per role and what was really probed;
        # this reads it without asking anyone anything, so a status page cannot become a
        # provider call and cannot claim more than the probes that ran.
        facts = models.registry().facts()
        first = facts["providers"][0] if facts["providers"] else {}
        return {
            "ready": False,
            "phase": "agent",
            "memory": {"required": "OSTIS", "tcp_reachable": reachable,
                       "verified": False, "fallback": None},
            "model": {"configured": bool(first.get("key_found")), "verified": False,
                      "providers": facts["providers"], "roles": facts["roles"],
                      "fallback": facts["fallback"], "discovered": facts["discovered"],
                      "probed": facts["probes"], "accounting": facts["accounting"],
                      "problem": facts.get("problem", ""),
                      # A code, not a sentence: the panel prints it in the reader's
                      # language, and `i18n.REASON_KEYS` is what makes that possible.
                      "reason_code": "reason.verify_model"},
            "dependencies": dependencies,
            "docker_cli": bool(shutil.which("docker")),
            "runtime_connected": False,
            "blocked": ([{"code": "blocked.adapter_absent"}]
                        + ([] if reachable else
                           [{"code": "blocked.graph_unreachable",
                             "data": {"host": host, "port": port}}])),
            "settings_error": config.describe()["error"],
            "autostart": False,
            "pid": os.getpid(),
        }
