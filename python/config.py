"""Compatibility imports for pre-package scientific and legacy entrypoints.

The implementation belongs to oneiro.config. This shim starts no services and
must remain until those entrypoints have been migrated and verified.
"""
from oneiro.config import (
    DEFAULT_DATA_DIR, SETTINGS, SETTINGS_FILENAME, Setting, data_root, describe,
    main, path, reset, resolve, save, settings, settings_path, snapshot, value,
)

if __name__ == "__main__":
    raise SystemExit(main())
