"""Oneiro-OSTIS Python bridge.

Drives the OSTIS stack: initiates agent actions and reads results.
Records attempts (subject, action, object, outcome) and retrieves them
back through the C++ agents of the oneiro-module.

The C++ RecordAttemptAgent creates the attempt node with the four core
relations (subject, action, object, outcome) and the chronological
nrel_prev_attempt chain. This bridge enriches each recorded attempt with
extra relations the scientific layer needs (source, kind, score, timestamp,
and the trajectory fields the dream cycle replays: episode, step index,
world state before the attempt, legal actions before the attempt, producing
strategy, note) and reads attempts back in chronological order.

The bridge also stores strategies (descriptor JSON + replay/online scores)
as first-class graph entities of class concept_strategy.

Usage:
    from bridge import OneiroBridge
    bridge = OneiroBridge("localhost", 8090)
    bridge.connect()
    record = bridge.record_attempt("agent1", "walk", "room3", "concept_success")
    attempts = bridge.retrieve_attempts("agent1")       # chronological order
    bridge.save_strategy("greedy_cove", descriptor, replay_score=42.0)
    strategies = bridge.load_strategies()
    bridge.save_memory_sessions("lme_q1", sessions)
    sessions = bridge.load_memory_sessions("lme_q1")
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
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
from sc_client.constants.exceptions import InvalidValueError
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

# trajectory / dream-cycle relations (see knowledge-base/ontology/experience.scs)
NREL_EPISODE = "nrel_episode"
NREL_STEP_INDEX = "nrel_step_index"
NREL_STATE = "nrel_state"
NREL_LEGAL = "nrel_legal"
NREL_STRATEGY = "nrel_strategy"
NREL_NOTE = "nrel_note"
NREL_ORIGIN = "nrel_origin"
NREL_CONFIDENCE = "nrel_confidence"
NREL_SESSION_RECORD = "nrel_session_record"
NREL_ORGANIZATION_RECORD = "nrel_organization_record"
NREL_STRATEGY_DESCRIPTOR = "nrel_strategy_descriptor"
NREL_STRATEGY_REPLAY_SCORE = "nrel_strategy_replay_score"
NREL_STRATEGY_ONLINE_SCORE = "nrel_strategy_online_score"
NREL_DERIVED_FROM = "nrel_derived_from"
NREL_DREAM_ROUND = "nrel_dream_round"

CONCEPT_STRATEGY = "concept_strategy"
CONCEPT_EXPERIENCE_EVENT = "concept_experience_event"
CONCEPT_SESSION = "concept_session"
CONCEPT_ORGANIZATION_RECORD = "concept_organization_record"
SESSION_PREFIX = "session_"
ORGANIZATION_PREFIX = "organization_"

# Harness policies: the search tree of the RSI loop (a different species of
# strategy — it is a program about what the agent is shown, not a behaviour).
NREL_HARNESS_DESCRIPTOR = "nrel_harness_descriptor"
NREL_HARNESS_REPLAY_SAVING = "nrel_harness_replay_saving"
NREL_HARNESS_GATE = "nrel_harness_gate"
NREL_HARNESS_ONLINE_RESULT = "nrel_harness_online_result"
NREL_HARNESS_SEARCH_ROUND = "nrel_harness_search_round"
NREL_HARNESS_ROUND_RECORD = "nrel_harness_round_record"

CONCEPT_HARNESS = "concept_harness"
CONCEPT_HARNESS_ROUND = "concept_harness_round"

# Memory benchmark (LongMemEval): the corpus under test and the answer ledger.
# A session is a typed record: its date is a numeric relation (so a time window
# is a graph query, not a substring search), its body a JSON payload, and it
# belongs to one corpus node. A bench result is one record per question / arm /
# run, so every number in the report can be walked back to the graph.
NREL_MEMORY_CORPUS = "nrel_memory_corpus"
NREL_MEMORY_SESSION_PAYLOAD = "nrel_memory_session_payload"
NREL_MEMORY_SESSION_DATE = "nrel_memory_session_date"
NREL_MEMORY_BENCH_RESULT = "nrel_memory_bench_result"
CONCEPT_MEMORY_CORPUS = "concept_memory_corpus"
CONCEPT_MEMORY_SESSION = "concept_memory_session"
CONCEPT_MEMORY_BENCH_RESULT = "concept_memory_bench_result"
MEMORY_CORPUS_PREFIX = "memory_corpus_"
MEMORY_BENCH_RESULT_PREFIX = "memory_bench_result_"

# Vocabulary that appeared after the first live graph was built. A running
# sc-machine cannot be reloaded without clearing its accumulated graph, so the
# bridge resolves these identifiers and creates the missing ones as named
# nodes at runtime. A freshly rebuilt graph still declares them from
# knowledge-base/ontology exactly as before.
RUNTIME_VOCABULARY = (
    CONCEPT_SESSION,
    CONCEPT_ORGANIZATION_RECORD,
    NREL_SESSION_RECORD,
    NREL_ORGANIZATION_RECORD,
    NREL_ORIGIN,
    NREL_CONFIDENCE,
    CONCEPT_MEMORY_CORPUS,
    CONCEPT_MEMORY_SESSION,
    CONCEPT_MEMORY_BENCH_RESULT,
    NREL_MEMORY_CORPUS,
    NREL_MEMORY_SESSION_PAYLOAD,
    NREL_MEMORY_SESSION_DATE,
    NREL_MEMORY_BENCH_RESULT,
)

EPISODE_PREFIX = "episode_"
STRATEGY_PREFIX = "strategy_"
HARNESS_PREFIX = "harness_"
HARNESS_ROUND_PREFIX = "harness_round_"

RRELS = ["rrel_1", "rrel_2", "rrel_3", "rrel_4", "rrel_5"]

POLL_INTERVAL = 0.05
POLL_TIMEOUT = 15.0


def _safe_graph_identifier(value: str) -> str:
    """Map external ids to valid OSTIS system identifiers without losing payload ids."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(value))
    return safe if safe and safe[0].isalpha() else f"id_{safe}"


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
    # trajectory fields (dream cycle): what the world looked like before the
    # attempt, which actions were legal, which strategy produced it.
    episode: Optional[str] = None
    step_index: Optional[int] = None
    state: Optional[str] = None    # JSON snapshot {location, carrying, dug, score, steps}
    legal: Optional[str] = None    # "|" separated action strings
    strategy: Optional[str] = None # strategy name (without prefix)
    note: Optional[str] = None
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


@dataclass
class LifeSession:
    """Append-only snapshot of one autonomous agent run.

    Events may be model-authored, but every event carries its origin and
    verification state in the payload. Snapshots are immutable graph nodes;
    a later revision never overwrites an earlier one.
    """

    session_id: str
    created_at: int
    status: str = "running"
    goals: list[dict] = field(default_factory=list)
    self_state: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    revision: int = 0

    def payload(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "status": self.status,
            "goals": self.goals,
            "self_state": self.self_state,
            "events": self.events,
            "revision": self.revision,
        }


@dataclass
class OrganizationRecord:
    """One append-only event in the persistent agent organization."""

    record_id: str
    session_id: str
    role: str
    kind: str
    payload: dict = field(default_factory=dict)
    origin: str = "model"
    verified: bool = False
    recorded_at: int = 0
    revision: int = 0

    def as_payload(self) -> dict:
        return {
            "record_id": self.record_id,
            "session_id": self.session_id,
            "role": self.role,
            "kind": self.kind,
            "payload": self.payload,
            "origin": self.origin,
            "verified": self.verified,
            "recorded_at": self.recorded_at,
            "revision": self.revision,
        }


class OneiroBridge:
    """Python facade over the oneiro-module agents."""

    def __init__(self, host: str = "localhost", port: int = 8090):
        self.host = host
        self.port = port
        self._addr_to_idtf: dict[int, str] = {}
        self._episodes_classified: set[str] = set()
        self._runtime_keynodes: dict[str, ScAddr] = {}

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
        try:
            return ScKeynodes[idtf]
        except (InvalidValueError, KeyError):
            if idtf not in RUNTIME_VOCABULARY:
                raise
            cached = self._runtime_keynodes.get(idtf)
            if cached is None:
                cached = self.resolve_entity(idtf)
                self._runtime_keynodes[idtf] = cached
            return cached

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
        # idtf link hangs off addr via a common arc attributed by nrel_system_identifier:
        #   addr -> common_arc -> idtf_link ;  nrel_system_identifier -> pos_arc -> common_arc
        template = ScTemplate()
        template.triple_with_relation(
            addr,
            sc_type.VAR_COMMON_ARC,
            sc_type.VAR_NODE_LINK,
            self.keynode(NREL_SYSTEM_IDENTIFIER),
            sc_type.VAR_PERM_POS_ARC,
        )
        found = search_by_template(template)
        if not found:
            return None
        link_addr = found[0].get(2)
        contents = get_link_content(link_addr)
        if contents and contents[0].data is not None:
            idtf = str(contents[0].data)
            self._addr_to_idtf[addr.value] = idtf  # cache: the same value node
            return idtf                           # is asked once per session
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
        episode: Optional[str] = None,
        step_index: Optional[int] = None,
        state: Optional[dict] = None,
        legal: Optional[list[str]] = None,
        strategy: Optional[str] = None,
        note: Optional[str] = None,
    ) -> AttemptRecord:
        """Initiate action_record_attempt; then enrich the attempt node with
        source/kind/score/timestamp relations (provenance and metrics support)
        and — when given — the trajectory fields the dream cycle replays.

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
            episode=episode,
            step_index=step_index,
            state=json.dumps(state, sort_keys=True) if state is not None else None,
            legal="|".join(legal) if legal is not None else None,
            strategy=strategy,
            note=note,
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

    def all_subjects(self) -> list[str]:
        """Every subject that has at least one attempt recorded in the KB.

        Walks all concept_attempt members and reads their nrel_subject.
        """
        template = ScTemplate()
        template.triple(
            self.keynode("concept_attempt"),
            sc_type.VAR_PERM_POS_ARC,
            sc_type.VAR_NODE,
        )
        found = search_by_template(template)
        subjects: list[str] = []
        seen: set[int] = set()
        for item in found:
            attempt_addr = item.get(2)
            if attempt_addr.value in seen:
                continue
            seen.add(attempt_addr.value)
            subject = self._relation_value_idtf(attempt_addr, NREL_SUBJECT)
            if subject and subject not in subjects:
                subjects.append(subject)
        return sorted(subjects)

    def retrieve_scores(self, subject: str) -> list[Optional[float]]:
        """Scores aligned with retrieve_attempts order."""
        return [r.score for r in self.retrieve_attempts(subject)]

    # ---------- autonomous life sessions ----------

    def start_life_session(
        self,
        session_id: str,
        *,
        goals: Optional[list[dict]] = None,
        self_state: Optional[dict] = None,
    ) -> LifeSession:
        """Create and persist the first immutable snapshot of a life session."""
        session = LifeSession(
            session_id=session_id,
            created_at=int(time.time()),
            goals=list(goals or []),
            self_state=dict(self_state or {}),
        )
        self.persist_life_session(session)
        return session

    def record_life_event(
        self,
        session: LifeSession,
        event: dict,
        *,
        origin: str,
        verified: bool = False,
    ) -> LifeSession:
        """Append one event and persist a new snapshot.

        `origin` is mandatory so model-authored observations cannot be
        mistaken for human-confirmed facts. The earlier snapshot remains in
        the graph and can be audited after a later correction.
        """
        if not origin:
            raise ValueError("life events require an origin")
        stored = dict(event)
        stored["origin"] = origin
        stored["verified"] = bool(verified)
        stored["recorded_at"] = int(time.time())
        session.events.append(stored)
        session.revision += 1
        self.persist_life_session(session)
        return session

    def finish_life_session(
        self,
        session: LifeSession,
        *,
        self_state: Optional[dict] = None,
        status: str = "finished",
    ) -> LifeSession:
        """Persist the terminal snapshot without rewriting earlier history."""
        session.status = status
        if self_state is not None:
            session.self_state = dict(self_state)
        session.revision += 1
        self.persist_life_session(session)
        return session

    def persist_life_session(self, session: LifeSession) -> None:
        """Write one immutable, graph-native session snapshot."""
        node = self.resolve_entity(
            f"{SESSION_PREFIX}{_safe_graph_identifier(session.session_id)}_v{session.revision}"
        )
        construction = ScConstruction()
        construction.generate_connector(
            sc_type.CONST_PERM_POS_ARC,
            self.keynode(CONCEPT_SESSION),
            node,
            "session_class_arc",
        )
        self._add_json_relation(
            construction,
            node,
            NREL_SESSION_RECORD,
            session.payload(),
        )
        generate_elements(construction)

    def load_life_sessions(self) -> list[LifeSession]:
        """Load the newest snapshot for each session id from OSTIS."""
        template = ScTemplate()
        template.triple(
            self.keynode(CONCEPT_SESSION),
            sc_type.VAR_PERM_POS_ARC,
            sc_type.VAR_NODE,
        )
        latest: dict[str, LifeSession] = {}
        for item in search_by_template(template):
            node = item.get(2)
            payload = self._json_relation(node, NREL_SESSION_RECORD)
            if not isinstance(payload, dict) or not payload.get("session_id"):
                continue
            try:
                candidate = LifeSession(
                    session_id=str(payload["session_id"]),
                    created_at=int(payload.get("created_at", 0)),
                    status=str(payload.get("status", "running")),
                    goals=list(payload.get("goals", [])),
                    self_state=dict(payload.get("self_state", {})),
                    events=list(payload.get("events", [])),
                    revision=int(payload.get("revision", 0)),
                )
            except (TypeError, ValueError):
                continue
            previous = latest.get(candidate.session_id)
            if previous is None or candidate.revision > previous.revision:
                latest[candidate.session_id] = candidate
        return sorted(latest.values(), key=lambda row: (row.created_at, row.session_id))

    def load_latest_life_session(self) -> Optional[LifeSession]:
        """Return the newest session snapshot, or None for a fresh graph."""
        sessions = self.load_life_sessions()
        return sessions[-1] if sessions else None

    # ---------- persistent organization protocol ----------

    def record_organization_event(
        self,
        *,
        session_id: str,
        role: str,
        kind: str,
        payload: Optional[dict] = None,
        origin: str = "model",
        verified: bool = False,
        record_id: Optional[str] = None,
    ) -> OrganizationRecord:
        """Append one role, coordination, escalation, or PR event to OSTIS."""
        if not session_id or not role or not kind:
            raise ValueError("organization events require session_id, role, and kind")
        if not origin:
            raise ValueError("organization events require an origin")
        record = OrganizationRecord(
            record_id=record_id or f"{kind}_{int(time.time() * 1000)}",
            session_id=session_id,
            role=role,
            kind=kind,
            payload=dict(payload or {}),
            origin=origin,
            verified=bool(verified),
            recorded_at=int(time.time()),
        )
        node = self.resolve_entity(ORGANIZATION_PREFIX + _safe_graph_identifier(record.record_id))
        construction = ScConstruction()
        construction.generate_connector(
            sc_type.CONST_PERM_POS_ARC,
            self.keynode(CONCEPT_ORGANIZATION_RECORD),
            node,
            "organization_class_arc",
        )
        self._add_json_relation(
            construction,
            node,
            NREL_ORGANIZATION_RECORD,
            record.as_payload(),
        )
        generate_elements(construction)
        return record

    def load_organization_events(self, session_id: Optional[str] = None) -> list[OrganizationRecord]:
        """Read organization events from the graph in recorded order."""
        template = ScTemplate()
        template.triple(
            self.keynode(CONCEPT_ORGANIZATION_RECORD),
            sc_type.VAR_PERM_POS_ARC,
            sc_type.VAR_NODE,
        )
        records: list[OrganizationRecord] = []
        for item in search_by_template(template):
            payload = self._json_relation(item.get(2), NREL_ORGANIZATION_RECORD)
            if not isinstance(payload, dict):
                continue
            if session_id is not None and payload.get("session_id") != session_id:
                continue
            try:
                records.append(OrganizationRecord(
                    record_id=str(payload["record_id"]),
                    session_id=str(payload["session_id"]),
                    role=str(payload["role"]),
                    kind=str(payload["kind"]),
                    payload=dict(payload.get("payload", {})),
                    origin=str(payload.get("origin", "model")),
                    verified=bool(payload.get("verified", False)),
                    recorded_at=int(payload.get("recorded_at", 0)),
                    revision=int(payload.get("revision", 0)),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return sorted(records, key=lambda row: (row.recorded_at, row.record_id))

    # ---------- strategy store ----------

    def save_strategy(
        self,
        name: str,
        descriptor: dict,
        *,
        replay_score: Optional[float] = None,
        online_score: Optional[float] = None,
        derived_from: Optional[str] = None,
        dream_round: Optional[int] = None,
    ) -> str:
        """Store a strategy as a graph entity of class concept_strategy.

        descriptor → string link (JSON); scores → numeric links; derived_from
        → node of the parent strategy; dream_round → numeric link.
        """
        node = self.resolve_entity(STRATEGY_PREFIX + name)
        constr = ScConstruction()

        # class membership: concept_strategy -> strategy node
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_STRATEGY), node, "class_arc")

        # descriptor JSON as a string link
        constr.generate_link(
            sc_type.CONST_NODE_LINK,
            ScLinkContent(json.dumps(descriptor, sort_keys=True), ScLinkContentType.STRING),
            "descriptor_link",
        )
        constr.generate_connector(sc_type.CONST_COMMON_ARC, node, "descriptor_link", "descriptor_arc")
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC, self.keynode(NREL_STRATEGY_DESCRIPTOR), "descriptor_arc"
        )

        if replay_score is not None:
            self._add_numeric_relation(constr, node, NREL_STRATEGY_REPLAY_SCORE, float(replay_score))
        if online_score is not None:
            self._add_numeric_relation(constr, node, NREL_STRATEGY_ONLINE_SCORE, float(online_score))
        if dream_round is not None:
            self._add_numeric_relation(constr, node, NREL_DREAM_ROUND, int(dream_round))
        if derived_from is not None:
            parent = self.resolve_entity(STRATEGY_PREFIX + derived_from)
            arc_alias = "derived_arc"
            constr.generate_connector(sc_type.CONST_COMMON_ARC, node, parent, arc_alias)
            constr.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(NREL_DERIVED_FROM), arc_alias)

        generate_elements(constr)
        return name

    def mark_strategy_online_score(self, name: str, online_score: float) -> None:
        """Attach the online measured score to an existing strategy node."""
        node = self.resolve_entity(STRATEGY_PREFIX + name)
        constr = ScConstruction()
        self._add_numeric_relation(constr, node, NREL_STRATEGY_ONLINE_SCORE, float(online_score))
        generate_elements(constr)

    def load_strategies(self) -> list[dict]:
        """All strategy nodes of class concept_strategy with their stored fields."""
        template = ScTemplate()
        template.triple(self.keynode(CONCEPT_STRATEGY), sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        found = search_by_template(template)

        strategies: list[dict] = []
        for item in found:
            node = item.get(2)
            idtf = self.idtf_of(node) or ""
            name = idtf[len(STRATEGY_PREFIX):] if idtf.startswith(STRATEGY_PREFIX) else idtf
            descriptor_text = self._relation_value_text(node, NREL_STRATEGY_DESCRIPTOR)
            descriptor = None
            if descriptor_text:
                try:
                    descriptor = json.loads(descriptor_text)
                except ValueError:
                    descriptor = None
            derived = self._relation_value_idtf(node, NREL_DERIVED_FROM)
            if derived and derived.startswith(STRATEGY_PREFIX):
                derived = derived[len(STRATEGY_PREFIX):]
            strategies.append(
                {
                    "name": name,
                    "descriptor": descriptor,
                    "replay_score": self._relation_value_number(node, NREL_STRATEGY_REPLAY_SCORE),
                    "online_score": self._relation_value_number(node, NREL_STRATEGY_ONLINE_SCORE),
                    "dream_round": self._relation_value_number(node, NREL_DREAM_ROUND),
                    "derived_from": derived,
                }
            )
        return strategies

    # ---------- harness policies (the RSI search tree) ----------

    def save_harness(
        self,
        name: str,
        descriptor: dict,
        *,
        replay_saving: Optional[float] = None,
        gate: Optional[dict] = None,
        online_result: Optional[dict] = None,
        derived_from: Optional[str] = None,
        round_index: Optional[int] = None,
    ) -> str:
        """Store a harness policy as a graph entity of class concept_harness.

        The policy descriptor, the judge's verdict, the gate decision and what
        the online run measured all hang off one node, so the search tree is
        readable in sc-web instead of being a log file somewhere.
        """
        node = self.resolve_entity(HARNESS_PREFIX + name)
        constr = ScConstruction()
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_HARNESS), node, "class_arc"
        )
        self._add_json_relation(constr, node, NREL_HARNESS_DESCRIPTOR, descriptor)
        if gate is not None:
            self._add_json_relation(constr, node, NREL_HARNESS_GATE, gate)
        if online_result is not None:
            self._add_json_relation(constr, node, NREL_HARNESS_ONLINE_RESULT, online_result)
        if replay_saving is not None:
            self._add_numeric_relation(constr, node, NREL_HARNESS_REPLAY_SAVING, float(replay_saving))
        if round_index is not None:
            self._add_numeric_relation(constr, node, NREL_HARNESS_SEARCH_ROUND, int(round_index))
        if derived_from is not None:
            parent = self.resolve_entity(HARNESS_PREFIX + derived_from)
            constr.generate_connector(sc_type.CONST_COMMON_ARC, node, parent, "derived_arc")
            constr.generate_connector(
                sc_type.CONST_PERM_POS_ARC, self.keynode(NREL_DERIVED_FROM), "derived_arc"
            )
        generate_elements(constr)
        return name

    def save_harness_round(self, index: int, record: dict) -> str:
        """Store one search round (frozen criteria, candidates, outcome)."""
        name = f"{HARNESS_ROUND_PREFIX}{index}"
        node = self.resolve_entity(name)
        constr = ScConstruction()
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_HARNESS_ROUND), node, "class_arc"
        )
        self._add_json_relation(constr, node, NREL_HARNESS_ROUND_RECORD, record)
        generate_elements(constr)
        return name

    def load_harnesses(self) -> list[dict]:
        """Every harness policy node with the fields the loop wrote to it."""
        template = ScTemplate()
        template.triple(self.keynode(CONCEPT_HARNESS), sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        found = search_by_template(template)

        rows: list[dict] = []
        for item in found:
            node = item.get(2)
            idtf = self.idtf_of(node) or ""
            name = idtf[len(HARNESS_PREFIX):] if idtf.startswith(HARNESS_PREFIX) else idtf
            derived = self._relation_value_idtf(node, NREL_DERIVED_FROM)
            if derived and derived.startswith(HARNESS_PREFIX):
                derived = derived[len(HARNESS_PREFIX):]
            rows.append({
                "name": name,
                "descriptor": self._json_relation(node, NREL_HARNESS_DESCRIPTOR),
                "replay_saving": self._relation_value_number(node, NREL_HARNESS_REPLAY_SAVING),
                "gate": self._json_relation(node, NREL_HARNESS_GATE),
                "online_result": self._json_relation(node, NREL_HARNESS_ONLINE_RESULT),
                "round_index": self._relation_value_number(node, NREL_HARNESS_SEARCH_ROUND),
                "derived_from": derived,
            })
        return rows

    def load_harness_rounds(self) -> list[dict]:
        """Every stored search round, newest last; one row per round.

        A round republished after a later run leaves the same record linked
        twice, so rows are deduplicated by round identifier: a reader wants one
        row per round, not one per arc in the graph.
        """
        template = ScTemplate()
        template.triple(self.keynode(CONCEPT_HARNESS_ROUND), sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        rows: dict[str, dict] = {}
        for item in search_by_template(template):
            node = item.get(2)
            idtf = self.idtf_of(node) or ""
            index = idtf[len(HARNESS_ROUND_PREFIX):] if idtf.startswith(HARNESS_ROUND_PREFIX) else idtf
            rows.setdefault(index, {"round": index,
                                    "record": self._json_relation(node, NREL_HARNESS_ROUND_RECORD)})
        return sorted(rows.values(), key=lambda row: str(row["round"]))

    # ---------- memory benchmark (LongMemEval corpus and ledger) ----------

    def save_memory_sessions(self, corpus: str, sessions: list[dict], batch: int = 25) -> int:
        """Write benchmark sessions as typed records belonging to `corpus`.

        One node per session: class concept_memory_session, linked to the
        corpus node through nrel_memory_corpus, the session date as a numeric
        relation and the body (session_id, date, turns) as a JSON payload.
        `batch` sessions share one construction, which is what makes a
        500-session haystack affordable; the caller gets the number written.
        """
        corpus_node = self.resolve_entity(MEMORY_CORPUS_PREFIX + corpus)
        constr = ScConstruction()
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_MEMORY_CORPUS), corpus_node, "corpus_class_arc"
        )
        generate_elements(constr)

        written = 0
        for start in range(0, len(sessions), batch):
            chunk = sessions[start:start + batch]
            constr = ScConstruction()
            for i, session in enumerate(chunk):
                node_alias = f"session_{i}"
                constr.generate_node(sc_type.CONST_NODE, node_alias)
                constr.generate_connector(
                    sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_MEMORY_SESSION), node_alias, f"class_arc_{i}"
                )
                constr.generate_connector(
                    sc_type.CONST_COMMON_ARC, node_alias, corpus_node, f"corpus_arc_{i}"
                )
                constr.generate_connector(
                    sc_type.CONST_PERM_POS_ARC, self.keynode(NREL_MEMORY_CORPUS), f"corpus_arc_{i}"
                )
                constr.generate_link(
                    sc_type.CONST_NODE_LINK,
                    ScLinkContent(json.dumps(session, sort_keys=True), ScLinkContentType.STRING),
                    f"payload_link_{i}",
                )
                constr.generate_connector(sc_type.CONST_COMMON_ARC, node_alias, f"payload_link_{i}", f"payload_arc_{i}")
                constr.generate_connector(
                    sc_type.CONST_PERM_POS_ARC, self.keynode(NREL_MEMORY_SESSION_PAYLOAD), f"payload_arc_{i}"
                )
                date_link = f"date_link_{i}"
                constr.generate_link(
                    sc_type.CONST_NODE_LINK,
                    ScLinkContent(int(session.get("date_epoch") or 0), ScLinkContentType.INT),
                    date_link,
                )
                constr.generate_connector(sc_type.CONST_COMMON_ARC, node_alias, date_link, f"date_arc_{i}")
                constr.generate_connector(
                    sc_type.CONST_PERM_POS_ARC, self.keynode(NREL_MEMORY_SESSION_DATE), f"date_arc_{i}"
                )
            generate_elements(constr)
            written += len(chunk)
        return written

    def memory_corpus_node(self, corpus: str) -> Optional[ScAddr]:
        """Find a corpus node by name without creating anything."""
        template = ScTemplate()
        template.triple(self.keynode(CONCEPT_MEMORY_CORPUS), sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        wanted = MEMORY_CORPUS_PREFIX + corpus
        for item in search_by_template(template):
            node = item.get(2)
            if self.idtf_of(node) == wanted:
                return node
        return None

    def load_memory_sessions(self, corpus: str) -> list[dict]:
        """Every session stored in `corpus`, deduplicated by session id.

        One template walks the corpus relation directly, so a read costs what
        the corpus holds, not what the whole graph holds; that matters once
        several haystacks have accumulated. The body is read from the payload
        relation, so a caller gets back exactly what was written.
        """
        corpus_node = self.memory_corpus_node(corpus)
        if corpus_node is None:
            return []
        template = ScTemplate()
        template.triple_with_relation(
            sc_type.VAR_NODE,
            sc_type.VAR_COMMON_ARC,
            corpus_node,
            self.keynode(NREL_MEMORY_CORPUS),
            sc_type.VAR_PERM_POS_ARC,
        )
        rows: dict[str, dict] = {}
        for item in search_by_template(template):
            node = item.get(0)
            payload = self._json_relation(node, NREL_MEMORY_SESSION_PAYLOAD)
            if payload and payload.get("session_id"):
                rows.setdefault(str(payload["session_id"]), payload)
        return list(rows.values())

    def save_memory_bench_result(self, name: str, payload: dict) -> str:
        """Store one benchmark verdict (question, arm, run) as a graph record."""
        node = self.resolve_entity(_safe_graph_identifier(name))
        constr = ScConstruction()
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_MEMORY_BENCH_RESULT), node, "class_arc"
        )
        self._add_json_relation(constr, node, NREL_MEMORY_BENCH_RESULT, payload)
        generate_elements(constr)
        return name

    def load_memory_bench_results(self) -> list[dict]:
        """Every stored benchmark verdict, in graph order, deduplicated by name."""
        template = ScTemplate()
        template.triple(self.keynode(CONCEPT_MEMORY_BENCH_RESULT), sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        rows: dict[str, dict] = {}
        for item in search_by_template(template):
            node = item.get(2)
            idtf = self.idtf_of(node) or ""
            payload = self._json_relation(node, NREL_MEMORY_BENCH_RESULT)
            if payload:
                rows[idtf] = payload
        return list(rows.values())

    def _json_relation(self, node: ScAddr, relation_idtf: str):
        """Read a JSON string link hanging off `node` through `relation_idtf`."""
        text = self._relation_value_text(node, relation_idtf)
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def _add_json_relation(self, constr: ScConstruction, node: ScAddr, relation_idtf: str, payload) -> None:
        """JSON relation: the payload is stored as a string link on an arc."""
        link_alias = f"json_link_{relation_idtf}"
        constr.generate_link(
            sc_type.CONST_NODE_LINK,
            ScLinkContent(json.dumps(payload, sort_keys=True), ScLinkContentType.STRING),
            link_alias,
        )
        arc_alias = f"json_arc_{relation_idtf}"
        constr.generate_connector(sc_type.CONST_COMMON_ARC, node, link_alias, arc_alias)
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(relation_idtf), arc_alias)

    def _add_numeric_relation(self, constr: ScConstruction, node: ScAddr, relation_idtf: str, value) -> None:
        """Numeric relation (link inside the same construction)."""
        link_alias = f"num_link_{relation_idtf}_{int(value * 1000) if isinstance(value, float) else value}"
        content_type = ScLinkContentType.INT if isinstance(value, int) else ScLinkContentType.FLOAT
        constr.generate_link(sc_type.CONST_NODE_LINK, ScLinkContent(value, content_type), link_alias)
        arc_alias = f"num_arc_{link_alias}"
        constr.generate_connector(sc_type.CONST_COMMON_ARC, node, link_alias, arc_alias)
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(relation_idtf), arc_alias)

    # ---------- enrichment ----------

    def _enrich(self, attempt_addr: ScAddr, record: AttemptRecord) -> None:
        """Attach source/kind/score/timestamp and trajectory relations to the
        attempt node. All graph writes go through one construction."""
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

        if record.episode is not None:
            episode_node = self.resolve_entity(EPISODE_PREFIX + record.episode)
            self._add_relation(constr, attempt_addr, NREL_EPISODE, episode_node)
            self._classify_episode_once(episode_node)
        if record.step_index is not None:
            link_addr = self._numeric_link(int(record.step_index))
            self._add_relation(constr, attempt_addr, NREL_STEP_INDEX, link_addr)
        if record.state is not None:
            self._add_text_relation(constr, attempt_addr, NREL_STATE, record.state)
        if record.legal is not None:
            self._add_text_relation(constr, attempt_addr, NREL_LEGAL, record.legal)
        if record.strategy is not None:
            strategy_node = self.resolve_entity(STRATEGY_PREFIX + record.strategy)
            self._add_relation(constr, attempt_addr, NREL_STRATEGY, strategy_node)
        if record.note is not None:
            self._add_text_relation(constr, attempt_addr, NREL_NOTE, record.note)

        if len(constr.commands):
            generate_elements(constr)

    def _classify_episode_once(self, episode_node: ScAddr) -> None:
        """Give an episode node its class arc exactly once per bridge session."""
        key = str(episode_node.value)
        if key in self._episodes_classified:
            return
        self._episodes_classified.add(key)
        constr = ScConstruction()
        constr.generate_connector(
            sc_type.CONST_PERM_POS_ARC, self.keynode(CONCEPT_EXPERIENCE_EVENT), episode_node
        )
        generate_elements(constr)

    def _add_text_relation(self, constr: ScConstruction, source: ScAddr, relation_idtf: str, text: str) -> None:
        """Relation whose value is a string link, all inside one construction."""
        link_alias = f"text_link_{relation_idtf}"
        constr.generate_link(
            sc_type.CONST_NODE_LINK,
            ScLinkContent(text, ScLinkContentType.STRING),
            link_alias,
        )
        arc_alias = f"text_arc_{relation_idtf}"
        constr.generate_connector(sc_type.CONST_COMMON_ARC, source, link_alias, arc_alias)
        constr.generate_connector(sc_type.CONST_PERM_POS_ARC, self.keynode(relation_idtf), arc_alias)

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
                # prev_attempt comes with the batched decode; only fall back to
                # the dedicated quintuple when the relation set is incomplete.
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

    # relation-name constants decoded by the batch decoder
    _DECODED_RELATIONS = (
        NREL_SUBJECT, NREL_ACTION, NREL_OBJECT, NREL_OUTCOME, NREL_SOURCE,
        NREL_KIND, NREL_SCORE, NREL_TIMESTAMP, NREL_EPISODE, NREL_STEP_INDEX,
        NREL_STATE, NREL_LEGAL, NREL_STRATEGY, NREL_NOTE, NREL_PREV_ATTEMPT,
    )

    def _relations_of(self, attempt_addr: ScAddr) -> dict[str, ScAddr]:
        """All (relation-name -> value) of one attempt in ONE template search.

        Ten-plus per-relation searches take ~150 ms per attempt server-side;
        a single triple_with_relation over every common arc attributed by any
        relation node returns the same data in ~5 ms. Relation nodes are
        matched against the cached keynodes by address.
        """
        rel_names = self._rel_addr_to_name()
        template = ScTemplate()
        template.triple_with_relation(
            attempt_addr,
            sc_type.VAR_COMMON_ARC,
            sc_type.VAR,
            sc_type.VAR_PERM_POS_ARC,
            sc_type.VAR_NODE,
        )
        found: dict[str, ScAddr] = {}
        for result in search_by_template(template):
            rel = result.get(3)
            name = rel_names.get(rel.value)
            if name and name not in found:
                found[name] = result.get(2)
        return found

    def _rel_addr_to_name(self) -> dict[int, str]:
        if not hasattr(self, "_rel_map"):
            self._rel_map = {}
            for name in self._DECODED_RELATIONS:
                try:
                    self._rel_map[self.keynode(name).value] = name
                except Exception:
                    pass
        return self._rel_map

    def _decode_single_attempt(self, attempt_addr: ScAddr) -> Optional[AttemptRecord]:
        rel = self._relations_of(attempt_addr)

        def idtf(name: str) -> Optional[str]:
            addr = rel.get(name)
            return self.idtf_of(addr) if addr is not None else None

        def _read(name: str):
            addr = rel.get(name)
            if addr is None:
                return None
            try:
                contents = get_link_content(addr)
            except Exception:
                return None  # not a link: node values go through idtf() instead
            if contents and contents[0].data is not None:
                return contents[0].data
            return None

        def number(name: str) -> Optional[float]:
            raw = _read(name)
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None

        def text(name: str) -> Optional[str]:
            raw = _read(name)
            return None if raw is None else str(raw)

        subject = idtf(NREL_SUBJECT)
        if subject is None:
            return None
        episode = idtf(NREL_EPISODE)
        if episode and episode.startswith(EPISODE_PREFIX):
            episode = episode[len(EPISODE_PREFIX):]
        strategy = idtf(NREL_STRATEGY)
        if strategy and strategy.startswith(STRATEGY_PREFIX):
            strategy = strategy[len(STRATEGY_PREFIX):]
        step_index_raw = number(NREL_STEP_INDEX)
        return AttemptRecord(
            subject=subject,
            action=idtf(NREL_ACTION) or "",
            object=idtf(NREL_OBJECT) or "",
            outcome=idtf(NREL_OUTCOME) or "",
            source=idtf(NREL_SOURCE),
            kind=idtf(NREL_KIND),
            score=number(NREL_SCORE),
            timestamp=number(NREL_TIMESTAMP),
            episode=episode,
            step_index=int(step_index_raw) if step_index_raw is not None else None,
            state=text(NREL_STATE),
            legal=text(NREL_LEGAL),
            strategy=strategy,
            note=text(NREL_NOTE),
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

    def _relation_value_text(self, source_addr: ScAddr, relation_idtf: str) -> Optional[str]:
        """Follow one nrel-relation to a string link and return its content."""
        value_addr = self._relation_value_link_addr(source_addr, relation_idtf)
        if value_addr is None:
            return None
        contents = get_link_content(value_addr)
        if contents and contents[0].data is not None:
            return str(contents[0].data)
        return None

    def _relation_value_link_addr(self, source_addr: ScAddr, relation_idtf: str) -> Optional[ScAddr]:
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
        return found[0].get(2)

    def _relation_value_number(self, source_addr: ScAddr, relation_idtf: str) -> Optional[float]:
        # The value is a sc-link, not a node — search for the link directly
        # (VAR_NODE in _relation_value_addr does not match links).
        value_addr = self._relation_value_link_addr(source_addr, relation_idtf)
        if value_addr is None:
            return None
        contents = get_link_content(value_addr)
        if contents and contents[0].data is not None:
            try:
                return float(contents[0].data)
            except (TypeError, ValueError):
                return None
        return None
