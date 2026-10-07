"""Offline protocol evidence; live persistence is a separate acceptance check."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from oneiro.ownership import OwnershipError
from oneiro.query import GraphQueryError
from oneiro.records import Note, Provenance, State
from oneiro.store import RecordStore


class Graph:
    def __init__(self):
        self.links = {}
        self.addresses = {}
        self.relations = set()
        self.classes = set()
        self.reads = []
        self.calls = 0
        self.fail_at = None
        self.after = False

    def _before(self):
        self.calls += 1
        if self.calls == self.fail_at and not self.after:
            raise GraphQueryError("server_unreachable", "injected interruption")

    def _after(self):
        if self.calls == self.fail_at and self.after:
            raise GraphQueryError("server_unreachable", "injected unknown write outcome")

    def read(self, name):
        self.reads.append(name)
        return self.links.get(name)

    def write(self, name, text):
        self._before()
        self.links[name] = text
        self.addresses.setdefault(name, len(self.addresses) + 100)
        self._after()

    def address(self, name):
        return self.addresses[name]

    def relate(self, source, target, relation):
        self._before()
        self.relations.add((source, target, relation))
        self._after()

    def classify(self, name, kind):
        self._before()
        self.classes.add((name, kind))
        self._after()


def note(index=0):
    return Note(id=f"note-{index}", topic="test", body=f"body {index}",
                provenance=Provenance.OBSERVATION)


def test_roundtrip_stable_identity_types_and_provenance(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        record = note()
        publication = store.append(record, "operation-0")
        assert publication.record == record
        assert publication.sequence == publication.revision == 1
        assert publication.durable is False
        assert store.entity(record.id) == record
        assert store.entity("absent") is None
        assert (publication.entry, "note") in graph.classes
        assert (publication.entry, store.head_key, "nrel_oneiro_publication") in graph.relations
    with RecordStore(graph, "test", tmp_path / "writer.lock") as reopened:
        assert reopened.entity(record.id) == record


def test_retry_is_one_logical_event_and_collision_is_not_an_update(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        first = store.append(note(), "op")
        writes = graph.calls
        retry = store.append(note(), "op")
        assert retry.duplicate and retry.entry == first.entry
        assert graph.calls == writes
        with pytest.raises(GraphQueryError, match="operation_collision"):
            store.append(replace(note(), body="changed"), "op")
        with pytest.raises(GraphQueryError, match="revision_conflict"):
            store.append(note(), "other-op")
        assert store.page().candidates == 1


def test_revision_preserves_prior_claim_and_requires_expected_revision(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        original = note()
        first = store.append(original, "first")
        changed = replace(original, body="verified", provenance=Provenance.VERIFIED_TOOL_OUTCOME,
                          state=State.COMPLETED)
        second = store.append(changed, "second", expected_revision=1)
        assert second.revision == 2
        assert store.entity(original.id) == changed
        assert (second.entry, first.entry, "nrel_oneiro_previous_revision") in graph.relations
        assert [row["provenance"] for row in store.page().items] == [
            "verified_tool_outcome", "observation"]
        with pytest.raises(GraphQueryError, match="identity_collision"):
            store.append(replace(changed, created_at="2000-01-01T00:00:00+00:00"), "third", expected_revision=2)


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("boundary", range(1, 8))
def test_each_interrupted_update_boundary_recovers_or_was_never_accepted(tmp_path, boundary, after):
    graph = Graph()
    lock = tmp_path / "writer.lock"
    original = note()
    changed = replace(original, body="changed")
    with RecordStore(graph, "test", lock) as store:
        store.append(original, "first")
        graph.calls = 0
        graph.fail_at, graph.after = boundary, after
        with pytest.raises(GraphQueryError, match="server_unreachable"):
            store.append(changed, "second", expected_revision=1)
    graph.fail_at = None
    with RecordStore(graph, "test", lock) as store:
        result = store.append(changed, "second", expected_revision=1)
        assert result.revision == 2
        assert store.entity(original.id) == changed
        page = store.page()
        assert page.candidates == page.scanned == 2
        assert len({row["__entry__"] for row in page.items}) == 2
        assert len(graph.classes) == 2
        assert len(graph.relations) == 4


def test_pending_publication_blocks_reads_and_new_appends_until_recovery(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        graph.fail_at = 2
        with pytest.raises(GraphQueryError):
            store.append(note(), "first")
        with pytest.raises(GraphQueryError, match="publication_pending"):
            store.page()
        with pytest.raises(GraphQueryError, match="publication_pending"):
            store.append(note(1), "second")
        graph.fail_at = None
        assert store.recover()
        assert not store.recover()
        assert store.entity(note().id) == note()


def test_page_work_is_independent_of_total_history_and_no_address_enumeration(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        for i in range(1000):
            store.append(note(i), f"op-{i}")
        graph.reads.clear()
        first = store.page(limit=5)
        assert first.candidates == 1000 and first.scanned == 5
        assert len(graph.reads) == 6  # head plus exactly five revision links
        assert [row["id"] for row in first.items] == [f"note-{i}" for i in range(999, 994, -1)]
        store.append(note(1000), "late")
        graph.reads.clear()
        second = store.page(cursor=first.cursor, limit=5)
        assert second.candidates == 1000
        assert len(graph.reads) == 6
        assert [row["id"] for row in second.items] == [f"note-{i}" for i in range(994, 989, -1)]


def test_bounded_filter_resumes_without_false_absence(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock", scan_limit=3) as store:
        for i in range(8):
            store.append(note(i), f"op-{i}")
        page = store.page(matches=lambda r: False)
        assert page.items == () and page.scanned == 3 and page.truncated
        with pytest.raises(GraphQueryError, match="scan_truncated"):
            store.latest(matches=lambda r: False)
        rest = store.page(cursor=page.cursor, limit=10)
        assert [row["id"] for row in rest.items] == ["note-4", "note-3", "note-2"]
        final = store.page(cursor=rest.cursor, limit=10)
        assert [row["id"] for row in final.items] == ["note-1", "note-0"]
        assert final.cursor is None and not final.truncated


def test_bad_payload_is_visible_but_bad_chain_is_not_silently_skipped(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        first = store.append(note(), "op")
        value = json.loads(graph.links[first.entry])
        value["record"]["body"] = "tampered"
        graph.links[first.entry] = json.dumps(value)
        page = store.page()
        assert page.items == () and page.scanned == 1
        assert page.skipped[0].address == first.address
        with pytest.raises(GraphQueryError, match="record_unreadable"):
            store.latest()
        value["previous"] = first.entry
        graph.links[first.entry] = json.dumps(value)
        with pytest.raises(GraphQueryError, match="chain_corrupt"):
            store.page()


@pytest.mark.parametrize("value", ["!", "a" * 1025, [], True])
def test_untrusted_cursor_refused(tmp_path, value):
    with RecordStore(Graph(), "test", tmp_path / "writer.lock") as store:
        with pytest.raises(GraphQueryError, match="bad_cursor"):
            store.page(cursor=value)


def test_foreign_cursor_refused_and_closed_store_cannot_write(tmp_path):
    graph = Graph()
    with RecordStore(graph, "first", tmp_path / "writer.lock") as store:
        for i in range(2):
            store.append(note(i), f"op-{i}")
        cursor = store.page(limit=1).cursor
    with pytest.raises(GraphQueryError, match="store_closed"):
        store.append(note(3), "closed")
    with RecordStore(graph, "second", tmp_path / "writer.lock") as other:
        with pytest.raises(GraphQueryError, match="bad_cursor"):
            other.page(cursor=cursor)


def test_one_writer_lease_and_thread_serialization(tmp_path):
    graph = Graph()
    lock = tmp_path / "writer.lock"
    with RecordStore(graph, "test", lock) as store:
        with pytest.raises(OwnershipError):
            with RecordStore(graph, "test", lock):
                pass
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda i: store.append(note(i), f"op-{i}"), range(20)))
        assert sorted(result.sequence for result in results) == list(range(1, 21))
        assert store.page().candidates == 20
        assert len(store.page().items) == 20


def test_oversized_record_refused_before_any_graph_write(tmp_path):
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock") as store:
        with pytest.raises(GraphQueryError, match="record_too_large"):
            store.append(replace(note(), body="x" * 140000), "op")
        assert graph.calls == 0


def test_range_handles_clock_inversion_and_reports_remaining_window(tmp_path):
    from datetime import datetime, timezone
    graph = Graph()
    with RecordStore(graph, "test", tmp_path / "writer.lock", scan_limit=2) as store:
        for i, stamp in enumerate((30, 5, 10)):
            store.append(replace(note(i), updated_at=datetime.fromtimestamp(stamp, timezone.utc).isoformat()), f"op-{i}")
        first = store.range(since=datetime.fromtimestamp(10, timezone.utc), limit=5)
        assert [row["id"] for row in first.items] == ["note-2"]
        assert first.truncated and first.scanned == 2
        rest = store.range(since=datetime.fromtimestamp(10, timezone.utc), cursor=first.cursor)
        assert [row["id"] for row in rest.items] == ["note-0"]
        assert rest.cursor is None
