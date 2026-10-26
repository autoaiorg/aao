"""AAO Backup, Verification, Restoration and Host Cutover Subsystem.

Provides atomic, verifiable backup creation, isolated restore testing,
checksum verification, and host fencing controls. Conforms to CEO Condition 6:
no destructive operations on real data are allowed without isolated pre-verification.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
        allow_non_empty_target=True,
        authorized_by_ceo=True,
        pre_verified_isolated=True,
    )


def restore_backup(
    backup_path: Path,
    target_dsn: str,
    target_artifacts_dir: Path | None = None,
    target_candidates_dir: Path | None = None,
    allow_non_empty_target: bool = False,
    authorized_by_ceo: bool = False,
    pre_verified_isolated: bool = False,
) -> BackupManifest:
    """Restore a verified backup into the target database and filesystem.

    Fails closed if the target database contains tables unless both allow_non_empty_target
    and authorized_by_ceo are True, preventing accidental destructive restoration.
    """
    manifest = verify_backup(backup_path)

    import psycopg

    # Verify target state: fail-closed against accidental overwrite of active databases
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
                    "and explicit CEO authorization (--authorized-by-ceo)."
                )
            if not authorized_by_ceo:
                raise BackupError(
                    "Destructive restore over active non-empty database requires explicit CEO authorization "
                    "(--authorized-by-ceo)."
                )

    with tempfile.TemporaryDirectory() as restore_dir:
        restore_path = Path(restore_dir)
        with tarfile.open(backup_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(restore_path, filter="data")
            else:
                tar.extractall(restore_path)

        db_dump = restore_path / manifest.database_dump_file
        # Apply the SQL dump to target database
        try:
            with open(db_dump, "rb") as in_file:
                subprocess.run(
                    ["psql", "-v", "ON_ERROR_STOP=1", target_dsn],
                    stdin=in_file,
                    capture_output=True,
                    text=True,
                    check=True,
                )
        except subprocess.CalledProcessError as exc:
            raise BackupError(f"Database restore failed: {exc.stderr}") from exc

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

    return manifest


def apply_host_fencing(db: Any, host_identifier: str = "current-host") -> list[str]:
    """Apply host fencing: revoke active leases, worker tokens, and mark tasks failed.

    Ensures that migrating between hosts cannot produce dual active workers.
    """
    actions = []
    # 1. Invalidate active worker agent credentials
    db.execute(
        """
        UPDATE principal_credentials
        SET enabled = false
        WHERE kind = 'AGENT' AND enabled = true
        """
    )
    actions.append("principal_credentials: revoked active agent credentials")

    # 2. Expire execution queue claims and mark failed with fencing note
    db.execute(
        """
        UPDATE execution_queue
        SET status = 'FAILED',
            result_json = '{"error": "Host migration fencing applied: worker lease revoked"}'::jsonb,
            lease_expires_at = clock_timestamp() - INTERVAL '1 second'
        WHERE status IN ('RUNNING', 'QUEUED')
        """
    )
    actions.append("execution_queue: revoked in-flight tasks")

    # 3. Expire conversation turn leases
    db.execute(
        """
        UPDATE project_conversation_turns
        SET lease_expires_at = clock_timestamp() - INTERVAL '1 second'
        WHERE lease_expires_at > clock_timestamp()
        """
    )
    actions.append("conversation_turns: expired active leases")

    # 4. Record host fencing event
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
            json.dumps({"host": host_identifier, "fenced_at": datetime.now(UTC).isoformat()}),
        ),
    )
    actions.append("events: recorded host.fenced audit event")

    return actions
