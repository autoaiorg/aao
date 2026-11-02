#!/usr/bin/env python3
"""Provision short-lived Self Development lifecycle implementer and reviewer roles.

This creates only AGENT lifecycle capabilities and a distinct AUDITOR work.review
identity. It does not issue code.publish or claim GOV-REV-001 independence.
Tokens travel only via stdin to each role-owned runtime installer.
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
from urllib.parse import quote
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provision_w2_publishers as common
from bootstrap_self_dev_agent import BootstrapError
from provision_w2_publishers import ProvisionError

PROJECT_NAME = "AAO — Self Development"
IMPLEMENTER = "aao-impl-codex"
REVIEWER = "aao-auditor"
ROLES = (
    (
        IMPLEMENTER,
        "selfdev-implementer",
        "AGENT",
        (
            "project.read",
            "work.create",
            "work.admit",
            "work.progress",
            "execution.claim",
            "code.propose",
            "evidence.submit",
        ),
    ),
    (REVIEWER, "selfdev-reviewer", "AUDITOR", ("work.review",)),
)
MAX_LIFETIME = timedelta(hours=2)
FROZEN_WRAPPER = "/usr/local/libexec/aao/selfdev_role_token_helper.py"


def parse_expiry(value: str) -> str:
    try:
        expiry = datetime.fromisoformat(value)
    except ValueError:
        raise ProvisionError("--expires-at must be an ISO-8601 timestamp") from None
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ProvisionError("--expires-at must include a timezone")
    now = datetime.now(UTC)
    expiry = expiry.astimezone(UTC)
    if expiry <= now or expiry > now + MAX_LIFETIME:
        raise ProvisionError("expiry must be in the future and no more than 2 hours away")
    return expiry.isoformat()


def _issue(api: str, principal: str, kind: str, ceo_token: str) -> str:
    row = common.request_json(
        api,
        "/v1/principals/credentials",
        method="POST",
        ceo_token=ceo_token,
        body={"principal_id": principal, "kind": kind},
    )
    if (
        not isinstance(row, dict)
        or row.get("principal_id") != principal
        or row.get("kind") != kind
        or not isinstance(row.get("token"), str)
        or not row["token"]
    ):
        raise ProvisionError("AAO returned an invalid role credential")
    return row["token"]


def _grant_and_verify(
    api: str,
    project: str,
    principal: str,
    kind: str,
    grants: tuple[str, ...],
    expiry: str,
    ceo_token: str,
) -> None:
    for capability in grants:
        common.request_json(
            api,
            f"/v1/projects/{project}/grants",
            method="POST",
            ceo_token=ceo_token,
            body={"principal_id": principal, "capability": capability, "expires_at": expiry},
        )
    rows = common._rows(
        common.request_json(api, f"/v1/projects/{project}/grants", ceo_token=ceo_token),
        "grant inventory",
    )
    scoped = [r for r in rows if r.get("principal_id") == principal]
    try:
        observed_values = [datetime.fromisoformat(r["expires_at"]) for r in scoped]
        if any(value.tzinfo is None or value.utcoffset() is None for value in observed_values):
            raise ValueError("timezone missing")
        observed_expiry = {value.astimezone(UTC) for value in observed_values}
        expected_expiry = datetime.fromisoformat(expiry).astimezone(UTC)
    except (TypeError, ValueError, KeyError):
        raise ProvisionError(f"could not verify expiry for {principal}") from None
    if (
        len(scoped) != len(grants)
        or {r.get("capability") for r in scoped} != set(grants)
        or any(r.get("kind") != kind or r.get("credential_enabled") is not True for r in scoped)
        or observed_expiry != {expected_expiry}
    ):
        raise ProvisionError(f"could not verify exact {kind} grants and expiry for {principal}")


def _run_token_helper(account: str, token_kind: str, operation: str, token: str | None = None) -> None:
    """Use only the root-owned frozen wrapper; never choose an interpreter at runtime."""
    if account not in {IMPLEMENTER, REVIEWER}:
        raise ProvisionError("unsupported role account")
    if token_kind not in {"selfdev-implementer", "selfdev-reviewer"}:
        raise ProvisionError("unsupported token kind")
    if operation not in {"check", "install", "verify", "remove"}:
        raise ProvisionError("unsupported token operation")
    command = [
        "/usr/bin/sudo", FROZEN_WRAPPER,
        "--account", account, "--token", token_kind, "--operation", operation,
    ]
    try:
        result = subprocess.run(
            command, input=(token + "\n") if token is not None else "", text=True,
            capture_output=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ProvisionError("fixed role-token wrapper could not be run") from None
    if result.returncode:
        # Helper output is intentionally not propagated: it must never echo token material.
        raise ProvisionError(f"fixed role-token helper failed for {account}/{operation}")


def provision(project_id: str, *, api_url: str, ceo_token: str, expiry: str):
    api = common.local_api_url(api_url)
    expiry = parse_expiry(expiry)
    if not common.INSTALLER.is_file() or common.INSTALLER.is_symlink():
        raise ProvisionError("role-token installer is missing or unsafe")
    projects = common._rows(
        common.request_json(api, "/v1/projects", ceo_token=ceo_token), "project inventory"
    )
    matches = [p for p in projects if str(p.get("id")) == project_id]
    if (
        len(matches) != 1
        or matches[0].get("name") != PROJECT_NAME
        or matches[0].get("state") != "ACTIVE"
    ):
        raise ProvisionError("project ID must resolve to the active AAO Self Development project")
    uids = [pwd.getpwnam(account).pw_uid for account, *_ in ROLES]
    if len(set(uids)) != len(uids) or os.getuid() in uids:
        raise ProvisionError("implementer, reviewer and CEO must be distinct Linux identities")
    for account, token_kind, _kind, _grants in ROLES:
        _run_token_helper(account, token_kind, "check")

    project = quote(project_id, safe="")
    stamp = datetime.now(UTC)
    suffix = f"{stamp:%Y%m%d%H%M%S}-{uuid4().hex[:8]}"
    issued: list[tuple[str, str, str, str]] = []
    try:
        for account, token_kind, kind, grants in ROLES:
            slug = "impl" if kind == "AGENT" else "review"
            principal = f"aao-selfdev-{slug}-{suffix}"
            issued.append((account, token_kind, principal, ""))
            token = _issue(api, principal, kind, ceo_token)
            issued[-1] = (account, token_kind, principal, token)
            _grant_and_verify(api, project, principal, kind, grants, expiry, ceo_token)
            for operation in ("install", "verify"):
                _run_token_helper(account, token_kind, operation, token)
        return [
            (account, principal, kind, grants, expiry)
            for (account, _token_kind, principal, _token), (_a, _k, kind, grants) in zip(
                issued, ROLES, strict=True
            )
        ]
    except BaseException as exc:
        cleanup_failures: list[str] = []
        for account, token_kind, principal, token in reversed(issued):
            if token:
                try:
                    _run_token_helper(account, token_kind, "remove", token)
                except Exception:  # noqa: BLE001
                    cleanup_failures.append(f"token file for {account} was not removed")
            try:
                common.request_json(
                    api,
                    f"/v1/principals/{quote(principal, safe='')}/revoke",
                    method="POST",
                    ceo_token=ceo_token,
                    body={},
                )
            except Exception:  # noqa: BLE001
                cleanup_failures.append(f"principal {principal} was NOT revoked")
        if isinstance(exc, Exception):
            note = (
                "; CLEANUP INCOMPLETE: " + "; ".join(cleanup_failures)
                if cleanup_failures
                else "; issued credentials revoked"
            )
            reason = str(exc) if isinstance(exc, ProvisionError) else "role setup failed"
            raise ProvisionError(reason + note) from None
        if cleanup_failures:
            print("CLEANUP INCOMPLETE: " + "; ".join(cleanup_failures), file=sys.stderr)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--expires-at", required=True, help="timezone-aware ISO-8601 expiry, at most 2 hours away"
    )
    parser.add_argument("--api", default=os.environ.get("AAO_API", "http://127.0.0.1:8001"))
    args = parser.parse_args(argv)
    try:
        expiry = parse_expiry(args.expires_at)
        result = provision(
            args.project_id,
            api_url=args.api,
            ceo_token=getpass.getpass("CEO token (input hidden): "),
            expiry=expiry,
        )
    except (ProvisionError, BootstrapError, OSError, KeyError) as exc:
        print(f"Self Development role provisioning did not complete: {exc}", file=sys.stderr)
        return 1
    for account, principal, kind, grants, expires in result:
        print(
            f"Provisioned role={kind} account={account} principal={principal} "
            f"grants={','.join(grants)} expires={expires}"
        )
    print("Credentials were not displayed; each role-owned runtime file was verified mode 0600.")
    print("AUDITOR work.review is an API lifecycle review, not GOV-REV-001 independent audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
