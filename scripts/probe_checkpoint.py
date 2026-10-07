"""Checkpoint probe for disposable NEW graphs; never touches old storage.

Use --prepare, then preserve consistent /kb.bin snapshot, hard-kill ONLY the
named scratch server and use --verify. Verification checks records and sc-types,
not just action acknowledgement. Reports are evidence, not runtime memory.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sc_client import client

from oneiro.records import Action, Effect, EffectOutcome, Note, Provenance, State, decode
from oneiro.sc_graph import ScLinkGraph
from oneiro.store import RecordStore, _key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.prepare == args.verify:
        parser.error("choose prepare or verify")
    client.connect(args.url)
    try:
        graph = ScLinkGraph()
        types = graph.ensure_ontology()
        if args.prepare:
            if args.evidence.exists():
                raise FileExistsError("preserve previous evidence; choose another path")
            evidence = {"stream": "checkpoint-" + uuid4().hex, "expected": [], "sc_types": types,
                        "url": args.url, "created_utc": datetime.now(timezone.utc).isoformat()}
            with RecordStore(graph, evidence["stream"], args.evidence.parent / "checkpoint-writer.lock") as store:
                for i in range(20):
                    record = Note(id=f"checkpoint-note-{i}", topic="checkpoint fault acceptance",
                                  body=f"synthetic verified observation {i}", provenance=Provenance.OBSERVATION)
                    store.append(record, f"checkpoint-operation-{i}")
                    evidence["expected"].append(record.to_dict())
                intention = Action(id="checkpoint-intention", run_id="checkpoint-run", tool="probe.no_external_effect",
                                   effect=Effect(kind="synthetic", target="no real effect", outcome=EffectOutcome.UNCERTAIN),
                                   state=State.UNCERTAIN)
                store.append(intention, "checkpoint-intention-op")
                evidence["expected"].append(intention.to_dict())
                evidence["sequence"] = store.page(limit=1).candidates
                start_wall = time.time()
                checkpoint = graph.checkpoint()
                evidence["checkpoint_started_epoch"] = start_wall
                evidence["checkpoint_completed_epoch"] = time.time()
                evidence["checkpoint"] = checkpoint
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps({"prepared_records": len(evidence["expected"]), "checkpoint": checkpoint,
                              "stream": evidence["stream"]}))
        else:
            evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
            with RecordStore(graph, evidence["stream"], args.evidence.parent / "checkpoint-writer.lock") as store:
                for payload in evidence["expected"]:
                    record = decode(payload)
                    assert store.entity(record.id) == record
                page = store.page(limit=50)
                assert page.scanned == page.candidates == evidence["sequence"]
                assert not page.skipped and page.cursor is None
                assert graph.ensure_ontology() == evidence["sc_types"]
                # Inspect real graph relations/types without repair writes; a
                # JSON chain alone does not prove the graph edges survived.
                for index, payload in enumerate(evidence["expected"]):
                    operation = f"checkpoint-operation-{index}" if index < 20 else "checkpoint-intention-op"
                    entry = _key(evidence["stream"], "entry", operation)
                    address = graph._resolve(entry)
                    assert graph._call("get_elements_types", address) == [graph.types.CONST_NODE_LINK]
                    classification = graph.models.ScTemplate()
                    classification.triple(graph._resolve("concept_oneiro_" + payload["kind"]),
                                          graph.types.VAR_PERM_POS_ARC, address)
                    assert len(graph._call("search_by_template", classification)) == 1
                    publication = graph.models.ScTemplate()
                    publication.triple_with_relation(address, graph.types.VAR_COMMON_ARC,
                        graph._resolve(store.head_key), graph._resolve("nrel_oneiro_publication"),
                        graph.types.VAR_PERM_POS_ARC)
                    assert len(graph._call("search_by_template", publication)) == 1
                    if index > 0:
                        previous_operation = f"checkpoint-operation-{index - 1}"
                        previous = graph._resolve(_key(evidence["stream"], "entry", previous_operation))
                        relation = graph.models.ScTemplate()
                        relation.triple_with_relation(address, graph.types.VAR_COMMON_ARC, previous,
                            graph._resolve("nrel_oneiro_previous"), graph.types.VAR_PERM_POS_ARC)
                        assert len(graph._call("search_by_template", relation)) == 1
                action = store.entity("checkpoint-intention")
                assert isinstance(action, Action)
                assert action.requires_inspection() and not action.may_retry()
            print(json.dumps({"verified_records": len(evidence["expected"]),
                              "uncertain_effect_not_retryable": True, "sc_types_match": True,
                              "graph_memberships_publications_previous_edges_match": True}))
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
