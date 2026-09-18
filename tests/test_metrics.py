"""Stage-3 metrics unit tests (no live stack needed)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from metrics import MemoryScore, make_results_table, order_accuracy
from world import Step


class _R:
    """Shim mimicking AttemptRecord fields for order_accuracy."""

    def __init__(self, action, object):
        self.action = action
        self.object = object


def _steps(*pairs):
    return [Step(action=a, object=o, outcome="concept_success", score=0.0) for a, o in pairs]


def test_order_accuracy_perfect():
    exp = _steps(("travel", "beach"), ("dig", "beach"), ("travel", "camp"))
    got = [_R("travel", "beach"), _R("dig", "beach"), _R("travel", "camp")]
    assert order_accuracy(exp, got) == 1.0


def test_order_accuracy_reversed():
    exp = _steps(("travel", "beach"), ("dig", "beach"), ("travel", "camp"))
    got = [_R("travel", "camp"), _R("dig", "beach"), _R("travel", "beach")]
    assert order_accuracy(exp, got) == 0.0


def test_order_accuracy_partial():
    exp = _steps(("a", "1"), ("b", "2"), ("c", "3"))
    got = [_R("a", "1"), _R("c", "3"), _R("b", "2")]
    # pairs: (a1,b2) wrong; (b2,c3) wrong; (a1,c3) correct
    assert abs(order_accuracy(exp, got) - 1 / 2) < 1e-9


def test_order_accuracy_empty():
    assert order_accuracy([], []) == 0.0


def test_results_table():
    s = MemoryScore(episode_id="e1", recall=1.0, order_accuracy=0.5,
                    provenance_accuracy=1.0, contradictions=0,
                    retrieval_latency_per_attempt=0.01, recorded=3, retrieved=3,
                    first_pass_score=10.0, memory_replay_score=12.0)
    table = make_results_table([s])
    assert "e1" in table
    assert "1.00" in table
    assert "12.0" in table
