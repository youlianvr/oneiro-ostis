#!/usr/bin/env bash
# Oneiro-OSTIS stage-1 smoke test: is the ostis-example-app stack alive?
# Usage: bash scripts/smoke-test.sh   (run from anywhere)
set -u

FAIL=0

say() { printf '%s\n' "$*"; }
check() {
  # check <name> <cmd...>
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    say "[OK]   $name"
  else
    say "[FAIL] $name"
    FAIL=1
  fi
}

say "=== Oneiro-OSTIS smoke test ==="

# 1. Containers up
compose_ps() { docker compose -f "$(dirname "$0")/../ostis-example-app/docker-compose.yml" ps --format json 2>/dev/null | grep -q '"healthy"\|"running"'; }
check "docker compose services running" docker ps

MACHINE_UP=$(docker ps --filter name=ostis-example-app-machine-1 --filter status=running -q)
check "machine container running" test -n "$MACHINE_UP"
WEB_UP=$(docker ps --filter name=ostis-example-app-web-1 --filter status=running -q)
check "web container running" test -n "$WEB_UP"

# 2. Healthchecks
check "machine healthy (docker hc)" docker inspect --format='{{.State.Health.Status}}' ostis-example-app-machine-1

# 3. HTTP probes
check "sc-server answers :8090" curl -sf --max-time 5 http://localhost:8090/
check "sc-web answers :8000" curl -sf --max-time 5 http://localhost:8000/

say ""
if [ "$FAIL" -eq 0 ]; then
  say "ALL GREEN — stack is alive. Stage 1 done."
else
  say "SOME CHECKS FAILED — see 'docker logs ostis-example-app-machine-1'"
fi
exit $FAIL
