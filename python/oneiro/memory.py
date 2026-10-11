"""What the memory layer can honestly say about OSTIS right now.

The plan forbids a silent SQLite or JSON substitute, so this module has no
fallback store and never pretends. There is exactly one backend — a real
sc-server — and when it is absent the answer is `reachable: false` with the
reason attached, not an empty graph that looks like a fresh install.

`sc_client` is deliberately not a package dependency. It talks to one specific
server, and a wheel that installs without it still starts and still tells the
truth about why it cannot read memory. The import happens inside the probe, so a
missing client is a reported condition rather than an ImportError at startup.

Reachability is not evidence. A TCP connect proves a socket answers and nothing
more, so `probe` goes further: it resolves a relation that exists in every OSTIS
knowledge base and reads the identifier string back out of the graph. That
traverses real structures, and it is the difference between "something is
listening" and "the knowledge base is loaded and readable".
"""
from __future__ import annotations

import importlib.util
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

#: Exists in any OSTIS knowledge base. Resolving and reading it back proves the
#: ontology is loaded rather than merely that a port is open.
ANCHOR_RELATION = "nrel_system_identifier"

#: Identifiers sampled from the anchor search, so the panel shows real strings
#: taken out of the graph rather than a bare count.
SAMPLE_LIMIT = 8

#: Longest a graph read may take before it is abandoned and reported as a
#: timeout rather than holding a request open.
PROBE_TIMEOUT = 4.0

#: The longest any page waits for the memory substrate before it says the read did
#: not finish. The read inside `sc_client` has no deadline of its own, so a port that
#: answers the connection and then goes silent used to hang the graph route until an
#: outer `wait_for` raised out of it and left `500 Internal Server Error` on screen
#: (measured 2026-10-11). Every route now asks `probe_within`, which returns facts
#: within this budget instead of an exception.
PROBE_BUDGET = 6.0

#: The codes a probe can finish with when the read does not complete in its budget.
TIMEOUT_CODE = "blocked.probe_timeout"


@dataclass(frozen=True)
class GraphFacts:
    """One honest reading of the memory substrate. No field is a guess."""

    reachable: bool = False
    verified: bool = False
    anchor: str = ""
    arcs_found: int = 0
    identifiers: tuple[str, ...] = ()
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    elapsed_ms: int = 0
    #: Why the graph could not be read, as `{"code": ..., "data": {...}}` rather than as
    #: sentences: the sentence belongs to `i18n`'s catalog, in the language of the page
    #: that shows it. A reason written here was English on the Russian graph page.
    blocked: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": "OSTIS",
            "fallback": None,
            "reachable": self.reachable,
            "verified": self.verified,
            "anchor": self.anchor,
            "arcs_found": self.arcs_found,
            "identifiers": list(self.identifiers),
            "checked_at": self.checked_at,
            "elapsed_ms": self.elapsed_ms,
            "blocked": [dict(item) for item in self.blocked],
        }


def _tcp_reachable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


#: How long a read that never came back stands for its target's next reading. A verdict
#: must not outlive its evidence: measured 2026-10-11, an unbounded note kept answering
#: `blocked.probe_timeout` for a target that had started answering again - with the graph
#: reading fine, the note answered in 0.018 s and never dialled - so the panel and the
#: graph page called a recovered graph unreadable. Past this window the target is read
#: again, and the reading that comes back is believed.
SILENT_SECONDS = 5.0

#: At most one *current* note per target whose read never came back: while it is fresh
#: every further read of *that* host and port reports the timeout immediately instead of
#: starting another worker, so a silent graph does not become one thread per page view.
#: Keyed by target, because a verdict is about one host and port: a process-wide one
#: restated a silent read of one graph as another port's verdict and lost the address it
#: was about (measured 2026-10-11). The value is that read and when it was parked, because
#: a read the note gives up on cannot be stopped - a target that never answers therefore
#: costs one new attempt per window, not one per view.
_SILENT: dict[tuple[str, int], tuple[threading.Thread, float]] = {}
_SILENT_LOCK = threading.Lock()


def _noted(target: tuple[str, int]) -> bool:
    """Whether a *fresh* note stands for this target's reading."""
    with _SILENT_LOCK:
        noted = _SILENT.get(target)
    return bool(noted and noted[0].is_alive()
                and time.monotonic() - noted[1] < SILENT_SECONDS)


#: A probe outcome a *panel* may interpolate: machine data only. The library's own
#: exception sentence is deliberately absent — `blocked.probe_failed` carries it on the
#: graph page, and printing it on every screen would spread the one English clause the
#: acceptance report names as a boundary.
PANEL_DATA = ("host", "port", "arcs", "anchor", "seconds")

#: A probe outcome in the panel's own vocabulary: the panel states the verdict and the
#: reason category, and the graph page carries the diagnosis.
_PANEL_CODES = {"blocked.probe_failed": "blocked.graph_unreadable",
                TIMEOUT_CODE: "blocked.graph_unreadable"}


def panel_reasons(facts: GraphFacts) -> list[dict[str, Any]]:
    """What a status page may report: codes with machine data, never a sentence."""
    reported: list[dict[str, Any]] = []
    for item in facts.blocked:
        code = str(item.get("code", "")) if isinstance(item, dict) else str(item)
        mapped = _PANEL_CODES.get(code)
        if mapped is not None:
            # The panel's own sentence, and it asks for no data: the diagnosis (and the
            # library's text) stays on the graph page.
            reported.append({"code": mapped})
            continue
        raw = item.get("data") if isinstance(item, dict) else None
        data = {key: value for key, value in (raw or {}).items() if key in PANEL_DATA}
        reported.append({"code": code, "data": data} if data else {"code": code})
    return reported


def probe_within(host: str, port: int, *, timeout: float = PROBE_TIMEOUT,
                 budget: float = PROBE_BUDGET) -> GraphFacts:
    """`probe`, with a deadline: it returns facts and never raises or hangs.

    The read runs in a daemon worker so a dependency that never returns cannot hold a
    request open; `budget` bounds it. A target that is still silent in the next window is
    reported from the same facts, not by starting a second stuck worker for it - but only
    for `SILENT_SECONDS`, because a note is evidence and evidence ages: the first read of
    the next window is a real one, so a graph that came back is read and believed again.
    """
    target = (host, port)
    if _noted(target):
        return _timed_out(host, port, timeout, budget)
    box: list[GraphFacts] = []

    def read() -> None:
        try:
            box.append(probe(host, port, timeout=timeout))
        except Exception as exc:                       # noqa: BLE001 - reported, never raised
            box.append(GraphFacts(blocked=(
                {"code": "blocked.probe_failed",
                 "data": {"exception": f"{type(exc).__name__}: {exc}"}},)))

    worker = threading.Thread(target=read, name="oneiro-probe", daemon=True)
    worker.start()
    worker.join(budget)
    if worker.is_alive():
        with _SILENT_LOCK:
            _SILENT[target] = (worker, time.monotonic())
        return _timed_out(host, port, timeout, budget)
    with _SILENT_LOCK:
        _SILENT.pop(target, None)       # the read finished, so nothing stands for it now
    return box[0] if box else _timed_out(host, port, timeout, budget)


def _timed_out(host: str, port: int, timeout: float, budget: float) -> GraphFacts:
    """The read did not finish. Reachability is measured here, not claimed."""
    return GraphFacts(reachable=_tcp_reachable(host, port, timeout),
                      blocked=(({"code": TIMEOUT_CODE, "data": {"seconds": budget}},)))


def probe(host: str, port: int, *, timeout: float = PROBE_TIMEOUT) -> GraphFacts:
    """Read the graph and report exactly what could and could not be read.

    Never raises: a broken memory substrate is a state to display, not a crash
    for the page that displays it.
    """
    started = datetime.now(timezone.utc)
    blocked: list[dict[str, Any]] = []

    if importlib.util.find_spec("sc_client") is None:
        blocked.append({"code": "blocked.client_absent"})
        return _finished(started, GraphFacts(reachable=False, blocked=tuple(blocked)))

    if not _tcp_reachable(host, port, timeout):
        blocked.append({"code": "blocked.graph_unreachable",
                        "data": {"host": host, "port": port}})
        return _finished(started, GraphFacts(reachable=False, blocked=tuple(blocked)))

    try:
        return _finished(started, _read_graph(host, port))
    except Exception as exc:                       # noqa: BLE001 - reported, never hidden
        # The exception's own prose is data, not a sentence to translate: it is
        # interpolated into the catalog's wording for this code.
        blocked.append({"code": "blocked.probe_failed",
                        "data": {"exception": f"{type(exc).__name__}: {exc}"}})
        return _finished(started, GraphFacts(reachable=True, verified=False,
                                             blocked=tuple(blocked)))


def _read_graph(host: str, port: int) -> GraphFacts:
    """Traverse the live graph and collect real identifiers."""
    from sc_client.client import connect, disconnect, search_by_template
    from sc_client.constants import sc_type
    from sc_client.models import ScTemplate
    from sc_kpm.sc_keynodes import ScKeynodes

    connect(f"ws://{host}:{port}")
    try:
        # Anchor on a CONCRETE SOURCE, not on the relation.
        #
        # A sweep that varies the source and fixes the connector - the obvious
        # way to "find everything using this relation" - does not work on this
        # sc-memory build. Measured 2026-10-02 against sc-server 0.10.5 on a
        # graph known to contain such arcs, every one of these returned exactly
        # one result whose endpoints were both ScAddr(0):
        #     (VAR, anchor, VAR)  (VAR_NODE, anchor, VAR_NODE)
        #     (VAR_NODE, anchor, VAR_NODE_LINK)  (VAR_NODE, anchor, VAR_CONNECTOR)
        # while the same server returned real triples the moment the SOURCE was
        # concrete:
        #     (ScAddr(196609), VAR_CONNECTOR, VAR_NODE) -> (196609, 196611, 196610)
        #
        # So: walk outward from a resolved relation instead of sweeping on it.
        # A relation node carries its own identifier through a common arc, and
        # reading that string back is exactly the proof this module exists for.
        anchor = ScKeynodes[ANCHOR_RELATION]
        template = ScTemplate()
        template.triple(anchor, sc_type.VAR_COMMON_ARC, sc_type.VAR_NODE_LINK)
        found = search_by_template(template)
        concrete = [t for t in found if t.get(0).value != 0 and t.get(2).value != 0]
        identifiers = []
        for triple in concrete[:SAMPLE_LIMIT]:
            try:
                identifier = _identifier_of(triple)
            except Exception:                      # noqa: BLE001 - a bad sample is skipped
                continue
            if identifier:
                identifiers.append(identifier)
        verified = bool(concrete) and bool(identifiers)
        blocked: list[dict[str, Any]] = []
        if found and not concrete:
            # A match with wildcard endpoints is sc-memory echoing the relation
            # itself back, not content hanging off it. Reporting that as a
            # populated graph is exactly the false confidence this module exists
            # to prevent.
            blocked.append({"code": "blocked.arcs_unresolved",
                            "data": {"arcs": len(found), "anchor": ANCHOR_RELATION}})
        elif not found:
            blocked.append({"code": "blocked.graph_empty",
                            "data": {"anchor": ANCHOR_RELATION}})
        elif not identifiers:
            blocked.append({"code": "blocked.identifiers_unreadable"})
        return GraphFacts(reachable=True, verified=verified, anchor=ANCHOR_RELATION,
                          arcs_found=len(found), identifiers=tuple(identifiers),
                          blocked=tuple(blocked))
    finally:
        try:
            disconnect()
        except Exception:                          # noqa: BLE001 - closing is best effort
            pass


def _identifier_of(triple: Any) -> str | None:
    """Read one identifier string back out of the graph."""
    from sc_client.client import get_link_content

    contents = get_link_content(triple.get(2))
    for content in contents or []:
        if content.data is not None:
            return str(content.data)
    return None


def _finished(started: datetime, facts: GraphFacts) -> GraphFacts:
    elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return GraphFacts(**{**facts.__dict__, "elapsed_ms": elapsed})