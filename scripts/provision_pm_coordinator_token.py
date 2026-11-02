#!/usr/bin/env python3
"""Issue the PM coordinator credential and install it as aao-pm's ``aao-pm.token``.

The token travels only through stdin to the role-owned installer (``--token pm``); it is
never printed, written by this process, or placed in command arguments or environment.
"""

from __future__ import annotations

import argparse
import getpass
import os
import pwd
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provision_w2_publishers as w2  # shared helpers; tests patch this module object
from bootstrap_self_dev_agent import BootstrapError
from provision_w2_publishers import ProvisionError, local_api_url

ACCOUNT = "aao-pm"
TOKEN_KIND = "pm"
# Exactly the preflight's REQUIRED_GRANTS; work.create needs a separate CEO decision.
GRANTS = ("project.read", "work.coordinate", "work.assign")


def parse_expiry(value: str) -> str:
    """Return a future, timezone-aware expiry normalised to UTC ISO-8601."""
    try:
        expiry = datetime.fromisoformat(value)
    except ValueError:
        raise ProvisionError("--expires-at must be an ISO-8601 timestamp") from None
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ProvisionError("--expires-at must include a timezone")
    expiry = expiry.astimezone(UTC)
    if expiry <= datetime.now(UTC):
        raise ProvisionError("--expires-at must be in the future")
    return expiry.isoformat()


def provision(
    project_id: str,
    *,
    api_url: str,
    ceo_token: str,
    expiry: str | None,
    api_python: str = sys.executable,
) -> tuple[str, str, str | None]:
    """Preflight, issue, grant, install and verify; revoke and remove on any failure."""
    api_url = local_api_url(api_url)
    if not w2.INSTALLER.is_file() or w2.INSTALLER.is_symlink():
        raise ProvisionError("token installer is missing or unsafe")
    projects = w2.request_json(api_url, "/v1/projects", ceo_token=ceo_token)
    if not isinstance(projects, list):
        raise ProvisionError("project inventory response is invalid")
    matches = [row for row in projects if str(row.get("id")) == project_id]
    if len(matches) != 1 or matches[0].get("state") != "ACTIVE":
        raise ProvisionError("project ID must resolve to exactly one ACTIVE project")
    if pwd.getpwnam(ACCOUNT).pw_uid == os.getuid():
        raise ProvisionError("aao-pm must be a Linux account distinct from the CEO invoker")
    w2._run_role_helper(
        ACCOUNT, api_python=api_python, token=None, operation="check", token_kind=TOKEN_KIND
    )

    project_path = quote(project_id, safe="")
    principal = f"aao-pm-coordinator-{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
    issued = [(ACCOUNT, principal, "")]
    try:
        token = w2.issue_agent_credential(api_url, principal, ceo_token=ceo_token)
        issued[0] = (ACCOUNT, principal, token)
        w2.grant_exactly(api_url, project_path, principal, GRANTS, expiry, ceo_token=ceo_token)
        for operation in ("install", "verify"):
            w2._run_role_helper(
                ACCOUNT,
                api_python=api_python,
                token=token,
                operation=operation,
                token_kind=TOKEN_KIND,
            )
        return ACCOUNT, principal, expiry
    except (BootstrapError, ProvisionError, OSError, ValueError) as exc:
        w2.cleanup(
            api_url, issued, ceo_token=ceo_token, api_python=api_python, token_kind=TOKEN_KIND
        )
        if isinstance(exc, ProvisionError):
            raise
        raise ProvisionError(
            "PM coordinator credential setup failed; the principal was revoked where possible"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--api", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))
    parser.add_argument(
        "--python", default=sys.executable, help="Python executable accessible to aao-pm"
    )
    expiry_group = parser.add_mutually_exclusive_group(required=True)
    expiry_group.add_argument(
        "--expires-at", help="CEO-decided grant expiry, ISO-8601 with timezone"
    )
    expiry_group.add_argument(
        "--no-expiry", action="store_true", help="CEO decision: grants without expiry"
    )
    args = parser.parse_args(argv)
    try:
        api_url = local_api_url(args.api)
        expiry = None if args.no_expiry else parse_expiry(args.expires_at)
        ceo_token = getpass.getpass("CEO token (input hidden): ")
        account, principal, expiry = provision(
            args.project_id,
            api_url=api_url,
            ceo_token=ceo_token,
            expiry=expiry,
            api_python=args.python,
        )
    except (ProvisionError, BootstrapError, OSError, KeyError) as exc:
        print(f"PM coordinator provisioning did not complete: {exc}", file=sys.stderr)
        return 1
    print(
        f"PM coordinator credential provisioned: account={account} principal={principal} "
        f"grants={','.join(GRANTS)} expires={expiry or 'never'}"
    )
    print("Token was not displayed; aao-pm.token was verified mode 0600 by the installer.")
    print(f"Set AAO_PM_PRINCIPAL_ID={principal} in the coordinator service environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
