"""Unified PostgreSQL migration runner for AAO.

Provides idempotent, transactional execution of schema migrations from db/postgres/
with PostgreSQL advisory locks, SHA-256 integrity verification, and tracking
in the schema_migrations ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIGRATION_PATTERN = re.compile(r"^(\d{3})_(.+)\.sql$")
ADVISORY_LOCK_ID = 84729103  # Fixed cluster-level lock ID for AAO migrations


class MigrationError(RuntimeError):
    """Raised when migration integrity or execution fails."""


@dataclass(frozen=True)
class MigrationFile:
    number: int
    name: str
    stem: str
    path: Path
    sha256: str


@dataclass
class MigrationStatus:
    available_count: int
    applied_count: int
    pending_count: int
    applied_versions: list[str]
    pending_versions: list[str]


def default_migrations_dir() -> Path:
    """Locate the db/postgres directory in the repository."""
    return Path(__file__).resolve().parents[2] / "db" / "postgres"


def compute_sha256(path: Path) -> str:
    """Calculate the hex SHA-256 digest of a file's contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def discover_migrations(migrations_dir: Path | None = None) -> list[MigrationFile]:
    """Scan and return all valid SQL migrations sorted strictly by sequence number."""
    directory = migrations_dir or default_migrations_dir()
    if not directory.is_dir():
        raise MigrationError(f"Migrations directory not found: {directory}")

    discovered: list[MigrationFile] = []
    seen_numbers: set[int] = set()

    for item in sorted(directory.iterdir()):
        if not item.is_file():
            continue
        match = MIGRATION_PATTERN.match(item.name)
        if not match:
            continue
        num = int(match.group(1))
        if num in seen_numbers:
            raise MigrationError(f"Duplicate migration sequence number {num:03d} found in {item.name}")
        seen_numbers.add(num)
        discovered.append(
            MigrationFile(
                number=num,
                name=item.name,
                stem=item.stem,
                path=item,
                sha256=compute_sha256(item),
            )
        )

    # Validate strict sequence without gaps from 1 to N
    for index, migration in enumerate(discovered, start=1):
        if migration.number != index:
            raise MigrationError(
                f"Migration sequence gap detected: expected {index:03d}, found {migration.number:03d} ({migration.name})"
            )

    return discovered


def ensure_schema_migrations_table(connection: Any) -> None:
    """Ensure the schema_migrations ledger exists and has the checksum column."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                checksum VARCHAR(64)
            )
            """
        )
        cursor.execute(
            """
            ALTER TABLE schema_migrations
            ADD COLUMN IF NOT EXISTS checksum VARCHAR(64)
            """
        )


def fetch_applied_migrations(connection: Any) -> dict[str, dict[str, Any]]:
    """Return a mapping of version_stem -> {applied_at, checksum} from schema_migrations."""
    with connection.cursor() as cursor:
        # Check if table exists
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'schema_migrations'
            )
            """
        )
        exists = cursor.fetchone()[0]
        if not exists:
            return {}

        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'schema_migrations'
            """
        )
        columns = {row[0] for row in cursor.fetchall()}
        has_checksum = "checksum" in columns

        query = "SELECT version, applied_at" + (", checksum" if has_checksum else ", NULL") + " FROM schema_migrations"
        cursor.execute(query)
        result: dict[str, dict[str, Any]] = {}
        for row in cursor.fetchall():
            result[row[0]] = {"applied_at": row[1], "checksum": row[2]}
        return result


def check_status(connection: Any, migrations_dir: Path | None = None) -> MigrationStatus:
    """Analyze applied vs available migrations and verify historical integrity."""
    available = discover_migrations(migrations_dir)
    applied = fetch_applied_migrations(connection)

    applied_stems = set(applied.keys())
    applied_versions: list[str] = []
    pending_versions: list[str] = []

    for migration in available:
        if migration.stem in applied_stems:
            applied_versions.append(migration.stem)
            recorded_hash = applied[migration.stem]["checksum"]
            if recorded_hash and recorded_hash != migration.sha256:
                raise MigrationError(
                    f"Integrity violation in migration {migration.name}: "
                    f"recorded SHA-256 {recorded_hash} != current {migration.sha256}"
                )
        else:
            pending_versions.append(migration.stem)

    # Check for foreign versions in the database not recognized in disk migrations
    available_stems = {m.stem for m in available}
    unrecognized = applied_stems - available_stems
    if unrecognized:
        raise MigrationError(
            f"Database contains unrecognized migrations not in catalog: {sorted(unrecognized)}"
        )

    # Fail if an applied migration comes after a pending migration (disordered state)
    if applied_versions and pending_versions:
        last_applied_num = int(applied_versions[-1].split("_")[0])
        first_pending_num = int(pending_versions[0].split("_")[0])
        if last_applied_num > first_pending_num:
            raise MigrationError(
                f"Inconsistent migration state: applied {last_applied_num:03d} "
                f"is greater than pending {first_pending_num:03d}"
            )

    return MigrationStatus(
        available_count=len(available),
        applied_count=len(applied_versions),
        pending_count=len(pending_versions),
        applied_versions=applied_versions,
        pending_versions=pending_versions,
    )


def apply_migrations(
    connection: Any,
    migrations_dir: Path | None = None,
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    """Apply pending migrations sequentially under advisory lock.

    Returns (applied_count, list_of_applied_stems).
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
    try:
        ensure_schema_migrations_table(connection)
        status = check_status(connection, migrations_dir)
        if not status.pending_versions:
            # Backfill checksums for existing applied migrations if missing
            available = {m.stem: m for m in discover_migrations(migrations_dir)}
            applied = fetch_applied_migrations(connection)
            with connection.cursor() as cursor:
                for stem, data in applied.items():
                    if data.get("checksum") is None and stem in available:
                        cursor.execute(
                            "UPDATE schema_migrations SET checksum = %s WHERE version = %s AND checksum IS NULL",
                            (available[stem].sha256, stem),
                        )
            return 0, []

        if dry_run:
            return len(status.pending_versions), status.pending_versions

        available_map = {m.stem: m for m in discover_migrations(migrations_dir)}
        applied_now: list[str] = []

        for stem in status.pending_versions:
            mig = available_map[stem]
            sql_content = mig.path.read_text(encoding="utf-8")

            # Execute the migration script. The script itself wraps operations in BEGIN...COMMIT.
            # We execute it on a cursor with autocommit=True so the script's transactions govern.
            with connection.cursor() as cursor:
                cursor.execute(sql_content)
                # Ensure the checksum is recorded for this version
                cursor.execute(
                    "UPDATE schema_migrations SET checksum = %s WHERE version = %s",
                    (mig.sha256, stem),
                )
            applied_now.append(stem)

        return len(applied_now), applied_now
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))


def run(
    dsn: str,
    action: str = "apply",
    migrations_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    """CLI orchestrator for migration operations."""
    import psycopg

    try:
        # autocommit=True allows the migration scripts' own BEGIN/COMMIT and advisory locks to work cleanly
        with psycopg.connect(dsn, autocommit=True) as conn:
            if action == "status":
                status = check_status(conn, migrations_dir)
                print(f"Total available migrations: {status.available_count}")
                print(f"Applied migrations:         {status.applied_count}")
                print(f"Pending migrations:         {status.pending_count}")
                if status.pending_versions:
                    print("\nPending:")
                    for p in status.pending_versions:
                        print(f"  [ ] {p}")
                return 0

            elif action == "verify":
                status = check_status(conn, migrations_dir)
                if status.pending_count > 0:
                    print(
                        f"FAIL: {status.pending_count} migrations pending application",
                        file=sys.stderr,
                    )
                    return 1
                print(f"PASS: All {status.applied_count} migrations applied and verified.")
                return 0

            elif action == "apply":
                count, applied = apply_migrations(conn, migrations_dir, dry_run=dry_run)
                if dry_run:
                    print(f"DRY RUN: {count} migrations would be applied:")
                    for m in applied:
                        print(f"  -> {m}")
                elif count == 0:
                    print("Schema is up to date. No pending migrations.")
                else:
                    print(f"Successfully applied {count} migrations:")
                    for m in applied:
                        print(f"  [+] {m}")
                return 0

            else:
                print(f"Unknown action: {action}", file=sys.stderr)
                return 2

    except MigrationError as exc:
        print(f"MIGRATION ERROR: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f"DATABASE ERROR: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AAO Unified PostgreSQL Migrator")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_const", const="apply", dest="action", default="apply",
                       help="Apply pending migrations (default)")
    group.add_argument("--status", action="store_const", const="status", dest="action",
                       help="Report migration status")
    group.add_argument("--verify", action="store_const", const="verify", dest="action",
                       help="Verify all migrations are applied and integrity is intact")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without applying")
    parser.add_argument("--dsn", default=os.environ.get("AAO_POSTGRES_URL") or os.environ.get("AAO_TEST_POSTGRES_URL"),
                        help="PostgreSQL DSN (defaults to AAO_POSTGRES_URL or AAO_TEST_POSTGRES_URL)")
    parser.add_argument("--migrations-dir", type=Path, default=None,
                        help="Custom path to migrations directory")

    args = parser.parse_args(argv)
    if not args.dsn:
        print("ERROR: PostgreSQL DSN must be provided via --dsn or AAO_POSTGRES_URL", file=sys.stderr)
        return 1

    return run(args.dsn, action=args.action, migrations_dir=args.migrations_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
