"""Resolve the local host identity from root-managed bootstrap state.

The value is an identifier, not a secret. Its trust comes from the protected
file and the fact that worker claim paths read it locally instead of accepting
an identity supplied by the caller.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

HOST_ID_FILE = Path("/etc/aao/host-id")


class HostIdentityError(RuntimeError):
    pass


def current_host_id() -> str:
    """Return the protected local host ID; fail closed if unavailable or unsafe."""
    mode = os.getenv("AAO_ENV", "development").lower()
    if mode != "production":
        configured = os.getenv("AAO_TEST_HOST_ID")
        if configured:
            return _validate(configured)

    try:
        parent = HOST_ID_FILE.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
            raise HostIdentityError("Host identity directory is not protected")
        fd = os.open(HOST_ID_FILE, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & 0o022
                or not info.st_mode & 0o040
                or info.st_size > 256
            ):
                raise HostIdentityError("Host identity file is not protected")
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                fd = -1
                value = stream.read(257).strip()
        finally:
            if fd >= 0:
                os.close(fd)
    except OSError as exc:
        raise HostIdentityError("Protected local host identity is unavailable") from exc
    return _validate(value)


def _validate(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 255 or any(char in value for char in "\r\n\x00"):
        raise HostIdentityError("Host identity has an invalid format")
    return value
