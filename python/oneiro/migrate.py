"""Additive, idempotent ontology migration. It never clears anything.

The graph's vocabulary is declared in `knowledge-base/ontology/experience.scs`
and built into the knowledge base by the KB build. Two things can then be out of
step with it: a build that predates a declaration, and a runtime writer that
needs a name the ontology never declared. This module settles both without
destroying anything, and it is safe to run twice - the second run creates
nothing.

**Relations may be created; classes may not.** A missing relation keynode is
created as CONST_NODE_NON_ROLE, never a generic ConstNode. Existing vocabulary
is checked for the declared sc-type, not just existence. A missing *class* is a
different thing. `experience.scs` declares
`concept_harness <- sc_node_class;;`; creating a bare `ConstNode` with that
identifier would satisfy a template anchored on it and read back fine, while not
being a node class at all. That is a quietly wrong ontology, which is worse than
an absent one because it will not announce itself. So a missing class is
reported as `missing_classes` with `needs_kb_build` set, and the answer is a
rebuild.

**There is no delete path in this module, on purpose.** The plan forbids a
startup clear, and the cheapest way to guarantee that is for there to be nothing
here to call: no `erase_elements`, no `delete`, no truncation of a class. A test
asserts the source contains none of them.

The vocabulary comes from the ontology file when it is readable, which is the
honest source of truth, and from the static table below otherwise, which is what
an installed wheel has. `tests/test_migrate_contract.py` asserts the two agree,
so the fallback cannot quietly rot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

#: The declarations the ontology file makes, grouped by what they are. Kept in
#: step with `knowledge-base/ontology/experience.scs` by a test that reads that
#: file when it is present; this is what an installed wheel has instead.
DECLARED_CLASSES: tuple[str, ...] = (
    "action_record_attempt",
    "action_retrieve_attempts",
    "action_oneiro_save_memory",
    "concept_action_kind",
    "concept_attempt",
    "concept_dream_cycle",
    "concept_experience_event",
    "concept_failure",
    "concept_harness",
    "concept_harness_round",
    "concept_no_temporal",
    "concept_oneiro_record",
    "concept_oneiro_conversation_message",
    "concept_oneiro_curated_fact",
    "concept_oneiro_question",
    "concept_oneiro_approval",
    "concept_oneiro_schedule",
    "concept_oneiro_task",
    "concept_oneiro_run",
    "concept_oneiro_action",
    "concept_oneiro_decision",
    "concept_oneiro_note",
    "concept_oneiro_experience",
    "concept_oneiro_experiment",
    "concept_oneiro_release",
    "concept_organization_record",
    "concept_outcome",
    "concept_session",
    "concept_strategy",
    "concept_subject",
    "concept_success",
    "source_direct",
    "source_hearsay",
)

DECLARED_RELATIONS: tuple[str, ...] = (
    "nrel_action",
    "nrel_confidence",
    "nrel_derived_from",
    "nrel_dream_round",
    "nrel_episode",
    "nrel_harness_descriptor",
    "nrel_harness_gate",
    "nrel_harness_online_result",
    "nrel_harness_replay_saving",
    "nrel_harness_round_record",
    "nrel_harness_search_round",
    "nrel_kind",
    "nrel_legal",
    "nrel_note",
    "nrel_object",
    "nrel_oneiro_previous",
    "nrel_oneiro_previous_revision",
    "nrel_oneiro_publication",
    "nrel_organization_record",
    "nrel_origin",
    "nrel_outcome",
    "nrel_prev_attempt",
    "nrel_score",
    "nrel_session_record",
    "nrel_source",
    "nrel_state",
    "nrel_step_index",
    "nrel_strategy",
    "nrel_strategy_descriptor",
    "nrel_strategy_online_score",
    "nrel_strategy_replay_score",
    "nrel_subject",
    "nrel_timestamp",
)

#: `name <- parent;;` as the ontology files write it.
_DECLARATION = re.compile(r"^([a-z_][a-z0-9_]*)\s*<-\s*([a-z_][a-z0-9_]*)\s*;;")

#: Where the ontology lives relative to the installed package's repository root.
ONTOLOGY = Path("knowledge-base/ontology/experience.scs")


@dataclass(frozen=True)
class MigrationReport:
    """What the migration found and what it did. Nothing here is a guess."""

    classes_checked: int = 0
    relations_checked: int = 0
    classes_present: tuple[str, ...] = ()
    relations_present: tuple[str, ...] = ()
    relations_created: tuple[str, ...] = ()
    missing_classes: tuple[str, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()
    source: str = "builtin"

    @property
    def needs_kb_build(self) -> bool:
        """True when the graph cannot serve the classes the product writes to;
        the answer is a KB build, not an additive write.
        """
        return bool(self.missing_classes)

    @property
    def changed(self) -> bool:
        """Whether this run altered the graph. A second run must be False."""
        return bool(self.relations_created)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "classes_checked": self.classes_checked,
            "relations_checked": self.relations_checked,
            "classes_present": list(self.classes_present),
            "relations_present": list(self.relations_present),
            "relations_created": list(self.relations_created),
            "missing_classes": list(self.missing_classes),
            "failed": [list(pair) for pair in self.failed],
            "needs_kb_build": self.needs_kb_build,
            "changed": self.changed,
        }


def declared(ontology: Optional[Path] = None) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Classes and relations the ontology declares, and where they came from.

    Reads the ontology file when it is readable, because that is the real source
    of truth, and falls back to the table above for an installed wheel.
    """
    path = ontology or ONTOLOGY
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return DECLARED_CLASSES, DECLARED_RELATIONS, "builtin"

    classes: list[str] = []
    relations: list[str] = []
    for line in text.splitlines():
        match = _DECLARATION.match(line.strip())
        if match is None:
            continue
        name, parent = match.group(1), match.group(2)
        if name in classes or name in relations:
            continue
        if parent == "sc_node_non_role_relation":
            relations.append(name)
        else:
            classes.append(name)
    return tuple(classes), tuple(relations), str(path)


def _present(identifier: str) -> bool:
    """Whether the graph already has this identifier. Creates nothing.

    The same non-creating lookup the entity query uses: an id that is absent
    raises rather than being resolved, which is what makes a migration check safe
    to run against a graph it must not disturb.
    """
    import importlib
    client = importlib.import_module("sc_client.client")
    addresses = client.resolve_keynodes({"idtf": identifier, "type": None})
    return bool(addresses and addresses[0].is_valid())


def _type_matches(identifier: str, parent: str) -> bool:
    import importlib
    client = importlib.import_module("sc_client.client")
    types = importlib.import_module("sc_client.constants.sc_type")
    expected = {"sc_node_class": types.CONST_NODE_CLASS,
                "sc_node_non_role_relation": types.CONST_NODE_NON_ROLE}.get(parent, types.CONST_NODE)
    addresses = client.resolve_keynodes({"idtf": identifier, "type": None})
    return bool(addresses and addresses[0].is_valid()
                and client.get_elements_types(addresses[0]) == [expected])


def _create_relation(identifier: str) -> Any:
    import importlib
    client = importlib.import_module("sc_client.client")
    types = importlib.import_module("sc_client.constants.sc_type")
    return client.resolve_keynodes({"idtf": identifier, "type": types.CONST_NODE_NON_ROLE})[0]


def ensure_ontology(bridge: Any, *, ontology: Optional[Path] = None,
                    present: Optional[Callable[[str], bool]] = None,
                    type_matches: Optional[Callable[[str, str], bool]] = None,
                    create_relation: Optional[Callable[[str], Any]] = None) -> MigrationReport:
    """Bring a graph up to the declared vocabulary, additively.

    Missing relation keynodes are created; missing classes are reported, never
    faked. Running this twice creates nothing the second time.

    `present` is the existence check, injectable so the rules above can be tested
    without a server. It defaults to the graph's own keynode table.
    """
    classes, relations, source = declared(ontology)
    check = present or _present
    validate = type_matches or _type_matches
    create = create_relation or _create_relation
    # Outcome/flag/source constants are members, not node classes. Preserve the
    # historical report grouping while checking each declaration's actual type.
    parents = {name: "sc_node_class" for name in classes}
    for name in ("concept_success", "concept_failure", "concept_no_temporal",
                 "source_direct", "source_hearsay"):
        parents[name] = "concept"
    try:
        text = (ontology or ONTOLOGY).read_text(encoding="utf-8")
    except OSError:
        pass
    else:
        for line in text.splitlines():
            match = _DECLARATION.match(line.strip())
            if match is not None:
                parents[match.group(1)] = match.group(2)
    failed: list[tuple[str, str]] = []

    classes_present: list[str] = []
    missing_classes: list[str] = []
    for name in classes:
        if check(name):
            if validate(name, parents[name]):
                classes_present.append(name)
            else:
                failed.append((name, "ontology_type_mismatch"))
        else:
            missing_classes.append(name)

    relations_present: list[str] = []
    relations_created: list[str] = []
    for name in relations:
        if check(name):
            if validate(name, "sc_node_non_role_relation"):
                relations_present.append(name)
            else:
                failed.append((name, "ontology_type_mismatch"))
            continue
        try:
            address = create(name)
        except Exception as exc:               # noqa: BLE001 - one bad name must not abort the rest
            failed.append((name, f"{type(exc).__name__}: {exc}"))
            continue
        if address is None or not getattr(address, "is_valid", lambda: False)():
            failed.append((name, "resolve returned no address"))
            continue
        if not validate(name, "sc_node_non_role_relation"):
            failed.append((name, "ontology_type_mismatch after creation"))
            continue
        relations_created.append(name)

    return MigrationReport(
        classes_checked=len(classes),
        relations_checked=len(relations),
        classes_present=tuple(classes_present),
        relations_present=tuple(relations_present),
        relations_created=tuple(relations_created),
        missing_classes=tuple(missing_classes),
        failed=tuple(failed),
        source=source,
    )