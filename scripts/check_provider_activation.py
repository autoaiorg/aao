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
    "AAO_CONVERSATION_PROVIDER",
    "AAO_CONVERSATION_API_URL",
    "AAO_CONVERSATION_MODEL",
    "AAO_CONVERSATION_API_KEY",
    "AAO_CONVERSATION_RECOVERY_ENABLED",
    "AAO_AGENT_PROVIDER",
    "AAO_AGENT_CODEX_HOME",
    "AAO_AGENT_DAILY_BUDGET_USD",
    "AAO_AGENT_MAX_ATTEMPTS",
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


def report(*, conversation_spend_limit_confirmed: bool = False) -> dict:
    from aao.agent_runner import activated_backends, daily_budget_usd

    home = os.getenv("AAO_AGENT_CODEX_HOME")
    activated = "codex" in activated_backends()
    # run_agent_patch checks the home inline (not importable), so this one condition is mirrored.
    home_ok = bool(home) and Path(home).is_dir()
    # Use the production parser/validation, not merely whether the variable is non-empty.
    budget_valid = daily_budget_usd() is not None
    codex_would_run = activated and home_ok and budget_valid
    conversation_active = conversation_would_call_provider()
    return {
        "variables_set": {name: bool(os.getenv(name, "").strip()) for name in VARIABLES},
        "conversation_provider_active": conversation_active,
        # AAO has no in-app conversation spend cap. This is deliberately a manual,
        # blocking prerequisite, not something this read-only checker can attest.
        "conversation_spend_limit_required": conversation_active,
        "conversation_spend_limit_confirmed_by_operator": conversation_spend_limit_confirmed,
        "codex_backend_activated": activated,
        "codex_home_is_directory": home_ok,
        "codex_budget_is_valid": budget_valid,
        "codex_backend_would_run": codex_would_run,
        "agent_budget_limit_set": budget_valid,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect",
        choices=("on", "off"),
        help="exit 1 unless both providers are on (or both off); 'on' also requires a valid Codex budget",
    )
    parser.add_argument(
        "--conversation-spend-limit-confirmed",
        action="store_true",
        help="operator attests that a spend limit is configured in the conversation provider console",
    )
    args = parser.parse_args(argv)
    result = report(conversation_spend_limit_confirmed=args.conversation_spend_limit_confirmed)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.expect:
        states = {result["conversation_provider_active"], result["codex_backend_would_run"]}
        if states != {args.expect == "on"}:
            return 1
        if (
            args.expect == "on"
            and result["conversation_provider_active"]
            and not args.conversation_spend_limit_confirmed
        ):
            # This cannot be checked locally. The flag is an operator attestation,
            # not a machine verification.
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
