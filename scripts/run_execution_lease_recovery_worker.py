#!/usr/bin/env python3
"""Quarantine expired PostgreSQL execution leases without retrying them.

The one-shot mode is safe to run after a service restart. Watch mode polls the
same durable queue and stops cleanly on SIGINT or SIGTERM. It does not assign,
retry, reconcile, or authorize work.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MAX_POLL_SECONDS = 300.0


def run(*, watch: bool = False, poll_seconds: float = 5.0) -> int:
    if not 0 < poll_seconds <= MAX_POLL_SECONDS:
        raise ValueError(
            f"poll interval must be greater than zero and at most {MAX_POLL_SECONDS:g} seconds"
        )

    from aao.execution_queue import quarantine_expired

    def reconcile_expired_leases() -> None:
        count = quarantine_expired()
        if count:
            print(f"Quarantined {count} expired execution lease(s)", flush=True)

    reconcile_expired_leases()
    if not watch:
        return 0

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    while not stop.wait(poll_seconds):
        try:
            reconcile_expired_leases()
        except Exception as exc:  # noqa: BLE001 - hide sensitive DB exception details.
            print(
                f"Execution lease recovery failed ({type(exc).__name__})",
                file=sys.stderr,
                flush=True,
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="poll until stopped")
    mode.add_argument("--once", action="store_true", help="run one recovery pass (default)")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    try:
        return run(watch=args.watch, poll_seconds=args.poll_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - hide sensitive DB exception details.
        print(
            f"Execution lease recovery failed ({type(exc).__name__})",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
