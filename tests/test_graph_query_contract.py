"""The bounded query layer's contract, checked without a server.

Every rule that decides what a caller gets - how many rows, in what order, what
happens to a record that will not decode, what a cursor refuses - is pure logic
over a `GraphBackend`. So it is tested here against a fake, and the real graph is
exercised separately by the probes recorded in `docs/REWRITE-BASELINE.md`.

The point of the failure cases is the reason this module exists. The loaders it
replaces return `[]` when something goes wrong, so "the server is down" and "the
graph is empty" look identical two layers away. Here they do not: a missing
record is `None`, an unreadable record is named in `skipped`, and a query that
could not run raises with a code.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from oneiro.query import (                                          # noqa: E402
    MAX_LIMIT,
    GraphQuery,
    GraphQueryError,
    decode_cursor,
    encode_cursor,
    row_timestamp,
)

CONCEPT = "concept_organization_record"


class FakeBackend:
    """A graph made of dicts, addressed the way real nodes are: by integer."""

    def __init__(self, records: dict[int, dict], *, unreadable=(), no_timestamp=(),
                 absent_ids=(), missing_class=False, transport_error=False,
                 transport_on_read=False) -> None:
        self.records = dict(records)
        self.unreadable = set(unreadable)
        self.no_timestamp = set(no_timestamp)
        self.absent_ids = set(absent_ids)
        self.missing_class = missing_class
        self.transport_error = transport_error
        self.transport_on_read = transport_on_read
        self.reads: list[int] = []

    def member_addresses(self, concept: str) -> list[int]:
        if self.transport_error:
            raise GraphQueryError("server_unreachable",
                                  f"the graph cannot be reached for {concept}")
        if self.missing_class:
            raise GraphQueryError("class_missing", f"{concept} is not in this graph")
        return sorted(self.records)

    def read(self, address: int) -> dict:
        self.reads.append(address)
        if self.transport_on_read:
            raise GraphQueryError("server_unreachable",
                                  f"connection lost reading {address}")
        if address in self.unreadable:
            raise ValueError(f"payload at {address} is not a JSON record")
        return dict(self.records[address])

    def timestamp(self, address: int) -> float | None:
        if address in self.no_timestamp:
            return None
        return float(self.records[address].get("recorded_at", 0))

    def exists(self, identifier: str) -> int | None:
        if self.transport_error:
            raise GraphQueryError("server_unreachable",
                                  f"the graph cannot be reached for {identifier!r}")
        if identifier in self.absent_ids:
            return None
        for address, row in self.records.items():
            if row.get("record_id") == identifier:
                return address
        return None


def records(count: int, *, start: int = 100, step: int = 10) -> dict[int, dict]:
    """Addresses ascend with time, the way the live graph's were measured to."""
    return {
        start + index * step: {"record_id": f"r{index}", "recorded_at": 1000 + index}
        for index in range(count)
    }


# ---------- page ----------

def test_a_page_returns_at_most_the_limit_and_counts_candidates_honestly():
    query = GraphQuery(FakeBackend(records(50)))
    page = query.page(CONCEPT, limit=5)

    assert len(page.items) == 5
    assert page.candidates == 50, "the caller is told the class is bigger"
    assert page.items[0]["record_id"] == "r49", "newest first"
    assert page.cursor, "more remain, so a cursor must be offered"


def test_paging_walks_every_record_exactly_once():
    backend = FakeBackend(records(7))
    query = GraphQuery(backend)
    seen: list[str] = []
    cursor = None
    while True:
        page = query.page(CONCEPT, cursor=cursor, limit=3)
        seen.extend(row["record_id"] for row in page.items)
        cursor = page.cursor
        if cursor is None:
            break
    assert seen == [f"r{index}" for index in range(6, -1, -1)]
    assert len(seen) == len(set(seen)), "no record may come back twice"


def test_a_record_written_between_pages_cannot_displace_the_first_page():
    """The cursor is a position, not an offset, so appends do not shift pages."""
    backend = FakeBackend(records(10))
    query = GraphQuery(backend)
    first = query.page(CONCEPT, limit=4)

    backend.records[999] = {"record_id": "late", "recorded_at": 5000}
    second = query.page(CONCEPT, cursor=first.cursor, limit=4)

    assert second.items[0]["record_id"] == "r5", (
        "the new record has a higher address and must not enter the next page")
    assert "late" not in [row["record_id"] for row in second.items]


def test_the_last_page_carries_no_cursor():
    page = GraphQuery(FakeBackend(records(4))).page(CONCEPT, limit=10)
    assert page.cursor is None, "nothing remains, so nothing is offered"
    assert len(page.items) == 4


# ---------- unreadable records ----------

def test_an_unreadable_record_is_reported_not_dropped():
    backend = FakeBackend(records(6), unreadable={140})     # 140 is r4
    page = GraphQuery(backend).page(CONCEPT, limit=3)

    assert [row["record_id"] for row in page.items] == ["r5", "r3", "r2"], (
        "the broken record cannot be a row, and the page still fills its limit")
    assert [(s.address, "not a JSON record" in s.reason) for s in page.skipped] == [(140, True)], (
        "and it is named, rather than the page quietly coming back short")


def test_a_page_of_nothing_but_broken_records_is_not_an_empty_page():
    backend = FakeBackend(records(2), unreadable={100, 110})
    page = GraphQuery(backend).page(CONCEPT, limit=5)

    assert page.items == ()
    assert [s.address for s in page.skipped] == [110, 100], (
        "two records exist and both are named; an empty list here would be a lie")


# ---------- range ----------

def test_range_returns_the_window_and_scans_to_its_bound():
    backend = FakeBackend(records(40))            # recorded_at 1000..1039
    query = GraphQuery(backend)
    page = query.range(CONCEPT, since=1030.0, until=1035.0, limit=10)

    assert sorted(row["recorded_at"] for row in page.items) == [1030, 1031, 1032,
                                                               1033, 1034, 1035]
    assert page.scanned == 40, (
        "every candidate is stamped before the window is decided - addresses are "
        "insertion order, not time order")


def test_range_finds_a_match_below_a_stamp_that_ran_backwards():
    """The measured defect, 2026-10-05: a higher address carried an older stamp,
    and the walk that stopped at the first stamp below `since` omitted matches."""
    backend = FakeBackend({
        100: {"record_id": "r_low_address_new_stamp", "recorded_at": 30},
        110: {"record_id": "r_backwards_middle", "recorded_at": 5},
        120: {"record_id": "r_high_address_mid_stamp", "recorded_at": 10},
    })
    page = GraphQuery(backend).range(CONCEPT, since=10.0, limit=10)

    assert [row["record_id"] for row in page.items] == [
        "r_low_address_new_stamp", "r_high_address_mid_stamp"], (
            "the row below the backwards stamp is in the window and must be returned")
    assert page.scanned == 3


def test_range_reports_a_record_it_cannot_place():
    backend = FakeBackend(records(5), no_timestamp={130})
    page = GraphQuery(backend).range(CONCEPT, limit=10)

    assert [s.address for s in page.skipped] == [130]
    assert "timestamp" in page.skipped[0].reason
    assert len(page.items) == 4


def test_range_says_when_its_scan_was_bounded():
    backend = FakeBackend(records(100))
    page = GraphQuery(backend, scan_limit=10).range(CONCEPT, since=0.0, limit=100)

    assert page.truncated is True
    assert page.scanned == 10


# ---------- recent and latest ----------

def test_recent_gives_the_newest_n_oldest_first_like_the_tools_expect():
    backend = FakeBackend(records(30))
    page = GraphQuery(backend).recent(CONCEPT, limit=4)

    assert [row["record_id"] for row in page.items] == ["r26", "r27", "r28", "r29"]
    assert len(backend.reads) == 4, (
        "only the page may be read; the other 26 records must not be touched")


def test_latest_finds_the_newest_match_without_reading_the_whole_class():
    backend = FakeBackend(records(30))
    for index, (address, row) in enumerate(backend.records.items()):
        row["session_id"] = "wanted" if index == 12 else "other"
    found = GraphQuery(backend).latest(
        CONCEPT, matches=lambda row: row.get("session_id") == "wanted")

    assert found is not None and found["record_id"] == "r12"
    assert len(backend.reads) == 30 - 12, "the scan stops at the first match"


def test_latest_reports_none_when_nothing_matches():
    assert GraphQuery(FakeBackend(records(5))).latest(
        CONCEPT, matches=lambda row: False) is None


# ---------- entity ----------

def test_entity_returns_the_record_for_a_stable_identifier():
    backend = FakeBackend(records(3))
    assert GraphQuery(backend).entity("r1")["recorded_at"] == 1001


def test_entity_reports_absence_as_none_rather_than_raising():
    assert GraphQuery(FakeBackend(records(3))).entity("nope") is None


def test_entity_names_an_existing_record_that_will_not_decode():
    backend = FakeBackend(records(3), unreadable={110})
    found = GraphQuery(backend).entity("r1")

    assert found["__unreadable__"], "the reason is reported, not swallowed"
    assert found["__address__"] == 110, "and the caller can go and look at it"


# ---------- refusals ----------

def test_limits_outside_the_contract_are_refused_with_a_code():
    query = GraphQuery(FakeBackend(records(3)))
    for bad in (0, -1, MAX_LIMIT + 1, "many"):
        try:
            query.page(CONCEPT, limit=bad)
        except GraphQueryError as exc:
            assert exc.code == "bad_limit", bad
        else:
            raise AssertionError(f"limit {bad!r} should have been refused")


def test_a_cursor_from_another_class_is_refused_rather_than_misapplied():
    cursor = encode_cursor("concept_session", 400)
    try:
        GraphQuery(FakeBackend(records(3))).page(CONCEPT, cursor=cursor)
    except GraphQueryError as exc:
        assert exc.code == "bad_cursor"
        assert "concept_session" in exc.reason
    else:
        raise AssertionError("a foreign cursor must not page another class")


def test_an_unreadable_cursor_says_so_instead_of_restarting_silently():
    for bad in ("not-base64!!", "eyJ2IjogOTksImMiOiJ4In0="):
        try:
            GraphQuery(FakeBackend(records(3))).page(CONCEPT, cursor=bad)
        except GraphQueryError as exc:
            assert exc.code == "bad_cursor"
        else:
            raise AssertionError(f"cursor {bad!r} should have been refused")


def test_a_missing_class_is_reported_and_never_read_as_an_empty_class():
    try:
        GraphQuery(FakeBackend(records(3), missing_class=True)).page(CONCEPT, limit=5)
    except GraphQueryError as exc:
        assert exc.code == "class_missing"
    else:
        raise AssertionError("an absent class must not look like an empty one")


def test_cursor_round_trips_its_position():
    assert decode_cursor(encode_cursor(CONCEPT, 4242), CONCEPT) == 4242


def test_a_bounded_scan_still_offers_a_resumable_cursor():
    backend = FakeBackend(records(100))
    page = GraphQuery(backend, scan_limit=5).page(CONCEPT, limit=50)

    assert page.truncated is True
    assert page.cursor, "a truncated page must be resumable"
    rest = GraphQuery(backend).page(CONCEPT, cursor=page.cursor, limit=100)
    assert rest.truncated is False
    assert len(page.items) + len(rest.items) == 100, "no record lost across the seam"


# ---------- the stamp a row carries ----------

def test_the_ordering_stamp_is_found_under_the_writers_keys():
    """created_at is the life-session writer's key; load_life_sessions uses it."""
    assert row_timestamp({"recorded_at": 5}) == 5.0
    assert row_timestamp({"ts": 6}) == 6.0
    assert row_timestamp({"created_at": 7}) == 7.0
    assert row_timestamp({}) is None
    assert row_timestamp({"created_at": "not a number"}) is None


def test_recent_places_session_rows_by_created_at():
    """The measured gap: sessions were sorted by nothing before this."""
    backend = FakeBackend({
        100: {"session_id": "s_mid", "created_at": 30},
        110: {"session_id": "s_old", "created_at": 10},
        120: {"session_id": "s_new", "created_at": 20},
    })
    page = GraphQuery(backend).recent(CONCEPT, limit=3)
    assert [row["session_id"] for row in page.items] == ["s_old", "s_new", "s_mid"]


# ---------- a dead server is not an empty class ----------

def test_a_transport_failure_surfaces_as_itself_not_as_an_empty_page():
    backend = FakeBackend(records(3), transport_error=True)
    try:
        GraphQuery(backend).page(CONCEPT, limit=5)
    except GraphQueryError as exc:
        assert exc.code == "server_unreachable"
    else:
        raise AssertionError("a dead server must not read as an empty class")


def test_a_transport_failure_mid_read_reaches_the_caller_too():
    backend = FakeBackend(records(3), transport_on_read=True)
    try:
        GraphQuery(backend).page(CONCEPT, limit=5)
    except GraphQueryError as exc:
        assert exc.code == "server_unreachable"
    else:
        raise AssertionError("a connection lost mid-read must not shorten the page")


def test_entity_reports_a_transport_failure_instead_of_absence():
    backend = FakeBackend(records(3), transport_error=True)
    try:
        GraphQuery(backend).entity("r1")
    except GraphQueryError as exc:
        assert exc.code == "server_unreachable"
    else:
        raise AssertionError("the server is gone must not look like no such record")


# ---------- uncovered boundaries found in the full rewrite review ----------

@pytest.mark.parametrize("scan_limit", [0, -1, True, 1.5, "5"])
def test_invalid_scan_bounds_are_refused_before_any_backend_work(scan_limit):
    with pytest.raises(GraphQueryError) as error:
        GraphQuery(FakeBackend(records(3)), scan_limit=scan_limit)
    assert error.value.code == "bad_scan_limit"


@pytest.mark.parametrize("limit", [True, 1.5, "1.5"])
def test_a_page_limit_cannot_silently_change_type_or_round_down(limit):
    with pytest.raises(GraphQueryError) as error:
        GraphQuery(FakeBackend(records(3))).page(CONCEPT, limit=limit)
    assert error.value.code == "bad_limit"


def test_truncated_page_counts_every_consumed_record_including_skipped():
    backend = FakeBackend(records(8), unreadable={160})
    page = GraphQuery(backend, scan_limit=3).page(CONCEPT, limit=8)
    assert page.scanned == 3 == len(backend.reads)
    assert len(page.items) + len(page.skipped) == page.scanned
    assert decode_cursor(page.cursor, CONCEPT) == 150


def test_latest_cannot_turn_a_scan_bound_into_false_absence():
    backend = FakeBackend(records(20))
    with pytest.raises(GraphQueryError) as error:
        GraphQuery(backend, scan_limit=3).latest(CONCEPT, matches=lambda row: False)
    assert error.value.code == "scan_truncated"
    assert len(backend.reads) == 3


def test_latest_limit_bounds_candidates_not_the_number_of_matches():
    backend = FakeBackend(records(20))
    with pytest.raises(GraphQueryError) as error:
        GraphQuery(backend).latest(CONCEPT, matches=lambda row: False, limit=2)
    assert error.value.code == "scan_truncated"
    assert len(backend.reads) == 2


def test_latest_cannot_hide_an_unreadable_newer_record():
    backend = FakeBackend(records(5), unreadable={140})
    with pytest.raises(GraphQueryError) as error:
        GraphQuery(backend).latest(CONCEPT)
    assert error.value.code == "record_unreadable"
    assert "140" in error.value.reason
    assert backend.reads == [140]


def test_range_reports_when_matching_rows_exceed_the_return_limit():
    page = GraphQuery(FakeBackend(records(10))).range(CONCEPT, limit=3)
    assert page.scanned == 10
    assert len(page.items) == 3
    assert page.truncated is True


@pytest.mark.parametrize("stamp", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_timestamps_are_not_ordering_evidence(stamp):
    assert row_timestamp({"recorded_at": stamp}) is None
    backend = FakeBackend({100: {"record_id": "bad-time", "recorded_at": stamp}})
    page = GraphQuery(backend).range(CONCEPT)
    assert page.items == ()
    assert len(page.skipped) == 1


@pytest.mark.parametrize("address", [True, False, 0, -1, 1.5, "10"])
def test_legacy_cursor_rejects_nonpositive_or_coerced_addresses(address):
    import base64
    import json
    raw = json.dumps({"v": 1, "c": CONCEPT, "a": address}).encode()
    cursor = base64.urlsafe_b64encode(raw).decode()
    with pytest.raises(GraphQueryError, match="bad_cursor"):
        decode_cursor(cursor, CONCEPT)
    with pytest.raises(GraphQueryError, match="bad_cursor"):
        encode_cursor(CONCEPT, address)


def test_legacy_cursor_rejects_oversized_input_and_boolean_version():
    import base64
    import json
    with pytest.raises(GraphQueryError, match="bad_cursor"):
        decode_cursor("a" * 2049, CONCEPT)
    raw = json.dumps({"v": True, "c": CONCEPT, "a": 10}).encode()
    with pytest.raises(GraphQueryError, match="bad_cursor"):
        decode_cursor(base64.urlsafe_b64encode(raw).decode(), CONCEPT)


def test_backend_duplicate_members_are_one_logical_candidate():
    class DuplicateBackend(FakeBackend):
        def member_addresses(self, concept):
            return [100, 100, 110, 110]

    page = GraphQuery(DuplicateBackend(records(2))).page(CONCEPT, limit=4)
    assert page.candidates == page.scanned == 2
    assert [row["record_id"] for row in page.items] == ["r1", "r0"]