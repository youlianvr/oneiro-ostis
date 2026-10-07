from __future__ import annotations

from types import SimpleNamespace
from collections import OrderedDict

import pytest

from oneiro.query import GraphQueryError
from oneiro.sc_graph import ScLinkGraph, ADDRESS_CACHE_LIMIT


class Address:
    def __init__(self, value):
        self.value = value

    def is_valid(self):
        return self.value != 0

    def __eq__(self, other):
        return isinstance(other, Address) and self.value == other.value


class Template:
    def __init__(self):
        self.patterns = []

    def triple(self, *args):
        self.patterns.append(args)

    def triple_with_relation(self, *args):
        self.patterns.append(args)


class Construction:
    def __init__(self):
        self.commands = []

    def generate_link(self, *args):
        self.commands.append(("link", args))

    def generate_connector(self, *args):
        self.commands.append(("connector", args))


class Row:
    def __init__(self, source):
        self.source = source

    def get(self, index):
        assert index == 0
        return self.source


def adapter():
    graph = ScLinkGraph.__new__(ScLinkGraph)
    graph._addresses = OrderedDict()
    graph.types = SimpleNamespace(CONST_NODE_LINK="link", CONST_NODE_NON_ROLE="relation",
                                  CONST_NODE_CLASS="class", VAR_NODE_CLASS="var-class",
                                  VAR_PERM_POS_ARC="var-member", VAR_COMMON_ARC="var-common",
                                  CONST_PERM_POS_ARC="member", CONST_COMMON_ARC="common")
    graph.models = SimpleNamespace(ScTemplate=Template, ScConstruction=Construction,
        ScLinkContent=lambda data, kind, address=None: SimpleNamespace(data=data, kind=kind, address=address),
        ScLinkContentType=SimpleNamespace(STRING="string"))
    return graph


def test_named_link_content_is_generated_before_identifier_is_published():
    graph = adapter()
    graph._resolve = lambda name, sc_type=None: None if name == "new-link" else Address(5)
    graph.read = lambda name: "payload"
    calls = []
    graph._call = lambda name, *args: calls.append((name, args))
    graph.write("new-link", "payload")
    assert calls[0][0] == "generate_elements"
    commands = calls[0][1][0].commands
    assert [kind for kind, _ in commands] == ["link", "link", "connector", "connector"]
    assert commands[0][1][1].data == "payload"
    assert commands[1][1][1].data == "new-link"
    assert commands[-1][1][1] == Address(5)
    assert not any(name == "set_link_contents" for name, _ in calls)


def test_existing_wrong_type_refuses_content_overwrite():
    graph = adapter()
    graph._resolve = lambda name, sc_type=None: Address(1)
    calls = []

    def call(name, *args):
        calls.append(name)
        return ["class"]
    graph._call = call
    with pytest.raises(GraphQueryError, match="ontology_type_mismatch"):
        graph.write("wrong-type", "payload")
    assert calls == ["get_elements_types"]


def test_class_membership_search_anchors_record_not_large_class():
    graph = adapter()
    source, target = Address(1), Address(2)
    patterns = []

    def call(name, *args):
        assert name == "search_by_template"
        patterns.extend(args[0].patterns)
        return [Row(source)]
    graph._call = call
    graph._arc_once(source, target)
    assert patterns == [("var-class", "var-member", target)]


def test_classification_filters_unrelated_incoming_class_and_is_idempotent():
    graph = adapter()
    source, other, target = Address(1), Address(3), Address(2)
    calls = []
    searches = 0

    def call(name, *args):
        nonlocal searches
        calls.append(name)
        if name == "search_by_template":
            searches += 1
            return [Row(other)] if searches == 1 else [Row(other), Row(source)]
        return []
    graph._call = call
    graph._arc_once(source, target)
    assert calls == ["search_by_template", "generate_elements", "search_by_template"]
    calls.clear()
    graph._arc_once(source, target)
    assert calls == ["search_by_template"]


def test_duplicate_membership_is_reported_instead_of_added_again():
    graph = adapter()
    source, target = Address(1), Address(2)
    graph._call = lambda *_: [Row(source), Row(source)]
    with pytest.raises(GraphQueryError, match="duplicate_relation"):
        graph._arc_once(source, target)


def test_wrong_keynode_type_is_not_migration_success():
    graph = adapter()
    graph._call = lambda name, *args: [Address(1)] if name == "resolve_keynodes" else ["link"]
    with pytest.raises(GraphQueryError, match="ontology_type_mismatch"):
        graph._resolve("concept_oneiro_note", "class")


def test_address_cache_is_bounded_and_never_caches_absence_or_payloads():
    graph = adapter()
    calls = []
    def call(name, params):
        assert name == "resolve_keynodes"
        calls.append(params["idtf"])
        return [Address(0 if params["idtf"] == "missing" else len(calls))]
    graph._call = call
    assert graph._resolve("missing") is None
    assert graph._resolve("missing") is None
    assert calls == ["missing", "missing"]
    for index in range(ADDRESS_CACHE_LIMIT + 10):
        graph._resolve(f"id-{index}")
    assert len(graph._addresses) == ADDRESS_CACHE_LIMIT
    count = len(calls)
    graph._resolve(f"id-{ADDRESS_CACHE_LIMIT + 9}")
    assert len(calls) == count
    graph._resolve("id-0")
    assert len(calls) == count + 1
    assert len(graph._addresses) == ADDRESS_CACHE_LIMIT


def test_cached_keynodes_still_validate_types():
    graph = adapter()
    graph._addresses["class"] = Address(1)
    graph._call = lambda name, *args: ["link"]
    with pytest.raises(GraphQueryError, match="ontology_type_mismatch"):
        graph._resolve("class", "class")


def test_native_checkpoint_missing_vocabulary_is_not_durable():
    graph = adapter()
    graph._resolve = lambda name, sc_type=None: None
    with pytest.raises(GraphQueryError, match="checkpoint_unavailable"):
        graph.checkpoint()
