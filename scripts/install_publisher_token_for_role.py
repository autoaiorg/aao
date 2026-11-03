#!/usr/bin/env python3
"""Install or verify a publisher token while running as its owning AAO role."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import os
import pwd
import secrets
import stat
import sys
from pathlib import Path

TARGETS = {"aao-impl-codex", "aao-pm", "aao-auditor"}
TOKEN_NAME = "aao-publisher.token"
# The PM coordinator token is a distinct principal; only aao-pm may hold it.
TOKEN_NAMES = {
    "publisher": TOKEN_NAME,
    "pm": "aao-pm.token",
    "selfdev-implementer": "aao-self-development-agent.token",
    "selfdev-reviewer": "aao-self-development-reviewer.token",
}
TOKEN_ACCOUNTS = {
    "publisher": {"aao-impl-codex", "aao-pm"},
    "pm": {"aao-pm"},
    "selfdev-implementer": {"aao-impl-codex"},
    "selfdev-reviewer": {"aao-auditor"},
}
# Only per-cycle Self Development tokens may be atomically replaced.
REPLACE_TOKENS = {"selfdev-implementer", "selfdev-reviewer"}
RUNTIME_ROOT = Path("/run/user")


class TokenInstallError(RuntimeError):
    pass


class TokenReplaceCommittedError(TokenInstallError):
    """Rename completed, but durability or verification could not be confirmed."""


def target_path(account: str, token_kind: str = "publisher") -> Path:
    if account not in TARGETS:
        raise TokenInstallError("unsupported role account")
    if account not in TOKEN_ACCOUNTS.get(token_kind, ()):
        raise TokenInstallError("unsupported token kind for this account")
    try:
        entry = pwd.getpwnam(account)
    except KeyError:
        raise TokenInstallError("role account is unavailable") from None
    expected_runtime = RUNTIME_ROOT / str(entry.pw_uid)
    configured_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if configured_runtime != str(expected_runtime):
        raise TokenInstallError("XDG_RUNTIME_DIR does not match the selected account")
    try:
        info = expected_runtime.lstat()
    except OSError:
        raise TokenInstallError("role runtime directory is unavailable") from None
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != entry.pw_uid
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise TokenInstallError("role runtime directory ownership or mode is unsafe")
    if os.geteuid() != entry.pw_uid:
        raise TokenInstallError("must run as the selected role account")
    return expected_runtime / TOKEN_NAMES[token_kind]


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


def _temp_prefix(name: str) -> str:
    return f".{name}."


def _clean_stale_temps(dir_fd: int, name: str) -> None:
    """Remove temp files a crashed earlier ``replace`` left for this token name."""
    prefix = _temp_prefix(name)
    for entry in os.listdir(dir_fd):
        if entry.startswith(prefix) and entry.endswith(".tmp"):
            # unlink never follows a symlink; it removes only the directory entry.
            os.unlink(entry, dir_fd=dir_fd)


@contextlib.contextmanager
def _replace_lock(dir_fd: int, name: str):
    """Serialize replacement and stale-temp cleanup for one token target."""
    lock_name = f".{name}.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(lock_name, flags, 0o600, dir_fd=dir_fd)
    except OSError:
        raise TokenInstallError("token replacement lock is unavailable") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise TokenInstallError("token replacement lock is unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX)
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise TokenInstallError("token replacement lock is unsafe")
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_private(dir_fd: int, name: str) -> bytes:
    """Read a role-owned, regular, single-link 0600 file without following links."""
    before = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise TokenInstallError("existing token is not a regular file; refusing replace")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(name, flags, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise TokenInstallError("existing token file is not private; refusing replace")
        return os.read(fd, 4097)
    finally:
        os.close(fd)


def replace(path: Path, token: str) -> None:
    """Replace ``path`` under a per-target lock; distinguish post-rename errors.

    A crash before rename leaves the previous token intact. After rename, the
    new token is installed; if directory durability or post-write verification
    fails, ``TokenReplaceCommittedError`` tells callers to inspect the target
    and not assume the previous token remains installed.
    """
    name = path.name
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise TokenInstallError("token directory is unavailable or a symlink") from None
    try:
        info = os.fstat(dir_fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise TokenInstallError("token directory ownership or mode is unsafe")
        with _replace_lock(dir_fd, name):
            _clean_stale_temps(dir_fd, name)
            payload = (token + "\n").encode("utf-8")
            try:
                existing = _read_private(dir_fd, name)
            except FileNotFoundError:
                existing = None
            except OSError:
                raise TokenInstallError("existing token is a symlink or unreadable") from None
            if existing is not None and hmac.compare_digest(existing, payload):
                raise TokenInstallError("new token equals the installed token; refusing replace")

            temp = f"{_temp_prefix(name)}{secrets.token_hex(8)}.tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            try:
                fd = os.open(temp, flags, 0o600, dir_fd=dir_fd)
            except FileExistsError:
                raise TokenInstallError("temporary token file already exists") from None
            renamed = False
            try:
                try:
                    os.fchmod(fd, 0o600)
                    view = memoryview(payload)
                    while view:
                        view = view[os.write(fd, view) :]
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.replace(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                renamed = True
            except BaseException:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temp, dir_fd=dir_fd)
                raise
            try:
                os.fsync(dir_fd)
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
                try:
                    new = os.fstat(fd)
                    written = os.read(fd, 4097)
                finally:
                    os.close(fd)
                if (
                    not stat.S_ISREG(new.st_mode)
                    or new.st_nlink != 1
                    or new.st_uid != os.geteuid()
                    or stat.S_IMODE(new.st_mode) != 0o600
                    or hashlib.sha256(written).digest() != hashlib.sha256(payload).digest()
                ):
                    raise OSError("post-write verification mismatch")
            except OSError:
                if renamed:
                    raise TokenReplaceCommittedError(
                        "replacement committed; durability or post-write verification failed"
                    ) from None
                raise
    finally:
        os.close(dir_fd)


def verify(path: Path, token: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise TokenInstallError("publisher token file is unavailable") from None
    try:
        info = os.fstat(fd)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            content = stream.read(4097)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or content != token + "\n"
        ):
            raise TokenInstallError("publisher token file does not match the expected private file")
    except OSError:
        raise TokenInstallError("publisher token file is unavailable") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, choices=sorted(TARGETS))
    parser.add_argument(
        "--token",
        choices=sorted(TOKEN_NAMES),
        default="publisher",
        help="publisher (default) or pm (aao-pm.token, aao-pm only)",
    )
    parser.add_argument(
        "--check", action="store_true", help="verify safe installation target is empty"
    )
    parser.add_argument("--verify", action="store_true", help="verify installed token from stdin")
    parser.add_argument(
        "--remove", action="store_true", help="remove only the matching token from stdin"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="atomically replace (or create) a Self Development token from stdin",
    )
    args = parser.parse_args()
    if sum((args.check, args.verify, args.remove, args.replace)) > 1:
        parser.error("--check, --verify, --remove, and --replace are mutually exclusive")
    try:
        if args.replace and args.token not in REPLACE_TOKENS:
            raise TokenInstallError("replace is only supported for Self Development tokens")
        path = target_path(args.account, args.token)
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
            elif args.replace:
                replace(path, token)
            else:
                install(path, token)
        print(
            f"{TOKEN_NAMES[args.token]} target verified for {args.account}; credential not displayed."
        )
        return 0
    except TokenReplaceCommittedError as exc:
        print(f"Publisher token operation requires recovery: {exc}", file=sys.stderr)
        return 3
    except (TokenInstallError, OSError, UnicodeError) as exc:
        print(f"Publisher token operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
