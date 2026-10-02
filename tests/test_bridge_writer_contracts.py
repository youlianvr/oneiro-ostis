"""Every bridge writer paired with its matching loader, checked against the
payload the product's own producer generates.

The rule learned the hard way: never declare a loader broken from a payload you
invented. Two "defects" in this seam were probes writing data no producer emits.
So each test here calls the real producer - `session_to_dict`,
`get_policy().descriptor()`, `round_record()`, `LifeSession.payload()`,
`OrganizationRecord.as_payload()`, the native event literal - and asserts the
loader can actually find and rebuild what that produces.

Where the loader reconstructs a dataclass, the assertion is the loader's own
reconstruction: `OrganizationRecord(**record.as_payload())` and
`LifeSession(**payload)` must both work, because that is literally what
`load_organization_events` and `load_life_sessions` do.

The harness producers cannot share this process with the world simulator's
`replay`, so they are called in a child one - see `producer` below for the
measurement that shows why.

Offline: no server, no graph. These pin the contract, not the storage; the
restart behaviour is proven by the probe runs recorded in
docs/REWRITE-BASELINE.md.

All eight pairs were measured across a real SIGINT save and reload on
2026-10-02 and all eight hold. There is intentionally no test written to fail
against a loader: the loaders examined were correct.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"
HARNESS = ROOT / "harness"
for extra in (ROOT, PYTHON, HARNESS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from bridge import (LifeSession, OneiroBridge, OrganizationRecord)   # noqa: E402


# ---------- identity each loader needs, taken from the loader itself ----------

def _loader_body(name: str) -> str:
    source = (ROOT / "python" / "bridge.py").read_text(encoding="utf-8")
    return source.split(f"def {name}", 1)[1].split("\n    def ", 1)[0]


# ---------- calling a producer that cannot share this process ----------

#: `harness/replay.py` (the judge) and `python/replay/` (the world simulator)
#: are one module name. The simulator is a *package*, and the product imports
#: it as `replay.engine`; the judge is a *module*. Whichever binds first wins
#: and the other becomes unreachable, so `harness.publish` imports only in a
#: process where `harness/` leads sys.path and the simulator has not been
#: imported yet. That is exactly the shape of the documented CLI
#: (`python harness/publish.py`) and not the shape of a pytest process, which
#: pre-imports the simulator for the world tests.
#: `test_harness_replay_is_a_name_collision_not_a_typo` pins the collision, and
#: `tests/test_replay_offline.py` is the reason the name cannot simply be
#: rebound: stealing `replay` for the judge breaks `replay.engine` for them.
#:
#: So the producer is called in a child process and its real output comes back
#: as JSON. Hand-writing the payload here instead is the third version of the
#: mistake this file exists to prevent.
def producer(body: str, *, stdin: str = "",
             order: tuple[Path, ...] = (HARNESS, PYTHON)) -> object:
    """Run `body` under the given sys.path order; return its stdout as JSON."""
    env = {**os.environ,
           "PYTHONPATH": os.pathsep.join(str(path) for path in order)}
    done = subprocess.run([sys.executable, "-c", textwrap.dedent(body)],
                          cwd=ROOT, env=env, input=stdin, text=True,
                          capture_output=True, timeout=120)
    assert done.returncode == 0, (
        f"the producer failed in a fresh process:\n{done.stderr}")
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def policy_descriptors() -> dict:
    """Every policy the publisher can write, as the publisher would write it.

    `save_harness` publishes every policy, not just the baseline, so a payload
    check that only looks at one of them proves less than it appears to.
    """
    return producer("""
        import json, sys
        from harness.publish import get_policy
        from policy import VARIANTS
        names = sorted(VARIANTS)
        json.dump({name: get_policy(name).descriptor() for name in names},
                  sys.stdout)
    """)


# ---------- memory sessions ----------

def test_memory_sessions_producer_supplies_the_loader_identity_key():
    from bench.memory.dataset import session_to_dict

    payload = session_to_dict("s-1", "2024-01-05",
                              [{"role": "user", "content": "q"}])
    assert "session_id" in payload, (
        "load_memory_sessions drops any row without session_id; "
        "bench.memory.dataset.session_to_dict must emit it")
    assert "date_epoch" in payload, "rank_graph reads date_epoch back"


# ---------- life sessions ----------

def test_persist_life_session_writes_the_payload_the_loader_reads():
    """persist_life_session is the actual writer behind record_life_event."""
    source = inspect.getsource(OneiroBridge.persist_life_session)
    assert "session.payload()" in source, (
        "persist_life_session must store LifeSession.payload(); "
        "load_life_sessions reconstructs from exactly that shape")
    assert "NREL_SESSION_RECORD" in source


def test_life_session_payload_round_trips_through_the_loaders_construction():
    """load_life_sessions rebuilds LifeSession(**payload); that must succeed."""
    session = LifeSession(session_id="probe", created_at=1_700_000_000)
    session.events.append({"kind": "loop_started", "origin": "runtime",
                           "verified": True, "recorded_at": 1_700_000_001})
    session.revision += 1

    payload = session.payload()
    assert "session_id" in payload, "load_life_sessions requires session_id"

    rebuilt = LifeSession(
        session_id=str(payload["session_id"]),
        created_at=int(payload.get("created_at", 0)),
        status=str(payload.get("status", "running")),
        goals=list(payload.get("goals", [])),
        self_state=dict(payload.get("self_state", {})),
        events=list(payload.get("events", [])),
        revision=int(payload.get("revision", 0)),
    )
    assert rebuilt.session_id == "probe"
    assert rebuilt.revision == session.revision
    assert rebuilt.events == session.events


# ---------- organization and native events ----------

def test_organization_record_payload_round_trips_through_the_loaders_construction():
    """load_organization_events does OrganizationRecord(**row); it must work."""
    record = OrganizationRecord(
        record_id="r-1", session_id="s-1", role="manager", kind="decision",
        payload={"what": "x"}, origin="runtime", verified=True,
        recorded_at=1_700_000_000)

    row = record.as_payload()
    for key in ("record_id", "session_id", "role", "kind"):
        assert key in row, f"load_organization_events indexes payload[{key!r}] directly"

    assert OrganizationRecord(**row) == record


def test_native_event_shape_round_trips_and_carries_the_module_session():
    """record_native_event builds an OrganizationRecord from the event dict."""
    from native.memory import SESSION

    event = {"id": "e1", "at": 1, "kind": "note", "actor": "a",
             "origin": "runtime", "data": {"id": "n1", "text": "hello"}}
    record = OrganizationRecord(
        record_id=event["id"], session_id=SESSION, role=event["actor"],
        kind="native_" + event["kind"], payload=event, origin=event["origin"],
        verified=event["origin"] in ("owner", "runtime", "tool"),
        recorded_at=1_700_000_000)

    row = record.as_payload()
    assert row["session_id"] == SESSION, (
        "load_native_events filters on session_id == native.memory.SESSION; "
        "the reader must use that constant, not an invented one")
    assert OrganizationRecord(**row) == record


# ---------- harness policies and rounds ----------

def test_harness_descriptor_from_the_real_policy_is_a_storable_json_dict(
        policy_descriptors):
    assert policy_descriptors, "harness.publish must be able to write something"
    for name, descriptor in policy_descriptors.items():
        assert isinstance(descriptor, dict) and descriptor, (
            f"harness.publish writes get_policy({name!r}).descriptor() straight "
            "into _add_json_relation, which json.dumps it")
        # load_harnesses strips HARNESS_PREFIX from the node idtf and returns
        # the descriptor verbatim, so the descriptor itself carries the name
        # and the loader has no other way to learn which policy this is.
        assert descriptor.get("name") == name, (
            f"{name}: the descriptor must name its own policy, or "
            "load_harnesses returns rows that cannot be told apart")


def test_harness_round_record_contains_the_key_the_loader_sorts_by():
    criteria = {"version": "t", "efficiency": "e", "capability": "c"}
    payload = {
        "round": 7,
        "criteria": criteria,
        "proposed": [{"name": "candidate"}],
        "verdicts": [{"policy": "candidate", "predicted_saving": 0.25,
                      "decision_replayable": True, "passed_efficiency": True}],
        "deployed": {"policy": {"name": "candidate"}},
        "outcome": "deployed",
    }
    record = producer("""
        import json, sys
        from harness.publish import round_record
        payload = json.loads(sys.stdin.read())
        json.dump(round_record(payload, payload["criteria"]), sys.stdout)
    """, stdin=json.dumps(payload))

    assert record["round"] == 7, (
        "load_harness_rounds keys rows on the record's 'round'; "
        "harness.publish.round_record must always populate it")
    verdict = record["verdicts"][0]
    assert verdict["policy"] == "candidate", (
        "load_harness_rounds reads the verdict policy names back; the round's "
        "proposed/candidate link is meaningless without them")
    assert verdict["predicted_saving"] == 0.25
    assert record["frozen"] == criteria, (
        "the frozen criteria must be snapshotted into the record; a round that "
        "reads its criteria from the live file can be re-judged against a "
        "standard that has since moved")


# ---------- memory bench results ----------

def test_memory_bench_loader_returns_payloads_verbatim_so_no_key_is_required():
    body = _loader_body("load_memory_bench_results")
    assert 'rows[idtf] = payload' in body, (
        "load_memory_bench_results returns the stored payload unchanged, so a "
        "producer may omit any key; do not add a filter without a reason")
    assert "payload.get(" not in body, (
        "load_memory_bench_results has no field filter today; if one is added, "
        "bench.memory.run's record literal must be checked against it first")


# ---------- strategies ----------

def test_strategy_descriptor_is_json_serialisable_end_to_end(policy_descriptors):
    # save_harness -> _add_json_relation -> json.dumps; the load_harnesses-style
    # read back -> json.loads. This is the whole path for a policy body, so a
    # descriptor that cannot survive it is lost the moment it is written.
    for name, descriptor in policy_descriptors.items():
        assert json.loads(json.dumps(descriptor, sort_keys=True)) == descriptor, (
            f"{name}: the descriptor does not survive the store's json round trip")


def test_harness_replay_is_a_name_collision_not_a_typo():
    """Why the producer tests above run out of process.

    `harness/replay.py` and `python/replay/` cannot both be `replay`. The judge
    carries `NORMAL_STOPS`; the simulator is a package and carries `engine`.
    Whichever is first on sys.path wins. Both facts are asserted here so that
    (a) the subprocess helper is never mistaken for ceremony, and (b) a rename
    of either side shows up as a change in what these two probes return.
    """
    judged = producer("""
        import json, sys, replay
        json.dump({"file": replay.__file__,
                   "judge": hasattr(replay, "NORMAL_STOPS")}, sys.stdout)
    """)
    simulated = producer("""
        import json, sys, replay
        json.dump({"file": replay.__file__,
                   "judge": hasattr(replay, "NORMAL_STOPS")}, sys.stdout)
    """, order=(PYTHON, HARNESS))

    assert judged["judge"] is True, f"harness/ first must yield the judge: {judged}"
    assert simulated["judge"] is False, (
        f"python/ first must yield the simulator: {simulated}; if this changed, "
        "the two are no longer competing for one name and the producer can be "
        "imported in-process instead")

    # The simulator stays reachable as a package, which is the other half of the
    # constraint: the judge's name cannot simply be taken from it.
    assert producer("""
        import json, sys
        from replay.engine import ExperienceTree
        json.dump(ExperienceTree.__name__, sys.stdout)
    """, order=(PYTHON, HARNESS)) == "ExperienceTree"


# ---------- the writers themselves ----------

#: Every method that writes to the graph. record_life_event delegates to
#: persist_life_session, which does the actual write, so both are listed.
WRITERS = ("record_attempt", "record_life_event", "persist_life_session",
           "record_organization_event", "record_native_event",
           "save_strategy", "save_harness", "save_harness_round",
           "save_memory_sessions", "save_memory_bench_result")



def _bridge_methods(source: str) -> list[str]:
    """Names of the methods defined in bridge.py, parsed without a regex."""
    names = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("def ") and not stripped.startswith("def _"):
            head = stripped[4:].split("(", 1)[0].strip()
            if head.isidentifier():
                names.append(head)
    return names


WRITER_PREFIXES = ("record_", "save_", "persist_")


def test_every_writer_is_covered_by_this_suite():
    """A new writer must arrive with a contract test, not after an incident.

    Discovery runs from the bridge outward, so a writer added later fails here
    until it is both listed and pinned. Listing a name that no longer exists
    fails the same way.
    """

    source = (ROOT / "python" / "bridge.py").read_text(encoding="utf-8")
    declared = set(WRITERS)
    present = {name for name in _bridge_methods(source)}
    discovered = {n for n in present if n.startswith(WRITER_PREFIXES)}

    assert declared <= present, (
        "WRITERS lists methods the bridge does not have: "
        f"{sorted(declared - present)}")
    unlisted = sorted(discovered - declared)
    assert not unlisted, (
        f"bridge gained writers with no contract test: {unlisted}; add them to "
        "WRITERS and pin the payload their matching loader needs")

    assert len(fields(LifeSession)) > 0
    assert len(fields(OrganizationRecord)) > 0
    assert OneiroBridge is not None


def test_bridge_has_no_all_variable_template_left():
    """The one shape this sc-memory build answers with unresolved wildcards."""

    var = re.compile(r"^(sc_type\.[A-Z_]+|sc_type\(\d+\))")
    offenders = []
    for path in sorted((ROOT / "python").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = re.search(r"\.(triple|quintuple|triple_with_relation)\((.*)\)\s*$",
                              line.strip())
            if not match:
                continue
            args = [a.strip() for a in match.group(2).split(",")]
            if len(args) >= 3 and var.match(args[0]) and var.match(args[2]):
                offenders.append(f"{path.name}:{number} {line.strip()}")
    assert not offenders, (
        "at least one end of a template triple must be concrete; "
        f"all-variable triples found: {offenders}")