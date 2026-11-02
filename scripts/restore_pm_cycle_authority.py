#!/usr/bin/env python3
"""Restore the existing PM credential and grant its scoped cycle-issuer authority.

The CEO token is read without echo. This command does not create a second PM
principal: it grants the existing PM identity the bounded Self Development
issuer capability, rotates that identity's token, and installs the new token
through the role-owned installer on stdin.
"""

from __future__ import annotations

import argparse
import getpass
import os
import pwd
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provision_w2_publishers as common
from bootstrap_self_dev_agent import BootstrapError
from provision_w2_publishers import ProvisionError, local_api_url

PM_ACCOUNT = "aao-pm"
PM_PREFIX = "aao-pm-coordinator-"
PROJECT_NAME = "AAO — Self Development"
BASE_GRANTS = {"project.read", "work.coordinate", "work.assign"}
ISSUER_GRANT = "credential.issue_selfdev_cycle_roles"
MAX_GRANT_TTL = timedelta(days=30)
ROLE_PYTHON = Path("/usr/bin/python3")
ROLE_INSTALLER = Path("/usr/local/libexec/aao/install_publisher_token_for_role.py")
SUDO = Path("/usr/bin/sudo")


def _role_helper(account: str, *, token: str | None, operation: str) -> None:
    """Run the fixed, root-installed token installer as the PM account."""
    try:
        for path in (SUDO, ROLE_PYTHON, ROLE_INSTALLER):
            resolved = path.resolve(strict=True)
            info = resolved.stat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                raise ProvisionError("installed PM token helper is not root-owned and immutable")
            for parent in resolved.parents:
                parent_info = parent.stat()
                if parent_info.st_uid != 0 or stat.S_IMODE(parent_info.st_mode) & 0o022:
                    raise ProvisionError("installed PM token helper path is not root-secure")
        entry = pwd.getpwnam(account)
        command = [
            str(SUDO),
            "-u",
            account,
            "-H",
            "env",
            f"XDG_RUNTIME_DIR=/run/user/{entry.pw_uid}",
            str(ROLE_PYTHON),
            str(ROLE_INSTALLER),
            "--account",
            account,
            "--token",
            "pm",
        ]
        if operation != "install":
            command.append(f"--{operation}")
        subprocess.run(
            command,
            input=None if token is None else token + "\n",
            text=True,
            check=True,
            timeout=120,
        )
    except ProvisionError:
        raise
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyError):
        raise ProvisionError(f"role token helper failed for {account} ({operation})") from None


def _rows(value: object, label: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ProvisionError(f"{label} response is invalid")
    return value


def _utc_expiry(value: str) -> datetime:
    try:
        expiry = datetime.fromisoformat(value)
    except ValueError:
        raise ProvisionError("grant expiry must be ISO-8601 with a timezone") from None
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ProvisionError("grant expiry must be ISO-8601 with a timezone")
    expiry = expiry.astimezone(UTC)
    now = datetime.now(UTC)
    if expiry <= now or expiry > now + MAX_GRANT_TTL:
        raise ProvisionError(
            "issuer grant expiry must be in the future and no more than 30 days away"
        )
    return expiry


def _parse_utc_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _validated_rotation(value: object, principal_id: str) -> str:
    if (
        not isinstance(value, dict)
        or value.get("principal_id") != principal_id
        or value.get("kind") != "AGENT"
        or not isinstance(value.get("token"), str)
        or not value["token"]
    ):
        raise ProvisionError("API returned an invalid rotated PM credential")
    return value["token"]


def restore(
    project_id: str,
    principal_id: str,
    *,
    api_url: str,
    ceo_token: str,
    grant_expiry: str,
) -> tuple[str, datetime]:
    """Grant bounded PM authority and rotate/install its token without exposing it."""
    api = local_api_url(api_url)
    expiry = _utc_expiry(grant_expiry)
    if not principal_id.startswith(PM_PREFIX):
        raise ProvisionError("principal ID is not an AAO PM coordinator identity")
    pm_uid = pwd.getpwnam(PM_ACCOUNT).pw_uid
    if pm_uid == os.getuid():
        raise ProvisionError("aao-pm must be distinct from the CEO invoker")

    project_rows = _rows(
        common.request_json(api, "/v1/projects", ceo_token=ceo_token), "project inventory"
    )
    projects = [row for row in project_rows if str(row.get("id")) == project_id]
    if (
        len(projects) != 1
        or projects[0].get("name") != PROJECT_NAME
        or projects[0].get("state") != "ACTIVE"
    ):
        raise ProvisionError("project must be the unique active AAO Self Development project")

    project_path = quote(project_id, safe="")
    grant_path = f"/v1/projects/{project_path}/grants"
    grant_rows = _rows(common.request_json(api, grant_path, ceo_token=ceo_token), "grant inventory")
    pm_rows = [row for row in grant_rows if row.get("principal_id") == principal_id]
    if not pm_rows or any(
        row.get("kind") != "AGENT" or not row.get("credential_enabled") for row in pm_rows
    ):
        raise ProvisionError("existing PM principal must be enabled and AGENT")
    caps = [row.get("capability") for row in pm_rows]
    if len(caps) != len(set(caps)) or not BASE_GRANTS.issubset(set(caps)):
        raise ProvisionError(
            "existing PM principal is missing required base grants or has duplicate grants"
        )
    if set(caps) - BASE_GRANTS - {ISSUER_GRANT}:
        raise ProvisionError(
            "existing PM principal has unexpected project grants; refusing to broaden it"
        )

    issuer_rows = [row for row in pm_rows if row.get("capability") == ISSUER_GRANT]
    needs_grant = not issuer_rows
    grant_created_by_us = False
    if issuer_rows:
        existing_expiry = _parse_utc_datetime(issuer_rows[0].get("expires_at"))
        if existing_expiry is None:
            raise ProvisionError("existing issuer grant has invalid expiry") from None
        now = datetime.now(UTC)
        if existing_expiry <= now or existing_expiry > now + MAX_GRANT_TTL:
            raise ProvisionError("existing issuer grant is expired or exceeds the 30-day limit")
        expiry = existing_expiry

    # Refuse to rotate if the token destination is already occupied.
    _role_helper(PM_ACCOUNT, token=None, operation="check")

    rotated_token: str | None = None
    rotation_attempted = False
    install_attempted = False
    grant_request_attempted = False
    try:
        if needs_grant:
            grant_request_attempted = True
            grant_result = common.request_json(
                api,
                grant_path,
                method="POST",
                ceo_token=ceo_token,
                body={
                    "principal_id": principal_id,
                    "capability": ISSUER_GRANT,
                    "expires_at": expiry.isoformat(),
                },
            )
            if not isinstance(grant_result, dict) or grant_result.get("created") is not True:
                raise ProvisionError("issuer grant was not newly created; refusing to rotate PM")
            grant_created_by_us = True
        verified_rows = _rows(
            common.request_json(api, grant_path, ceo_token=ceo_token), "grant inventory"
        )
        scoped = [row for row in verified_rows if row.get("principal_id") == principal_id]
        verified_caps = {row.get("capability") for row in scoped}
        issuer = [row for row in scoped if row.get("capability") == ISSUER_GRANT]
        if (
            verified_caps != BASE_GRANTS | {ISSUER_GRANT}
            or len(scoped) != len(verified_caps)
            or len(issuer) != 1
            or issuer[0].get("kind") != "AGENT"
            or not issuer[0].get("credential_enabled")
        ):
            raise ProvisionError("could not verify the exact least-privilege PM grant set")
        observed_expiry = _parse_utc_datetime(issuer[0].get("expires_at"))
        if observed_expiry is None:
            raise ProvisionError("could not verify issuer grant expiry") from None
        if observed_expiry != expiry:
            raise ProvisionError("issuer grant expiry differs from the requested expiry")

        rotation_attempted = True
        rotated = common.request_json(
            api,
            f"/v1/principals/{quote(principal_id, safe='')}/rotate",
            method="POST",
            ceo_token=ceo_token,
            body={},
        )
        rotated_token = _validated_rotation(rotated, principal_id)
        install_attempted = True
        _role_helper(PM_ACCOUNT, token=rotated_token, operation="install")
        _role_helper(PM_ACCOUNT, token=rotated_token, operation="verify")
        return principal_id, expiry
    except BaseException as exc:
        cleanup_failures: list[str] = []
        if grant_request_attempted and not grant_created_by_us:
            # A timeout can happen after the API transaction committed. Reconcile
            # against the exact expiry before attempting cleanup; never guess from
            # the HTTP exception alone.
            try:
                current_rows = _rows(
                    common.request_json(api, grant_path, ceo_token=ceo_token),
                    "grant reconciliation",
                )
                matching = [
                    row
                    for row in current_rows
                    if row.get("principal_id") == principal_id
                    and row.get("capability") == ISSUER_GRANT
                ]
                observed_expiry = (
                    _parse_utc_datetime(matching[0].get("expires_at"))
                    if len(matching) == 1
                    else None
                )
                if len(matching) == 1 and observed_expiry == expiry:
                    grant_created_by_us = True
                elif matching:
                    cleanup_failures.append(
                        "issuer grant state differs from this attempt; inspect and revoke explicitly"
                    )
            except Exception:  # noqa: BLE001 - preserve uncertainty rather than mask original error
                cleanup_failures.append(
                    "could not reconcile issuer grant after ambiguous API result"
                )
        if install_attempted and rotated_token is not None:
            try:
                _role_helper(PM_ACCOUNT, token=rotated_token, operation="remove")
            except Exception:  # noqa: BLE001 - report incomplete recovery
                cleanup_failures.append("matching PM token file was not removed")
        if rotation_attempted:
            # A lost API response may still have rotated the credential. Rotate
            # again and attempt installation; failures are surfaced for operator recovery.
            try:
                recovery = common.request_json(
                    api,
                    f"/v1/principals/{quote(principal_id, safe='')}/rotate",
                    method="POST",
                    ceo_token=ceo_token,
                    body={},
                )
                recovery_token = _validated_rotation(recovery, principal_id)
                try:
                    _role_helper(PM_ACCOUNT, token=recovery_token, operation="install")
                    _role_helper(PM_ACCOUNT, token=recovery_token, operation="verify")
                except Exception:  # noqa: BLE001 - report incomplete recovery
                    try:
                        _role_helper(PM_ACCOUNT, token=recovery_token, operation="remove")
                    except Exception:  # noqa: BLE001 - surface a potentially partial file
                        cleanup_failures.append("possible partial PM recovery token file remains")
                    cleanup_failures.append(
                        "PM recovery credential may be active but was not verified; CEO must rotate and reinstall"
                    )
            except Exception:  # noqa: BLE001 - report incomplete recovery
                cleanup_failures.append(
                    "PM credential state uncertain; manual CEO rotation required"
                )
        if grant_created_by_us:
            try:
                common.request_json(
                    api,
                    f"{grant_path}/{quote(principal_id, safe='')}/{ISSUER_GRANT}",
                    method="DELETE",
                    ceo_token=ceo_token,
                )
            except Exception:  # noqa: BLE001 - report incomplete recovery
                cleanup_failures.append("temporary issuer grant was not revoked")
        if not isinstance(exc, Exception):
            if cleanup_failures:
                print("RECOVERY INCOMPLETE: " + "; ".join(cleanup_failures), file=sys.stderr)
            raise
        reason = str(exc) if isinstance(exc, ProvisionError) else "PM authority restoration failed"
        suffix = "; recovery incomplete: " + "; ".join(cleanup_failures) if cleanup_failures else ""
        raise ProvisionError(reason + suffix) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--api", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))
    parser.add_argument(
        "--grant-days",
        type=int,
        default=30,
        help="issuer grant lifetime in days (1..30; default 30)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.grant_days <= 30:
        parser.error("--grant-days must be between 1 and 30")
    expiry = (datetime.now(UTC) + timedelta(days=args.grant_days)).isoformat()
    try:
        api = local_api_url(args.api)
        print(f"PM issuer grant will expire at {expiry}")
        ceo_token = getpass.getpass("CEO token (input hidden): ")
        principal, final_expiry = restore(
            args.project_id,
            args.principal_id,
            api_url=api,
            ceo_token=ceo_token,
            grant_expiry=expiry,
        )
    except (ProvisionError, BootstrapError, OSError, KeyError) as exc:
        print(f"PM authority restoration did not complete: {exc}", file=sys.stderr)
        return 1
    print(f"PM authority restored: principal={principal} expires={final_expiry.isoformat()}")
    print("The existing principal was rotated and the token installed; token was not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
