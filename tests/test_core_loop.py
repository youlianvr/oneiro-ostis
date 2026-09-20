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


def test_life_session_survives_bridge_restart(bridge):
    """The latest self-state is recovered from OSTIS after reconnecting."""
    import uuid

    session_id = f"restart_{uuid.uuid4().hex}"
    session = bridge.start_life_session(
        session_id,
        goals=[{"text": "inspect the memory adapter", "origin": "human"}],
        self_state={"confidence": {"memory": 0.2}},
    )
    bridge.record_life_event(
        session,
        {"kind": "observation", "text": "the adapter has no restart test"},
        origin="model",
    )
    bridge.finish_life_session(
        session,
        self_state={"confidence": {"memory": 0.4}, "last_action": "write test"},
    )

    bridge.close()
    fresh = OneiroBridge(HOST, PORT)
    fresh.connect()
    try:
        recovered = fresh.load_latest_life_session()
        assert recovered is not None
        assert recovered.session_id == session_id
        assert recovered.status == "finished"
        assert recovered.self_state["last_action"] == "write test"
        assert recovered.events[-1]["origin"] == "model"
        assert recovered.events[-1]["verified"] is False

        manager = fresh.record_organization_event(
            session_id=session_id,
            role="manager",
            kind="proposal_decision",
            payload={"decision": "send_to_worker", "reason": "testable change"},
            origin="rule",
            verified=True,
            record_id=f"decision_{uuid.uuid4().hex}",
        )
        worker = fresh.record_organization_event(
            session_id=session_id,
            role="worker",
            kind="pr_packet",
            payload={"branch": "agent/test", "tests": ["core loop"]},
            origin="worker",
            record_id=f"pr_{uuid.uuid4().hex}",
        )
        records = fresh.load_organization_events(session_id)
        assert [record.role for record in records[-2:]] == ["manager", "worker"]
        assert manager.verified is True
        assert worker.payload["branch"] == "agent/test"
    finally:
        fresh.close()
