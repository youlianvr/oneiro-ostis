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


def test_delivery_legality_and_gain():
    """Delivery is legal only while standing at a delivery point, and the
    multiplier applies (cove 1.5x > beach 1.2x > camp 1.0x).

    Regression: an earlier version offered deliver:<neighbour> only, which
    the executor always rejected as illegal — deliveries never succeeded.
    """
    w = ExpeditionWorld(seed="oneiro-0", max_steps=40)
    assert "deliver:camp" not in w.legal_actions()  # nothing carried yet

    w.step("travel:beach")
    w.step("dig:beach")
    assert "deliver:beach" in w.legal_actions()  # standing at a delivery point
    carry = w.state.carrying
    assert carry.startswith("artefact_beach_")

    step = w.step("deliver:beach")
    assert step.outcome == "concept_success"
    assert step.score > 0
    assert w.state.score == step.score


def test_site_can_be_dig_out_completely():
    """Every artefact of a site is reachable: digging stays legal while any
    remains (regression: the old gate stopped at half the site).
    """
    w = ExpeditionWorld(seed="oneiro-0", max_steps=200)
    w.reset()
    counts: dict[str, int] = {}
    # travel to beach (camp has no dig), then dig and deliver in place
    w.step("travel:beach")
    for _ in range(50):
        legal = w.legal_actions()
        digs = [a for a in legal if a.startswith("dig:beach")]
        if digs:
            w.step(digs[0])
            counts["beach"] = w.state.dug_count.get("beach", 0)
        elif "deliver:beach" in legal:
            w.step("deliver:beach")
        else:
            break
    assert counts["beach"] == w._site_value_counters["beach"], (
        f"only dug {counts['beach']} of {w._site_value_counters['beach']} artefacts"
    )


def test_trace_hash_stable_across_processes():
    """The same seed gives the same trace in a fresh interpreter.

    Regression: artefact values used Python's built-in hash(), which is
    randomized per process (PYTHONHASHSEED) — traces differed between runs.
    """
    import subprocess

    script = (
        "import sys, hashlib; "
        "sys.path.insert(0, r'%s'); "
        "from world import ExpeditionWorld; "
        "w = ExpeditionWorld(seed='oneiro-0'); "
        "trace = w.run_episode(lambda state, legal, rng: ([a for a in legal if a.startswith('dig:')] or legal)[0], seed=7); "
        "print(hashlib.sha256(repr([(s.action, s.object, s.outcome, round(s.score, 6)) for s in trace]).encode()).hexdigest())"
        % os.path.join(os.path.dirname(__file__), "..", "python")
    )

    env_base = dict(os.environ)
    hashes = []
    for hashseed in ("1", "12345"):
        env = dict(env_base)
        env["PYTHONHASHSEED"] = hashseed
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env)
        assert out.returncode == 0, out.stderr
        hashes.append(out.stdout.strip())
    assert hashes[0] == hashes[1], f"trace differs across processes: {hashes}"
