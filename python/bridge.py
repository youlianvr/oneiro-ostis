"""Oneiro-OSTIS Python bridge.

Drives the OSTIS stack: initiates agent actions and reads results.
Records attempts (subject, action, object, outcome) and retrieves them
back through the C++ agents of the oneiro-module.

The C++ RecordAttemptAgent creates the attempt node with the four core
relations (subject, action, object, outcome) and the chronological
nrel_prev_attempt chain. This bridge enriches each recorded attempt with
extra relations the scientific layer needs (source, kind, score, timestamp)
and reads attempts back in chronological order.

Usage:
    from bridge import OneiroBridge
    bridge = OneiroBridge("localhost", 8090)
    bridge.connect()
    record = bridge.record_attempt("agent1", "walk", "room3", "concept_success")
    attempts = bridge.retrieve_attempts("agent1")       # chronological order
    scores   = bridge.retrieve_scores("agent1")         # aligned with attempts
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from sc_client.client import (
    connect as _client_connect,
    disconnect as _client_disconnect,
    generate_elements,
    get_link_content,
    resolve_keynodes,
    search_by_template,
)
from sc_client.constants import sc_type
from sc_client.models import (
    ScAddr,
    ScConstruction,
    ScIdtfResolveParams,
    ScLinkContent,
    ScLinkContentType,
    ScTemplate,
)
from sc_kpm.sc_keynodes import ScKeynodes

ACTION_INITIATED = "action_initiated"
ACTION_FINISHED = "action_finished"
ACTION_FINISHED_SUCCESSFULLY = "action_finished_successfully"
ACTION_FINISHED_UNSUCCESSFULLY = "action_finished_unsuccessfully"
ACTION_FINISHED_WITH_ERROR = "action_finished_with_error"
NREL_RESULT = "nrel_result"
NREL_SYSTEM_IDENTIFIER = "nrel_system_identifier"

NREL_SUBJECT = "nrel_subject"
NREL_ACTION = "nrel_action"
NREL_OBJECT = "nrel_object"
NREL_OUTCOME = "nrel_outcome"
NREL_PREV_ATTEMPT = "nrel_prev_attempt"
NREL_SOURCE = "nrel_source"
NREL_KIND = "nrel_kind"
NREL_SCORE = "nrel_score"
NREL_TIMESTAMP = "nrel_timestamp"

RRELS = ["rrel_1", "rrel_2", "rrel_3", "rrel_4", "rrel_5"]

POLL_INTERVAL = 0.05
POLL_TIMEOUT = 15.0


@dataclass
class AttemptRecord:
    """One recorded attempt of a subject."""

    subject: str
    action: str
    object: str
    outcome: str
    source: Optional[str] = None
    kind: Optional[str] = None
    score: Optional[float] = None
    timestamp: Optional[int] = None
    addr: Optional[ScAddr] = None

    def core(self) -> tuple:
        """The four fields that define the attempt identity."""
        return (self.subject, self.action, self.object, self.outcome)

    def as_tuple(self) -> tuple:
        """Full tuple used for equality checks in metrics."""
        return (
            self.subject,
            self.action,
            self.object,
            self.outcome,
            self.source or "",
            self.kind or "",
            self.score,
        )


class OneiroBridge:
    """Python facade over the oneiro-module agents."""

    def __init__(self, host: str = "localhost", port: int = 8090):
        self.host = host
        self.port = port
        self._addr_to_idtf: dict[int, str] = {}

    # ---------- connection ----------

    def connect(self) -> None:
        """Open the WebSocket connection and verify the server answers."""
        _client_connect(f"ws://{self.host}:{self.port}")
        self.keynode(ACTION_INITIATED)

    def close(self) -> None:
        """Close the WebSocket connection (otherwise the process hangs on exit:
        the client's background socket threads are non-daemon)."""
        try:
            _client_disconnect()
        except Exception:
            pass

    # ---------- keynodes and idtf helpers ----------

    def keynode(self, idtf: str) -> ScAddr:
        return ScKeynodes[idtf]

    def resolve_entity(self, name: str) -> ScAddr:
        """Resolve a node by system identifier; create it (ConstNode) if missing."""
        addrs = resolve_keynodes(ScIdtfResolveParams(idtf=name, type=sc_type.CONST_NODE))
        addr = addrs[0]
        self._addr_to_idtf[addr.value] = name
        return addr

    def idtf_of(self, addr: ScAddr) -> Optional[str]:
        """Best-effort identifier of an address: cache first, then KB system idtf."""
        cached = self._addr_to_idtf.get(addr.value)
        if cached:
            return cached
        template = ScTemplate()
        template.quintuple(
            addr,
            sc_type.VAR_PERM_POS_ARC,
            sc_type.VAR_NODE_LINK,
            sc_type.VAR_PERM_POS_ARC,
            self.keynode(NREL_SYSTEM_IDENTIFIER),
        )
        found = search_by_template(template)
        if not found:
            return None
        link_addr = found[0].get(2)
        contents = get_link_content(link_addr)
        if contents and contents[0].data is not None:
            return str(contents[0].data)
        return None

    # ---------- public API ----------

    def record_attempt(
        self,
        subject: str,
        action: str,
        object: str,
        outcome: str,
        *,
        source: Optional[str] = None,
        kind: Optional[str] = None,
        score: Optional[float] = None,
        timestamp: Optional[int] = None,
        no_temporal: bool = False,
    ) -> AttemptRecord:
        """Initiate action_record_attempt; then enrich the attempt node with
        source/kind/score/timestamp relations (provenance and metrics support).

        no_temporal=True passes concept_no_temporal as rrel_5: the C++ agent
        skips nrel_prev_attempt chaining (chronology ablation).
        """
        args = [
            self.resolve_entity(subject),
            self.resolve_entity(action),
            self.resolve_entity(object),
            self.resolve_entity(outcome),
        ]
        if no_temporal:
            args.append(self.resolve_entity("concept_no_temporal"))
        action_addr = self._initiate_action("action_record_attempt", args)
        status = self._wait_for_result(action_addr)
        if status == self.keynode(ACTION_FINISHED_WITH_ERROR):
            raise RuntimeError("record_attempt finished with error")
        if status is None:
            raise TimeoutError("record_attempt timed out")

        result_struct = self._action_result(action_addr)
        attempt_addr = None
        if result_struct is not None:
            elements = self._structure_elements(result_struct)
            attempt_addr = elements[0] if elements else None
        record = AttemptRecord(
            subject=subject,
            action=action,
            object=object,
            outcome=outcome,
            source=source,
            kind=kind,
            score=score,
            timestamp=timestamp,
            addr=attempt_addr,
        )
        if attempt_addr is not None:
            self._enrich(attempt_addr, record)
        return record

    def retrieve_attempts(self, subject: str, action: Optional[str] = None) -> list[AttemptRecord]:
        """Initiate action_retrieve_attempts; returns attempts in chronological
        order (oldest first) when the prev-chain is intact, unordered otherwise."""
        args = [self.resolve_entity(subject)]
        if action is not None:
            args.append(self.resolve_entity(action))
        action_addr = self._initiate_action("action_retrieve_attempts", args)
        status = self._wait_for_result(action_addr)
        if status == self.keynode(ACTION_FINISHED_WITH_ERROR):
            raise RuntimeError("retrieve_attempts finished with error")
        if status is None:
            raise TimeoutError("retrieve_attempts timed out")

        result_struct = self._action_result(action_addr)
        if result_struct is None:
            return []
        return self._decode_attempts_ordered(result_struct)

    def retrieve_scores(self, subject: str) -> list[Optional[float]]:
        """Scores aligned with retrieve_attempts order."""
        return [r.score for r in self.retrieve_attempts(subject)]

    # ---------- enrichment ----------

    def _enrich(self, attempt_addr: ScAddr, record: AttemptRecord) -> None:
        """Attach source/kind/score/timestamp relations to the attempt node."""
        constr = ScConstruction()

        if record.source is not None:
            self._add_relation(constr, attempt_addr, NREL_SOURCE, self.resolve_entity(record.source))
        if record.kind is not None:
            self._add_relation(constr, attempt_addr, NREL_KIND, self.resolve_entity(record.kind))
        if record.score is not None:
            link_addr = self._numeric_link(record.score)
            self._add_relation(constr, attempt_addr, NREL_SCORE, link_addr)
        if record.timestamp is not None:
            link_addr = self._numeric_link(int(record.timestamp))
            self._add_relation(constr, attempt_addr, NREL_TIMESTAMP, link_addr)

        if len(constr.commands):
            generate_elements(constr)

    def _add_relation(self, constr: ScConstruction, attempt: ScAddr, relation_idtf: str, value: ScAddr) -> None:
        main_arc_alias = f"rel_arc_{relation_idtf}"
        constr.generate_connector(sc_type.CONST_COMMON_ARC, attempt, value, main_arc_alias)
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC,
            self.keynode(relation_idtf),
            main_arc_alias,
        )

    def _numeric_link(self, value: int | float) -> ScAddr:
        constr = ScConstruction()
        content = ScLinkContent(value, ScLinkContentType.INT if isinstance(value, int) else ScLinkContentType.FLOAT)
        constr.generate_link(sc_type.CONST_NODE_LINK, content, "link")
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC,
            self.resolve_entity("nrel_score_value"),
            "link",
            "score_value_arc",
        )
        addrs = generate_elements(constr)
        return addrs[constr.get_index("link")]

    # ---------- action machinery ----------

    def _initiate_action(self, action_class_idtf: str, args: list[ScAddr]) -> ScAddr:
        """Generate an action instance with rrel-attributed arguments, then initiate it.

        Two separate generations on purpose: the agent reacts to the
        `action_initiated` arc, so the action node, its class arc and all
        rrel-attributed arguments must exist in the KB *before* the initiation
        arc is generated. Building everything in one construction races with
        the agent thread (it can fire between commands and see no arguments).
        """
        action_class = self.keynode(action_class_idtf)

        constr = ScConstruction()
        constr.generate_node(sc_type.CONST_NODE, "action")
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, action_class, "action", "class_arc")
        for i, arg in enumerate(args):
            alias = f"arg_arc_{i}"
            constr.generate_connector(sc_type.CONST_PERM_POS_ARC, "action", arg, alias)
            constr.generate_connector(
                sc_type.CONST_PERM_POS_ARC,
                self.keynode(RRELS[i]),
                alias,
            )
        addrs = generate_elements(constr)
        action_addr = addrs[constr.get_index("action")]

        # Initiation is a separate request: fires the agent only when the
        # action instance is fully formed.
        init_constr = ScConstruction()
        init_constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC,
            self.keynode(ACTION_INITIATED),
            action_addr,
            "initiated_arc",
        )
        generate_elements(init_constr)
        return action_addr

    def _wait_for_result(self, action_addr: ScAddr) -> Optional[ScAddr]:
        """Poll until the action is finished; return the finished-state keynode."""
        deadline = time.time() + POLL_TIMEOUT
        statuses = [
            self.keynode(ACTION_FINISHED_SUCCESSFULLY),
            self.keynode(ACTION_FINISHED_UNSUCCESSFULLY),
            self.keynode(ACTION_FINISHED_WITH_ERROR),
        ]
        while time.time() < deadline:
            for status in statuses:
                template = ScTemplate()
                template.triple(status, sc_type.VAR_PERM_POS_ARC, action_addr)
                if search_by_template(template):
                    return status
            time.sleep(POLL_INTERVAL)
        return None

    def _action_result(self, action_addr: ScAddr) -> Optional[ScAddr]:
        """Decode the action result structure: (action -common-> structure,
        nrel_result attribute). Callers unwrap the structure's elements.
        """
        template = ScTemplate()
        template.quintuple(
            action_addr,
            sc_type.VAR_COMMON_ARC,
            sc_type.VAR_NODE,
            sc_type.VAR_PERM_POS_ARC,
            self.keynode(NREL_RESULT),
        )
        found = search_by_template(template)
        if not found:
            return None
        return found[0].get(2)

    @staticmethod
    def _structure_elements(struct: ScAddr) -> list[ScAddr]:
        """Elements of a result structure (nodes connected by arcs from it)."""
        template = ScTemplate()
        template.triple(struct, sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        return [item.get(2) for item in search_by_template(template)]

    # ---------- decoding ----------

    def _decode_attempts_ordered(self, structure: ScAddr) -> list[AttemptRecord]:
        """Decode attempts from the result structure and order them along the
        nrel_prev_attempt chain (oldest first); falls back to KB order."""
        records: dict[int, AttemptRecord] = {}
        prev_map: dict[int, int] = {}  # attempt addr value -> its previous attempt addr value

        template = ScTemplate()
        template.triple(structure, sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        found = search_by_template(template)

        for item in found:
            attempt_addr = item.get(2)
            rec = self._decode_single_attempt(attempt_addr)
            if rec is not None:
                rec.addr = attempt_addr
                records[attempt_addr.value] = rec
                prev_addr = self._prev_attempt_addr(attempt_addr)
                if prev_addr is not None:
                    prev_map[attempt_addr.value] = prev_addr.value

        if not records:
            return []

        # Walk the chain: an attempt whose prev is not in the result set is a head.
        heads = [a for a in records if prev_map.get(a) not in records]
        ordered: list[AttemptRecord] = []
        visited: set[int] = set()
        for head in heads:
            current = head
            while current is not None and current not in visited:
                visited.add(current)
                ordered.append(records[current])
                nxt = next((a for a, p in prev_map.items() if p == current), None)
                current = nxt

        # Anything not on a chain (should not happen) is appended.
        for addr, rec in records.items():
            if addr not in visited:
                ordered.append(rec)
        return ordered

    def _prev_attempt_addr(self, attempt_addr: ScAddr) -> Optional[ScAddr]:
        template = ScTemplate()
        template.quintuple(
            attempt_addr,
            sc_type.VAR_COMMON_ARC,
            sc_type.VAR_NODE,
            sc_type.VAR_PERM_POS_ARC,
            self.keynode(NREL_PREV_ATTEMPT),
        )
        found = search_by_template(template)
        if not found:
            return None
        return found[0].get(2)

    def _decode_single_attempt(self, attempt_addr: ScAddr) -> Optional[AttemptRecord]:
        subject = self._relation_value_idtf(attempt_addr, NREL_SUBJECT)
        if subject is None:
            return None
        action = self._relation_value_idtf(attempt_addr, NREL_ACTION)
        object_ = self._relation_value_idtf(attempt_addr, NREL_OBJECT)
        outcome = self._relation_value_idtf(attempt_addr, NREL_OUTCOME)
        source = self._relation_value_idtf(attempt_addr, NREL_SOURCE)
        kind = self._relation_value_idtf(attempt_addr, NREL_KIND)
        score = self._relation_value_number(attempt_addr, NREL_SCORE)
        timestamp = self._relation_value_number(attempt_addr, NREL_TIMESTAMP)
        return AttemptRecord(
            subject=subject,
            action=action or "",
            object=object_ or "",
            outcome=outcome or "",
            source=source,
            kind=kind,
            score=score,
            timestamp=timestamp,
        )

    def _relation_value_idtf(self, source_addr: ScAddr, relation_idtf: str) -> Optional[str]:
        """Follow one nrel-relation from source_addr and return the target identifier."""
        value_addr = self._relation_value_addr(source_addr, relation_idtf)
        if value_addr is None:
            return None
        return self.idtf_of(value_addr)

    def _relation_value_addr(self, source_addr: ScAddr, relation_idtf: str) -> Optional[ScAddr]:
        template = ScTemplate()
        template.quintuple(
            source_addr,
            sc_type.VAR_COMMON_ARC,
            sc_type.VAR_NODE,
            sc_type.VAR_PERM_POS_ARC,
            self.keynode(relation_idtf),
        )
        found = search_by_template(template)
        if not found:
            return None
        return found[0].get(2)

    def _relation_value_number(self, source_addr: ScAddr, relation_idtf: str) -> Optional[float]:
        # The value is a sc-link, not a node — search for the link directly
        # (VAR_NODE in _relation_value_addr does not match links).
        template = ScTemplate()
        template.quintuple(
            source_addr,
            sc_type.VAR_COMMON_ARC,
            sc_type.VAR_NODE_LINK,
            sc_type.VAR_PERM_POS_ARC,
            self.keynode(relation_idtf),
        )
        found = search_by_template(template)
        if not found:
            return None
        contents = get_link_content(found[0].get(2))
        if contents and contents[0].data is not None:
            try:
                return float(contents[0].data)
            except (TypeError, ValueError):
                return None
        return None
