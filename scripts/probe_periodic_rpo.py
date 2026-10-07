"""Timed RPO trial, explicit disposable NEW graph binding only.

Preserves independent verified snapshots before hard-killing the exact bound
container. No delete/clear/volume removal. Measures actual missing records and
includes checkpoint duration; script does not claim arbitrary-host power-loss
or kill-mid-save acceptance. Never point it at the retained old graph.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from oneiro.checkpoints import SnapshotBinding, CheckpointSupervisor, verify_binding
from oneiro.graph_worker import GraphWorker
from oneiro.query import GraphQueryError
from oneiro.records import Note, Provenance, Action, State, Effect, EffectOutcome


async def trial(args: argparse.Namespace) -> None:
    args.output.mkdir(parents=True, exist_ok=False)
    binding = SnapshotBinding(args.container, args.volume, args.output / "snapshots")
    verify_binding(binding, args.url)
    stream = "rpo-" + uuid4().hex
    lease = args.output / "writer.lock"
    lane = GraphWorker(args.url, stream, lease, timeout=30, snapshot_binding=binding)
    supervisor = CheckpointSupervisor(lane, interval=120, deadline=30)
    evidence = {"stream": stream, "url": args.url, "container": args.container, "volume": args.volume,
                "pid": __import__("os").getpid(), "records": [], "periodic_reports": [],
                "scope": "container hard kill between saves; not power loss or kill-mid-save"}
    report_path = args.output / "report.json"

    def save_evidence():
        report_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    try:
        # Unknown intention survives a durable barrier, without an actual effect.
        intention = Action(id="rpo-unknown-intention", tool="probe.no_external_effect", state=State.UNCERTAIN,
                           effect=Effect(kind="synthetic", target="no effect", outcome=EffectOutcome.UNCERTAIN))
        publication = await lane.call("append", record=intention.to_dict(), operation_id="intent")
        await supervisor.before_effect(publication["sequence"])
        evidence["intention"] = intention.to_dict()
        evidence["barrier"] = supervisor.last_report
        supervisor.start()
        start = time.monotonic()
        last_checkpoint = None
        index = 0
        while time.monotonic() - start < args.seconds:
            record = Note(id=f"rpo-note-{index}", topic="RPO acceptance", body=f"synthetic timed record {index}",
                          provenance=Provenance.OBSERVATION)
            result = await lane.call("append", record=record.to_dict(), operation_id=f"record-{index}")
            evidence["records"].append({"record": record.to_dict(), "sequence": result["sequence"],
                                        "accepted_epoch": time.time(), "accepted_elapsed": time.monotonic() - start})
            if supervisor.last_report is not None and supervisor.last_report is not last_checkpoint:
                last_checkpoint = supervisor.last_report
                evidence["periodic_reports"].append(last_checkpoint)
                print(json.dumps({"checkpoint_sequence": last_checkpoint["save"]["sequence"],
                                  "cycle_seconds": last_checkpoint["cycle_seconds"]}), flush=True)
            save_evidence()
            index += 1
            await asyncio.sleep(5)
        periodic_sequences = [r["save"]["sequence"] for r in evidence["periodic_reports"]]
        assert (len(periodic_sequences) >= 2 and max(periodic_sequences) - min(periodic_sequences) >= 10), \
            "need two actual periodic completions separated by ongoing writes"
        assert supervisor.last_error is None
        latest = supervisor.last_report
        assert latest is not None
        checkpointed_sequence = latest["save"]["sequence"]
        checkpoint_age = lane.durability.status()["age_seconds"]
        assert checkpoint_age is not None and checkpoint_age <= 300
        # Verify preserved archive exists before any destructive fault injection.
        assert Path(latest["archive"]).is_file()
        await supervisor.close()
        await lane.close()
        verify_binding(binding, args.url)
        evidence["kill_epoch"] = time.time()
        evidence["checkpoint_age_including_cycle_seconds"] = checkpoint_age
        save_evidence()
        subprocess.run(["docker", "kill", "--signal", "KILL", args.container], check=True, timeout=15)
        subprocess.run(["docker", "start", args.container], check=True, timeout=15)
        # Readiness retry is finite and does not replay any owner effect.
        ready = False
        for _ in range(20):
            candidate = GraphWorker(args.url, stream, lease, timeout=3, snapshot_binding=binding)
            try:
                page = await candidate.call("page", limit=1)
                lane = candidate
                ready = True
                break
            except GraphQueryError:
                await candidate.close()
                await asyncio.sleep(0.5)
        if not ready:
            raise RuntimeError("graph did not become readable after hard kill; restore retained snapshot")
        assert page["candidates"] >= checkpointed_sequence
        surviving, missing = [], []
        for item in evidence["records"]:
            record = await lane.call("entity", record_id=item["record"]["id"])
            if record is None:
                missing.append(item)
            else:
                assert record == item["record"]
                surviving.append(item)
        assert all(item["sequence"] > checkpointed_sequence for item in missing), "checkpointed record lost"
        action = await lane.call("entity", record_id=intention.id)
        assert action == intention.to_dict()
        assert intention.requires_inspection() and not intention.may_retry()
        loss_window = max((evidence["kill_epoch"] - item["accepted_epoch"] for item in missing), default=0)
        assert loss_window <= 300
        evidence["result"] = {"surviving": len(surviving), "missing": len(missing),
                              "measured_oldest_missing_age_seconds": loss_window,
                              "all_checkpointed_records_survived": True, "uncertain_retry_refused": True,
                              "periodic_completions": len(evidence["periodic_reports"])}
        evidence["missing_ids"] = [item["record"]["id"] for item in missing]
        save_evidence()
        print(json.dumps(evidence["result"]), flush=True)
    finally:
        await supervisor.close()
        await lane.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--container", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=140)
    parser.add_argument("--allow-hard-kill-new-graph", action="store_true", required=True)
    args = parser.parse_args()
    if not 135 <= args.seconds <= 600:
        parser.error("trial duration must be 135..600 seconds")
    if "oneiro-ostis_kb-binary" == args.volume or "oneiro-ostis-machine-1" == args.container:
        parser.error("retained old graph is forbidden")
    asyncio.run(trial(args))


if __name__ == "__main__":
    main()
