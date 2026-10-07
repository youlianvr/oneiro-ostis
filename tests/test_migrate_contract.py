"""The ontology migration's contract: additive, idempotent, and honest.

The migration exists because a graph can be out of step with
`knowledge-base/ontology/experience.scs` - a build that predates a declaration, or
a graph that was never built from the ontology at all. It fixes that additively
and reports what it cannot fix.

The distinction it turns on: a missing *relation* keynode may be created, because
that is what the writers already do and the live graph proves the result works; a
missing *class* may not, because a bare ConstNode in a class's place reads back
correctly and is not a node class. So the class is reported and `needs_kb_build`
is set. A migration that quietly faked it would be the worst outcome available,
because nothing downstream would announce the mistake.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from oneiro import migrate                                        # noqa: E402
from oneiro.migrate import (                                      # noqa: E402
    DECLARED_CLASSES,
    DECLARED_RELATIONS,
    declared,
)

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "knowledge-base" / "ontology" / "experience.scs"


class FakeBridge:
    """Records what a migration would write, and can be told to fail."""

    def __init__(self, *, refuse=()) -> None:
        self.created: list[str] = []
        self.refuse = set(refuse)
        self.types = {name: ("concept" if name in {"concept_success", "concept_failure",
                     "concept_no_temporal", "source_direct", "source_hearsay"} else "sc_node_class")
                      for name in DECLARED_CLASSES}
        self.types.update({name: "concept_outcome" for name in ("concept_success", "concept_failure")})
        self.types.update({name: "sc_node_non_role_relation" for name in DECLARED_RELATIONS})

    def type_matches(self, name, parent):
        return self.types.get(name) == parent

    def create_relation(self, name: str):
        class Address:
            def __init__(self, value: int) -> None:
                self.value = value

            def is_valid(self) -> bool:
                return True

        if name in self.refuse:
            raise RuntimeError(f"server refused {name}")
        self.created.append(name)
        return Address(len(self.created) + 1000)


def ensure_ontology(bridge, **kwargs):
    return migrate.ensure_ontology(bridge, type_matches=bridge.type_matches,
                                   create_relation=bridge.create_relation, **kwargs)


def everything_present(name: str) -> bool:
    return True


def only_classes_present(name: str) -> bool:
    return name in DECLARED_CLASSES


# ---------- the vocabulary comes from the ontology, not from invention ----------

def test_the_builtin_table_is_the_ontology_file_it_claims_to_be():
    """A wheel has no .scs file, so the fallback must not drift from it."""
    if not ONTOLOGY.is_file():
        return
    classes, relations, source = declared(ONTOLOGY)
    assert set(classes) == set(DECLARED_CLASSES), "class table drifted from the ontology"
    assert set(relations) == set(DECLARED_RELATIONS), "relation table drifted from the ontology"
    assert "concept_harness" in classes, "the table kept the harness class"
    assert source.endswith("experience.scs")


def test_relations_and_classes_are_read_from_different_declaration_lines():
    classes, relations, _ = declared(ONTOLOGY)
    assert "concept_harness" in classes, "declared as `<- sc_node_class;;`"
    assert "nrel_timestamp" in relations, "declared as `<- sc_node_non_role_relation;;`"
    assert not set(classes) & set(relations), "a name cannot be both"


def test_a_missing_ontology_file_falls_back_to_the_builtin_table():
    classes, relations, source = declared(Path("does/not/exist.scs"))
    assert source == "builtin"
    assert classes == DECLARED_CLASSES and relations == DECLARED_RELATIONS


# ---------- nothing is ever destroyed ----------

def test_there_is_no_delete_path_to_call():
    """The plan forbids a startup clear; the cheapest proof is that none exists.

    Parsed rather than grepped: this module's own docstring names the calls it
    refuses to make, and prose mentioning `erase_elements` is not a call to it.
    """
    import ast

    tree = ast.parse((ROOT / "python" / "oneiro" / "migrate.py")
                     .read_text(encoding="utf-8"))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                called.add(target.id)
            elif isinstance(target, ast.Attribute):
                called.add(target.attr)
    for forbidden in ("erase_elements", "erase", "delete", "delete_elements",
                      "truncate", "clear"):
        assert forbidden not in called, (
            f"migrate.py must not be able to destroy anything, but it calls {forbidden!r}")


# ---------- what it does ----------

def test_a_graph_already_up_to_date_is_left_alone():
    bridge = FakeBridge()
    report = ensure_ontology(bridge, ontology=ONTOLOGY, present=everything_present)

    assert bridge.created == [], "an up-to-date graph must not be written to at all"
    assert report.changed is False
    assert report.missing_classes == ()
    assert report.needs_kb_build is False
    assert report.classes_checked == len(DECLARED_CLASSES)
    assert report.relations_checked == len(DECLARED_RELATIONS)


def test_missing_relations_are_created_and_a_second_run_creates_nothing():
    """Idempotency: this is the property the whole module is for."""
    bridge = FakeBridge()
    # Start from a graph that has the classes but none of the relations.
    present_now = set(DECLARED_CLASSES)

    def has(name: str) -> bool:
        return name in present_now

    first = ensure_ontology(bridge, ontology=ONTOLOGY, present=has)
    assert set(first.relations_created) == set(DECLARED_RELATIONS), (
        "every declared relation was missing and every one was added")
    assert first.changed is True
    assert first.missing_classes == (), "the classes were already there"

    # The graph now has everything the first run created.
    present_now.update(bridge.created)
    second = ensure_ontology(bridge, ontology=ONTOLOGY, present=has)

    assert second.relations_created == (), "the second run must create nothing"
    assert second.changed is False
    assert len(bridge.created) == len(DECLARED_RELATIONS), "no extra writes"


def test_a_class_is_never_created_however_absent_it_is():
    """Relations are additive; a class is not, and never is faked."""
    bridge = FakeBridge()
    report = ensure_ontology(bridge, ontology=ONTOLOGY, present=only_classes_present)

    assert report.missing_classes == (), "every declared class was present"
    assert set(report.relations_created) == set(DECLARED_RELATIONS)
    assert not any(name.startswith("concept_") for name in bridge.created), (
        "a class must never be faked with a ConstNode: it would read correctly "
        "and not be a node class")


def test_a_graph_with_no_ontology_at_all_asks_for_a_rebuild():
    bridge = FakeBridge()
    report = ensure_ontology(bridge, ontology=ONTOLOGY, present=lambda name: False)

    assert report.needs_kb_build is True
    assert set(report.missing_classes) == set(DECLARED_CLASSES), (
        "every declared class is absent, which is the bare-seed case measured "
        "on 2026-10-02")
    assert set(bridge.created) == set(DECLARED_RELATIONS), (
        "relations are additive and are still created")
    assert report.failed == ()


def test_one_refused_creation_is_recorded_and_the_rest_continue():
    bridge = FakeBridge(refuse={"nrel_timestamp"})
    report = ensure_ontology(bridge, ontology=ONTOLOGY, present=lambda name: False)

    assert dict(report.failed)["nrel_timestamp"].startswith("RuntimeError")
    assert set(bridge.created) == set(DECLARED_RELATIONS) - {"nrel_timestamp"}


def test_the_report_says_plainly_whether_it_changed_anything():
    bridge = FakeBridge()
    changed = ensure_ontology(bridge, ontology=ONTOLOGY, present=only_classes_present)
    quiet = ensure_ontology(bridge, ontology=ONTOLOGY, present=everything_present)

    assert changed.to_dict()["changed"] is True
    assert quiet.to_dict()["changed"] is False
    assert set(quiet.to_dict()) == {
        "source", "classes_checked", "relations_checked", "classes_present",
        "relations_present", "relations_created", "missing_classes", "failed",
        "needs_kb_build", "changed"}, "a report is a stable shape for a caller to read"


def test_existing_wrong_types_are_reported_not_accepted_or_overwritten():
    bridge = FakeBridge()
    bridge.types["concept_harness"] = "concept"
    bridge.types["nrel_timestamp"] = "concept"
    report = ensure_ontology(bridge, ontology=ONTOLOGY, present=everything_present)
    assert dict(report.failed) == {"concept_harness": "ontology_type_mismatch",
                                   "nrel_timestamp": "ontology_type_mismatch"}
    assert "concept_harness" not in report.classes_present
    assert "nrel_timestamp" not in report.relations_present
    assert bridge.created == []


def test_creation_with_wrong_type_is_not_reported_as_a_success():
    bridge = FakeBridge()
    bridge.types["nrel_timestamp"] = "concept"
    report = ensure_ontology(bridge, ontology=ONTOLOGY, present=only_classes_present)
    assert dict(report.failed)["nrel_timestamp"] == "ontology_type_mismatch after creation"
    assert "nrel_timestamp" not in report.relations_created


def test_the_ontology_path_default_points_at_the_repository_file():
    """A source checkout reads the file; that is what keeps the table honest."""
    assert migrate.ONTOLOGY.name == "experience.scs"
    assert migrate.ONTOLOGY.parent.name == "ontology"