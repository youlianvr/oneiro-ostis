from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from oneiro import checkpoints
from oneiro.checkpoints import SnapshotBinding, DurabilityGate, snapshot
from oneiro.query import GraphQueryError


def archive_bytes(name="./segments.scdb", body=b"synthetic graph"):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        member = tarfile.TarInfo(name)
        member.size = len(body)
        tar.addfile(member, io.BytesIO(body))
    return buffer.getvalue()


def fake_docker(monkeypatch, payload, *, volume="new-volume"):
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[1] == "inspect":
            return json.dumps([{"Mounts": [{"Destination": "/kb.bin", "Type": "volume", "Name": volume}],
                                "State": {"Running": True}}]).encode()
        assert args[1:] == ["exec", "scratch", "sync"]
        return b""
    class Process:
        returncode = 0
        def __init__(self, args, *, stdout, stderr):
            calls.append(args)
            stdout.write(payload)
        def poll(self):
            return 0
    monkeypatch.setattr(checkpoints, "_command", command)
    monkeypatch.setattr(checkpoints.subprocess, "Popen", Process)
    return calls


def test_snapshot_is_verified_retained_and_duration_includes_save_copy(tmp_path, monkeypatch):
    payload = archive_bytes()
    calls = fake_docker(monkeypatch, payload)
    binding = SnapshotBinding("scratch", "new-volume", tmp_path)
    report = snapshot(binding, lambda: {"saved": True, "seconds": 0.1})
    assert Path(report["archive"]).read_bytes() == payload
    assert report["files"]["segments.scdb"]["bytes"] == len(b"synthetic graph")
    assert report["crash_atomic"] is False
    assert Path(report["archive"]).with_suffix(".json").is_file()
    second = snapshot(binding, lambda: {"saved": True})
    assert second["archive"] != report["archive"]
    assert Path(report["archive"]).is_file()
    assert calls[0] == ["docker", "inspect", "scratch"]
    assert ["docker", "exec", "scratch", "sync"] in calls


def test_graph_url_must_match_owned_container_loopback_port(tmp_path, monkeypatch):
    binding = SnapshotBinding("scratch", "new-volume", tmp_path)
    inspected = [{"Mounts": [{"Destination": "/kb.bin", "Type": "volume", "Name": "new-volume"}],
                  "State": {"Running": True},
                  "NetworkSettings": {"Ports": {"8090/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8098"}]}}}]
    monkeypatch.setattr(checkpoints, "_command", lambda *_: json.dumps(inspected).encode())
    checkpoints.verify_binding(binding, "ws://127.0.0.1:8098/ws_json")
    for url in ("ws://127.0.0.1:8096/ws_json", "ws://example.com:8098/ws_json"):
        with pytest.raises(GraphQueryError, match="snapshot_binding"):
            checkpoints.verify_binding(binding, url)


def test_wrong_volume_prevents_save_or_copy(tmp_path, monkeypatch):
    fake_docker(monkeypatch, archive_bytes(), volume="foreign-volume")
    def forbidden_save():
        raise AssertionError("must not save another volume")
    with pytest.raises(GraphQueryError, match="snapshot_binding"):
        snapshot(SnapshotBinding("scratch", "new-volume", tmp_path), forbidden_save)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["../segments.scdb", "/segments.scdb"])
def test_unsafe_archive_is_retained_but_never_published(tmp_path, monkeypatch, name):
    fake_docker(monkeypatch, archive_bytes(name))
    with pytest.raises(GraphQueryError, match="unsafe_snapshot"):
        snapshot(SnapshotBinding("scratch", "new-volume", tmp_path), lambda: {"saved": True})
    assert list(tmp_path.glob("*.tar"))
    assert not list(tmp_path.glob("*.json"))


def test_disk_limit_refuses_without_publishing_manifest(tmp_path, monkeypatch):
    fake_docker(monkeypatch, archive_bytes())
    with pytest.raises(GraphQueryError, match="snapshot_too_large"):
        snapshot(SnapshotBinding("scratch", "new-volume", tmp_path, max_bytes=10), lambda: {"saved": True})
    assert not list(tmp_path.glob("*.json"))


def test_durability_gate_includes_checkpoint_duration_and_fails_closed(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(checkpoints.time, "monotonic", lambda: clock[0])
    gate = DurabilityGate(300)
    with pytest.raises(GraphQueryError, match="durability_unverified"):
        gate.require()
    report = {"save": {"saved": True}, "sha256": "verified", "files": {"segments": {}}, "crash_atomic": False}
    gate.confirmed(report, cycle_started=90)
    assert gate.status()["age_seconds"] == 10
    gate.require()
    clock[0] = 391
    assert gate.status()["age_seconds"] == 301
    with pytest.raises(GraphQueryError, match="durability_unverified"):
        gate.require()
    clock[0] = 200
    gate.fail("snapshot_failed")
    with pytest.raises(GraphQueryError, match="durability_unverified"):
        gate.require()
    assert gate.status()["failure"] == "snapshot_failed"


def test_retention_quota_closes_checkpoint_without_deleting_previous_artifacts(tmp_path, monkeypatch):
    fake_docker(monkeypatch, archive_bytes())
    prior = tmp_path / "prior.tar"
    prior.write_bytes(b"preserved" * 100)
    binding = SnapshotBinding("scratch", "new-volume", tmp_path, max_bytes=1000, max_total_bytes=1000)
    with pytest.raises(GraphQueryError, match="snapshot_quota"):
        snapshot(binding, lambda: {"saved": True})
    assert prior.read_bytes() == b"preserved" * 100
    assert list(tmp_path.iterdir()) == [prior]


def test_old_checkpoint_never_authorizes_a_new_intention():
    import time
    gate = DurabilityGate()
    gate.confirmed({"save": {"saved": True, "sequence": 5}, "sha256": "verified",
                    "files": {"segments": {}}, "crash_atomic": False}, time.monotonic())
    gate.require(5)
    with pytest.raises(GraphQueryError, match="intent_not_durable"):
        gate.require(6)
    with pytest.raises(GraphQueryError, match="intent_not_durable"):
        gate.require(True)


def test_supervisor_periodic_failure_is_visible_and_intent_barrier_rechecks():
    import asyncio
    import time
    from oneiro.checkpoints import CheckpointSupervisor

    class Lane:
        def __init__(self):
            self.durability = DurabilityGate()
            self.calls = 0
            self.sequence = 1
            self.fail = False
        async def checkpoint(self):
            self.calls += 1
            if self.fail:
                raise GraphQueryError("snapshot_failed", "injected")
            report = {"save": {"saved": True, "sequence": self.sequence}, "sha256": "verified",
                      "files": {"segments": {}}, "crash_atomic": False}
            self.durability.confirmed(report, time.monotonic())
            return report

    async def scenario():
        lane = Lane()
        supervisor = CheckpointSupervisor(lane, interval=0.02, deadline=1)
        supervisor.start()
        await asyncio.sleep(0.055)
        assert lane.calls >= 2
        lane.sequence = 2
        count = lane.calls
        await supervisor.before_effect(2)
        assert lane.calls > count
        lane.durability.require(2)
        lane.fail = True
        lane.durability.fail("new_intention")
        with pytest.raises(GraphQueryError, match="snapshot_failed"):
            await supervisor.before_effect(3)
        assert supervisor.last_error == "snapshot_failed"
        assert not lane.durability.status()["external_effects_allowed"]
        await supervisor.close()
        assert supervisor._task is None
        assert not lane.durability.status()["external_effects_allowed"]
    asyncio.run(scenario())


def test_invalid_confirmation_does_not_open_effect_gate():
    gate = DurabilityGate()
    with pytest.raises(GraphQueryError, match="checkpoint_failed"):
        gate.confirmed({"save": {"saved": True}, "crash_atomic": True}, 0)
    assert not gate.status()["external_effects_allowed"]
