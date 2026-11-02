#!/usr/bin/env python3
"""Rotate an existing W2 publisher principal for this Linux role.

This helper only rotates an already-issued principal. It cannot create or issue
new publisher principals.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_self_dev_agent import BootstrapError, request_json

ACCOUNTS = {"aao-pm", "aao-impl-codex"}
TOKEN_NAME = "aao-publisher.token"


class RotationError(RuntimeError):
    pass


def _loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RotationError("rotation API must be a credential-free loopback URL")
    return value.rstrip("/")


def _paths(account: str) -> tuple[Path, Path]:
    if account not in ACCOUNTS:
        raise RotationError("unsupported W2 account")
    entry = pwd.getpwnam(account)
    if os.geteuid() != entry.pw_uid:
        raise RotationError("rotation must run as the target account")
    runtime = Path(f"/run/user/{entry.pw_uid}")
    try:
        info = runtime.lstat()
    except OSError:
        raise RotationError("target runtime directory unavailable") from None
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != entry.pw_uid
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RotationError("target runtime directory ownership or mode is unsafe")
    return runtime / TOKEN_NAME, runtime / f".{TOKEN_NAME}.pending"


def _read_private(path: Path) -> str:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(fd)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            token = stream.read(4097)
    except (OSError, UnicodeError):
        raise RotationError("publisher token file is unavailable") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or len(token) > 4096
        or not token.endswith("\n")
        or token.count("\n") != 1
    ):
        raise RotationError("publisher token file metadata or contents are unsafe")
    return token[:-1]


def _write_pending(path: Path, token: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def _write_pending_identity(path: Path, account: str, principal_id: str) -> None:
    metadata = path.with_name(path.name + ".identity")
    payload = json.dumps({"account": account, "principal_id": principal_id}) + "\n"
    fd = os.open(
        metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        metadata.unlink(missing_ok=True)
        raise
    _fsync_dir(metadata.parent)


def _read_pending_identity(path: Path, account: str) -> str:
    metadata = path.with_name(path.name + ".identity")
    try:
        fd = os.open(metadata, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(fd)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RotationError("pending identity metadata unavailable") from None
    principal_id = value.get("principal_id") if isinstance(value, dict) else None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or not isinstance(principal_id, str)
        or value.get("account") != account
        or not principal_id.startswith(_expected_prefix(account))
    ):
        raise RotationError("pending identity metadata does not match this W2 account")
    return principal_id


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise RotationError(f"invalid {label} response")
    return value


def _request(
    api: str, path: str, *, token: str, method: str = "GET", body: dict | None = None
) -> dict:
    try:
        return _object(
            request_json(api, path, method=method, agent_token=token, body=body), "AAO API"
        )
    except BootstrapError:
        raise RotationError("AAO API request failed; credential material withheld") from None


def _request_grants(api: str, token: str) -> list:
    try:
        value = request_json(api, "/v1/principals/me/grants", agent_token=token)
    except BootstrapError:
        raise RotationError("AAO API request failed; credential material withheld") from None
    if not isinstance(value, list):
        raise RotationError("invalid AAO grant response")
    return value


def _request_projects(api: str, token: str) -> list:
    try:
        value = request_json(api, "/v1/projects", agent_token=token)
    except BootstrapError:
        raise RotationError("AAO API request failed; credential material withheld") from None
    if not isinstance(value, list):
        raise RotationError("invalid AAO project response")
    return value


def _expected_prefix(account: str) -> str:
    return "aao-publisher-pm-" if account == "aao-pm" else "aao-publisher-impl-"


def _validate_w2_identity(api: str, token: str, account: str) -> str:
    """Require the token to identify an active publisher for this exact role."""
    me = _request(api, "/v1/principals/me", token=token)
    principal_id = me.get("principal_id")
    if (
        me.get("kind") != "AGENT"
        or me.get("enabled") is not True
        or not isinstance(principal_id, str)
        or not principal_id.startswith(_expected_prefix(account))
    ):
        raise RotationError("credential does not belong to this W2 account")

    grants = _request_grants(api, token)
    expected = {"project.read", "code.publish"}
    if (
        not isinstance(grants, list)
        or len(grants) != 2
        or {grant.get("capability") for grant in grants if isinstance(grant, dict)} != expected
        or any(
            not isinstance(grant, dict)
            or grant.get("principal_id") != principal_id
            or grant.get("active") is not True
            or not grant.get("project_id")
            or not grant.get("expires_at")
            for grant in grants
        )
        or len({grant.get("project_id") for grant in grants if isinstance(grant, dict)}) != 1
    ):
        raise RotationError("credential does not have the exact active W2 grant set")
    project_id = grants[0]["project_id"]
    projects = _request_projects(api, token)
    if (
        len(projects) != 1
        or not isinstance(projects[0], dict)
        or str(projects[0].get("id")) != str(project_id)
        or projects[0].get("name") != "AAO — Self Development"
        or projects[0].get("state") != "ACTIVE"
    ):
        raise RotationError("credential is not scoped to the active Self Development project")
    return principal_id


def rotate(account: str, api_url: str = "http://127.0.0.1:8001") -> None:
    api = _loopback_url(api_url)
    live, pending = _paths(account)
    old = _read_private(live)

    # Recover safely if an earlier run confirmed the new token but died before
    # replacing the live path. The target itself, not the PM, authenticates it.
    if pending.exists() or pending.is_symlink():
        staged = _read_private(pending)
        expected_principal = _read_pending_identity(pending, account)
        try:
            staged_me = _request(api, "/v1/principals/me", token=staged)
        except RotationError:
            # A token which is not yet active can only be used at confirm.
            staged_me = None
        if staged_me is not None:
            # An already-active token must be the exact principal recorded
            # before rotation; never confirm a different active principal.
            if staged_me.get("principal_id") != expected_principal:
                raise RotationError("pending token belongs to another W2 principal")
            staged_principal = _validate_w2_identity(api, staged, account)
            if staged_principal != expected_principal:
                raise RotationError("pending token belongs to another W2 principal")
            os.replace(pending, live)
            pending.with_name(pending.name + ".identity").unlink(missing_ok=True)
            _fsync_dir(live.parent)
            return
        # Only a token which did not authenticate as an active identity reaches
        # confirm. The response is still bound to the exact pre-rotation ID.
        try:
            confirmed = _request(
                api,
                "/v1/principals/me/w2-publisher/rotate/confirm",
                token=staged,
                method="POST",
                body={"expected_principal_id": expected_principal},
            )
            if (
                confirmed.get("rotated") is not True
                or confirmed.get("principal_id") != expected_principal
            ):
                raise RotationError("AAO rejected pending-token recovery")
            os.replace(pending, live)
            pending.with_name(pending.name + ".identity").unlink(missing_ok=True)
            _fsync_dir(live.parent)
            return
        except RotationError:
            # A 403 from an expired pending token is recoverable only if the old
            # bearer still authenticates. If the API is unavailable, retain the
            # staged token and fail closed rather than guessing.
            try:
                old_principal = _validate_w2_identity(api, old, account)
            except RotationError:
                raise RotationError(
                    "pending rotation recovery failed; staged file retained"
                ) from None
            if old_principal != expected_principal:
                raise RotationError("pending rotation belongs to another W2 principal")
            pending.unlink()
            pending.with_name(pending.name + ".identity").unlink(missing_ok=True)
            _fsync_dir(live.parent)

    principal_id = _validate_w2_identity(api, old, account)
    staged_response = _request(
        api,
        "/v1/principals/me/w2-publisher/rotate",
        token=old,
        method="POST",
    )
    new_token = staged_response.get("token")
    if (
        staged_response.get("principal_id") != principal_id
        or staged_response.get("account") != account
        or not isinstance(new_token, str)
        or not new_token
        or any(c.isspace() for c in new_token)
    ):
        raise RotationError("AAO returned an invalid pending rotation")
    _write_pending(pending, new_token)
    try:
        _write_pending_identity(pending, account, principal_id)
    except BaseException:
        pending.unlink(missing_ok=True)
        _fsync_dir(pending.parent)
        raise
    confirmed = _request(
        api,
        "/v1/principals/me/w2-publisher/rotate/confirm",
        token=new_token,
        method="POST",
        body={"expected_principal_id": principal_id},
    )
    if confirmed.get("principal_id") != principal_id or confirmed.get("rotated") is not True:
        raise RotationError("AAO did not confirm the rotation; staged file retained")
    os.replace(pending, live)
    pending.with_name(pending.name + ".identity").unlink(missing_ok=True)
    _fsync_dir(live.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, choices=sorted(ACCOUNTS))
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    args = parser.parse_args(argv)
    try:
        rotate(args.account, args.api)
    except (RotationError, OSError, BootstrapError) as exc:
        print(f"W2 publisher rotation failed: {exc}", file=sys.stderr)
        return 1
    print(f"W2 publisher token rotated for {args.account}; credential not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
