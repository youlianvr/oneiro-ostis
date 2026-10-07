#!/usr/bin/env bash
set -euo pipefail

SC_MACHINE_VERSION="0.10.5"
SC_MACHINE_DESTINATION_DIR="${SC_MACHINE_DESTINATION_DIR:-install/sc-machine}"
SC_MACHINE_CACHE="${SC_MACHINE_CACHE:-.runtime/vendor}"
case "$(uname -s)" in
    Linux)
        platform="Linux"
        checksum="f0f169656c53c2cbac7c52f9bc364c952e3122a12930e954657c4a418af54c08"
        ;;
    Darwin)
        platform="Darwin"
        checksum="7b544d35d0d35346afd0ee82a95e4906bc88067a488fa0408219fc8b1ddffa4b"
        ;;
    *) echo "Unsupported operating system" >&2; exit 1 ;;
esac
archive="sc-machine-${SC_MACHINE_VERSION}-${platform}.tar.gz"
url="https://github.com/ostis-ai/sc-machine/releases/download/${SC_MACHINE_VERSION}/${archive}"
mkdir -p "$SC_MACHINE_CACHE"
artifact="$SC_MACHINE_CACHE/$archive"
if [ ! -e "$artifact" ]; then
    # A failed download remains a unique diagnostic artifact, not a truncated
    # trusted cache file. Never overwrite/remove previous downloads.
    pending=$(mktemp "$SC_MACHINE_CACHE/download.XXXXXXXX.tar.gz")
    curl --fail --location --retry 3 --connect-timeout 30 --max-time 180 -o "$pending" "$url"
    printf '%s  %s\n' "$checksum" "$pending" | sha256sum --check --status
    mv "$pending" "$artifact"
fi
printf '%s  %s\n' "$checksum" "$artifact" | sha256sum --check
if [ -d "$SC_MACHINE_DESTINATION_DIR" ] && [ -n "$(ls -A "$SC_MACHINE_DESTINATION_DIR")" ]; then
    echo "Destination is not empty; preserve it and choose a new destination." >&2
    exit 3
fi
mkdir -p "$SC_MACHINE_DESTINATION_DIR"
tar -xzf "$artifact" -C "$SC_MACHINE_DESTINATION_DIR" --strip-components 1
echo "Verified sc-machine $SC_MACHINE_VERSION installed; archive retained at $artifact"
