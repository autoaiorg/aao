#!/usr/bin/env python3
"""Recover expired persisted CEO conversation turns (strictly opt-in).

The service reads configuration from its process environment; it does not load
local dotenv files or accept provider credentials on its command line.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAX_POLL_SECONDS = 300


def run(*, watch: bool = False, poll_seconds: float = 5) -> int:
    if not 0 < poll_seconds <= MAX_POLL_SECONDS:
        raise ValueError(f"poll interval must be greater than zero and at most {MAX_POLL_SECONDS} seconds")
    from aao.conversation_turn_recovery import recover_one_turn

    result = recover_one_turn()
    status = result["status"]
    if status == "COMPLETED":
        print(f"Recovered conversation turn {result['turn_id']}")
    elif status not in {"IDLE", "DISABLED"}:
        print(f"Conversation recovery worker: {status}", file=sys.stderr)
    if not watch:
        return 0 if status in {"COMPLETED", "IDLE", "DISABLED"} else 1

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    while not stop.wait(poll_seconds):
        result = recover_one_turn()
        status = result["status"]
        if status == "COMPLETED":
            print(f"Recovered conversation turn {result['turn_id']}")
        elif status not in {"IDLE", "DISABLED"}:
            print(f"Conversation recovery worker: {status}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="poll the PostgreSQL queue until stopped")
    mode.add_argument("--once", action="store_true", help="process at most one expired turn (default)")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    try:
        return run(watch=args.watch, poll_seconds=args.poll_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
