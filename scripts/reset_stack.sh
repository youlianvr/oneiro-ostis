#!/usr/bin/env bash
# Reset the RUNTIME knowledge base of oneiro-ostis.
#
# What this does: stops the stack, removes the runtime KB volume (`kb-binary`)
# and starts again — the machine container rebuilds the KB from the sources in
# `knowledge-base/` (our ontology + the vendored IMS base), so nothing that is
# not regenerable is lost. The repository (sources, docs, tests) is untouched.
#
# Why it exists: demos and test runs add strategy/episode nodes to the live
# graph; before a talk you want a clean graph that contains exactly the demo's
# artifacts (docs/demo-log.md, docs/dream-tree.html).
#
# Usage:  scripts/reset_stack.sh --yes
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${1:-}" != "--yes" ]; then
  echo "This drops the RUNTIME KB volume and rebuilds it from knowledge-base/ sources."
  echo "Re-run as: scripts/reset_stack.sh --yes"
  exit 1
fi

PROJECT=$(basename "$(pwd)")
VOLUME="${PROJECT}_kb-binary"

echo "==> stopping the stack"
docker compose down

echo "==> removing runtime KB volume ${VOLUME} (rebuilds from sources on start)"
docker volume rm -f "${VOLUME}" >/dev/null 2>&1 || true

echo "==> starting (full KB rebuild: 201 sources, takes a couple of minutes)"
docker compose up -d --force-recreate

echo "==> waiting for the healthcheck"
for i in $(seq 1 40); do
  status=$(docker inspect --format '{{.State.Health.Status}}' "${PROJECT}-machine-1" 2>/dev/null || echo unknown)
  if [ "$status" = "healthy" ]; then
    echo "==> stack healthy"
    exit 0
  fi
  sleep 10
done

echo "!! stack did not become healthy in time; check: docker logs ${PROJECT}-machine-1" >&2
exit 1
