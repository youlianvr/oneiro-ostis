"""Compatibility imports for pre-package scientific and legacy entrypoints.

The implementation belongs to oneiro.config, and the command line belongs to
oneiro.cli (`oneiro settings`). This shim starts no services and must remain
until those entrypoints have been migrated and verified.
"""
import sys

from oneiro.cli import main
from oneiro.config import (
    DEFAULT_DATA_DIR, SETTINGS, SETTINGS_FILENAME, Setting, SettingsRejected, data_root,
    describe, path, reset, resolve, save, settings, settings_path, snapshot, value,
)

if __name__ == "__main__":
    raise SystemExit(main(["settings", *sys.argv[1:]]))
