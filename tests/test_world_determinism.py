"""Stage-3 world determinism test: same seed -> identical trace, twice."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from world import ExpeditionWorld, _noise


def _fixed_policy(state, legal, rng):
    """A fixed deterministic policy: first dig if possible, else first travel."""
    digs = [a for a in legal if a.startswith("dig:")]
    return digs[0] if digs else legal[0]


def test_same_seed_identical_trace():
    w1 = ExpeditionWorld(seed="oneiro-0")
    t1 = w1.run_episode(_fixed_policy, seed=7)
    w2 = ExpeditionWorld(seed="oneiro-0")
    t2 = w2.run_episode(_fixed_policy, seed=7)

    assert len(t1) == len(t2)
    for s1, s2 in zip(t1, t2):
        assert s1.action == s2.action
        assert s1.object == s2.object
        assert s1.outcome == s2.outcome
        assert abs(s1.score - s2.score) < 1e-9


def test_trace_hash_stable():
    import hashlib

    w = ExpeditionWorld(seed="oneiro-0")
    trace = w.run_episode(_fixed_policy, seed=7)
    h1 = hashlib.sha256(repr([(s.action, s.object, s.outcome, round(s.score, 6)) for s in trace]).encode()).hexdigest()
    w = ExpeditionWorld(seed="oneiro-0")
    trace = w.run_episode(_fixed_policy, seed=7)
    h2 = hashlib.sha256(repr([(s.action, s.object, s.outcome, round(s.score, 6)) for s in trace]).encode()).hexdigest()
    assert h1 == h2


def test_noise_values_deterministic():
    assert _noise("oneiro-0", 1) == _noise("oneiro-0", 1)
    assert _noise("a", 1) != _noise("b", 1)
    assert 1.0 <= _noise("x", 42) < 2.0


def test_budget_stops_episode():
    w = ExpeditionWorld(seed="oneiro-0", max_steps=5)
    trace = w.run_episode(_fixed_policy, seed=7)
    assert len(trace) <= 5
