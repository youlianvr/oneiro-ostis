"""Thin sc-client 0.4.0 adapter; all memory stays in the OSTIS graph.

sc-client owns a process-global socket. Use this in a dedicated graph worker,
not alongside an independent bridge connection in the same process. Runtime
coordination/connection timeout supervision belongs outside this synchronous seam.
"""
from __future__ import annotations

import importlib
from collections import OrderedDict
from typing import Any

from oneiro.query import GraphQueryError
from oneiro.store import MAX_LINK_BYTES

KINDS = ("record", "conversation_message", "task", "run", "action", "decision",
         "note", "experience", "experiment", "release", "curated_fact",
         "question", "approval", "schedule")
RELATIONS = ("nrel_oneiro_previous", "nrel_oneiro_previous_revision", "nrel_oneiro_publication")


ADDRESS_CACHE_LIMIT = 1024


class ScLinkGraph:
    def __init__(self) -> None:
        # Rebuildable, bounded process-local address cache, never payload/state
        # truth. A new connection must use a new adapter; graph-worker does so.
        self._addresses: OrderedDict[str, Any] = OrderedDict()
        # Optional graph dependency: importing the package without it is safe.
        try:
            self.client: Any = importlib.import_module("sc_client.client")
            self.models: Any = importlib.import_module("sc_client.models")
            self.types: Any = importlib.import_module("sc_client.constants.sc_type")
        except ImportError:
            raise GraphQueryError("client_missing", "install the locked graph dependency group") from None

    def _call(self, name: str, *args: Any) -> Any:
        try:
            return getattr(self.client, name)(*args)
        except Exception as exc:
            raise GraphQueryError("server_unreachable", f"{name} failed ({type(exc).__name__})") from None

    def _resolve(self, name: str, sc_type: Any = None) -> Any:
        address = self._addresses.get(name)
        if address is None:
            addresses = self._call("resolve_keynodes", {"idtf": name, "type": sc_type})
            if len(addresses) != 1:
                raise GraphQueryError("protocol_error", "resolve returned unexpected address count")
            address = addresses[0]
            if not address.is_valid():
                return None
            self._addresses[name] = address
            if len(self._addresses) > ADDRESS_CACHE_LIMIT:
                self._addresses.popitem(last=False)
        else:
            self._addresses.move_to_end(name)
        if sc_type is not None:
            actual = self._call("get_elements_types", address)
            if len(actual) != 1 or actual[0] != sc_type:
                raise GraphQueryError("ontology_type_mismatch", f"wrong sc-type for {name}")
        return address

    def read(self, name: str) -> str | None:
        address = self._resolve(name)
        if address is None:
            return None
        actual = self._call("get_elements_types", address)
        if actual != [self.types.CONST_NODE_LINK]:
            raise GraphQueryError("ontology_type_mismatch", f"{name} is not a constant link")
        content = self._call("get_link_content", address)
        if len(content) != 1 or content[0].data is None:
            # A named link may have been created just before a crash. Empty is
            # not absence: recovery must decide using the pending publication.
            return ""
        text = content[0].data
        if not isinstance(text, str):
            raise GraphQueryError("record_unreadable", f"non-text graph link {name}")
        if len(text.encode("utf-8")) > MAX_LINK_BYTES:
            raise GraphQueryError("record_too_large", f"oversized graph link {name}")
        return text

    def write(self, name: str, text: str) -> None:
        if len(text.encode("utf-8")) > MAX_LINK_BYTES:
            raise GraphQueryError("record_too_large", "oversized graph write")
        address = self._resolve(name)
        if address is None:
            # Content exists before its system identifier is published. A
            # partially generated construction can leave anonymous orphans,
            # but never an empty named head masquerading as an empty stream.
            identifier_relation = self._resolve("nrel_system_identifier", self.types.CONST_NODE_NON_ROLE)
            construction = self.models.ScConstruction()
            construction.generate_link(self.types.CONST_NODE_LINK,
                self.models.ScLinkContent(text, self.models.ScLinkContentType.STRING), "value")
            construction.generate_link(self.types.CONST_NODE_LINK,
                self.models.ScLinkContent(name, self.models.ScLinkContentType.STRING), "identifier")
            construction.generate_connector(self.types.CONST_COMMON_ARC, "value", "identifier", "id_arc")
            construction.generate_connector(self.types.CONST_PERM_POS_ARC, identifier_relation, "id_arc")
            self._call("generate_elements", construction)
            if self.read(name) != text:
                raise GraphQueryError("readback_failed", "new named link not confirmed")
            return
        actual = self._call("get_elements_types", address)
        if actual != [self.types.CONST_NODE_LINK]:
            raise GraphQueryError("ontology_type_mismatch", f"{name} is not a constant link")
        content = self.models.ScLinkContent(text, self.models.ScLinkContentType.STRING, address)
        if not self._call("set_link_contents", content):
            raise GraphQueryError("write_failed", "set_link_contents did not confirm the write")

    def address(self, name: str) -> int:
        address = self._resolve(name)
        if address is None:
            raise GraphQueryError("record_unreadable", f"missing graph identifier {name}")
        return int(address.value)

    def _arc_once(self, source: Any, target: Any, relation: Any = None) -> None:
        template = self.models.ScTemplate()
        if relation is None:
            # Membership checks must start at the low-degree record endpoint,
            # not the class with 100k outgoing memberships. Filter the returned
            # incoming class arcs against the concrete class afterwards.
            template.triple(self.types.VAR_NODE_CLASS, self.types.VAR_PERM_POS_ARC, target)
        else:
            template.triple_with_relation(source, self.types.VAR_COMMON_ARC, target,
                                          relation, self.types.VAR_PERM_POS_ARC)

        def matches() -> list[Any]:
            results = self._call("search_by_template", template)
            return [row for row in results if row.get(0) == source] if relation is None else results

        found = matches()
        if len(found) > 1:
            raise GraphQueryError("duplicate_relation", "duplicate concrete graph relation")
        if found:
            return
        construction = self.models.ScConstruction()
        if relation is None:
            construction.generate_connector(self.types.CONST_PERM_POS_ARC, source, target)
        else:
            construction.generate_connector(self.types.CONST_COMMON_ARC, source, target, "arc")
            construction.generate_connector(self.types.CONST_PERM_POS_ARC, relation, "arc")
        self._call("generate_elements", construction)
        if len(matches()) != 1:
            raise GraphQueryError("readback_failed", "graph relation write not confirmed")

    def relate(self, source: str, target: str, relation: str) -> None:
        if relation not in RELATIONS:
            raise GraphQueryError("bad_relation", "undeclared publication relation")
        a, b = self._resolve(source), self._resolve(target)
        if a is None or b is None:
            raise GraphQueryError("record_unreadable", "relation endpoint is missing")
        r = self._resolve(relation, self.types.CONST_NODE_NON_ROLE)
        self._arc_once(a, b, r)

    def classify(self, name: str, kind: str) -> None:
        if kind not in KINDS:
            raise GraphQueryError("bad_kind", "undeclared record kind")
        record = self._resolve(name)
        if record is None:
            raise GraphQueryError("record_unreadable", "classification endpoint is missing")
        cls = self._resolve("concept_oneiro_" + kind, self.types.CONST_NODE_CLASS)
        self._arc_once(cls, record)

    def checkpoint(self) -> dict[str, Any]:
        """Request native Save and wait for observed completion, not just RAM.

        The coordinator must hold the sole writer lane for this entire call.
        Save is not crash-atomic; retain the last verified independent snapshot.
        Parent graph-worker enforces a hard deadline even for a stuck RPC.
        """
        import time
        action_class = self._resolve("action_oneiro_save_memory")
        initiated = self._resolve("action_initiated")
        finished = self._resolve("action_finished")
        success = self._resolve("action_finished_successfully")
        if any(a is None for a in (action_class, initiated, finished, success)):
            raise GraphQueryError("checkpoint_unavailable", "native Save action vocabulary is missing")
        construction = self.models.ScConstruction()
        construction.generate_node(self.types.CONST_NODE, "action")
        construction.generate_connector(self.types.CONST_PERM_POS_ARC, action_class, "action")
        construction.generate_connector(self.types.CONST_PERM_POS_ARC, initiated, "action")
        start = time.monotonic()
        addresses = self._call("generate_elements", construction)
        action = addresses[0]

        def has(source: Any) -> bool:
            template = self.models.ScTemplate()
            template.triple(source, self.types.VAR_PERM_POS_ARC, action)
            return bool(self._call("search_by_template", template))

        deadline = start + 60
        while time.monotonic() < deadline:
            if has(finished):
                if not has(success):
                    raise GraphQueryError("checkpoint_failed", "native Save action did not succeed")
                return {"saved": True, "seconds": time.monotonic() - start,
                        "crash_atomic": False, "action_address": int(action.value)}
            time.sleep(0.02)
        raise GraphQueryError("checkpoint_timeout", "Save completion unobserved; durability unknown")

    def ensure_ontology(self) -> dict[str, str]:
        """Typed additive migration; reject mismatches instead of faking types."""
        result: dict[str, str] = {}
        for name in KINDS:
            identifier = "concept_oneiro_" + name
            self._resolve(identifier, self.types.CONST_NODE_CLASS)
            result[identifier] = "CONST_NODE_CLASS"
        for identifier in RELATIONS:
            self._resolve(identifier, self.types.CONST_NODE_NON_ROLE)
            result[identifier] = "CONST_NODE_NON_ROLE"
        return result
