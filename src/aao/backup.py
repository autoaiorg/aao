"""AAO Backup, Verification, Restoration and Host Cutover Subsystem.

Provides atomic, verifiable backup creation, isolated restore testing,
checksum verification, and host fencing controls. Conforms to CEO Condition 6:
no destructive operations on real data are allowed without isolated pre-verification.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg

from aao.postgresql_connection import connect_postgres

logger = logging.getLogger(__name__)

RESTORE_AUTHORITY_PUBLIC_KEY_FILE = Path("/etc/aao/governance/ceo_restore_authority.pub")
RESTORE_AUTHORITY_DATABASE_URL_FILE = Path("/etc/aao/restore-authority.database-url")
RESTORE_AUTHORITY_ID = "ceo-restore-authority"
RESTORE_AUTHORITY_FILE_OWNER_UID = 0
MAX_RESTORE_AUTHORIZATION_MINUTES = 60
_ISOLATION_VERIFICATION_TOKEN = object()


class BackupError(RuntimeError):
    """Raised when backup, verification, or restoration fails."""


@dataclass
class BackupManifest:
    version: str
    product_version: str
    git_revision: str
    created_at_utc: str
    database_dump_file: str
    database_dump_sha256: str
    schema_migration_version: str | None
    artifacts_included: list[str]
    file_checksums: dict[str, str]


def compute_file_sha256(path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def get_git_revision() -> str:
    """Detect current Git HEAD revision if available."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "UNKNOWN_REVISION"


def create_backup(
    output_dir: Path,
    database_url: str | None = None,
    artifacts_dir: Path | None = None,
) -> Path:
    """Create an atomic tar.gz backup bundle containing DB dump, artifacts and manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bundle_filename = f"aao-backup-{timestamp}.tar.gz"
    bundle_path = output_dir / bundle_filename

    # Gather DB info and perform dump
    with tempfile.TemporaryDirectory() as staging_dir:
        staging_path = Path(staging_dir)
        db_dump_filename = "database_dump.sql"
        db_dump_path = staging_path / db_dump_filename

        schema_version = None
        try:
            with connect_postgres() as db:
                row = db.execute(
                    "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1"
                ).fetchone()
                if row:
                    schema_version = str(row[0])
        except (RuntimeError, OSError):
            pass

        # Perform pg_dump
        dsn = database_url or os.environ.get("AAO_POSTGRES_URL")
        if not dsn:
            raise BackupError("Cannot perform backup: PostgreSQL DSN not configured")

        # Run pg_dump via subprocess
        try:
            with open(db_dump_path, "wb") as out_file:
                subprocess.run(
                    ["pg_dump", "--clean", "--if-exists", dsn],
                    stdout=out_file,
                    stderr=subprocess.PIPE,
                    check=True,
                )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise BackupError(f"pg_dump failed: {exc}") from exc

        db_dump_hash = compute_file_sha256(db_dump_path)

        # Collect artifacts (e.g. from /var/lib/aao or designated dir)
        collected_artifacts: list[str] = []
        file_checksums: dict[str, str] = {
            db_dump_filename: db_dump_hash,
        }

        art_source = artifacts_dir or Path("/var/lib/aao")
        if art_source.is_dir():
            art_dest = staging_path / "artifacts"
            art_dest.mkdir(parents=True, exist_ok=True)
            for item in art_source.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(art_source)
                    dest_file = art_dest / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_file)
                    collected_artifacts.append(f"artifacts/{rel}")
                    file_checksums[f"artifacts/{rel}"] = compute_file_sha256(dest_file)

        # Include candidate repository if present
        candidate_repo = Path(os.environ.get("AAO_CANDIDATE_REPOSITORY") or "/var/lib/aao/candidates.git")
        if candidate_repo.is_dir():
            cand_dest = staging_path / "candidates.git"
            cand_dest.mkdir(parents=True, exist_ok=True)
            for item in candidate_repo.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(candidate_repo)
                    dest_file = cand_dest / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_file)
                    collected_artifacts.append(f"candidates.git/{rel}")
                    file_checksums[f"candidates.git/{rel}"] = compute_file_sha256(dest_file)

        manifest = BackupManifest(
            version="1.0.0",
            product_version="0.1.0",
            git_revision=get_git_revision(),
            created_at_utc=datetime.now(UTC).isoformat(),
            database_dump_file=db_dump_filename,
            database_dump_sha256=db_dump_hash,
            schema_migration_version=schema_version,
            artifacts_included=collected_artifacts,
            file_checksums=file_checksums,
        )

        manifest_path = staging_path / "manifest.json"
        manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")

        # Bundle into tar.gz with strict 0600 permissions
        temp_tar = output_dir / f".tmp-{bundle_filename}"
        with tarfile.open(temp_tar, "w:gz") as tar:
            for item in staging_path.iterdir():
                tar.add(item, arcname=item.name)

        os.chmod(temp_tar, 0o600)
        temp_tar.replace(bundle_path)

    return bundle_path


def verify_backup(backup_path: Path) -> BackupManifest:
    """Verify integrity, manifest checksums, and structure of a backup tar.gz."""
    if not backup_path.is_file():
        raise BackupError(f"Backup file not found: {backup_path}")

    with tempfile.TemporaryDirectory() as inspect_dir:
        inspect_path = Path(inspect_dir)
        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                # Security: validate members to avoid traversal
                for member in tar.getmembers():
                    if member.name.startswith(("/", "..")) or "/../" in member.name:
                        raise BackupError(f"Dangerous path traversal in backup: {member.name}")
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(inspect_path, filter="data")
                else:
                    tar.extractall(inspect_path)
        except (tarfile.TarError, OSError) as exc:
            raise BackupError(f"Unreadable or corrupt backup archive: {exc}") from exc

        manifest_file = inspect_path / "manifest.json"
        if not manifest_file.is_file():
            raise BackupError("Backup archive missing manifest.json")

        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = BackupManifest(**manifest_data)
        except Exception as exc:
            raise BackupError(f"Invalid manifest in backup: {exc}") from exc

        # Verify all checksums recorded in the manifest
        for rel_name, expected_sha in manifest.file_checksums.items():
            file_path = inspect_path / rel_name
            if not file_path.is_file():
                raise BackupError(f"Manifest entry missing from backup archive: {rel_name}")
            actual_sha = compute_file_sha256(file_path)
            if actual_sha != expected_sha:
                raise BackupError(
                    f"Checksum mismatch for {rel_name}: expected {expected_sha}, got {actual_sha}"
                )

        return manifest


def extract_database_name(dsn: str) -> str:
    """Extract database name from a PostgreSQL connection string/URL."""
    if dsn.startswith(("postgresql://", "postgres://")):
        parsed = urlparse(dsn)
        return parsed.path.lstrip("/") or "aao_prod"
    for part in dsn.split():
        if part.startswith("dbname="):
            return part.split("=", 1)[1]
    return "aao_prod"


class AuthorizationReplayError(BackupError):
    """Raised when an authorization nonce has already been consumed."""


class AuthorizationAuthorityError(BackupError):
    """Raised when authorization signature or authority validation fails."""


def get_authorization_store_dir() -> Path:
    """Return the protected directory used by the persistent authorization authority.

    Requires an explicitly provisioned host-local directory. A temporary directory
    is not a durable replay authority and must never be used as a fallback.
    """
    custom = os.environ.get("AAO_AUTH_STORE_DIR")
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
    else:
        p = Path("/var/lib/aao/authorizations")
    try:
        info = p.lstat()
    except OSError as exc:
        raise OSError(f"Authorization authority store unavailable: {p}: {exc}") from exc
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OSError(f"Authorization authority store must be a real directory: {p}")
    if info.st_uid != os.geteuid():
        raise OSError(f"Authorization authority store must be owned by uid {os.geteuid()}: {p}")
    if info.st_mode & 0o077:
        raise OSError(f"Authorization authority store permissions must be 0700 or stricter: {p}")
    return p


def consume_authorization_nonce_host(nonce: str, metadata: dict[str, Any]) -> tuple[bool, str]:
    """Legacy host-local nonce helper retained only for legacy callers and tests.

    This does not provide cross-host exclusivity and is not used by the destructive
    restore authorization path. Production restores use the dedicated PostgreSQL
    authority database via :func:`consume_restore_authorization_nonce`.
    """
    if (
        not isinstance(nonce, str)
        or not nonce
        or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in nonce)
    ):
        return False, "Authorization nonce has invalid characters."
    try:
        store_dir = get_authorization_store_dir()
    except OSError as exc:
        return False, f"Authorization authority store unavailable: {exc}"
    consumed_dir = store_dir / "consumed_nonces"
    consumed_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    consumed_info = consumed_dir.lstat()
    if (not stat.S_ISDIR(consumed_info.st_mode) or stat.S_ISLNK(consumed_info.st_mode)
            or consumed_info.st_uid != os.geteuid() or consumed_info.st_mode & 0o077):
        return False, "Consumed nonce directory is not a protected real directory."
    nonce_file = consumed_dir / f"{nonce}.consumed"

    try:
        fd = os.open(
            nonce_file,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        return False, (
            f"Authorization nonce '{nonce}' has already been consumed (replay denied by persistent "
            "authorization authority independent of destination database)."
        )
    except OSError as exc:
        return False, f"Failed to access persistent authorization authority store: {exc}"

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        return False, f"Failed to persist consumed authorization record: {exc}"

    try:
        dir_fd = os.open(consumed_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        return False, f"Failed to durably persist nonce reservation: {exc}"

    ledger_file = store_dir / "authorization_consumption_audit.jsonl"
    try:
        import fcntl
        ledger_fd = os.open(
            ledger_file,
            os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            ledger_info = os.fstat(ledger_fd)
            if (not stat.S_ISREG(ledger_info.st_mode) or ledger_info.st_uid != os.geteuid()
                    or ledger_info.st_mode & 0o077):
                return False, "Authorization audit ledger is not a protected regular file."
            fcntl.flock(ledger_fd, fcntl.LOCK_EX)
            with os.fdopen(os.dup(ledger_fd), "a", encoding="utf-8") as lf:
                lf.write(json.dumps(metadata) + "\n")
                lf.flush()
                os.fsync(lf.fileno())
            fcntl.flock(ledger_fd, fcntl.LOCK_UN)
        finally:
            os.close(ledger_fd)
    except OSError as exc:
        return False, f"Nonce reserved but consumption audit could not be persisted: {exc}"

    return True, f"Nonce '{nonce}' atomically consumed in persistent host authority store."


def consume_restore_authorization_nonce(
    nonce: str,
    metadata: dict[str, Any],
    target_database: str,
) -> tuple[bool, str]:
    """Atomically reserve a restore nonce in a separate durable PostgreSQL authority DB.

    The authority database must be separately provisioned and named differently
    from the database being restored. Its executor role should have INSERT and
    SELECT(nonce) only on the append-only ledger table. No DDL is performed here.
    """
    if (
        not isinstance(nonce, str)
        or not nonce
        or len(nonce) > 200
        or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in nonce)
    ):
        return False, "Authorization nonce has invalid characters."
    try:
        dsn = _read_root_owned_secret_file(
            RESTORE_AUTHORITY_DATABASE_URL_FILE,
            description="Restore authority database URL",
        )
    except (OSError, UnicodeError):
        return False, "Dedicated protected restore authority database configuration is unavailable."
    try:
        with psycopg.connect(dsn) as authority_db:
            row = authority_db.execute(
                "SELECT current_database(), current_setting('fsync'), "
                "current_setting('synchronous_commit')"
            ).fetchone()
            authority_database, fsync, synchronous_commit = row
            if authority_database == target_database:
                return False, "Restore authority database must differ from the restore target database."
            if fsync != "on" or synchronous_commit != "on":
                return False, "Restore authority PostgreSQL durability settings must enable fsync and synchronous_commit."
            inserted = authority_db.execute(
                """
                INSERT INTO restore_authority.consumed_authorizations
                    (nonce, action, authority_id, backup_sha256, target_database, metadata)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (nonce) DO NOTHING
                RETURNING nonce
                """,
                (
                    nonce,
                    metadata["action"],
                    metadata["authority_id"],
                    metadata["backup_sha256"],
                    target_database,
                    json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                ),
            ).fetchone()
            if inserted is None:
                return False, f"Authorization nonce '{nonce}' has already been consumed (replay denied)."
    except psycopg.Error:
        # Do not expose DSNs or connection details; a commit outcome may be uncertain.
        return False, "Restore authority database unavailable or reservation outcome uncertain; retry is denied pending reconciliation."
    return True, f"Nonce '{nonce[:8]}...' durably consumed by the separate restore authority database."


def _read_root_owned_secret_file(path: Path, *, description: str) -> str:
    """Read a fixed-path root-owned secret; caller-controlled env cannot replace trust roots."""
    try:
        parent_info = path.parent.lstat()
        info = path.lstat()
    except OSError as exc:
        raise OSError(f"{description} is unavailable") from exc
    if (not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != RESTORE_AUTHORITY_FILE_OWNER_UID
            or parent_info.st_mode & 0o022
            or not stat.S_ISREG(info.st_mode) or info.st_uid != RESTORE_AUTHORITY_FILE_OWNER_UID
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise OSError(f"{description} must be a root-owned regular file with mode 0600")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise OSError(f"{description} must contain one non-empty line")
    return value


def create_restore_authorization(
    backup_path: Path,
    target_database: str,
    signing_key: str | Path,
    authority_id: str = "ceo-restore-authority",
    valid_minutes: int = 60,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Generate a structured, cryptographically signed decision artifact issued by CEO authority.

    Enforces Finding A-11:
    - Separation between identification/authentication of CEO and issuance of authorization.
    - Uses dedicated signing key of the CEO Authorization Authority.
    - Bounds authorization to specific backup hash, destination, nonce, and validity window.
    """
    from uuid import uuid4
    if not isinstance(valid_minutes, int) or not 1 <= valid_minutes <= MAX_RESTORE_AUTHORIZATION_MINUTES:
        raise BackupError(
            f"Restore authorizations must be valid for 1 to {MAX_RESTORE_AUTHORIZATION_MINUTES} minutes."
        )
    backup_sha = compute_file_sha256(backup_path)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=valid_minutes)
    auth_nonce = nonce or str(uuid4())
    unsigned_payload = {
        "version": 1,
        "action": "database.destructive_restore",
        "authority_id": authority_id,
        "backup_sha256": backup_sha,
        "target_database": target_database,
        "authorized_at_utc": now.isoformat(),
        "expires_at_utc": expires.isoformat(),
        "authorization_nonce": auth_nonce,
    }
    message = json.dumps(unsigned_payload, sort_keys=True, separators=(",", ":"))
    signing_path = Path(signing_key)
    info = signing_path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise BackupError("Restore signing key must be a private regular file owned by the issuer with mode 0600 or stricter")
    try:
        signed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(signing_path)],
            input=message.encode("utf-8"), capture_output=True, check=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupError("Restore signing key could not issue authorization") from exc
    signature = base64.b64encode(signed.stdout).decode("ascii")
    return {**unsigned_payload, "ceo_signature": signature}


def verify_destructive_restore_authorization(
    db: Any | None,
    backup_path: Path,
    target_database: str,
    authorization: dict[str, Any] | str | Path | None = None,
    ceo_token: str | None = None,
) -> tuple[bool, str, str | None]:
    """Verify that a destructive restore has authentic, structured CEO authorization.

    Returns (is_valid, reason, nonce).
    Enforces findings A-10 & A-11:
    1. Separation of duties: an API bearer token (ceo_token) alone does NOT authorize
       destructive restore. An explicit signed decision artifact is required.
    2. Authority verification: cryptographic signature verified against dedicated
       authorization verification key.
    3. Scope: action must be exactly 'database.destructive_restore'.
    4. Specific backup: backup_sha256 must match current backup archive.
    5. Destination binding: target_database must match current target database name.
    6. Validity window: expires_at_utc must be strictly valid and not expired.
    7. Independent anti-replay: nonce committed to the protected external authority DB.
    """
    # A-11 check: Reject raw CEO token without structured authorization
    if ceo_token is not None and not authorization:
        return False, (
            "Separation of duties violation: CEO authentication token cannot be converted "
            "into autonomous authorization for destructive restore. An explicit decision artifact "
            "issued by the CEO Authorization Authority is mandatory."
        ), None

    payload = authorization
    if not payload:
        return False, (
            "Destructive restore requires an explicit, pre-issued structured CEO authorization artifact. "
            "An authentication credential or CEO token alone does not authorize destructive operations."
        ), None

    if isinstance(payload, (str, Path)):
        p_path = Path(payload)
        if p_path.is_file():
            try:
                payload = json.loads(p_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                return False, f"Failed to read authorization file: {exc}", None
        else:
            try:
                payload = json.loads(str(payload))
            except json.JSONDecodeError as exc:
                return False, f"Failed to parse authorization JSON: {exc}", None

    if not isinstance(payload, dict):
        return False, "Authorization payload must be a JSON object dictionary.", None

    if payload.get("version") != 1:
        return False, "Unsupported restore authorization artifact version.", None

    # Check 1: Action scope
    if payload.get("action") != "database.destructive_restore":
        return False, f"Unauthorized action '{payload.get('action')}'. Must be 'database.destructive_restore'.", None

    # Check 2: Backup hash match
    actual_hash = compute_file_sha256(backup_path)
    if payload.get("backup_sha256") != actual_hash:
        return False, (
            f"Authorization backup hash mismatch (authorized: {payload.get('backup_sha256')}, "
            f"actual: {actual_hash})."
        ), None

    # Check 3: Destination database match
    if payload.get("target_database") != target_database:
        return False, (
            f"Authorization target database mismatch (authorized: '{payload.get('target_database')}', "
            f"target: '{target_database}')."
        ), None

    # Check 4: Signed issuance and bounded expiration window.
    issued_str = payload.get("authorized_at_utc")
    exp_str = payload.get("expires_at_utc")
    if not issued_str or not exp_str:
        return False, "Authorization must include 'authorized_at_utc' and 'expires_at_utc'.", None
    try:
        issued_dt = datetime.fromisoformat(issued_str)
        exp_dt = datetime.fromisoformat(exp_str)
        if issued_dt.tzinfo is None or issued_dt.utcoffset() is None or exp_dt.tzinfo is None or exp_dt.utcoffset() is None:
            return False, "Authorization timestamps must include a timezone offset.", None
        issued_dt = issued_dt.astimezone(UTC)
        exp_dt = exp_dt.astimezone(UTC)
        now = datetime.now(UTC)
        if issued_dt > now:
            return False, "Authorization issue time is in the future.", None
        if exp_dt <= issued_dt:
            return False, "Authorization expiry must follow its issue time.", None
        if exp_dt - issued_dt > timedelta(minutes=MAX_RESTORE_AUTHORIZATION_MINUTES):
            return False, "Authorization validity window exceeds the configured maximum.", None
        if now >= exp_dt:
            return False, f"Authorization expired at {exp_str}.", None
    except (TypeError, ValueError):
        return False, "Invalid authorization timestamp format.", None

    # Check 5: Cryptographic signature verification using dedicated authority key
    nonce = payload.get("authorization_nonce")
    if not nonce:
        return False, "Authorization missing 'authorization_nonce'.", None

    authority_id = payload.get("authority_id")

    # Resolve dedicated verification key (separated from API bearer token)
    canonical_key = RESTORE_AUTHORITY_PUBLIC_KEY_FILE

    expected_authority = RESTORE_AUTHORITY_ID
    if not isinstance(authority_id, str) or authority_id != expected_authority:
        return False, "Authorization issuer identity does not match the configured authority.", None
    signed_payload = {key: value for key, value in payload.items() if key != "ceo_signature"}
    expected_msg = json.dumps(signed_payload, sort_keys=True, separators=(",", ":"))
    try:
        signature = base64.b64decode(payload.get("ceo_signature", ""), validate=True)
        key_path = Path(canonical_key)
        parent_info = key_path.parent.lstat()
        key_info = key_path.lstat()
        if (not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid != RESTORE_AUTHORITY_FILE_OWNER_UID
                or parent_info.st_mode & 0o022
                or not stat.S_ISREG(key_info.st_mode)
                or key_info.st_uid != RESTORE_AUTHORITY_FILE_OWNER_UID
                or key_info.st_mode & 0o022):
            raise OSError("Pinned public verification key is not a root-owned protected regular file")
        with tempfile.TemporaryDirectory(prefix="aao-restore-verify-") as tmp:
            signature_path = Path(tmp) / "signature.bin"
            signature_path.write_bytes(signature)
            signature_path.chmod(0o600)
            verified = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", str(key_path), "-signature", str(signature_path)],
                input=expected_msg.encode("utf-8"), capture_output=True, timeout=5, check=False,
            )
        sig_valid = verified.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        sig_valid = False
    if not sig_valid:
        return False, "CEO authority cryptographic signature verification failed.", None

    # Check 6: Atomic anti-replay reservation in the external authority database.
    metadata = {
        "nonce": nonce,
        "action": "database.destructive_restore",
        "authority_id": authority_id,
        "backup_sha256": actual_hash,
        "target_database": target_database,
        "consumed_at_utc": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
    }
    authority_ok, authority_msg = consume_restore_authorization_nonce(
        nonce, metadata, target_database,
    )
    if not authority_ok:
        return False, authority_msg, None

    # Target-database event is informational only; the dedicated authority DB above
    # is the sole anti-replay source of truth and is never restored with this DB.
    if db is not None:
        try:
            from uuid import uuid4
            event_id = str(uuid4())
            db.execute(
                """
                INSERT INTO events (id, subject_id, kind, details)
                VALUES (%s, %s, 'ceo.restore.consumed', %s::jsonb)
                """,
                (
                    event_id,
                    nonce,
                    json.dumps(metadata),
                ),
            )
        except (RuntimeError, OSError, psycopg.Error) as db_exc:
            # The dedicated authority database already guarantees anti-replay;
            # this target-database event is informational only.
            logger.warning(
                "Could not record secondary nonce audit in destination database before restore: %s",
                db_exc,
            )

    return True, f"Structured CEO authorization verified (nonce: {nonce[:8]}..., valid until {exp_str})", nonce


def verify_restore_isolated(backup_path: Path, isolated_dsn: str) -> BackupManifest:
    """Validate that the backup can be successfully restored into an isolated destination.

    Verifies that the target is completely empty, restores the dump, and verifies schema consistency.
    """
    verify_backup(backup_path)
    import psycopg

    with psycopg.connect(isolated_dsn, autocommit=True) as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        table_count = cursor.fetchone()[0]
        if table_count > 0:
            raise BackupError(
                f"Isolated verification destination must be empty; contains {table_count} tables"
            )

    return _restore_backup_impl(
        backup_path,
        isolated_dsn,
        allow_non_empty_target=False,
        _isolation_verified=_ISOLATION_VERIFICATION_TOKEN,
    )


def restore_backup(
    backup_path: Path,
    target_dsn: str,
    target_artifacts_dir: Path | None = None,
    target_candidates_dir: Path | None = None,
    allow_non_empty_target: bool = False,
    restore_authorization: dict[str, Any] | str | Path | None = None,
    ceo_token: str | None = None,
    isolated_dsn: str | None = None,
) -> BackupManifest:
    """Restore a backup; non-empty targets require a real isolated-dry-run path."""
    return _restore_backup_impl(
        backup_path,
        target_dsn,
        target_artifacts_dir=target_artifacts_dir,
        target_candidates_dir=target_candidates_dir,
        allow_non_empty_target=allow_non_empty_target,
        restore_authorization=restore_authorization,
        ceo_token=ceo_token,
        isolated_dsn=isolated_dsn,
    )


def _restore_backup_impl(
    backup_path: Path,
    target_dsn: str,
    target_artifacts_dir: Path | None = None,
    target_candidates_dir: Path | None = None,
    allow_non_empty_target: bool = False,
    restore_authorization: dict[str, Any] | str | Path | None = None,
    ceo_token: str | None = None,
    isolated_dsn: str | None = None,
    *,
    _isolation_verified: object | None = None,
) -> BackupManifest:
    """Restore a verified backup into the target database and filesystem.

    Enforces CEO Condition 6 and Finding A-08:
    1. If target database contains existing tables, requires allow_non_empty_target=True.
    2. Requires structured, cryptographically signed CEO authorization (bound to backup SHA, target DB, and validity window).
    3. Requires prior isolated verification in a clean destination.
    4. Takes a pre-restoration snapshot of the destination; automatically rolls back if restore fails partially.
    """
    manifest = verify_backup(backup_path)
    target_database = extract_database_name(target_dsn)

    import psycopg

    # Step 1: Pre-verification in isolated destination if requested
    if isolated_dsn and extract_database_name(isolated_dsn) == target_database:
        raise BackupError(
            "Isolated verification destination must be a different database from the restore target."
        )
    isolation_verified = _isolation_verified is _ISOLATION_VERIFICATION_TOKEN
    if isolated_dsn and not isolation_verified:
        verify_restore_isolated(backup_path, isolated_dsn)
        isolation_verified = True

    # Step 2: Verify target database state and enforce authorization
    table_count = 0
    auth_nonce: str | None = None
    with psycopg.connect(target_dsn, autocommit=True) as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        table_count = cursor.fetchone()[0]

    if table_count > 0:
        if not allow_non_empty_target:
            raise BackupError(
                f"Refusing destructive restore: target database contains {table_count} tables. "
                "Restoration over existing databases requires prior isolated verification "
                "and explicit, structured CEO authorization."
            )

        if not isolation_verified:
            raise BackupError(
                "Destructive restore denied: prior verification in an isolated destination "
                "is mandatory before modifying an active database. Use --verify-isolated-dsn."
            )

        # Check verifiable structured CEO authorization
        with psycopg.connect(target_dsn, autocommit=True) as conn, conn.cursor() as cursor:
            authorized, auth_msg, auth_nonce = verify_destructive_restore_authorization(
                cursor,
                backup_path=backup_path,
                target_database=target_database,
                authorization=restore_authorization,
                ceo_token=ceo_token,
            )
            if not authorized:
                raise BackupError(
                    f"Destructive restore over active non-empty database denied: {auth_msg}"
                )

    # Step 3: Extract and stage everything; verify all checksums BEFORE touching targets (Finding B-09)
    with tempfile.TemporaryDirectory() as restore_dir:
        restore_path = Path(restore_dir)
        safety_snapshot_path = restore_path / "pre_restore_safety_db.sql"
        safety_artifacts_dir = restore_path / "pre_restore_safety_artifacts"
        safety_candidates_dir = restore_path / "pre_restore_safety_candidates"

        with tarfile.open(backup_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(restore_path, filter="data")
            else:
                tar.extractall(restore_path)

        # Integrity verification of staged files against manifest prior to any modifications
        for rel_file, expected_hash in manifest.file_checksums.items():
            staged_file = restore_path / rel_file
            if not staged_file.is_file():
                raise BackupError(f"Backup consistency failure: expected file '{rel_file}' missing from archive.")
            actual_staged_hash = compute_file_sha256(staged_file)
            if actual_staged_hash != expected_hash:
                raise BackupError(
                    f"Backup consistency failure: staged file '{rel_file}' checksum mismatch "
                    f"(expected: {expected_hash}, actual: {actual_staged_hash})."
                )

        # Pre-restoration safety snapshots across ALL components (PostgreSQL, artifacts, candidate repo)
        if table_count > 0:
            try:
                with open(safety_snapshot_path, "wb") as snap_file:
                    subprocess.run(
                        ["pg_dump", "--clean", "--if-exists", target_dsn],
                        stdout=snap_file,
                        stderr=subprocess.PIPE,
                        check=True,
                    )
            except (subprocess.CalledProcessError, FileNotFoundError) as exc:
                raise BackupError(f"Failed to create pre-restoration database safety snapshot: {exc}") from exc

        if target_artifacts_dir and target_artifacts_dir.is_dir() and any(target_artifacts_dir.iterdir()):
            try:
                shutil.copytree(target_artifacts_dir, safety_artifacts_dir, dirs_exist_ok=True)
            except OSError as exc:
                raise BackupError(f"Failed to create pre-restoration artifacts safety snapshot: {exc}") from exc

        if target_candidates_dir and target_candidates_dir.is_dir() and any(target_candidates_dir.iterdir()):
            try:
                shutil.copytree(target_candidates_dir, safety_candidates_dir, dirs_exist_ok=True)
            except OSError as exc:
                raise BackupError(f"Failed to create pre-restoration candidate repository safety snapshot: {exc}") from exc

        # Phase 1: Database restoration
        db_dump = restore_path / manifest.database_dump_file
        try:
            with open(db_dump, "rb") as in_file:
                subprocess.run(
                    ["psql", "-v", "ON_ERROR_STOP=1", target_dsn],
                    stdin=in_file,
                    capture_output=True,
                    text=True,
                    check=True,
                )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            # Compensating rollback of database
            rollback_msg = "No database safety snapshot needed (target was empty)."
            if safety_snapshot_path.is_file():
                try:
                    with open(safety_snapshot_path, "rb") as snap_in:
                        subprocess.run(
                            ["psql", "-v", "ON_ERROR_STOP=1", target_dsn],
                            stdin=snap_in,
                            capture_output=True,
                            text=True,
                            check=True,
                        )
                    rollback_msg = "Target database safely rolled back to original pre-restoration state."
                except (subprocess.CalledProcessError, OSError) as rb_exc:
                    rollback_msg = f"Critical: rollback from database safety snapshot failed: {rb_exc}"
            err_details = exc.stderr.strip() if hasattr(exc, "stderr") and exc.stderr else str(exc)
            raise BackupError(f"Database restore failed: {err_details}. {rollback_msg}") from exc

        # Phase 2: Artifacts restoration with coordinated rollback on failure
        art_src = restore_path / "artifacts"
        if art_src.is_dir() and target_artifacts_dir:
            try:
                target_artifacts_dir.mkdir(parents=True, exist_ok=True)
                for item in art_src.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(art_src)
                        dest = target_artifacts_dir / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
            except OSError as exc:
                # Coordinated rollback of database and artifacts
                if safety_snapshot_path.is_file():
                    with open(safety_snapshot_path, "rb") as snap_in:
                        subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", target_dsn], stdin=snap_in, check=False)
                if safety_artifacts_dir.is_dir():
                    shutil.copytree(safety_artifacts_dir, target_artifacts_dir, dirs_exist_ok=True)
                raise BackupError(f"Artifacts restoration failed ({exc}). Compensating rollback applied across all components.") from exc

        # Phase 3: Candidate repository restoration with coordinated rollback on failure
        cand_src = restore_path / "candidates.git"
        if cand_src.is_dir() and target_candidates_dir:
            try:
                target_candidates_dir.mkdir(parents=True, exist_ok=True)
                shutil.copytree(cand_src, target_candidates_dir, dirs_exist_ok=True)
            except OSError as exc:
                # Coordinated rollback of database, artifacts, and candidate repo
                if safety_snapshot_path.is_file():
                    with open(safety_snapshot_path, "rb") as snap_in:
                        subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", target_dsn], stdin=snap_in, check=False)
                if safety_artifacts_dir.is_dir():
                    shutil.copytree(safety_artifacts_dir, target_artifacts_dir, dirs_exist_ok=True)
                if safety_candidates_dir.is_dir():
                    shutil.copytree(safety_candidates_dir, target_candidates_dir, dirs_exist_ok=True)
                raise BackupError(f"Candidate repository restoration failed ({exc}). Compensating rollback applied across all components.") from exc

    # Step 4: Record the restore event in the target database. Anti-replay state
    # was committed to the independent authority database before any mutation.
    try:
        from uuid import uuid4
        with psycopg.connect(target_dsn, autocommit=True) as conn, conn.cursor() as cursor:
            event_id = str(uuid4())
            cursor.execute(
                """
                INSERT INTO events (id, subject_id, kind, details)
                VALUES (%s, %s, 'database.restored', %s::jsonb)
                """,
                (
                    event_id,
                    event_id,
                    json.dumps({
                        "backup_git_revision": str(manifest.git_revision),
                        "backup_dump_sha256": str(manifest.database_dump_sha256),
                        "restored_at": datetime.now(UTC).isoformat(),
                    }),
                ),
            )
            if auth_nonce:
                consumed_event_id = str(uuid4())
                consumed_subject_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO events (id, subject_id, kind, details)
                    VALUES (%s, %s, 'ceo.restore.consumed', %s::jsonb)
                    """,
                    (
                        consumed_event_id,
                        consumed_subject_id,
                        json.dumps({
                            "target_database": target_database,
                            "authorization_nonce": auth_nonce,
                            "consumed_at": datetime.now(UTC).isoformat(),
                        }),
                    ),
                )
    except (RuntimeError, OSError, psycopg.Error):
        pass

    return manifest


def ensure_host_worker_registry(db: Any) -> None:
    """Require the versioned host-fencing schema; never create privileged schema ad hoc."""
    registry = db.execute("SELECT to_regclass('public.host_worker_bindings')").fetchone()
    epoch = db.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name='execution_queue' AND column_name='claim_fence_epoch'"
    ).fetchone()
    if not registry or registry[0] is None or not epoch:
        raise BackupError("Host fencing schema is unavailable; apply PostgreSQL migration 031")


def register_host_worker(db: Any, host_id: str, worker_id: str) -> None:
    """Explicitly register a worker identity as bound to a specific host machine."""
    ensure_host_worker_registry(db)
    db.execute(
        """
        INSERT INTO host_worker_bindings (host_id, worker_id, status, fence_epoch)
        VALUES (%s, %s, 'ACTIVE', 1)
        ON CONFLICT (host_id, worker_id) DO UPDATE
        SET status = 'ACTIVE', fenced_at = NULL;
        """,
        (host_id, worker_id),
    )


def apply_host_fencing(
    db: Any,
    host_identifier: str = "current-host",
) -> list[str]:
    """Apply targeted host fencing: revoke worker leases, tokens and claims for a specific host.

    Ensures that migrating between hosts guarantees exclusivity without blanket
    revocation of unrelated agents or other active hosts in the cluster.
    Increments fence_epoch to guarantee that any in-flight execution fails closed.
    """
    actions = []
    ensure_host_worker_registry(db)

    # 1. Identify all workers explicitly bound to this host
    target_workers: list[str] = []
    rows = db.execute(
        """
        SELECT worker_id FROM host_worker_bindings
        WHERE host_id = %s AND status = 'ACTIVE'
        """,
        (host_identifier,),
    ).fetchall()
    for r in rows:
        w_id = str(r[0])
        if w_id not in target_workers:
            target_workers.append(w_id)

    # 2. Mark host bindings as FENCED and increment fence_epoch
    db.execute(
        """
        UPDATE host_worker_bindings
        SET status = 'FENCED', fence_epoch = fence_epoch + 1, fenced_at = clock_timestamp()
        WHERE host_id = %s
        """,
        (host_identifier,),
    )
    actions.append(f"host_worker_bindings: marked host '{host_identifier}' bindings as FENCED (epoch incremented)")

    # 3. Revoke credentials in principal_credentials only for target workers
    if target_workers:
        db.execute(
            """
            UPDATE principal_credentials
            SET enabled = false
            WHERE principal_id = ANY(%s) AND enabled = true
            """,
            (target_workers,),
        )
        actions.append(f"principal_credentials: revoked credentials for host workers: {target_workers}")
    else:
        actions.append(f"principal_credentials: no active agent credentials bound to host '{host_identifier}'")

    # 4. Invalidate execution queue claims
    if target_workers:
        db.execute(
            """
            UPDATE execution_queue
            SET status = 'FAILED',
                result_json = jsonb_build_object(
                    'error', 'Host migration cutover fencing applied: worker lease revoked',
                    'fenced_host', %s::text
                ),
                lease_expires_at = clock_timestamp() - INTERVAL '1 second'
            WHERE worker_id = ANY(%s) AND status IN ('RUNNING', 'QUEUED')
            """,
            (host_identifier, target_workers),
        )
        actions.append(f"execution_queue: revoked in-flight tasks for workers {target_workers}")
    else:
        actions.append(f"execution_queue: no in-flight tasks for host '{host_identifier}'")

    # 5. Expire conversation turn leases
    db.execute(
        """
        UPDATE project_conversation_turns
        SET lease_expires_at = clock_timestamp() - INTERVAL '1 second'
        WHERE lease_expires_at > clock_timestamp()
        """
    )
    actions.append("conversation_turns: expired active leases")

    # 6. Record host fencing audit event
    from uuid import uuid4
    event_id = str(uuid4())
    db.execute(
        """
        INSERT INTO events (id, subject_id, kind, details)
        VALUES (%s, %s, 'host.fenced', %s::jsonb)
        """,
        (
            event_id,
            event_id,
            json.dumps({
                "host": host_identifier,
                "fenced_workers": target_workers,
                "fenced_at": datetime.now(UTC).isoformat(),
            }),
        ),
    )
    actions.append("events: recorded host.fenced audit event")

    return actions
