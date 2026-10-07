"""Live protocol probe on explicitly named NEW scratch graph; no clear/delete.

Writes only synthetic observations, produces an evidence file and can verify it
again after a controlled server restart. File is evidence, never runtime memory.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sc_client import client

from oneiro.migrate import ensure_ontology
from oneiro.query import GraphQueryError
from oneiro.records import Note, Provenance
from oneiro.sc_graph import ScLinkGraph
from oneiro.store import RecordStore


class InterruptGraph(ScLinkGraph):
    def __init__(self):
        super().__init__()
        self.remaining = None

    def write(self, name, text):
        if self.remaining is not None:
            self.remaining -= 1
            if self.remaining == 0:
                raise GraphQueryError("server_unreachable", "probe interruption before link write")
        return super().write(name, text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    client.connect(args.url)
    try:
        graph = InterruptGraph()
        ontology = graph.ensure_ontology()
        if args.verify:
            evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        else:
            if args.evidence.exists():
                raise FileExistsError("choose a new evidence path, preserve prior probe")
            stream = "probe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            evidence = {"stream": stream, "url": args.url, "typed_ontology": ontology,
                        "expected": [], "durability": "not yet restart-verified"}
            # Also verify legacy ontology types without touching old data.
            report = ensure_ontology(None)
            assert not report.failed and not report.missing_classes, report.to_dict()
            evidence["legacy_migration"] = report.to_dict()
            with RecordStore(graph, stream, args.evidence.parent / "probe-writer.lock", scan_limit=3) as store:
                for i in range(8):
                    record = Note(id=f"probe-note-{i}", topic="live protocol test",
                                  body=f"synthetic observation {i}", provenance=Provenance.OBSERVATION)
                    first = store.append(record, f"operation-{i}")
                    retry = store.append(record, f"operation-{i}")
                    assert retry.duplicate and retry.entry == first.entry
                    assert store.entity(record.id) == record
                    evidence["expected"].append(record.to_dict())
                page = store.page(limit=8)
                assert page.candidates == 8 and page.scanned == 3 and page.truncated
                assert [r["id"] for r in page.items] == [f"probe-note-{i}" for i in (7, 6, 5)]
                try:
                    store.latest(matches=lambda _: False)
                except GraphQueryError as exc:
                    assert exc.code == "scan_truncated"
                else:
                    raise AssertionError("bounded scan falsely proved absence")
                original = Note.from_dict(evidence["expected"][0])
                revised = replace(original, body="recovered revision")
                graph.remaining = 2  # intent exists, immutable revision not yet written
                try:
                    store.append(revised, "interrupted-operation", expected_revision=1)
                except GraphQueryError as exc:
                    assert exc.code == "server_unreachable"
                else:
                    raise AssertionError("probe did not interrupt")
                graph.remaining = None
            # Opening performs graph-owned pending recovery.
            with RecordStore(graph, stream, args.evidence.parent / "probe-writer.lock") as recovered:
                assert recovered.entity(original.id) == revised
                assert recovered.append(revised, "interrupted-operation", expected_revision=1).duplicate
                assert recovered.page().candidates == 9
                evidence["expected"][0] = revised.to_dict()
                evidence["count"] = 9
                evidence["head"] = recovered.head_key
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        with RecordStore(graph, evidence["stream"], args.evidence.parent / "probe-writer.lock") as store:
            for value in evidence["expected"]:
                record = Note.from_dict(value)
                assert store.entity(record.id) == record
            page = store.page(limit=50)
            assert page.scanned == page.candidates == evidence["count"]
            assert not page.skipped and page.cursor is None
            # Real sc-types were checked on entry by ensure_ontology.
            assert graph.ensure_ontology() == ontology
        print(json.dumps({"verified_records": len(evidence["expected"]),
                          "revisions": evidence["count"], "stream": evidence["stream"],
                          "post_restart_check": args.verify}))
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
