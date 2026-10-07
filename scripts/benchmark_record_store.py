"""Real OSTIS scale evidence, not a mock or a production memory fallback.

Explicit scratch URL, fixed synthetic data, finite sizes, incremental evidence.
Resume reads authoritative count from the graph; the manifest stores only probe
identity/parameters/measurements. No graph clear or deletion is performed.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path
from uuid import uuid4

from sc_client import client

from oneiro.records import Note, Provenance
from oneiro.sc_graph import ScLinkGraph
from oneiro.store import RecordStore


class MeasuredGraph(ScLinkGraph):
    def __init__(self):
        super().__init__()
        self.calls = Counter()
        self.link_reads = 0

    def _call(self, name, *args):
        self.calls[name] += 1
        return super()._call(name, *args)

    def read(self, name):
        self.link_reads += 1
        return super().read(name)

    def reset(self):
        self.calls.clear()
        self.link_reads = 0


def rss_bytes() -> int:
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not get_info(get_process(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError()
        return int(counters.WorkingSetSize)
    # Linux /proc reports current resident pages, not process-wide historical peak.
    return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def synthetic(index: int) -> Note:
    return Note(id=f"scale-note-{index}", topic="scale-contract", body=f"synthetic observation {index}",
                created_at="2026-10-07T00:00:00+00:00", updated_at="2026-10-07T00:00:00+00:00",
                provenance=Provenance.OBSERVATION)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--container", help="Optional scratch container name for read-only resource stats")
    parser.add_argument("--checkpoint-every", type=int, default=0,
                        help="Native Save every N seeded records; explicit new checkpoint-capable graph only")
    args = parser.parse_args()
    if args.sizes != sorted(set(args.sizes)) or not all(100 <= n <= 100000 for n in args.sizes):
        parser.error("sizes must be ascending, unique, 100..100000")
    if not 3 <= args.repeats <= 20:
        parser.error("repeats must be 3..20")
    if args.checkpoint_every < 0 or args.checkpoint_every > 1000:
        parser.error("checkpoint-every must be 0..1000")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest["url"] != args.url or manifest["sizes"] != args.sizes
                or manifest["repeats"] != args.repeats):
            raise ValueError("resume parameters differ; choose another output directory")
    else:
        manifest = {"stream": "scale-" + uuid4().hex, "url": args.url,
                    "sizes": args.sizes, "repeats": args.repeats,
                    "platform": platform.platform(), "python": sys.version, "pid": os.getpid(),
                    "page_size": 50, "scan_limit": 2000,
                    "comparison": "absolute correctness/resources; no claimed speedup"}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"pid": os.getpid(), "stream": manifest["stream"], "output": str(args.output)}), flush=True)
    client.connect(args.url)
    try:
        graph = MeasuredGraph()
        graph.ensure_ontology()
        with RecordStore(graph, manifest["stream"], args.output / "writer.lock") as store:
            count = store.page(limit=1).candidates
            for size in args.sizes:
                if (args.output / f"{size}.json").exists():
                    if count < size:
                        raise AssertionError("graph is older than saved measurements; inspect recovery")
                    continue
                if count > size:
                    raise AssertionError("missed scale checkpoint; use an independent stream")
                seed_start = time.monotonic()
                seed_count = count
                for index in range(count, size):
                    publication = store.append(synthetic(index), f"scale-operation-{index}")
                    assert publication.sequence == index + 1 and publication.revision == 1
                    if args.checkpoint_every and (index + 1) % args.checkpoint_every == 0:
                        checkpoint = graph.checkpoint()
                        print(json.dumps({"native_save_sequence": index + 1,
                                          "save_seconds": checkpoint["seconds"],
                                          "independent_snapshot": False}), flush=True)
                    if (index + 1) % 100 == 0:
                        print(json.dumps({"seeded": index + 1, "target": size,
                                          "elapsed_seconds": round(time.monotonic() - seed_start, 3)}), flush=True)
                count = size
                seed_seconds = time.monotonic() - seed_start
                results = []
                expected = [f"scale-note-{i}" for i in range(size - 1, size - 51, -1)]
                for repeat in range(args.repeats):
                    graph.reset()
                    rss_before = rss_bytes()
                    tracemalloc.start()
                    start = time.perf_counter()
                    page = store.page(limit=50)
                    elapsed = time.perf_counter() - start
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    assert [row["id"] for row in page.items] == expected
                    assert page.candidates == size and page.scanned == 50
                    assert page.cursor and not page.truncated and not page.skipped
                    assert graph.link_reads == 51
                    assert graph.calls["search_by_template"] == 0
                    results.append({"repeat": repeat, "seconds": elapsed, "link_reads": graph.link_reads,
                                    "rpc": dict(graph.calls), "tracemalloc_peak_bytes": peak,
                                    "rss_before_bytes": rss_before, "rss_after_bytes": rss_bytes()})
                resumed = store.page(cursor=page.cursor, limit=50)
                assert [row["id"] for row in resumed.items] == [f"scale-note-{i}" for i in range(size - 51, size - 101, -1)]
                # Correctness of key lookup, latest and idempotent retry at scale.
                assert store.entity(f"scale-note-{size // 2}") == synthetic(size // 2)
                assert store.latest() == synthetic(size - 1)
                assert store.append(synthetic(size - 1), f"scale-operation-{size - 1}").duplicate
                assert store.page(limit=1).candidates == size
                result = {"size": size, "seeded_this_run": size - seed_count,
                          "seed_seconds": seed_seconds, "page_samples": results,
                          "median_seconds": statistics.median(r["seconds"] for r in results),
                          "max_seconds": max(r["seconds"] for r in results),
                          "resume_entity_latest_retry_correct": True,
                          "durability": "server RAM; no checkpoint claim"}
                if args.container:
                    stats = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", args.container],
                                           capture_output=True, text=True, timeout=20, check=True)
                    result["container_stats"] = json.loads(stats.stdout)
                (args.output / f"{size}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(json.dumps({"checkpoint": size, "median_seconds": result["median_seconds"],
                                  "max_seconds": result["max_seconds"], "page_link_reads": 51}), flush=True)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
