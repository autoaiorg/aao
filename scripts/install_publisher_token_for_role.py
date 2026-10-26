#!/usr/bin/env python3
"""Install or verify a publisher token while running as its owning AAO role."""
from __future__ import annotations

import argparse
import os
import pwd
import stat
import sys
from pathlib import Path

TARGETS = {"aao-impl-codex", "aao-pm"}
TOKEN_NAME = "aao-publisher.token"
RUNTIME_ROOT = Path("/run/user")


class TokenInstallError(RuntimeError):
    pass


def target_path(account: str) -> Path:
    if account not in TARGETS:
        raise TokenInstallError("unsupported publisher account")
    try:
        entry = pwd.getpwnam(account)
    except KeyError:
        raise TokenInstallError("publisher account is unavailable") from None
    expected_runtime = RUNTIME_ROOT / str(entry.pw_uid)
    configured_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if configured_runtime != str(expected_runtime):
        raise TokenInstallError("XDG_RUNTIME_DIR does not match the selected account")
    try:
        info = expected_runtime.lstat()
    except OSError:
        raise TokenInstallError("role runtime directory is unavailable") from None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != entry.pw_uid
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise TokenInstallError("role runtime directory ownership or mode is unsafe")
    if os.geteuid() != entry.pw_uid:
        raise TokenInstallError("must run as the selected publisher account")
    return expected_runtime / TOKEN_NAME


def read_token() -> str:
    raw = sys.stdin.buffer.read(4097)
    if len(raw) > 4096:
        raise TokenInstallError("publisher token input is invalid")
    token = raw.decode("utf-8").strip()
    if not token or any(ch.isspace() for ch in token):
        raise TokenInstallError("publisher token input is invalid")
    return token


def install(path: Path, token: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        raise TokenInstallError("publisher token already exists; refusing overwrite") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def verify(path: Path, token: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise TokenInstallError("publisher token file is unavailable") from None
    try:
        info = os.fstat(fd)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            content = stream.read(4097)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or content != token + "\n"):
            raise TokenInstallError("publisher token file does not match the expected private file")
    except OSError:
        raise TokenInstallError("publisher token file is unavailable") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, choices=sorted(TARGETS))
    parser.add_argument("--check", action="store_true", help="verify safe installation target is empty")
    parser.add_argument("--verify", action="store_true", help="verify installed token from stdin")
    parser.add_argument("--remove", action="store_true", help="remove only the matching token from stdin")
    args = parser.parse_args()
    if sum((args.check, args.verify, args.remove)) > 1:
        parser.error("--check, --verify, and --remove are mutually exclusive")
    try:
        path = target_path(args.account)
        if args.check:
            if path.exists() or path.is_symlink():
                raise TokenInstallError("publisher token already exists; refusing overwrite")
        else:
            token = read_token()
            if args.verify:
                verify(path, token)
            elif args.remove:
                verify(path, token)
                path.unlink()
            else:
                install(path, token)
        print(f"Publisher token target verified for {args.account}; credential not displayed.")
        return 0
    except (TokenInstallError, OSError, UnicodeError) as exc:
        print(f"Publisher token operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
