#!/usr/bin/env python3
"""CLI wrapper for AAO Operations and Diagnostics (aao-ops)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aao.ops import main

if __name__ == "__main__":
    sys.exit(main())
