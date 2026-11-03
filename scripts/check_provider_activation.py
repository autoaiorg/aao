#!/usr/bin/env python3
"""Read-only report of provider activation state. Prints booleans only, never a value.

Run it with the same environment as the service under inspection (the variables must be
exported in the shell that runs it). It makes no network call and changes nothing.
Exit 0 unless --expect is given and the state differs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

VARIABLES = (
    "AAO_CONVERSATION_PROVIDER", "AAO_CONVERSATION_API_URL", "AAO_CONVERSATION_MODEL",
    "AAO_CONVERSATION_API_KEY", "AAO_CONVERSATION_RECOVERY_ENABLED", "AAO_AGENT_PROVIDER",
    "AAO_AGENT_CODEX_HOME", "AAO_AGENT_DAILY_BUDGET_USD", "AAO_AGENT_MAX_ATTEMPTS",
)


class _NoNetwork(Exception):
    pass


def conversation_would_call_provider() -> bool:
    """Reuse the real gate: stream_reply refuses before any I/O unless fully configured. urlopen is
    stubbed, so reaching it proves the gate passed and no request is ever sent."""
    from aao import conversation_provider as cp

    def stub(*_args, **_kwargs):
        raise _NoNetwork

    real, cp.urlopen = cp.urlopen, stub
    try:
        list(cp.stream_reply([]))
    except cp.ProviderUnavailable as exc:
        return exc.code != "PROVIDER_NOT_CONFIGURED"
    except _NoNetwork:
        return True
    finally:
        cp.urlopen = real
    return True


def report() -> dict:
    from aao.agent_runner import activated_backends

    home = os.getenv("AAO_AGENT_CODEX_HOME")
    activated = "codex" in activated_backends()
    # run_agent_patch checks the home inline (not importable), so this one condition is mirrored.
    home_ok = bool(home) and Path(home).is_dir()
    return {
        "variables_set": {name: bool(os.getenv(name, "").strip()) for name in VARIABLES},
        "conversation_provider_active": conversation_would_call_provider(),
        "codex_backend_activated": activated,
        "codex_home_is_directory": home_ok,
        "codex_backend_would_run": activated and home_ok,
        "agent_budget_limit_set": bool(os.getenv("AAO_AGENT_DAILY_BUDGET_USD", "").strip()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", choices=("on", "off"),
                        help="exit 1 unless both providers are on (or both off)")
    args = parser.parse_args(argv)
    result = report()
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.expect:
        states = {result["conversation_provider_active"], result["codex_backend_would_run"]}
        if states != {args.expect == "on"}:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
