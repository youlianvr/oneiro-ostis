"""Typed revision streams in OSTIS; no whole-class search on read paths.

A graph link owns the stream head and at most one pending publication. Immutable
revision links form a backwards chain. Named per-record links point to current
revisions; these are graph-owned projections, not files or a second database.

All writers must use the same local lease path and coordinator. This is not a
distributed lock or an ACID claim. A pending publication is completed on recovery
before more work is accepted. Read-back confirms publication in server memory;
callers still need a verified durable checkpoint before external effects.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from oneiro.ownership import FileLease
from oneiro.query import GraphQueryError, QueryPage, Skipped, _check_limit
from oneiro.records import Record, RecordError, decode

MAX_LINK_BYTES = 131072
MAX_CURSOR_BYTES = 1024
_NAME = re.compile(r"^[a-zA-Z0-9_.:-]{1,160}$")


class LinkGraph(Protocol):
    """Bounded-count named-link operations and concrete-endpoint relations.

    Server-side identifier lookup cost still requires scale measurements; the
    seam promises neither O(1) upstream work nor crash-atomic writes.
    """

    def read(self, name: str) -> str | None: ...
    def write(self, name: str, text: str) -> None: ...
    def address(self, name: str) -> int: ...
    def relate(self, source: str, target: str, relation: str) -> None: ...
    def classify(self, name: str, kind: str) -> None: ...
    def checkpoint(self) -> dict[str, Any]: ...


def _json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-8")) > MAX_LINK_BYTES:
        raise GraphQueryError("record_too_large", "graph link exceeds 131072 bytes")
    return text


def _object(text: str | None, name: str) -> dict[str, Any]:
    if text is None or len(text.encode("utf-8")) > MAX_LINK_BYTES:
        raise GraphQueryError("record_unreadable", f"missing or oversized link {name}")
    try:
        value = json.loads(text)
    except ValueError:
        raise GraphQueryError("record_unreadable", f"invalid JSON at {name}") from None
    if not isinstance(value, dict):
        raise GraphQueryError("record_unreadable", f"non-object at {name}")
    return value


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _key(stream: str, category: str, identifier: str) -> str:
    return "oneiro_v1_" + category + "_" + hashlib.sha256(
        f"{stream}\0{identifier}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Publication:
    entry: str
    address: int
    sequence: int
    revision: int
    record: Record
    duplicate: bool = False
    durable: bool = False  # only a separate, measured checkpoint may prove this


class RecordStore:
    """One leased writer, bounded readers, stable IDs and explicit revisions."""

    def __init__(self, graph: LinkGraph, stream: str, lease_path: Path,
                 *, scan_limit: int = 2000) -> None:
        if not isinstance(stream, str) or not _NAME.fullmatch(stream):
            raise GraphQueryError("bad_stream", "stream must be a bounded identifier")
        if type(scan_limit) is not int or scan_limit < 1:
            raise GraphQueryError("bad_scan_limit", "scan_limit must be a positive integer")
        self.graph = graph
        self.stream = stream
        self.scan_limit = scan_limit
        self.head_key = _key(stream, "head", stream)
        self._lock = threading.RLock()
        self._lease = FileLease(lease_path)
        self._opened = False

    def __enter__(self) -> RecordStore:
        self._lease.acquire()
        self._opened = True
        try:
            self.recover()
        except BaseException:
            self.close()
            raise
        return self

    def close(self) -> None:
        with self._lock:
            self._opened = False
            self._lease.release()

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ready(self) -> None:
        if not self._opened:
            raise GraphQueryError("store_closed", "record store has no writer lease")

    def _head(self) -> dict[str, Any]:
        self._ready()
        raw = self.graph.read(self.head_key)
        if raw is None:
            return {"v": 1, "stream": self.stream, "tail": None,
                    "count": 0, "pending": None}
        head = _object(raw, self.head_key)
        count = head.get("count")
        tail = head.get("tail")
        if (head.get("v") != 1 or head.get("stream") != self.stream
                or type(count) is not int or count < 0
                or ((count == 0) != (tail is None))
                or (tail is not None and not self._entry_key(tail))
                or "pending" not in head):
            raise GraphQueryError("chain_corrupt", "invalid stream head")
        return head

    @staticmethod
    def _entry_key(value: Any) -> bool:
        return isinstance(value, str) and re.fullmatch(r"oneiro_v1_entry_[0-9a-f]{64}", value) is not None

    def _idle_head(self) -> dict[str, Any]:
        head = self._head()
        if head["pending"] is not None:
            raise GraphQueryError("publication_pending", "recover pending publication before reading")
        return head

    def _write_checked(self, name: str, value: dict[str, Any]) -> None:
        text = _json(value)
        self.graph.write(name, text)
        if self.graph.read(name) != text:
            raise GraphQueryError("readback_failed", f"write not confirmed at {name}")

    def _envelope(self, entry: str, sequence: int) -> dict[str, Any]:
        value = _object(self.graph.read(entry), entry)
        previous = value.get("previous")
        if (value.get("v") != 1 or value.get("stream") != self.stream
                or type(value.get("sequence")) is not int or value["sequence"] != sequence
                or type(value.get("revision")) is not int or value["revision"] < 1
                or not isinstance(value.get("operation"), str) or not _NAME.fullmatch(value["operation"])
                or "previous_revision" not in value
                or ((value["revision"] == 1) != (value["previous_revision"] is None))
                or (value["previous_revision"] is not None and not self._entry_key(value["previous_revision"]))
                or entry != _key(self.stream, "entry", value["operation"])
                or ((sequence == 1) != (previous is None))
                or (previous is not None and not self._entry_key(previous))):
            raise GraphQueryError("chain_corrupt", f"invalid chain metadata at {entry}")
        return value

    @staticmethod
    def _record(envelope: dict[str, Any]) -> Record:
        data = envelope.get("record")
        try:
            digest = _digest(data) if isinstance(data, dict) else None
        except (ValueError, TypeError):
            raise RecordError("record is not finite JSON") from None
        if digest != envelope.get("digest") or not isinstance(data, dict):
            raise RecordError("record digest mismatch")
        record = decode(data)
        if (not isinstance(record.id, str) or not _NAME.fullmatch(record.id)
                or type(record.schema_version) is not int):
            raise RecordError("invalid record identity or schema version")
        for stamp in (record.created_at, record.updated_at):
            try:
                parsed = datetime.fromisoformat(stamp)
            except (TypeError, ValueError):
                raise RecordError("invalid record timestamp") from None
            if parsed.utcoffset() is None:
                raise RecordError("record timestamp has no timezone")
        return record

    def _publication(self, entry: str, envelope: dict[str, Any],
                     *, duplicate: bool = False) -> Publication:
        return Publication(entry, self.graph.address(entry), envelope["sequence"],
                           envelope["revision"], self._record(envelope), duplicate)

    def append(self, record: Record, operation_id: str,
               *, expected_revision: int = 0) -> Publication:
        """Publish once per operation ID; updates require a known prior revision.

        Reusing an operation ID with different content is a collision, not an
        update. Each revision keeps its own provenance and prior revision link.
        """
        if not isinstance(operation_id, str) or not _NAME.fullmatch(operation_id):
            raise GraphQueryError("bad_operation", "operation ID must be a bounded identifier")
        if type(expected_revision) is not int or expected_revision < 0:
            raise GraphQueryError("bad_revision", "expected revision must be a nonnegative integer")
        data = record.to_dict()
        decode(data)
        if not isinstance(record.id, str) or not _NAME.fullmatch(record.id):
            raise GraphQueryError("bad_record_id", "record ID must be a bounded identifier")
        digest = _digest(data)
        self._record({"record": data, "digest": digest})
        entry = _key(self.stream, "entry", operation_id)
        with self._lock:
            head = self._idle_head()
            existing = self.graph.read(entry)
            if existing is not None:
                old = _object(existing, entry)
                if (old.get("digest") != digest or old.get("record") != data
                        or old.get("stream") != self.stream or old.get("operation") != operation_id):
                    raise GraphQueryError("operation_collision", "operation ID already has different content")
                sequence = old.get("sequence")
                if type(sequence) is not int or not 1 <= sequence <= head["count"]:
                    raise GraphQueryError("publication_pending", "operation is not published")
                old = self._envelope(entry, sequence)
                return self._publication(entry, old, duplicate=True)
            pointer_key = _key(self.stream, "current", record.id)
            pointer_text = self.graph.read(pointer_key)
            prior = _object(pointer_text, pointer_key) if pointer_text is not None else None
            if prior is not None and (type(prior.get("revision")) is not int
                                      or prior["revision"] < 1 or not self._entry_key(prior.get("entry"))):
                raise GraphQueryError("chain_corrupt", "invalid prior revision pointer")
            revision = prior["revision"] if prior else 0
            if revision != expected_revision:
                raise GraphQueryError("revision_conflict", f"expected revision {expected_revision}, found {revision}")
            if prior:
                old_record = self.entity(record.id)
                if old_record is None or old_record.KIND != record.KIND or old_record.created_at != record.created_at:
                    raise GraphQueryError("identity_collision", "record kind or creation time changed")
            envelope = {"v": 1, "stream": self.stream, "operation": operation_id,
                        "sequence": head["count"] + 1, "revision": revision + 1,
                        "previous": head["tail"],
                        "previous_revision": prior["entry"] if prior else None,
                        "digest": digest, "record": data}
            pending = {"entry": entry, "envelope": envelope}
            # Validate total size before any write. Pending owns enough to finish
            # even a crash before the immutable entry is created.
            next_head = {**head, "pending": pending}
            _json(next_head)
            self._write_checked(self.head_key, next_head)
            self._finish(next_head)
            return self._publication(entry, envelope)

    def _finish(self, head: dict[str, Any]) -> None:
        pending = head["pending"]
        if not isinstance(pending, dict):
            raise GraphQueryError("chain_corrupt", "invalid pending publication")
        entry, envelope = pending.get("entry"), pending.get("envelope")
        if (not self._entry_key(entry) or not isinstance(envelope, dict)
                or envelope.get("sequence") != head["count"] + 1
                or envelope.get("previous") != head["tail"]
                or envelope.get("stream") != self.stream
                or not isinstance(envelope.get("operation"), str)
                or entry != _key(self.stream, "entry", envelope["operation"])
                or type(envelope.get("revision")) is not int or envelope["revision"] < 1
                or "previous_revision" not in envelope
                or (envelope["previous_revision"] is not None
                    and not self._entry_key(envelope["previous_revision"]))):
            raise GraphQueryError("chain_corrupt", "pending publication disagrees with head")
        record = self._record(envelope)
        prior_text = self.graph.read(entry)
        if prior_text is not None and prior_text != _json(envelope):
            raise GraphQueryError("operation_collision", "immutable revision already differs")
        self._write_checked(entry, envelope)
        self.graph.classify(entry, record.KIND)
        if envelope["previous"]:
            self.graph.relate(entry, envelope["previous"], "nrel_oneiro_previous")
        if envelope["previous_revision"]:
            self.graph.relate(entry, envelope["previous_revision"], "nrel_oneiro_previous_revision")
        # Anchor on the low-degree revision, never on an ever-growing head.
        self.graph.relate(entry, self.head_key, "nrel_oneiro_publication")
        pointer = _key(self.stream, "current", record.id)
        self._write_checked(pointer, {"entry": entry, "sequence": envelope["sequence"],
                                     "revision": envelope["revision"]})
        # Publishing the head is last. A failed/unknown set leaves either the old
        # head + pending (recoverable) or the new complete head (idempotent retry).
        self._write_checked(self.head_key, {"v": 1, "stream": self.stream,
                                          "tail": entry, "count": envelope["sequence"],
                                          "pending": None})

    def recover(self) -> bool:
        """Finish the one graph-owned pending publication, idempotently."""
        with self._lock:
            head = self._head()
            if head["pending"] is None:
                return False
            self._finish(head)
            return True

    def entity(self, record_id: str) -> Record | None:
        with self._lock:
            head = self._idle_head()
            pointer_key = _key(self.stream, "current", record_id)
            text = self.graph.read(pointer_key)
            if text is None:
                return None
            pointer = _object(text, pointer_key)
            sequence = pointer.get("sequence")
            if (type(sequence) is not int or not 1 <= sequence <= head["count"]
                    or not self._entry_key(pointer.get("entry"))):
                raise GraphQueryError("chain_corrupt", "invalid current revision pointer")
            value = self._envelope(pointer["entry"], sequence)
            record = self._record(value)
            if record.id != record_id or pointer.get("revision") != value["revision"]:
                raise GraphQueryError("identity_collision", "current pointer belongs to another record")
            return record

    def _cursor(self, entry: str, sequence: int, total: int) -> str:
        raw = _json({"v": 2, "s": self.stream, "e": entry, "n": sequence, "total": total})
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")

    def _position(self, cursor: str | None, head: dict[str, Any]) -> tuple[str | None, int, int]:
        if cursor is None:
            return head["tail"], head["count"], head["count"]
        try:
            if not isinstance(cursor, str) or len(cursor) > MAX_CURSOR_BYTES:
                raise ValueError("oversized cursor")
            raw = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
            value = json.loads(raw)
            if (not isinstance(value, dict) or value.get("v") != 2
                    or value.get("s") != self.stream or not self._entry_key(value.get("e"))
                    or type(value.get("n")) is not int or type(value.get("total")) is not int
                    or not 1 <= value["n"] <= value["total"] <= head["count"]):
                raise ValueError("wrong stream/version/position")
        except (ValueError, UnicodeError):
            raise GraphQueryError("bad_cursor", "unusable publication cursor") from None
        return value["e"], value["n"], value["total"]

    def page(self, *, cursor: str | None = None, limit: int | None = None,
             matches: Callable[[Record], bool] | None = None) -> QueryPage:
        """Newest-publication-first revisions; work and buffering <=scan_limit.

        No graph address ordering is assumed. Concurrent appends do not enter a
        resumed snapshot. A malformed payload is skipped explicitly; malformed
        chain metadata refuses the walk, since its continuation is unknown.
        """
        want = _check_limit(limit)
        with self._lock:
            entry, sequence, total = self._position(cursor, self._idle_head())
            items: list[dict[str, Any]] = []
            skipped: list[Skipped] = []
            scanned = 0
            while entry is not None and scanned < self.scan_limit and len(items) < want:
                envelope = self._envelope(entry, sequence)
                scanned += 1
                try:
                    record = self._record(envelope)
                except (RecordError, ValueError) as exc:
                    skipped.append(Skipped(self.graph.address(entry), str(exc)))
                else:
                    if matches is None or matches(record):
                        items.append({**record.to_dict(), "__entry__": entry,
                                      "__sequence__": sequence, "__revision__": envelope["revision"]})
                entry = envelope["previous"]
                sequence -= 1
            resume = self._cursor(entry, sequence, total) if entry is not None else None
            return QueryPage(tuple(items), resume, total, scanned, tuple(skipped),
                             truncated=entry is not None and scanned >= self.scan_limit and len(items) < want)

    def latest(self, *, matches: Callable[[Record], bool] | None = None) -> Record | None:
        page = self.page(limit=1, matches=matches)
        if page.skipped:
            raise GraphQueryError("record_unreadable", "newer revision is unreadable")
        if page.items:
            row = {k: v for k, v in page.items[0].items() if not k.startswith("__")}
            return decode(row)
        if page.cursor is not None:
            raise GraphQueryError("scan_truncated", "latest match is unknown beyond scan bound")
        return None

    def range(self, *, since: datetime | None = None, until: datetime | None = None,
              cursor: str | None = None, limit: int | None = None) -> QueryPage:
        """Time-filtered insertion page, NOT global timestamp sorting."""
        for stamp in (since, until):
            if stamp is not None and stamp.utcoffset() is None:
                raise GraphQueryError("bad_timestamp", "range requires timezone-aware instants")
        if since is not None and until is not None and since > until:
            raise GraphQueryError("bad_timestamp", "since exceeds until")

        def matches(record: Record) -> bool:
            stamp = datetime.fromisoformat(record.updated_at)
            if stamp.utcoffset() is None:
                raise GraphQueryError("bad_timestamp", "record timestamp has no timezone")
            return (since is None or stamp >= since) and (until is None or stamp <= until)

        return self.page(cursor=cursor, limit=limit, matches=matches)
