"""Technical OSTIS recovery artifacts; never a second semantic memory store.

Invoke only with the graph writer lane quiesced for the entire Save/copy cycle.
The container/volume binding is an explicit supervisor-owned configuration, not
a model-provided tool argument. Every generation is retained. Snapshot duration
counts against max loss; an expired/failed checkpoint forbids external effects.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from uuid import uuid4
from urllib.parse import urlsplit

from oneiro.query import GraphQueryError


@dataclass(frozen=True)
class SnapshotBinding:
    container: str
    volume: str
    directory: Path
    max_bytes: int = 1024 * 1024 * 1024
    max_loss_seconds: float = 300.0
    max_total_bytes: int = 4 * 1024 * 1024 * 1024
    free_reserve_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        if (not self.container or not self.volume or type(self.max_bytes) is not int
                or self.max_bytes < 1 or not 0 < self.max_loss_seconds <= 300
                or type(self.max_total_bytes) is not int or self.max_total_bytes < self.max_bytes
                or type(self.free_reserve_bytes) is not int or self.free_reserve_bytes < 0):
            raise ValueError("explicit binding, positive bytes and loss bound <=300 required")


def _command(arguments: list[str], *, timeout: float = 30) -> bytes:
    try:
        return subprocess.run(arguments, capture_output=True, check=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        raise GraphQueryError("snapshot_failed", "owned graph snapshot command failed") from None


def verify_binding(binding: SnapshotBinding, url: str | None = None) -> None:
    raw = _command(["docker", "inspect", binding.container])
    try:
        inspected = json.loads(raw)[0]
        mounts = [m for m in inspected["Mounts"] if m["Destination"] == "/kb.bin"]
        if (len(mounts) != 1 or mounts[0].get("Type") != "volume"
                or mounts[0].get("Name") != binding.volume or not inspected["State"]["Running"]):
            raise ValueError("wrong mount/state")
        if url is not None:
            parsed = urlsplit(url)
            ports = inspected["NetworkSettings"]["Ports"].get("8090/tcp", []) or []
            if (parsed.hostname not in ("127.0.0.1", "localhost")
                    or not any(p["HostIp"] == "127.0.0.1" and int(p["HostPort"]) == parsed.port for p in ports)):
                raise ValueError("graph URL does not match owned published port")
    except (ValueError, TypeError, KeyError, IndexError):
        raise GraphQueryError("snapshot_binding", "container/volume/graph URL binding is not verified") from None


def snapshot(binding: SnapshotBinding, save: Any,
             cancelled: threading.Event | None = None) -> dict[str, Any]:
    """Save and archive an explicitly bound NEW graph without dropping writes.

    The caller holds its graph lane, so there are no Oneiro writes between Save
    and copy. External graph writers invalidate this contract and are forbidden.
    Archive is streamed to disk, limited, inspected and fsynced before publishing
    its manifest. Failure retains the unique pending artifact for diagnosis.
    """
    started_epoch = time.time()
    started = time.monotonic()
    verify_binding(binding)
    binding.directory.mkdir(parents=True, exist_ok=True)
    retained_bytes = sum(path.stat().st_size for path in binding.directory.iterdir() if path.is_file())
    if retained_bytes + binding.max_bytes > binding.max_total_bytes:
        raise GraphQueryError("snapshot_quota", "retained snapshot quota reached; preserve/archive before continuing")
    if shutil.disk_usage(binding.directory).free < binding.max_bytes + binding.free_reserve_bytes:
        raise GraphQueryError("snapshot_disk_low", "snapshot reserve unavailable; no data removed")
    if cancelled is not None and cancelled.is_set():
        raise GraphQueryError("snapshot_cancelled", "snapshot cancelled before save")
    saved = save()
    if saved.get("saved") is not True:
        raise GraphQueryError("checkpoint_failed", "native graph save did not confirm completion")
    # Flush kernel buffers before copying: native Save completion alone does
    # not prove writes reached the storage device. This is a container-local
    # sync, not a graph mutation or a system configuration change.
    _command(["docker", "exec", binding.container, "sync"], timeout=30)
    binding.directory.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    archive = binding.directory / f"graph-{token}.tar"
    stderr = binding.directory / f"graph-{token}.copy.log"
    # Explicitly track only this subprocess and never mass-kill docker jobs.
    with archive.open("xb") as output, stderr.open("xb") as errors:
        process = subprocess.Popen(["docker", "cp", binding.container + ":/kb.bin/.", "-"],
                                   stdout=output, stderr=errors)
        try:
            deadline = time.monotonic() + binding.max_loss_seconds
            while process.poll() is None:
                if cancelled is not None and cancelled.is_set():
                    raise GraphQueryError("snapshot_cancelled", "snapshot cancelled; pending artifact retained")
                if output.tell() > binding.max_bytes or archive.stat().st_size > binding.max_bytes:
                    raise GraphQueryError("snapshot_too_large", "snapshot exceeds configured disk bound")
                if time.monotonic() > deadline:
                    raise GraphQueryError("snapshot_timeout", "graph copy exceeded checkpoint deadline")
                time.sleep(0.02)
            if process.returncode != 0:
                raise GraphQueryError("snapshot_failed", "graph copy did not succeed")
            output.flush()
            os.fsync(output.fileno())
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
    if archive.stat().st_size > binding.max_bytes:
        raise GraphQueryError("snapshot_too_large", "snapshot exceeds configured disk bound")
    files: dict[str, dict[str, Any]] = {}
    with tarfile.open(archive) as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise GraphQueryError("unsafe_snapshot", "snapshot has unsafe path/type")
            if member.isdir():
                continue
            name = str(path)
            if name in files:
                raise GraphQueryError("unsafe_snapshot", "snapshot has duplicate paths")
            source = tar.extractfile(member)
            if source is None:
                raise GraphQueryError("snapshot_failed", "snapshot file unreadable")
            digest = hashlib.sha256()
            size = 0
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            if size != member.size:
                raise GraphQueryError("snapshot_failed", "snapshot file truncated")
            files[name] = {"bytes": size, "sha256": digest.hexdigest()}
    if not files or not any(name.endswith("segments.scdb") for name in files):
        raise GraphQueryError("snapshot_failed", "no sc-memory segments in snapshot")
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    report = {"v": 1, "container": binding.container, "volume": binding.volume,
              "archive": str(archive), "sha256": digest.hexdigest(), "files": files,
              "started_epoch": started_epoch, "completed_epoch": time.time(),
              "duration_seconds": time.monotonic() - started, "save": saved,
              "crash_atomic": False}
    if report["duration_seconds"] > binding.max_loss_seconds:
        raise GraphQueryError("checkpoint_late", "checkpoint duration exceeded maximum loss window")
    manifest = archive.with_suffix(".json")
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    return report


class DurabilityGate:
    """Conservative same-process checkpoint age; restart begins unverified."""

    def __init__(self, max_loss_seconds: float = 300) -> None:
        if not 0 < max_loss_seconds <= 300:
            raise ValueError("maximum loss must be 0..300 seconds")
        self.max_loss_seconds = max_loss_seconds
        self._start: float | None = None
        self.failure: str | None = "no verified checkpoint in this process"
        self.sequence: int | None = None

    def confirmed(self, report: dict[str, Any], cycle_started: float) -> None:
        # Caller supplies monotonic start, not completion. Snapshot duration
        # cannot silently lengthen the safe interval.
        if (report.get("crash_atomic") is not False or report.get("save", {}).get("saved") is not True
                or not report.get("sha256") or not report.get("files")):
            self.failure = "invalid checkpoint evidence"
            raise GraphQueryError("checkpoint_failed", self.failure)
        sequence = report.get("save", {}).get("sequence")
        self.sequence = sequence if type(sequence) is int and sequence >= 0 else None
        self._start = cycle_started
        self.failure = None

    def fail(self, code: str) -> None:
        self.failure = code

    def status(self) -> dict[str, Any]:
        age = time.monotonic() - self._start if self._start is not None else None
        safe = self.failure is None and age is not None and age <= self.max_loss_seconds
        return {"external_effects_allowed": safe, "age_seconds": age,
                "max_loss_seconds": self.max_loss_seconds, "failure": self.failure,
                "scope": "checkpointed_sequence_only_not_new_intentions",
                "sequence": self.sequence}

    def require(self, intention_sequence: int | None = None) -> None:
        if not self.status()["external_effects_allowed"]:
            raise GraphQueryError("durability_unverified", "external effects require a current verified graph checkpoint")
        if intention_sequence is not None:
            if (type(intention_sequence) is not int or intention_sequence < 1
                    or self.sequence is None or intention_sequence > self.sequence):
                raise GraphQueryError("intent_not_durable", "intention is newer than the verified checkpoint")


class CheckpointLane(Protocol):
    durability: DurabilityGate
    async def checkpoint(self) -> dict[str, Any]: ...


class CheckpointSupervisor:
    """Finite-deadline periodic recovery checkpoints; explicit startup only.

    No OS autostart, no system-wide changes. Failures close the effect gate;
    newer intentions always require an immediate barrier, not merely a timer.
    """

    def __init__(self, lane: CheckpointLane, *, interval: float = 120, deadline: float = 60) -> None:
        if not 0 < interval <= 120 or not 0 < deadline <= 120 or interval + deadline > 240:
            raise ValueError("checkpoint interval/deadline must leave margin within 300 seconds")
        self.lane, self.interval, self.deadline = lane, interval, deadline
        self.last_report: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._cycle = asyncio.Lock()

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("checkpoint supervisor already started")
        self._task = asyncio.create_task(self._run())

    async def checkpoint(self) -> dict[str, Any]:
        async with self._cycle:
            try:
                report = await asyncio.wait_for(self.lane.checkpoint(), timeout=self.deadline)
            except GraphQueryError as exc:
                self.last_error = exc.code
                self.lane.durability.fail(exc.code)
                raise
            except TimeoutError:
                self.last_error = "checkpoint_timeout"
                self.lane.durability.fail(self.last_error)
                raise GraphQueryError(self.last_error, "checkpoint supervisor deadline exceeded") from None
            self.last_report, self.last_error = report, None
            return report

    async def before_effect(self, intention_sequence: int) -> None:
        # Never use an old checkpoint to authorize a newly accepted intention.
        try:
            self.lane.durability.require(intention_sequence)
        except GraphQueryError:
            await self.checkpoint()
            self.lane.durability.require(intention_sequence)

    async def _run(self) -> None:
        while True:
            try:
                await self.checkpoint()
            except GraphQueryError:
                # Failure remains visible and effect gate remains closed. A
                # later finite cycle may recover; no empty/success substitution.
                pass
            await asyncio.sleep(self.interval)

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.lane.durability.fail("checkpoint_supervisor_stopped")
