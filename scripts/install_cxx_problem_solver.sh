#!/usr/bin/env bash
set -eo pipefail

# Oneiro-OSTIS vendor binary installer.
# Unlike the example-app script, this one:
#   1. downloads only what the oneiro-module needs (sc-machine),
#   2. keeps the include/ headers so the module can compile against the
#      release binaries without conan (conan.ostis.net was unreachable).

SC_MACHINE_VERSION="0.10.5"
SC_MACHINE_DESTINATION_DIR="install/sc-machine"

get_archive_name() {
    local os_name=$(uname -s)
    case "$os_name" in
        Linux)
            echo "$1-$2-Linux.tar.gz"
            ;;
        Darwin)
            echo "$1-$2-Darwin.tar.gz"
            ;;
        *)
            echo "Unsupported operating system: $os_name"
            exit 1
            ;;
    esac
}

download_archive() {
    local url="$1"
    echo "Downloading ${url}..."
    if ! curl -LO "${url}"; then
        echo "Error downloading ${url}"
        exit 1
    fi
}

extract_archive() {
    local archive="$1"
    local destination_dir="$2"
    echo "Creating directory ${destination_dir} and extracting files..."
    mkdir -p "${destination_dir}" && tar -xvzf "${archive}" -C "${destination_dir}" --strip-components 1
}

cleanup() {
    local archive="$1"
    rm -f "${archive}"
}

SC_MACHINE_ARCHIVE=$(get_archive_name "sc-machine" "${SC_MACHINE_VERSION}")
SC_MACHINE_URL="https://github.com/ostis-ai/sc-machine/releases/download/${SC_MACHINE_VERSION}/${SC_MACHINE_ARCHIVE}"

download_archive "${SC_MACHINE_URL}"
extract_archive "${SC_MACHINE_ARCHIVE}" "${SC_MACHINE_DESTINATION_DIR}"
cleanup "${SC_MACHINE_ARCHIVE}"

echo "Installation complete!"
