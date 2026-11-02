#!/usr/bin/env python3
"""Rotate this Linux role's own W2 publisher token without exposing it."""

from __future__ import annotations

import argparse
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


def _request(api: str, path: str, *, token: str, method: str = "GET") -> dict:
    try:
        return _object(request_json(api, path, method=method, agent_token=token), "AAO API")
    except BootstrapError:
        raise RotationError("AAO API request failed; credential material withheld") from None


def _expected_prefix(account: str) -> str:
    return "aao-publisher-pm-" if account == "aao-pm" else "aao-publisher-impl-"


def rotate(account: str, api_url: str = "http://127.0.0.1:8001") -> None:
    api = _loopback_url(api_url)
    live, pending = _paths(account)
    old = _read_private(live)

    # Recover safely if an earlier run confirmed the new token but died before
    # replacing the live path. The target itself, not the PM, authenticates it.
    if pending.exists() or pending.is_symlink():
        staged = _read_private(pending)
        try:
            me = _request(api, "/v1/principals/me", token=staged)
            if me.get("kind") == "AGENT" and str(me.get("principal_id", "")).startswith(
                _expected_prefix(account)
            ):
                os.replace(pending, live)
                _fsync_dir(live.parent)
                return
        except RotationError:
            pass
        # The staged bearer may be pending rather than promoted. Confirming it
        # is safe; it is accepted only at this endpoint until confirmation.
        try:
            confirmed = _request(
                api,
                "/v1/principals/me/w2-publisher/rotate/confirm",
                token=staged,
                method="POST",
            )
            if confirmed.get("rotated") is not True or not str(
                confirmed.get("principal_id", "")
            ).startswith(_expected_prefix(account)):
                raise RotationError("AAO rejected pending-token recovery")
            os.replace(pending, live)
            _fsync_dir(live.parent)
            return
        except RotationError:
            # A 403 from an expired pending token is recoverable only if the old
            # bearer still authenticates. If the API is unavailable, retain the
            # staged token and fail closed rather than guessing.
            try:
                old_me = _request(api, "/v1/principals/me", token=old)
            except RotationError:
                raise RotationError(
                    "pending rotation recovery failed; staged file retained"
                ) from None
            if old_me.get("kind") != "AGENT" or not str(old_me.get("principal_id", "")).startswith(
                _expected_prefix(account)
            ):
                raise RotationError(
                    "pending rotation recovery failed; staged file retained"
                ) from None
            pending.unlink()
            _fsync_dir(live.parent)

    me = _request(api, "/v1/principals/me", token=old)
    principal_id = me.get("principal_id")
    if (
        me.get("kind") != "AGENT"
        or not isinstance(principal_id, str)
        or not principal_id.startswith(_expected_prefix(account))
    ):
        raise RotationError("installed credential does not belong to this W2 account")
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
    confirmed = _request(
        api,
        "/v1/principals/me/w2-publisher/rotate/confirm",
        token=new_token,
        method="POST",
    )
    if confirmed.get("principal_id") != principal_id or confirmed.get("rotated") is not True:
        raise RotationError("AAO did not confirm the rotation; staged file retained")
    os.replace(pending, live)
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
