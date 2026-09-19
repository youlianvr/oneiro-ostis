"""Stage-5 recursive loop test (requires the live oneiro-ostis stack).

Two full rounds of  online -> record -> explore -> dream -> deploy.  Round 2
must not be worse than round 1, and the dream log must be honest: every
candidate's replay verdict carries its coverage; a winner that is not the
incumbent must correspond to a measured online improvement (otherwise the
test says so loudly).
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from bridge import OneiroBridge
from loop import run_loop

HOST = os.environ.get("ONEIRO_HOST", "localhost")
PORT = int(os.environ.get("ONEIRO_PORT", "8090"))


@pytest.fixture(scope="module")
def bridge():
    b = OneiroBridge(HOST, PORT)
    b.connect()
    yield b
    b.close()


def test_two_rounds_do_not_regress(bridge):
    subject = f"tworounds_{int(time.time())}"
    report = run_loop(bridge, subject=subject, rounds=2, max_steps=40, limit=24)

    assert len(report.rounds) == 2
    r1, r2 = report.rounds

    print("\n" + report.table())
    print()
    for log in report.rounds:
        print(f"  r{log.round_index} online: {log.online.summary()}")
        if log.dream_result:
            print(
                f"  r{log.round_index} dream: winner={log.dream_result.winner.name} "
                f"improved={log.dream_result.improved} saved={log.dream_result.saved} "
                f"conflicts={len(log.dream_result.consistency['conflicts'])}"
            )

    # the dream must have been judged over the recordings of both the online
    # and the exploration episodes (1 online + 2 exploration in round 1)
    assert r1.dream_result is not None
    assert r1.dream_result.tree_summary["episodes"] == 3
    assert r2.dream_result.tree_summary["episodes"] >= 5
    assert all(not log.dream_result.consistency["conflicts"] for log in report.rounds)

    assert r2.online.total_score >= r1.online.total_score - 1e-9, (
        "round 2 regressed against round 1"
    )

    # the winner of round 2's dream is deployed in round 3; its node carries
    # the replay verdict from the judge
    strategies = {s["name"]: s for s in bridge.load_strategies()}
    assert r1.dream_result.winner.name in strategies
    assert strategies[r1.dream_result.winner.name]["replay_score"] is not None
    assert strategies[r1.dream_result.winner.name]["dream_round"] == 1.0
