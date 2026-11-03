#!/usr/bin/env python3
"""Explicitly bind or revoke a verified mTLS certificate for one AAO principal.

This is a host-administrator operation. It never creates principals, grants,
certificates, or private keys. The database connection must be provisioned
out-of-band with only the table privileges required for the selected action.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aao.postgresql_connection import connect_postgres


class BindingError(ValueError):
    """A workload identity binding request was invalid or unsafe."""


def read_admin_dsn(path: Path) -> str:
    """Read an explicitly supplied root-only admin DSN file, never runtime env.

    This utility must be invoked by an administrator with access to a dedicated
    provisioning connection. Runtime service credentials are not a fallback.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise BindingError("admin connection file cannot be opened safely") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
            raise BindingError("admin connection file must be root-owned mode 0600 regular file")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
            value = stream.read(4097)
    finally:
        os.close(fd)
    dsn = value.strip()
    if "\n" in dsn or "\r" in dsn or not dsn.startswith(("postgresql://", "postgres://")):
        raise BindingError("admin connection file must contain one PostgreSQL DSN line")
    return dsn


def certificate_fingerprint(path: Path) -> str:
    """Read one public PEM certificate without following symlinks; return SHA-256."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise BindingError("certificate file cannot be opened safely") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size < 1 or info.st_size > 65536:
            raise BindingError("certificate must be a regular PEM file no larger than 64 KiB")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            pem = stream.read(65537)
    finally:
        os.close(fd)
    if len(pem) > 65536 or b"-----BEGIN PRIVATE KEY-----" in pem:
        raise BindingError("expected a public certificate, not private key material")
    match = re.fullmatch(
        rb"\s*-----BEGIN CERTIFICATE-----\s*([A-Za-z0-9+/=\r\n]+?)\s*"
        rb"-----END CERTIFICATE-----\s*",
        pem,
    )
    if not match:
        raise BindingError("file must contain exactly one PEM certificate")
    import base64

    try:
        der = base64.b64decode(re.sub(rb"\s+", b"", match.group(1)), validate=True)
    except ValueError as exc:
        raise BindingError("certificate PEM is malformed") from exc
    if not der:
        raise BindingError("certificate PEM is empty")
    return hashlib.sha256(der).hexdigest()


def parse_expiry(value: str) -> datetime:
    try:
        expires_at = datetime.fromisoformat(value)
    except ValueError:
        raise BindingError("--expires-at must be an ISO-8601 timestamp") from None
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise BindingError("--expires-at must include a timezone")
    expires_at = expires_at.astimezone(UTC)
    if expires_at <= datetime.now(UTC):
        raise BindingError("--expires-at must be in the future")
    return expires_at


def bind(principal_id: str, fingerprint: str, expires_at: datetime, *, admin_dsn: str) -> bool:
    """Insert one immutable binding; return False for an exact existing binding."""
    if os.getenv("AAO_ENV", "").strip().lower() != "production":
        raise BindingError("binding management is available only in production mode")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise BindingError("certificate fingerprint is malformed")
    if not admin_dsn.startswith(("postgresql://", "postgres://")):
        raise BindingError("explicit administrator connection required")
    with connect_postgres(admin_dsn) as db:
        row = db.execute(
            "SELECT kind,enabled,expires_at FROM principal_credentials "
            "WHERE principal_id=%s FOR UPDATE",
            (principal_id,),
        ).fetchone()
        if not row or row[0] not in {"AGENT", "AUDITOR"} or not row[1]:
            raise BindingError("principal must exist, be enabled, and be AGENT or AUDITOR")
        principal_expiry = row[2]
        if principal_expiry is not None and expires_at > principal_expiry:
            raise BindingError("binding expiry must not exceed principal expiry")

        existing = db.execute(
            "SELECT principal_id,enabled,expires_at FROM workload_identity_bindings "
            "WHERE certificate_sha256=%s FOR UPDATE",
            (fingerprint,),
        ).fetchone()
        if existing:
            if existing[0] == principal_id and existing[1] and existing[2] == expires_at:
                return False
            raise BindingError("certificate fingerprint is already bound; refusing reassignment")
        db.execute(
            "INSERT INTO workload_identity_bindings "
            "(certificate_sha256,principal_id,expires_at) VALUES (%s,%s,%s)",
            (fingerprint, principal_id, expires_at),
        )
        db.execute(
            "INSERT INTO events(id,subject_id,kind,details) VALUES (%s,%s,%s,%s::jsonb)",
            (
                str(uuid4()),
                principal_id,
                "principal.workload_identity.bound",
                '{"kind":"mTLS","result":"bound"}',
            ),
        )
    return True


def revoke(fingerprint: str, *, admin_dsn: str) -> str:
    """Disable one certificate binding and audit the revocation."""
    if os.getenv("AAO_ENV", "").strip().lower() != "production":
        raise BindingError("binding management is available only in production mode")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise BindingError("certificate fingerprint is malformed")
    if not admin_dsn.startswith(("postgresql://", "postgres://")):
        raise BindingError("explicit administrator connection required")
    with connect_postgres(admin_dsn) as db:
        row = db.execute(
            "UPDATE workload_identity_bindings SET enabled=false,revoked_at=clock_timestamp() "
            "WHERE certificate_sha256=%s AND enabled=true AND revoked_at IS NULL "
            "RETURNING principal_id",
            (fingerprint,),
        ).fetchone()
        if not row:
            raise BindingError("active certificate binding not found")
        principal_id = row[0]
        db.execute(
            "INSERT INTO events(id,subject_id,kind,details) VALUES (%s,%s,%s,%s::jsonb)",
            (
                str(uuid4()),
                principal_id,
                "principal.workload_identity.revoked",
                '{"kind":"mTLS","result":"revoked"}',
            ),
        )
    return principal_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    bind_parser = subparsers.add_parser("bind")
    bind_parser.add_argument("--admin-connection-file", required=True, type=Path)
    bind_parser.add_argument("--principal-id", required=True)
    bind_parser.add_argument("--certificate", required=True, type=Path)
    bind_parser.add_argument("--expires-at", required=True)
    revoke_parser = subparsers.add_parser("revoke")
    revoke_parser.add_argument("--admin-connection-file", required=True, type=Path)
    revoke_parser.add_argument("--fingerprint-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        admin_dsn = read_admin_dsn(args.admin_connection_file)
        if args.operation == "bind":
            fingerprint = certificate_fingerprint(args.certificate)
            created = bind(
                args.principal_id, fingerprint, parse_expiry(args.expires_at),
                admin_dsn=admin_dsn,
            )
            result = "created" if created else "already bound identically"
            print(
                f"Workload identity binding {result}; principal={args.principal_id}; SHA-256={fingerprint}"
            )
        else:
            principal_id = revoke(args.fingerprint_sha256, admin_dsn=admin_dsn)
            print(f"Workload identity binding revoked; principal={principal_id}")
    except (BindingError, OSError, RuntimeError) as exc:
        print(f"Workload identity operation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
