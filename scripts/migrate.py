#!/usr/bin/env python3
"""CLI entrypoint for AAO Unified PostgreSQL Migrator."""

import sys
from pathlib import Path

# Add src to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aao.migrator import main

if __name__ == "__main__":
    sys.exit(main())
