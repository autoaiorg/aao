#!/usr/bin/env python3
"""Request the fixed, short-lived Self Development cycle role pair as aao-pm.

The script uses the existing PM coordinator token. The CEO must first grant
``credential.issue_selfdev_cycle_roles`` to that PM principal for the Self
Development project. Tokens are delivered only to the role-owned runtime
installers on stdin and are never printed or placed in argv/environment.
"""

from __future__ import annotations

import argparse
import os
import pwd
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provision_w2_publishers as common
from bootstrap_self_dev_agent import BootstrapError
from provision_w2_publishers import ProvisionError, local_api_url

PM_ACCOUNT = "aao-pm"
ROLES = (
    ("aao-impl-codex", "selfdev-implementer", "AGENT"),
    ("aao-auditor", "selfdev-reviewer", "AUDITOR"),
)
ROLE_GRANTS = (
    {
        "project.read",
        "work.create",
        "work.admit",
        "work.progress",
        "execution.claim",
        "code.propose",
        "evidence.submit",
    },
    {"work.review"},
)
MAX_LIFETIME_SECONDS = 2 * 60 * 60


def read_pm_token() -> str:
    entry = pwd.getpwnam(PM_ACCOUNT)
    if os.getuid() != entry.pw_uid:
        raise ProvisionError("this provisioner must run as the aao-pm Linux account")
    path = Path(f"/run/user/{entry.pw_uid}/aao-pm.token")
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != entry.pw_uid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise ProvisionError("PM token file must be a regular aao-pm-owned mode-0600 file")
        token = path.read_text(encoding="utf-8")
    except OSError:
        raise ProvisionError("PM token file is unavailable") from None
    token = token.rstrip("\n")
    if not token or "\n" in token or "\r" in token:
        raise ProvisionError("PM token file has invalid content")
    return token


def _call(api: str, path: str, *, token: str, method: str = "GET", body=None):
    return common.request_json(api, path, method=method, agent_token=token, body=body)


def provision(
    project_id: str,
    *,
    api_url: str,
    lifetime_seconds: int = MAX_LIFETIME_SECONDS,
    api_python: str = sys.executable,
    token: str | None = None,
):
    """Issue, install and verify the fixed pair; revoke the known cycle on failure."""
    if not isinstance(lifetime_seconds, int) or not 1 <= lifetime_seconds <= MAX_LIFETIME_SECONDS:
        raise ProvisionError("lifetime must be between 1 second and 2 hours")
    api = local_api_url(api_url)
    pm_token = read_pm_token() if token is None else token
    if not pm_token:
        raise ProvisionError("PM token is required")
    installer = common.INSTALLER
    if not installer.is_file() or installer.is_symlink():
        raise ProvisionError("role-token installer is missing or unsafe")
    for account, token_kind, _kind in ROLES:
        common._run_role_helper(
            account, api_python=api_python, token=None, operation="check", token_kind=token_kind
        )

    cycle_id = uuid4().hex
    project_path = quote(project_id, safe="")
    installed: list[tuple[str, str, str]] = []
    try:
        result = _call(
            api,
            f"/v1/projects/{project_path}/selfdev-cycle-roles",
            token=pm_token,
            method="POST",
            body={"cycle_id": cycle_id, "lifetime_seconds": lifetime_seconds},
        )
        if (
            not isinstance(result, dict)
            or result.get("cycle_id") != cycle_id
            or result.get("project_id") != project_id
            or not isinstance(result.get("roles"), list)
            or len(result["roles"]) != len(ROLES)
        ):
            raise ProvisionError("AAO returned an invalid cycle role response")
        expires_at = result.get("expires_at")
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry.tzinfo is None or expiry.utcoffset() is None:
                raise ValueError
            expiry = expiry.astimezone(UTC)
            if expiry <= datetime.now(UTC) or expiry > datetime.now(UTC) + timedelta(
                seconds=lifetime_seconds + 5
            ):
                raise ValueError
        except (TypeError, ValueError):
            raise ProvisionError("AAO returned an invalid cycle expiry") from None
        roles = result["roles"]
        expected_ids = (f"aao-selfdev-impl-{cycle_id}", f"aao-selfdev-review-{cycle_id}")
        for record, (account, token_kind, kind), allowed_grants, expected_id in zip(
            roles, ROLES, ROLE_GRANTS, expected_ids, strict=True
        ):
            if (
                not isinstance(record, dict)
                or record.get("kind") != kind
                or record.get("principal_id") != expected_id
                or not isinstance(record.get("token"), str)
                or not record["token"]
                or not isinstance(record.get("grants"), list)
                or set(record["grants"]) != allowed_grants
            ):
                raise ProvisionError("AAO returned an invalid cycle role")
            installed.append((account, token_kind, record["token"]))
            common._run_role_helper(
                account,
                api_python=api_python,
                token=record["token"],
                operation="install",
                token_kind=token_kind,
            )
            common._run_role_helper(
                account,
                api_python=api_python,
                token=record["token"],
                operation="verify",
                token_kind=token_kind,
            )
        return cycle_id, expires_at, [r["principal_id"] for r in roles]
    except BaseException as exc:
        failures = []
        for account, token_kind, role_token in reversed(installed):
            try:
                common._run_role_helper(
                    account,
                    api_python=api_python,
                    token=role_token,
                    operation="remove",
                    token_kind=token_kind,
                )
            except Exception:  # noqa: BLE001
                failures.append(f"token file for {account} was not removed")
        try:
            _call(
                api,
                f"/v1/projects/{project_path}/selfdev-cycle-roles/{cycle_id}",
                token=pm_token,
                method="DELETE",
            )
        except Exception:  # noqa: BLE001
            failures.append(f"cycle {cycle_id} was NOT revoked")
        if isinstance(exc, Exception):
            detail = (
                "; CLEANUP INCOMPLETE: " + "; ".join(failures) if failures else "; cycle revoked"
            )
            reason = str(exc) if isinstance(exc, ProvisionError) else "role setup failed"
            raise ProvisionError(reason + detail) from None
        if failures:
            print("CLEANUP INCOMPLETE: " + "; ".join(failures), file=sys.stderr)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--lifetime-seconds", type=int, default=MAX_LIFETIME_SECONDS)
    parser.add_argument("--api", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    try:
        cycle_id, expires_at, principals = provision(
            args.project_id,
            api_url=args.api,
            lifetime_seconds=args.lifetime_seconds,
            api_python=args.python,
        )
    except (ProvisionError, BootstrapError, OSError, KeyError) as exc:
        print(f"Self Development cycle provisioning did not complete: {exc}", file=sys.stderr)
        return 1
    print(f"Self Development cycle issued: cycle_id={cycle_id} expires_at={expires_at}")
    print("Role principals: " + ",".join(principals))
    print("Tokens were not displayed; each role-owned runtime file was verified mode 0600.")
    print("The reviewer is an API lifecycle reviewer, not an independent GOV-REV-001 auditor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
