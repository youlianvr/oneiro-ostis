"""Bounded queries over the graph, so nothing has to read the whole log.

`load_organization_events()`, `load_life_sessions()` and `load_strategies()`
read every member of a class and then slice in Python. The consumers want the
opposite of that. The host MCP tools ask for "the most recent N"; the Telegram
entry point and the task runner want "the latest session with this prefix"; both
currently read the whole class to find it. Measured on the live graph,
`concept_attempt` holds 3270 members and reading their payloads costs 11.2
seconds, so a full-log read is a latency problem, not a style one.

**The paging key is the node address, not the timestamp.** A record's
`recorded_at` lives only inside its JSON string link, so any time-ordered read
costs one link read per candidate. Addresses are allocated in creation order and
survive a save and reload, so a page can be *selected* from addresses alone and
only the page's payloads are read. Measured 2026-10-02 on the live graph:
descending-address order equalled descending-`recorded_at` order for every
organisation record that could be compared, and the entity lookup it enables is
a single `ScKeynodes` hit.

That is insertion order, and it is deliberately not claimed to be time order. A
clock that steps backwards makes the two disagree, which is why `recent()` sorts
what it returns and why `range()` reads a timestamp per candidate instead of
trusting the address.

**A page reports what it could not read.** A record whose payload will not decode
is returned in `skipped` with its address and the reason. It is never dropped
into a shorter list, because a silently shortened result is indistinguishable
from a graph that holds nothing - the exact failure this stage exists to remove.

**A missing thing is not a broken thing.** `entity()` returning `None` means the
identifier is absent, and that is an answer. Anything that prevented the answer -
no client, no server, no class, an unusable cursor - raises `GraphQueryError`
with a code. Nothing here catches an exception and returns an empty page,
because that is how "the server is down" becomes "there is no memory" two
layers away.

`sc_client` is imported inside the functions that use it, as in `memory.py`: a
wheel without it still installs and its absence is reported rather than raised at
import time.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

#: Bumped when the cursor encoding changes, so an old cursor is refused with a
#: reason instead of paging from the wrong place.
CURSOR_VERSION = 1

#: How many members of a class one query may look at before it stops and says so.
#: A page needs a handful; an old range window may need many. Either way the
#: caller is told the scan was bounded, rather than handed a partial answer
#: dressed as a complete one.
DEFAULT_SCAN_LIMIT = 2000

#: A page is a page. This caps what one call returns, so a caller asking for a
#: million rows gets an error it can act on instead of a hung request.
MAX_LIMIT = 500

DEFAULT_LIMIT = 50

#: Relation carrying an ordering timestamp as a numeric link, tried before the
#: payload: an attempt writes `nrel_timestamp`, so a range read over attempts
#: needs no JSON at all. `TIMESTAMP_KEYS` is the fallback for writers that only
#: stored the stamp inside the payload.
TIMESTAMP_RELATIONS = ("nrel_timestamp",)

#: Payload keys a record may carry its timestamp under, in the order the writers
#: write them. `created_at` is last because it is the life-session writer's key:
#: `LifeSession.payload()` writes it and `load_life_sessions()` orders by it, so
#: a range or recent over sessions must find it here or it places nothing.
TIMESTAMP_KEYS = ("recorded_at", "ts", "timestamp", "created_at")

#: Which relation each class's payload hangs off, taken from the writers that
#: create those records rather than guessed per address. A class not listed here
#: has no single JSON payload - attempts hold several typed relations, strategies
#: a descriptor link plus three numeric ones - so those need an injected reader.
RECORD_RELATIONS = {
    "concept_organization_record": "nrel_organization_record",
    "concept_session": "nrel_session_record",
    "concept_memory_session": "nrel_memory_session_payload",
    "concept_harness": "nrel_harness_descriptor",
}


class GraphQueryError(RuntimeError):
    """A query that could not be answered, with the reason attached.

    Raised instead of returning an empty page.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.reason = message


@dataclass(frozen=True)
class Skipped:
    """One record the query found but could not hand back, and why."""

    address: int
    reason: str


@dataclass(frozen=True)
class QueryPage:
    """One bounded result.

    `items` is newest-last, which is the order the host tools display. The
    cursor walks the other way, because a cursor is a position you resume *from*.
    """

    items: tuple[dict[str, Any], ...] = ()
    cursor: Optional[str] = None
    candidates: int = 0
    scanned: int = 0
    skipped: tuple[Skipped, ...] = ()
    truncated: bool = False


class GraphBackend(Protocol):
    """What the paging logic needs from the graph.

    Narrow on purpose. `BridgeBackend` implements it over the bridge's proven
    primitives and a test implements it over a dict, so the cursor, limit and
    failure rules are checkable without a server.
    """

    def member_addresses(self, concept: str) -> list[int]:
        """Addresses of every member of `concept`, ascending."""

    def read(self, address: int) -> dict[str, Any]:
        """One record. Raises `ValueError` when it will not decode."""

    def timestamp(self, address: int) -> Optional[float]:
        """The record's ordering timestamp, or None when it has none."""

    def exists(self, identifier: str) -> Optional[int]:
        """Address for a stable identifier, or None. Never creates."""


# ---------- cursors ----------


def encode_cursor(concept: str, last_address: int) -> str:
    """An opaque, self-describing position in the descending address order."""
    raw = json.dumps({"v": CURSOR_VERSION, "c": concept, "a": int(last_address)},
                     sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str, concept: str) -> int:
    """The address a cursor points at, or a refusal explaining why not.

    A cursor minted for another class is refused rather than honoured: paging
    one class's cursor through another's members returns plausible rows from the
    wrong place, which is worse than an error.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        payload = json.loads(raw)
    except Exception as exc:                  # noqa: BLE001 - every decode failure is one refusal
        raise GraphQueryError("bad_cursor", f"cursor is not readable ({exc})") from None
    if not isinstance(payload, dict) or payload.get("v") != CURSOR_VERSION:
        seen = payload.get("v") if isinstance(payload, dict) else "?"
        raise GraphQueryError(
            "bad_cursor",
            f"cursor version {seen!r} is not {CURSOR_VERSION}; start from the first page")
    if payload.get("c") != concept:
        raise GraphQueryError(
            "bad_cursor",
            f"cursor was issued for {payload.get('c')!r}, not {concept!r}")
    address = payload.get("a")
    if not isinstance(address, int):
        raise GraphQueryError("bad_cursor", "cursor carries no address")
    return address


def _check_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        value = int(limit)
    except (TypeError, ValueError):
        raise GraphQueryError("bad_limit", f"limit {limit!r} is not a number") from None
    if value < 1:
        raise GraphQueryError("bad_limit", f"limit must be at least 1, got {value}")
    if value > MAX_LIMIT:
        raise GraphQueryError(
            "bad_limit", f"limit {value} exceeds the {MAX_LIMIT} a page may return")
    return value


def row_timestamp(row: dict[str, Any]) -> Optional[float]:
    """The ordering stamp a row carries, by the keys the writers use.

    One function, so `recent()` and a range walk cannot disagree about which key
    places a record; None means the row cannot be placed in time.
    """
    for key in TIMESTAMP_KEYS:
        if key in row:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    return None


# ---------- the queries ----------


class GraphQuery:
    """Entity, cursor, range and page reads over one class of records."""

    def __init__(self, backend: GraphBackend,
                 *, scan_limit: int = DEFAULT_SCAN_LIMIT) -> None:
        self._backend = backend
        self._scan_limit = scan_limit

    def entity(self, identifier: str) -> Optional[dict[str, Any]]:
        """One record by stable identifier, or None when it is absent.

        Absence is an answer and must not raise; a transport failure must, so
        the caller can tell "no such record" from "the server is gone".
        """
        address = self._backend.exists(identifier)
        if address is None:
            return None
        try:
            return self._backend.read(address)
        except ValueError as exc:
            # The node exists but will not decode. Say so, as a record carrying
            # the reason, rather than reporting the identifier as unknown - the
            # node is there and a caller retrying by name would never see it.
            return {"__unreadable__": str(exc), "__address__": address}

    def page(self, concept: str, *, cursor: Optional[str] = None,
             limit: Optional[int] = None) -> QueryPage:
        """One page of `concept`, resumable by cursor.

        Records appended between pages cannot displace an already-read page,
        because the cursor is a position in address order rather than an offset:
        a record created after the cursor was minted has a higher address and is
        simply outside the remaining window.
        """
        want = _check_limit(limit)
        before = decode_cursor(cursor, concept) if cursor else None
        addresses = self._backend.member_addresses(concept)
        window = [a for a in reversed(addresses) if before is None or a < before]

        items: list[dict[str, Any]] = []
        skipped: list[Skipped] = []
        for position, address in enumerate(window):
            if position >= self._scan_limit:
                # Resume below the last address actually consumed, not at this
                # one: the cursor filters `address < before`, so pointing it
                # here would skip the record this page never looked at.
                consumed = max(position - 1, 0)
                return QueryPage(tuple(items),
                                 encode_cursor(concept, window[consumed]),
                                 len(addresses), consumed, tuple(skipped),
                                 truncated=True)
            try:
                items.append(self._backend.read(address))
            except ValueError as exc:
                skipped.append(Skipped(address, str(exc)))
            if len(items) >= want:
                break

        consumed = min(len(items) + len(skipped), len(window))
        exhausted = consumed >= len(window)
        resume = None
        if not exhausted and window:
            # Resume below the last address looked at, decoded or not: a skipped
            # record must not come back on the next call.
            resume = encode_cursor(concept, window[consumed - 1])
        return QueryPage(tuple(items), resume, len(addresses), consumed,
                         tuple(skipped))

    def range(self, concept: str, *, since: Optional[float] = None,
              until: Optional[float] = None,
              limit: Optional[int] = None) -> QueryPage:
        """Records whose timestamp falls in [since, until], newest first.

        Walks addresses downward and stops as soon as it passes `since`, so a
        recent window reads a page's worth of timestamps rather than the class's
        whole history. `scanned` and `truncated` say how much was actually read,
        because the walk costs depend on where the window sits.
        """
        want = _check_limit(limit)
        addresses = self._backend.member_addresses(concept)

        items: list[dict[str, Any]] = []
        skipped: list[Skipped] = []
        scanned = 0
        truncated = False
        for address in reversed(addresses):
            if scanned >= self._scan_limit:
                truncated = True
                break
            scanned += 1
            stamp = self._backend.timestamp(address)
            if stamp is None:
                # No timestamp means it cannot be placed in a range. Report it
                # rather than quietly including or excluding it.
                skipped.append(Skipped(address, "no ordering timestamp"))
                continue
            if until is not None and stamp > until:
                continue
            if since is not None and stamp < since:
                break                # addresses descend, so timestamps do too
            try:
                items.append(self._backend.read(address))
            except ValueError as exc:
                skipped.append(Skipped(address, str(exc)))
            if len(items) >= want:
                break

        return QueryPage(tuple(items), None, len(addresses), scanned,
                         tuple(skipped), truncated=truncated)

    def recent(self, concept: str, *, limit: Optional[int] = None) -> QueryPage:
        """The newest N records, returned oldest-first for display.

        This is the shape the host tools already produce - `records[-limit:]` of
        a chronologically sorted list - as one page read plus a sort of that
        page. The records outside the page are never read.
        """
        want = _check_limit(limit)
        page = self.page(concept, limit=want)
        ordered = tuple(sorted(
            page.items,
            key=lambda row: (row_timestamp(row) or 0.0,
                             str(row.get("record_id") or ""))))
        return QueryPage(ordered, page.cursor, page.candidates, page.scanned,
                         page.skipped, page.truncated)

    def latest(self, concept: str, *,
               matches: Optional[Callable[[dict[str, Any]], bool]] = None,
               limit: Optional[int] = None) -> Optional[dict[str, Any]]:
        """The newest record satisfying `matches`, or None.

        Replaces the `for record in reversed(load_...()): if ...: break` shape
        used to find the current session, and stops at the first match instead of
        materialising the whole class.
        """
        want = _check_limit(limit)
        for address in reversed(self._backend.member_addresses(concept)):
            try:
                row = self._backend.read(address)
            except ValueError:
                continue
            if matches is None or matches(row):
                return row
        return None


# ---------- the production backend ----------


def _unreachable(action: str, exc: Exception) -> GraphQueryError:
    """A failure that is not the graph's answer, reported as transport with context."""
    return GraphQueryError(
        "server_unreachable", f"{action}: {type(exc).__name__}: {exc}")


def json_record_reader(bridge: Any, payload_relation: str) -> Callable[[int], dict[str, Any]]:
    """A reader for the classes whose writer stored one JSON payload.

    Raises `ValueError` for anything that is not a record, which is what puts the
    record in `skipped` with a reason instead of vanishing.
    """
    from sc_client.models import ScAddr                 # type: ignore[import-not-found]

    def read(address: int) -> dict[str, Any]:
        payload = bridge.json_payload(ScAddr(int(address)), payload_relation)
        if not isinstance(payload, dict):
            raise ValueError(
                f"{payload_relation} at {address} is not a JSON record")
        return payload

    return read


class BridgeBackend:
    """`GraphBackend` over the bridge's proven primitives.

    Member selection is a template anchored on the concrete class keynode - the
    shape Block C measured, where at least one end of a triple must be concrete -
    and what it yields is the address. Payloads are read through the bridge's own
    relation readers, so a bounded read here and a loader read there cannot drift.

    A reader may reject one record with `ValueError` - it becomes `Skipped` - or
    report an unreachable graph with `GraphQueryError`, which passes through;
    any other failure is `server_unreachable`.
    """

    def __init__(self, bridge: Any, *,
                 reader: Optional[Callable[[int], dict[str, Any]]] = None,
                 concept: Optional[str] = None) -> None:
        if reader is None:
            relation = RECORD_RELATIONS.get(concept or "")
            if relation is None:
                raise GraphQueryError(
                    "no_reader",
                    f"{concept or 'this class'} has no single payload relation; "
                    "pass a reader for it")
            reader = json_record_reader(bridge, relation)
        self._bridge = bridge
        self._reader = reader

    @classmethod
    def for_concept(cls, bridge: Any, concept: str,
                    **kwargs: Any) -> "BridgeBackend":
        return cls(bridge, concept=concept, **kwargs)

    def member_addresses(self, concept: str) -> list[int]:
        from sc_client.client import search_by_template      # type: ignore[import-not-found]
        from sc_client.constants import sc_type              # type: ignore[import-not-found]
        from sc_client.constants.exceptions import InvalidValueError  # type: ignore[import-not-found]
        from sc_client.models import ScTemplate

        try:
            anchor = self._bridge.keynode(concept)
        except (InvalidValueError, KeyError) as exc:
            # The documented absence signal: the class is not in this graph.
            raise GraphQueryError(
                "class_missing",
                f"{concept} is not in this graph: {exc}") from None
        except Exception as exc:                    # noqa: BLE001 - not an absence: the query never ran
            raise _unreachable(f"could not resolve {concept}", exc) from None
        template = ScTemplate()
        template.triple(anchor, sc_type.VAR_PERM_POS_ARC, sc_type.VAR_NODE)
        try:
            results = list(search_by_template(template))
        except Exception as exc:                    # noqa: BLE001 - the class is not empty, the server is gone
            raise _unreachable(f"could not search members of {concept}", exc) from None
        found: list[int] = []
        for item in results:
            address = item.get(2)
            # An address of 0 is sc-memory echoing the wildcard back, not a
            # member. Counting it would inflate every count in this module.
            if address is None or address.value == 0:
                continue
            found.append(int(address.value))
        return sorted(found)

    def read(self, address: int) -> dict[str, Any]:
        try:
            return self._reader(int(address))
        except (ValueError, GraphQueryError):
            raise
        except Exception as exc:                    # noqa: BLE001 - a dead client is not a bad record
            raise _unreachable(f"could not read a record at {address}", exc) from None

    def timestamp(self, address: int) -> Optional[float]:
        from sc_client.models import ScAddr

        node = ScAddr(int(address))
        try:
            for relation in TIMESTAMP_RELATIONS:
                value = self._bridge.relation_number(node, relation)
                if value is not None:
                    return float(value)
        except Exception as exc:                    # noqa: BLE001 - a dead client is not a missing timestamp
            raise _unreachable(f"could not read a timestamp at {address}", exc) from None
        try:
            payload = self._reader(int(address))
        except ValueError:
            return None
        except GraphQueryError:
            raise
        except Exception as exc:                    # noqa: BLE001 - a dead client is not a missing timestamp
            raise _unreachable(f"could not read a timestamp at {address}", exc) from None
        return row_timestamp(payload)

    def exists(self, identifier: str) -> Optional[int]:
        """Address for a stable identifier, or None. Creates nothing.

        `ScKeynodes.__getitem__` resolves with no type, which asks the server for
        no creation - verified against the live graph on 2026-10-02: a written
        record resolved to its own address, and an id that cannot exist raised
        `InvalidValueError` instead of appearing.
        """
        from sc_client.constants.exceptions import InvalidValueError
        from sc_kpm.sc_keynodes import ScKeynodes                     # type: ignore[import-not-found]

        try:
            address = ScKeynodes[identifier]
        except (InvalidValueError, KeyError):
            return None
        except Exception as exc:                    # noqa: BLE001 - absent is an answer; unreachable is not
            raise _unreachable(f"could not resolve {identifier!r}", exc) from None
        return int(address.value) if address.is_valid() else None