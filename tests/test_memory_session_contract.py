"""Writer/loader contracts for the OSTIS bridge seam.

Two probes in this project declared defects that did not exist. The first put a
node type in a template's connector slot. The second wrote session payloads that
the real producer never emits and concluded the loader was broken. Both were
the probe's fault, and both cost a full investigation.

The lesson is worth encoding as the default for this seam: for every writer and
its matching loader, assert that the payload the *product's own producer*
generates carries what the loader needs. Not a hand-written sample — the real
producer, called. Where the loader reconstructs a dataclass, assert the
round-trip the loader performs actually works.

`test_bridge_writer_contracts.py` holds the pairs. This file keeps the memory
session pair it grew out of, because that is the one that has already been
wrong once.

There is deliberately no test written to fail against a loader. Two of the three
loaders examined were correct; a test failing against correct code only encodes
the mistake and breaks when it is reverted.
"""
from __future__ import annotations

import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "python"

#: The key `load_memory_sessions` uses to accept and deduplicate a row.
IDENTITY_KEY = "session_id"

#: Keys a consumer of `bench.memory.retrieval.rank_graph` relies on.
CONSUMER_KEYS = ("date_epoch", "turns")


def _session_to_dict():
    from bench.memory.dataset import session_to_dict
    return session_to_dict


def test_real_producer_supplies_the_key_the_loader_demands():
    """The producer's payload must carry the loader's identity key."""
    payload = _session_to_dict()("s-1", "2024-01-05",
                                 [{"role": "user", "content": "q"}])

    assert IDENTITY_KEY in payload, (
        f"bench.memory.dataset.session_to_dict must emit {IDENTITY_KEY!r}: "
        "bridge.load_memory_sessions silently drops every row without it"
    )


def test_real_producer_supplies_the_keys_consumers_read_back():
    payload = _session_to_dict()("s-1", "2024-01-05",
                                 [{"role": "user", "content": "q"}])

    for key in CONSUMER_KEYS:
        assert key in payload, (
            f"bench.memory.retrieval.rank_graph reads {key!r} back off loaded "
            "sessions; the producer must emit it or retrieval breaks downstream"
        )


def test_loader_stores_and_reads_the_contract_shape_unchanged():
    """save/load must be lossless for the shape the producer emits."""
    import inspect

    sys.path.insert(0, str(BRIDGE.parent))
    from bridge import OneiroBridge

    payload = _session_to_dict()("s-7", "2024-03-01",
                                 [{"role": "user", "content": "q"},
                                  {"role": "assistant", "content": "a"}])

    source = inspect.getsource(OneiroBridge.save_memory_sessions)
    # The writer hands the caller's dict straight to the payload link, so the
    # loader's identity key is a caller guarantee and not something the writer
    # invents. If that ever changes, this is the place to notice.
    assert "json.dumps(session, sort_keys=True)" in source, (
        "save_memory_sessions no longer stores the caller's session verbatim; "
        "if it now synthesises fields, load_memory_sessions' identity key must "
        "be revisited"
    )
    assert IDENTITY_KEY in payload


def test_loader_documented_identity_key_is_the_one_it_filters_on():
    source = (BRIDGE / "bridge.py").read_text(encoding="utf-8")
    body = source.split("def load_memory_sessions", 1)[1].split("\n    def ", 1)[0]

    assert f'payload.get("{IDENTITY_KEY}")' in body, (
        f"load_memory_sessions must dedupe on {IDENTITY_KEY!r}; update "
        "IDENTITY_KEY here and the producer contract together"
    )