#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<USAGE
Usage:
  $0 run [-b binaries] [-c config] [sc-machine args]
  $0 build [-b binaries] [-c config] [knowledge-base sources]

Build is allowed only on a verified empty, accessible KB_STORAGE directory.
Existing storage is never cleared. For a rebuild, retain the current volume and
choose a separate new volume and matching configuration. REBUILD_KB=1 refuses
startup even with the historical confirmation phrase.
USAGE
    exit 1
}

storage_empty() {
    local storage="${KB_STORAGE:-/kb.bin}"
    if [ ! -d "$storage" ]; then
        echo "KB storage is missing or not a directory: $storage" >&2
        exit 4
    fi
    local listing
    # Capture ls status separately. A read error is not an empty graph.
    if ! listing=$(ls -A -- "$storage"); then
        echo "Cannot inspect KB storage; refusing to build or start." >&2
        exit 4
    fi
    [ -z "$listing" ]
}

build_kb() {
    if ! storage_empty; then
        echo "REFUSING TO REBUILD EXISTING STORAGE. Retain it and use a separate new volume." >&2
        exit 3
    fi
    local source="${1:-${KB_PATH:-/knowledge-base}}"
    if [ ! -e "$source" ]; then
        echo "Invalid KB source path: $source" >&2
        exit 4
    fi
    "$BINARY_PATH"/sc-builder -c "$CONFIG_PATH" -i "$source"
}

start_machine() {
    if [ "${REBUILD_KB:-0}" != "0" ]; then
        echo "REFUSING TO CLEAR THE KNOWLEDGE BASE. Starting nothing." >&2
        echo "Rebuild requests are forbidden, including CONFIRM_KB_CLEAR. Use a separate new volume." >&2
        exit 3
    fi
    if storage_empty; then
        echo "KB storage ${KB_STORAGE:-/kb.bin} is empty: building from sources for the first time."
        build_kb "${KB_PATH:-/knowledge-base}"
    else
        echo "Existing graph found in ${KB_STORAGE:-/kb.bin}: starting sc-machine without rebuilding."
    fi
    # tini must signal sc-machine directly; a shell parent swallowed SIGINT and
    # prevented saving on shutdown in the measured October 2 failure.
    if [ $# -eq 0 ]; then
        exec "$BINARY_PATH"/sc-machine -c "$CONFIG_PATH" -e "${EXTENSIONS_PATH:-}"
    else
        exec "$BINARY_PATH"/sc-machine "$@"
    fi
}

command="${1:-help}"
if [ $# -gt 0 ]; then shift; fi
while getopts "b:c:h" opt; do
    case "$opt" in
        b) BINARY_PATH="$OPTARG" ;;
        c) CONFIG_PATH="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done
shift $((OPTIND - 1))
case "$command" in
    build) build_kb "$@" ;;
    run) start_machine "$@" ;;
    *) usage ;;
esac
