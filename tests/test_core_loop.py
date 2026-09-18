"""Stage-2 core loop test: record attempts then retrieve them back.

Requires a live stack (docker compose up of oneiro-ostis).
Run: pytest tests/test_core_loop.py -v
"""

import os

import pytest

from bridge import OneiroBridge

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))


@pytest.fixture(scope="module")
def bridge():
    b = OneiroBridge(HOST, PORT)
    b.connect()
    yield b
    b.close()  # otherwise the client's background threads can linger


def test_record_then_retrieve_roundtrip(bridge):
    """Record three attempts for one subject; retrieve all three back."""
    subject = "test_subject_alpha"
    records = [
        bridge.record_attempt(subject, "walk", "room1", "concept_success"),
        bridge.record_attempt(subject, "walk", "room2", "concept_failure"),
        bridge.record_attempt(subject, "open", "door1", "concept_success"),
    ]
    assert all(r.addr is not None for r in records)

    got = bridge.retrieve_attempts(subject)
    by = {(r.subject, r.action, r.object, r.outcome) for r in got}
    assert ("test_subject_alpha", "walk", "room1", "concept_success") in by
    assert ("test_subject_alpha", "walk", "room2", "concept_failure") in by
    assert ("test_subject_alpha", "open", "door1", "concept_success") in by


def test_record_link_prev_attempt(bridge):
    """Second recorded attempt of a subject links back to the previous one."""
    subject = "test_subject_beta"
    first = bridge.record_attempt(subject, "scan", "corridor", "concept_success")
    second = bridge.record_attempt(subject, "scan", "corridor2", "concept_success")
    assert first.addr is not None and second.addr is not None
    assert first.addr != second.addr
