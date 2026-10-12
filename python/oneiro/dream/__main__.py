"""`python -m oneiro.dream` — the kernel's own command line."""
from __future__ import annotations

import sys

from oneiro.dream.cli import main

if __name__ == "__main__":                       # pragma: no cover - module entry
    sys.exit(main())
