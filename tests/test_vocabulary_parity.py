"""Every record kind the schema defines must be writable to the live graph.

The offline test graph does not check kinds, so a kind missing from the graph
vocabulary would pass every test and then be refused by the real graph. This
test closes that gap by comparing the two lists directly.
"""
from __future__ import annotations

from oneiro import migrate, sc_graph
from oneiro.records import _KINDS


def test_the_graph_vocabulary_lists_every_schema_kind():
    assert set(sc_graph.KINDS) == set(_KINDS)


def test_every_kind_has_a_declared_class_in_the_migration_table():
    for kind in _KINDS:
        assert f"concept_oneiro_{kind}" in migrate.DECLARED_CLASSES, kind
