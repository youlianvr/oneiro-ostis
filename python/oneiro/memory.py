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
    blocked: tuple[str, ...] = ()

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
            "blocked": list(self.blocked),
        }


def _tcp_reachable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(host: str, port: int, *, timeout: float = PROBE_TIMEOUT) -> GraphFacts:
    """Read the graph and report exactly what could and could not be read.

    Never raises: a broken memory substrate is a state to display, not a crash
    for the page that displays it.
    """
    started = datetime.now(timezone.utc)
    blocked: list[str] = []

    if importlib.util.find_spec("sc_client") is None:
        blocked.append("sc_client is not installed; the memory backend cannot be reached")
        return _finished(started, GraphFacts(reachable=False, blocked=tuple(blocked)))

    if not _tcp_reachable(host, port, timeout):
        blocked.append(f"OSTIS server is unreachable at {host}:{port}")
        return _finished(started, GraphFacts(reachable=False, blocked=tuple(blocked)))

    try:
        return _finished(started, _read_graph(host, port))
    except Exception as exc:                       # noqa: BLE001 - reported, never hidden
        blocked.append(f"{type(exc).__name__}: {exc}")
        return _finished(started, GraphFacts(reachable=True, verified=False,
                                             blocked=tuple(blocked)))


def _read_graph(host: str, port: int) -> GraphFacts:
    """Traverse the live graph and collect real identifiers."""
    from sc_client.client import connect, disconnect, search_by_template  # type: ignore[import-not-found]
    from sc_client.constants import sc_type  # type: ignore[import-not-found]
    from sc_client.models import ScTemplate  # type: ignore[import-not-found]
    from sc_kpm.sc_keynodes import ScKeynodes  # type: ignore[import-not-found]

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
        blocked: list[str] = []
        if found and not concrete:
            # A match with wildcard endpoints is sc-memory echoing the relation
            # itself back, not content hanging off it. Reporting that as a
            # populated graph is exactly the false confidence this module exists
            # to prevent.
            blocked.append(
                f"the {len(found)} arc(s) matching {ANCHOR_RELATION} all have unresolved "
                "wildcard endpoints, so no content hangs off them: the graph answers "
                "the protocol but holds no traversable knowledge base"
            )
        elif not found:
            blocked.append(
                f"no arc in the graph uses {ANCHOR_RELATION}; the knowledge base appears empty"
            )
        elif not identifiers:
            blocked.append(
                "identifier arcs exist but their content could not be read back"
            )
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