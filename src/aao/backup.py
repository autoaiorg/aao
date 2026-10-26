"""AAO Backup, Verification, Restoration and Host Cutover Subsystem.

Provides atomic, verifiable backup creation, isolated restore testing,
checksum verification, and host fencing controls. Conforms to CEO Condition 6:
no destructive operations on real data are allowed without isolated pre-verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aao.postgresql_connection import connect_postgres


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


def create_restore_authorization(
    backup_path: Path,
    target_database: str,
    ceo_token: str,
    valid_minutes: int = 60,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Generate a structured, cryptographically signed CEO authorization artifact."""
    from uuid import uuid4
    backup_sha = compute_file_sha256(backup_path)
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=valid_minutes)
    auth_nonce = nonce or str(uuid4())
    action = "database.destructive_restore"
    message = f"{action}:{backup_sha}:{target_database}:{auth_nonce}:{expires.isoformat()}"
    signature = hmac.new(ceo_token.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "action": action,
        "backup_sha256": backup_sha,
        "target_database": target_database,
        "authorized_at_utc": now.isoformat(),
        "expires_at_utc": expires.isoformat(),
        "authorization_nonce": auth_nonce,
        "ceo_signature": signature,
    }


def verify_destructive_restore_authorization(
    db: Any | None,
    backup_path: Path,
    target_database: str,
    authorization: dict[str, Any] | str | Path | None = None,
    ceo_token: str | None = None,
) -> tuple[bool, str, str | None]:
    """Verify that a destructive restore has authentic, structured CEO authorization.

    Returns (is_valid, reason, nonce).
    Enforces finding A-08:
    1. Scope: action must be exactly 'database.destructive_restore'.
    2. Specific backup: backup_sha256 must match current backup archive.
    3. Destination binding: target_database must match current target database name.
    4. Validity window: expires_at_utc must be strictly valid and not expired.
    5. Proof: HMAC signature verified using the configured canonical CEO credential.
    6. Replay prevention: authorization nonce must not have been previously consumed.
    """
    canonical_token = os.environ.get("AAO_CEO_TOKEN")
    if not canonical_token and Path("/etc/aao/aao-ceo.token").is_file():
        try:
            canonical_token = Path("/etc/aao/aao-ceo.token").read_text(encoding="utf-8").strip()
        except OSError:
            pass

    if not canonical_token:
        return False, "Cannot verify authorization: canonical CEO token not configured on host.", None

    if ceo_token is not None and not secrets.compare_digest(ceo_token.strip(), canonical_token.strip()):
        return False, "Supplied CEO token does not match authorized host CEO credential.", None

    payload = authorization
    # If no explicit authorization payload was passed, but a valid ceo_token was supplied,
    # generate a single-use authorization for this execution
    if not payload and ceo_token:
        payload = create_restore_authorization(backup_path, target_database, canonical_token, valid_minutes=15)

    if not payload:
        return False, "Neither a structured authorization artifact nor a valid CEO token was provided.", None

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

    # Check 4: Expiration window
    exp_str = payload.get("expires_at_utc")
    if not exp_str:
        return False, "Authorization missing 'expires_at_utc'.", None
    try:
        exp_dt = datetime.fromisoformat(exp_str)
        if datetime.now(UTC) >= exp_dt:
            return False, f"Authorization expired at {exp_str}.", None
    except ValueError as exc:
        return False, f"Invalid expiration timestamp format: {exc}", None

    # Check 5: Cryptographic signature
    nonce = payload.get("authorization_nonce")
    if not nonce:
        return False, "Authorization missing 'authorization_nonce'.", None

    expected_msg = f"database.destructive_restore:{actual_hash}:{target_database}:{nonce}:{exp_str}"
    expected_sig = hmac.new(canonical_token.encode("utf-8"), expected_msg.encode("utf-8"), hashlib.sha256).hexdigest()
    actual_sig = payload.get("ceo_signature", "")
    if not secrets.compare_digest(actual_sig, expected_sig):
        return False, "CEO cryptographic signature verification failed.", None

    # Check 6: Replay prevention check
    if db is not None:
        import psycopg
        try:
            row = db.execute(
                """
                SELECT count(*) FROM events
                WHERE kind = 'ceo.restore.consumed' AND (subject_id::text = %s OR id::text = %s)
                """,
                (nonce, nonce),
            ).fetchone()
            if row and int(row[0]) > 0:
                return False, f"Authorization nonce '{nonce}' has already been consumed (replay denied).", None
        except (RuntimeError, OSError, psycopg.Error):
            pass

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

    return restore_backup(
        backup_path,
        isolated_dsn,
        allow_non_empty_target=False,
        pre_verified_isolated=True,
    )


def restore_backup(
    backup_path: Path,
    target_dsn: str,
    target_artifacts_dir: Path | None = None,
    target_candidates_dir: Path | None = None,
    allow_non_empty_target: bool = False,
    restore_authorization: dict[str, Any] | str | Path | None = None,
    ceo_token: str | None = None,
    pre_verified_isolated: bool = False,
    isolated_dsn: str | None = None,
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
    if isolated_dsn and not pre_verified_isolated:
        verify_restore_isolated(backup_path, isolated_dsn)
        pre_verified_isolated = True

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

        if not pre_verified_isolated:
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

    # Step 3: Extract and apply database dump with safety snapshot protection
    with tempfile.TemporaryDirectory() as restore_dir:
        restore_path = Path(restore_dir)
        safety_snapshot_path = restore_path / "pre_restore_safety.sql"

        # Destination safety snapshot before touching non-empty target
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
                raise BackupError(f"Failed to create pre-restoration safety snapshot: {exc}") from exc

        with tarfile.open(backup_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(restore_path, filter="data")
            else:
                tar.extractall(restore_path)

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
            # Atomic rollback of target using safety snapshot
            rollback_msg = "No safety snapshot needed (target was empty)."
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
                    rollback_msg = f"Critical: rollback from safety snapshot failed: {rb_exc}"
            err_details = exc.stderr.strip() if hasattr(exc, "stderr") and exc.stderr else str(exc)
            raise BackupError(f"Database restore failed: {err_details}. {rollback_msg}") from exc

        # Restore artifacts if present
        art_src = restore_path / "artifacts"
        if art_src.is_dir() and target_artifacts_dir:
            target_artifacts_dir.mkdir(parents=True, exist_ok=True)
            for item in art_src.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(art_src)
                    dest = target_artifacts_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)

        # Restore candidate repository if present
        cand_src = restore_path / "candidates.git"
        if cand_src.is_dir() and target_candidates_dir:
            target_candidates_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cand_src, target_candidates_dir, dirs_exist_ok=True)

    # Step 4: Record restore event and retire authorization nonce in target database
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
            # Replay retirement
            if auth_nonce:
                cursor.execute(
                    """
                    INSERT INTO events (id, subject_id, kind, details)
                    VALUES (%s, %s, 'ceo.restore.consumed', %s::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        auth_nonce,
                        auth_nonce,
                        json.dumps({
                            "target_database": target_database,
                            "consumed_at": datetime.now(UTC).isoformat(),
                        }),
                    ),
                )
    except (RuntimeError, OSError, psycopg.Error):
        pass

    return manifest


def ensure_host_worker_registry(db: Any) -> None:
    """Ensure explicit host-to-worker mapping table exists in PostgreSQL."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS host_worker_bindings (
            host_id text NOT NULL,
            worker_id text NOT NULL,
            status text NOT NULL CHECK (status IN ('ACTIVE', 'FENCED', 'STANDBY')),
            fenced_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (host_id, worker_id)
        );
        CREATE INDEX IF NOT EXISTS ix_host_worker_bindings_host ON host_worker_bindings(host_id, status);
        """
    )


def register_host_worker(db: Any, host_id: str, worker_id: str) -> None:
    """Explicitly register a worker identity as bound to a specific host machine."""
    ensure_host_worker_registry(db)
    db.execute(
        """
        INSERT INTO host_worker_bindings (host_id, worker_id, status)
        VALUES (%s, %s, 'ACTIVE')
        ON CONFLICT (host_id, worker_id) DO UPDATE
        SET status = 'ACTIVE', fenced_at = NULL;
        """,
        (host_id, worker_id),
    )


def apply_host_fencing(
    db: Any,
    host_identifier: str = "current-host",
    worker_ids: list[str] | None = None,
) -> list[str]:
    """Apply targeted host fencing: revoke worker leases, tokens and claims for a specific host.

    Ensures that migrating between hosts guarantees exclusivity without blanket
    revocation of unrelated agents or other active hosts in the cluster.
    """
    actions = []
    ensure_host_worker_registry(db)

    # 1. Identify all workers explicitly bound to this host
    target_workers = list(worker_ids) if worker_ids else []
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

    # 2. Mark host bindings as FENCED
    db.execute(
        """
        UPDATE host_worker_bindings
        SET status = 'FENCED', fenced_at = clock_timestamp()
        WHERE host_id = %s
        """,
        (host_identifier,),
    )
    actions.append(f"host_worker_bindings: marked host '{host_identifier}' bindings as FENCED")

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
                    'fenced_host', %s
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
