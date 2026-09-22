"""One-off: what is actually inside the live organization feed.

Answers three questions for the explanatory note: how many records are real
runs and how many are test leftovers, which run tags exist, and whether the
deployment-growth card has any episodes behind it.
"""

import collections
import json
import urllib.request

BASE = "http://127.0.0.1:8130"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=180) as r:
        return json.load(r)


swarm = get("/api/swarm")
rows = swarm.get("records", swarm)
print("swarm rows:", len(rows))
print("record keys:", sorted(rows[0].keys()) if rows else "-")

by_session = collections.Counter()
by_kind = collections.Counter()
for r in rows:
    by_session[str(r.get("session"))[:34]] += 1
    by_kind[str(r.get("kind"))[:34]] += 1
print("\nby session (the run tag):")
for t, n in by_session.most_common(20):
    print(f"  {n:>4}  {t}")
print("\nby kind:")
for t, n in by_kind.most_common(20):
    print(f"  {n:>4}  {t}")

print("\ntest-looking records:")
for r in rows:
    blob = json.dumps(r, ensure_ascii=False)
    if "test" in blob.lower() and "tests/" not in blob:
        print("  ", r.get("recorded_at"), r.get("role"), r.get("kind"),
              blob[:150])

state = get("/api/state")
print("\nstate keys:", sorted(state.keys()))
for key in ("episodes", "strategies", "benchmarks", "consistency", "subject"):
    v = state.get(key)
    if isinstance(v, list):
        print(f"  {key}: {len(v)} items")
    elif isinstance(v, dict):
        print(f"  {key}: dict with {len(v)} keys")
    else:
        print(f"  {key}: {json.dumps(v, ensure_ascii=False)[:200]}")
