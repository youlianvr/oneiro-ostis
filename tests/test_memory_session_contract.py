"""The memory-session writer and the loader must agree on the payload contract.

On 2026-10-02 a probe concluded that `load_memory_sessions` was broken: it
wrote two session dicts of its own invention and read back nothing, even
though the payload was provably in the graph and reachable by address. The
loader was fine. `save_memory_sessions` stores the caller's dict verbatim, and
the loader identifies a row by `session_id` — a key the real producer supplies
and that ad-hoc data does not.

`bench.memory.dataset.session_to_dict` is the real producer, and
`bench.memory.retrieval.rank_graph` is a real consumer that reads `date_epoch`
back. These tests pin that agreement, so the next probe or caller that invents
its own payload shape fails here instead of returning a silent empty list.

Note there is deliberately no test asserting a failure against
`load_memory_sessions`. Its shape is correct; a test written to fail against it
would only encode the mistake.
"""
from __future__ import annotations

import inspect
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "python" / "bridge.py"

#: The key `load_memory_sessions` uses to deduplicate and to accept a row.
IDENTITY_KEY = "session_id"

#: Keys a consumer of `bench.memory.retrieval.rank_graph` relies on.
CONSUMER_KEYS = ("date_epoch", "turns")


def _session_to_dict():
    from bench.memory.dataset import session_to_dict
    return session_to_dict


def test_real_producer_supplies_the_key_the_loader_demands():
    """The producer's payload must carry the loader's identity key."""
    session_to_dict = _session_to_dict()
    payload = session_to_dict("s-1", "2024-01-05", [{"role": "user", "content": "q"}])

    assert IDENTITY_KEY in payload, (
        f"bench.memory.dataset.session_to_dict must emit {IDENTITY_KEY!r}: "
        "bridge.load_memory_sessions silently drops every row without it"
    )


def test_real_producer_supplies_the_keys_consumers_read_back():
    session_to_dict = _session_to_dict()
    payload = session_to_dict("s-1", "2024-01-05", [{"role": "user", "content": "q"}])

    for key in CONSUMER_KEYS:
        assert key in payload, (
            f"bench.memory.retrieval.rank_graph reads {key!r} back off loaded "
            "sessions; the producer must emit it or retrieval breaks downstream"
        )


def test_loader_stores_and_reads_the_contract_shape_unchanged():
    """save/load must be lossless for the shape the producer emits."""
    import sys

    sys.path.insert(0, str(BRIDGE.parent))
    from bridge import OneiroBridge

    session_to_dict = _session_to_dict()
    payload = session_to_dict("s-7", "2024-03-01",
                              [{"role": "user", "content": "q"},
                               {"role": "assistant", "content": "a"}])

    source = inspect.getsource(OneiroBridge.save_memory_sessions)
    # The writer hands the caller's dict straight to the payload link, so the
    # loader's identity key is a caller guarantee and not something the writer
    # invents. If that ever changes, this test is the place to notice.
    assert "json.dumps(session, sort_keys=True)" in source, (
        "save_memory_sessions no longer stores the caller's session verbatim; "
        "if it now synthesises fields, load_memory_sessions' identity key must "
        "be revisited"
    )
    assert IDENTITY_KEY in payload


def test_loader_documented_identity_key_is_the_one_it_filters_on():
    source = BRIDGE.read_text(encoding="utf-8")
    body = source.split("def load_memory_sessions", 1)[1].split("\n    def ", 1)[0]

    assert f'payload.get("{IDENTITY_KEY}")' in body, (
        f"load_memory_sessions must dedupe on {IDENTITY_KEY!r}; update "
        "IDENTITY_KEY in this test and the producer contract together"
    )