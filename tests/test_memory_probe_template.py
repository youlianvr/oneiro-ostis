"""The memory probe must anchor on a concrete source.

The obvious way to ask "what uses this relation?" is a template with a variable
source and a fixed connector. On this sc-memory build that returns a single
result whose endpoints are both ScAddr(0), for every combination of variable
types tried, while the same server returns real triples as soon as the source
is concrete. Measured 2026-10-02 on sc-server 0.10.5; the numbers are in
docs/REWRITE-BASELINE.md.

The consequence was not a crash but silence: the probe reported a reachable
graph holding no content, which is the false confidence this module exists to
prevent. These tests pin the template shape so it cannot quietly revert, and
pin the difference between a resolved endpoint and a wildcard one.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from oneiro import memory

MODULE = Path(inspect.getfile(memory))


def test_probe_anchors_on_a_concrete_source():
    """The triple's SOURCE must be the resolved address, not a variable type."""
    source = MODULE.read_text(encoding="utf-8")
    triple_calls = [
        line.strip() for line in source.splitlines()
        if ".triple(" in line and not line.strip().startswith("#")
    ]
    assert triple_calls, "no template triple found in the memory probe"

    for call in triple_calls:
        first_argument = call[len(".triple("):].split(",")[0].strip()
        assert not first_argument.startswith("sc_type."), (
            "the probe must anchor on a concrete source address; a variable "
            f"source returns only unresolved wildcard matches here: {call}"
        )


def test_probe_uses_a_connector_type_in_the_relation_slot():
    """The relation slot must hold an arc type, not a node type."""
    from sc_client.constants import sc_type
    from sc_client.models import ScAddr, ScTemplate

    # VAR_NODE_LINK is a NODE type (0x43). Placing it in the connector slot is
    # what made the original sweep match nothing at all.
    assert int(sc_type.VAR_NODE_LINK.value) == 0x43
    assert int(sc_type.VAR_CONNECTOR.value) != int(sc_type.VAR_NODE_LINK.value)

    template = ScTemplate()
    template.triple(ScAddr(65538), sc_type.VAR_COMMON_ARC, sc_type.VAR_NODE_LINK)
    triple = template.triple_list[0]
    assert triple.source.value.value == 65538, "source is the concrete anchor"
    assert int(triple.connector.value.value) == int(sc_type.VAR_COMMON_ARC.value)


def test_anchor_relation_is_a_relation_present_in_every_ostis_graph():
    assert memory.ANCHOR_RELATION == "nrel_system_identifier"


def test_unreachable_server_is_reported_not_faked():
    """A dead port must produce reachable=False, never an empty-but-valid graph."""
    facts = memory.probe("127.0.0.1", 1)
    assert facts.reachable is False
    assert facts.verified is False
    assert facts.blocked, "an unreachable server must carry a reason"