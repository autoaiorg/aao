#!/usr/bin/env python3
"""Issue separate, short-lived W2 publisher credentials to the two host roles.

Credentials are sent only through stdin to the role-owned runtime installer; they are
never written by this process to disk, command arguments, or environment variables.
"""
from __future__ import annotations

import argparse
import getpass
import os
import pwd
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_self_dev_agent import BootstrapError, request_json

ACCOUNTS = ("aao-impl-codex", "aao-pm")
GRANTS = ("project.read", "code.publish")
PROJECT_NAME = "AAO — Self Development"
INSTALLER = Path(__file__).with_name("install_publisher_token_for_role.py")


class ProvisionError(RuntimeError):
    pass


def local_api_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ProvisionError("W2 publisher provisioning is restricted to the loopback AAO API")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProvisionError("AAO API URL must not contain credentials or query data")
    return value.rstrip("/")


def _run_role_helper(account: str, *, api_python: str, token: str | None,
                     operation: str) -> None:
    entry = pwd.getpwnam(account)
    runtime = f"/run/user/{entry.pw_uid}"
    args = ["sudo", "-u", account, "-H", "env", f"XDG_RUNTIME_DIR={runtime}",
            api_python, str(INSTALLER), "--account", account, f"--{operation}"]
    try:
        subprocess.run(args, input=None if token is None else token + "\n", text=True,
                       check=True, timeout=120)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ProvisionError(f"role token helper failed for {account} ({operation})") from None


def provision(project_id: str, *, api_url: str, ceo_token: str,
              api_python: str = sys.executable) -> list[tuple[str, str, str]]:
    """Preflight, issue and deliver credentials; revoke and remove partial delivery on failure."""
    api_url = local_api_url(api_url)
    if not INSTALLER.is_file() or INSTALLER.is_symlink():
        raise ProvisionError("publisher-token installer is missing or unsafe")
    projects = request_json(api_url, "/v1/projects", ceo_token=ceo_token)
    if not isinstance(projects, list):
        raise ProvisionError("project inventory response is invalid")
    matches = [row for row in projects if row.get("name") == PROJECT_NAME]
    if (len(matches) != 1 or str(matches[0].get("id")) != project_id
            or matches[0].get("state") != "ACTIVE"):
        raise ProvisionError("project ID must resolve to the active AAO Self Development project")
    project_path = quote(project_id, safe="")
    role_uids = [pwd.getpwnam(account).pw_uid for account in ACCOUNTS]
    if len(set(role_uids)) != len(ACCOUNTS) or os.getuid() in role_uids:
        raise ProvisionError("publisher roles must map to distinct non-CEO Linux accounts")
    for account in ACCOUNTS:
        _run_role_helper(account, api_python=api_python, token=None, operation="check")

    stamp = datetime.now(UTC)
    expiry = (stamp + timedelta(hours=8)).isoformat()
    nonce = uuid4().hex[:8]
    issued: list[tuple[str, str, str]] = []
    try:
        for role, account in (("impl", ACCOUNTS[0]), ("pm", ACCOUNTS[1])):
            principal = f"aao-publisher-{role}-{stamp:%Y%m%d%H%M%S}-{nonce}"
            issued.append((account, principal, ""))
            credential = request_json(
                api_url, "/v1/principals/credentials", method="POST", ceo_token=ceo_token,
                body={"principal_id": principal, "kind": "AGENT"},
            )
            token = credential.get("token") if isinstance(credential, dict) else None
            if (not isinstance(token, str) or not token
                    or credential.get("principal_id") != principal
                    or credential.get("kind") != "AGENT"):
                raise ProvisionError("AAO returned an invalid publisher credential")
            issued[-1] = (account, principal, token)
            for grant in GRANTS:
                request_json(
                    api_url, f"/v1/projects/{project_path}/grants", method="POST",
                    ceo_token=ceo_token,
                    body={"principal_id": principal, "capability": grant, "expires_at": expiry},
                )
            grant_rows = request_json(api_url, f"/v1/projects/{project_path}/grants", ceo_token=ceo_token)
            if not isinstance(grant_rows, list):
                raise ProvisionError("project grant inventory response is invalid")
            scoped = [row for row in grant_rows if row.get("principal_id") == principal]
            actual_caps = {row.get("capability") for row in scoped}
            actual_expiries = {row.get("expires_at") for row in scoped}
            if (actual_caps != set(GRANTS) or len(scoped) != len(GRANTS)
                    or any(row.get("kind") != "AGENT" or not row.get("credential_enabled") for row in scoped)
                    or len(actual_expiries) != 1):
                raise ProvisionError("could not verify the exact least-privilege publisher grants")
            try:
                actual_expiry = datetime.fromisoformat(next(iter(actual_expiries)))
            except (TypeError, ValueError):
                raise ProvisionError("could not verify publisher grant expiry") from None
            if actual_expiry.astimezone(UTC) != datetime.fromisoformat(expiry):
                raise ProvisionError("publisher grant expiry differs from the requested eight-hour limit")
            _run_role_helper(account, api_python=api_python, token=token, operation="install")
            _run_role_helper(account, api_python=api_python, token=token, operation="verify")
        return [(account, principal, expiry) for account, principal, _ in issued]
    except (BootstrapError, ProvisionError, OSError, ValueError) as exc:
        for account, _principal, token in reversed(issued):
            if not token:
                continue
            try:
                _run_role_helper(account, api_python=api_python, token=token, operation="remove")
            except ProvisionError:
                pass
        for _account, principal, _token in reversed(issued):
            try:
                request_json(api_url, f"/v1/principals/{quote(principal, safe='')}/revoke",
                             method="POST", ceo_token=ceo_token, body={})
            except BootstrapError:
                pass
        if isinstance(exc, ProvisionError):
            raise
        raise ProvisionError("publisher credential setup failed; issued credentials were revoked where possible") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--api", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))
    parser.add_argument("--python", default=sys.executable,
                        help="Python executable accessible to both role accounts")
    args = parser.parse_args()
    try:
        api_url = local_api_url(args.api)
        ceo_token = getpass.getpass("CEO token (input hidden): ")
        result = provision(args.project_id, api_url=api_url, ceo_token=ceo_token,
                           api_python=args.python)
    except (ProvisionError, BootstrapError, OSError, KeyError) as exc:
        print(f"Publisher provisioning did not complete: {exc}", file=sys.stderr)
        return 1
    print("W2 publisher credentials provisioned separately:")
    for account, principal, expiry in result:
        print(f"- account={account} principal={principal} grants={','.join(GRANTS)} expires={expiry}")
    print("Tokens were not displayed; each target file was verified mode 0600.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
