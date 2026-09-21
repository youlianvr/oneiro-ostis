"""Offline test: a graph built before the session vocabulary still accepts it.

The live sc-machine cannot be reloaded without clearing its accumulated graph,
so missing session/organization keynodes are created as named nodes at runtime.
Everything outside that vocabulary must still fail loudly.
"""

import pytest
from sc_client.constants.exceptions import InvalidValueError

from bridge import NREL_SESSION_RECORD, OneiroBridge, RUNTIME_VOCABULARY


class FakeKeynodes:
    """Stands in for the sc_kpm singleton: every identifier looks missing."""

    def __getitem__(self, idtf):
        raise InvalidValueError(f"ScAddr of {idtf} is invalid")


def test_missing_vocabulary_keynode_is_created_once(monkeypatch):
    bridge = OneiroBridge()
    created: dict[str, object] = {}

    def fake_resolve(name: str):
        created[name] = object()
        return created[name]

    monkeypatch.setattr("bridge.ScKeynodes", FakeKeynodes())
    monkeypatch.setattr(bridge, "resolve_entity", fake_resolve)

    first = bridge.keynode(NREL_SESSION_RECORD)
    second = bridge.keynode(NREL_SESSION_RECORD)

    assert first is created[NREL_SESSION_RECORD]
    assert second is first
    assert list(created) == [NREL_SESSION_RECORD]


def test_non_vocabulary_keynodes_still_raise(monkeypatch):
    bridge = OneiroBridge()
    monkeypatch.setattr("bridge.ScKeynodes", FakeKeynodes())

    with pytest.raises(InvalidValueError):
        bridge.keynode("concept_attempt")


def test_vocabulary_is_exactly_the_session_and_organization_set():
    assert "concept_session" in RUNTIME_VOCABULARY
    assert "nrel_session_record" in RUNTIME_VOCABULARY
    assert "concept_organization_record" in RUNTIME_VOCABULARY
    assert "concept_attempt" not in RUNTIME_VOCABULARY
