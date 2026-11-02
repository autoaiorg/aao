#!/usr/bin/python3
"""Narrow root wrapper for installing fixed Self Development role tokens."""

from __future__ import annotations

import argparse
import os
import pwd
import stat
import subprocess
import sys
from pathlib import Path

PYTHON = Path("/usr/bin/python3")
INSTALLER = Path("/usr/local/libexec/aao/install_publisher_token_for_role.py")
ROOT_WRAPPER = Path("/usr/local/libexec/aao/selfdev_role_token_helper.py")
RUNUSER = Path("/usr/sbin/runuser")
TARGETS = {
    ("aao-impl-codex", "selfdev-implementer"),
    ("aao-auditor", "selfdev-reviewer"),
}
OPERATIONS = {"check", "install", "verify", "remove"}


def _root_owned_safe(path: Path, *, allow_symlink: bool = False) -> bool:
    """Require the target and every parent to be root-owned, non-writable."""
    try:
        info = path.lstat()
        resolved = path.resolve(strict=True)
        if not allow_symlink and stat.S_ISLNK(info.st_mode):
            return False
        for candidate in (resolved, *resolved.parents):
            metadata = candidate.stat()
            if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                return False
    except OSError:
        return False
    return True


def _installed_as_expected() -> bool:
    """Require root-secure copies outside the trust-owned frozen tree."""
    try:
        this_file = Path(__file__).resolve(strict=True)
        wrapper_parents = [ROOT_WRAPPER.parent, *ROOT_WRAPPER.parent.parents]
        safe_wrapper_dirs = all(
            path.is_dir()
            and path.stat().st_uid == 0
            and not (stat.S_IMODE(path.stat().st_mode) & 0o022)
            for path in wrapper_parents
        )
        return (
            this_file == ROOT_WRAPPER
            and safe_wrapper_dirs
            and _root_owned_safe(ROOT_WRAPPER)
            and _root_owned_safe(PYTHON, allow_symlink=True)
            and _root_owned_safe(INSTALLER)
            and _root_owned_safe(RUNUSER)
        )
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--operation", required=True)
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or (args.account, args.token) not in TARGETS:
        return 2
    if args.operation not in OPERATIONS:
        return 2
    if not _installed_as_expected():
        return 2
    try:
        entry = pwd.getpwnam(args.account)
    except KeyError:
        return 2
    runtime = Path("/run/user") / str(entry.pw_uid)
    helper_args = ["--account", args.account, "--token", args.token]
    if args.operation == "check":
        helper_args.append("--check")
    elif args.operation == "verify":
        helper_args.append("--verify")
    elif args.operation == "remove":
        helper_args.append("--remove")
    command = [
        str(RUNUSER),
        "-u",
        args.account,
        "--",
        str(PYTHON),
        str(INSTALLER),
        *helper_args,
    ]
    env = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": str(runtime)}
    data = sys.stdin.buffer.read(4097)
    if len(data) > 4096:
        return 2
    try:
        result = subprocess.run(command, input=data, env=env, check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
