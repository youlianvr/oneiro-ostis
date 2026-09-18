"""Oneiro-OSTIS Python bridge.

Drives the OSTIS stack: initiates agent actions and reads results.
Records attempts (subject, action, object, outcome) and retrieves them
back through the C++ agents of the oneiro-module.

Usage:
    from bridge import OneiroBridge
    bridge = OneiroBridge("localhost", 8090)
    bridge.connect()
    record = bridge.record_attempt("agent1", "walk", "room3", "concept_success")
    attempts = bridge.retrieve_attempts("agent1")
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from sc_client.client import (
    connect as _client_connect,
    generate_elements,
    get_link_content,
    resolve_keynodes,
    search_by_template,
)
from sc_client.constants import sc_type
from sc_client.models import ScAddr, ScConstruction, ScIdtfResolveParams, ScTemplate
from sc_kpm.sc_keynodes import ScKeynodes

ACTION_INITIATED = "action_initiated"
ACTION_FINISHED = "action_finished"
ACTION_FINISHED_SUCCESSFULLY = "action_finished_successfully"
ACTION_FINISHED_UNSUCCESSFULLY = "action_finished_unsuccessfully"
ACTION_FINISHED_WITH_ERROR = "action_finished_with_error"
NREL_RESULT = "nrel_result"
NREL_SYSTEM_IDENTIFIER = "nrel_system_identifier"

RRELS = ["rrel_1", "rrel_2", "rrel_3", "rrel_4"]

POLL_INTERVAL = 0.1
POLL_TIMEOUT = 15.0


@dataclass
class AttemptRecord:
    """One recorded attempt of a subject."""

    subject: str
    action: str
    object: str
    outcome: str
    addr: Optional[ScAddr] = None


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
            sc_type.VAR_LINK,
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

    def record_attempt(self, subject: str, action: str, object: str, outcome: str) -> AttemptRecord:
        """Initiate action_record_attempt; the C++ agent records the attempt."""
        args = [self.resolve_entity(subject), self.resolve_entity(action), self.resolve_entity(object), self.resolve_entity(outcome)]
        action_addr = self._initiate_action("action_record_attempt", args)
        status = self._wait_for_result(action_addr)
        if status == self.keynode(ACTION_FINISHED_WITH_ERROR):
            raise RuntimeError("record_attempt finished with error")
        if status is None:
            raise TimeoutError("record_attempt timed out")

        attempt_addr = self._action_result(action_addr)
        return AttemptRecord(subject=subject, action=action, object=object, outcome=outcome, addr=attempt_addr)

    def retrieve_attempts(self, subject: str, action: Optional[str] = None) -> list[AttemptRecord]:
        """Initiate action_retrieve_attempts and decode the result structure."""
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
        return self._decode_attempts(result_struct)

    # ---------- action machinery ----------

    def _initiate_action(self, action_class_idtf: str, args: list[ScAddr]) -> ScAddr:
        """Generate an action instance with rrel-attributed arguments and initiate it."""
        action_class = self.keynode(action_class_idtf)
        initiated = self.keynode(ACTION_INITIATED)

        constr = ScConstruction()
        constr.generate_node(sc_type.CONST_NODE, "action")
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, action_class, "action", "class_arc")
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, initiated, "action", "initiated_arc")
        for i, arg in enumerate(args):
            alias = f"arg_arc_{i}"
            constr.generate_connector(sc_type.CONST_PERM_POS_ARC, "action", arg, alias)
            constr.generate_connector(
                sc_type.CONST_PERM_POS_ARC,
                self.keynode(RRELS[i]),
                alias,
            )
        addrs = generate_elements(constr)
        return addrs[constr.get_index("action")]

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
        """Decode the action result: (action -common-> result, nrel_result attribute)."""
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

    # ---------- decoding ----------

    def _decode_attempts(self, structure: ScAddr) -> list[AttemptRecord]:
        """Decode attempts from the result structure membership arcs."""
        records: list[AttemptRecord] = []
        template = ScTemplate()
        template.triple(structure, sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        found = search_by_template(template)
        for item in found:
            attempt_addr = item.get(2)
            rec = self._decode_single_attempt(attempt_addr)
            if rec is not None:
                rec.addr = attempt_addr
                records.append(rec)
        return records

    def _decode_single_attempt(self, attempt_addr: ScAddr) -> Optional[AttemptRecord]:
        subject = self._relation_value_idtf(attempt_addr, "nrel_subject")
        if subject is None:
            return None
        action = self._relation_value_idtf(attempt_addr, "nrel_action")
        object_ = self._relation_value_idtf(attempt_addr, "nrel_object")
        outcome = self._relation_value_idtf(attempt_addr, "nrel_outcome")
        return AttemptRecord(subject=subject, action=action or "", object=object_ or "", outcome=outcome or "")

    def _relation_value_idtf(self, source_addr: ScAddr, relation_idtf: str) -> Optional[str]:
        """Follow one nrel-relation from source_addr and return the target identifier."""
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
        value_addr = found[0].get(2)
        return self.idtf_of(value_addr)
