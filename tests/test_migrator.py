"""Unit and integration tests for the unified PostgreSQL migrator."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aao.migrator import (
    MigrationError,
    apply_migrations,
    check_status,
    compute_sha256,
    discover_migrations,
    run,
)


def test_discover_migrations_finds_ordered_sql_files():
    migrations = discover_migrations()
    assert len(migrations) >= 30
    assert migrations[0].number == 1
    assert migrations[0].stem == "001_foundation"
    assert migrations[-1].number == len(migrations)
    for idx, mig in enumerate(migrations, start=1):
        assert mig.number == idx
        assert mig.path.is_file()
        assert len(mig.sha256) == 64


def test_discover_migrations_rejects_gaps():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "001_initial.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp_path / "003_skip.sql").write_text("SELECT 1;", encoding="utf-8")
        with pytest.raises(MigrationError, match="sequence gap detected: expected 002"):
            discover_migrations(tmp_path)


def test_discover_migrations_rejects_duplicates():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "001_initial.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp_path / "001_dup.sql").write_text("SELECT 1;", encoding="utf-8")
        with pytest.raises(MigrationError, match="Duplicate migration sequence number 001"):
            discover_migrations(tmp_path)


def test_check_status_detects_tampered_migration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        f1 = tmp_path / "001_first.sql"
        f1.write_text("SELECT 1;", encoding="utf-8")
        compute_sha256(f1)

        # Mock connection where 001 is applied but has a different checksum
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = [True]  # table exists
        mock_cursor.fetchall.side_effect = [
            [("version",), ("applied_at",), ("checksum",)],  # columns
            [("001_first", "2026-01-01T00:00:00Z", "bad_hash_1234567890")],  # rows
        ]

        with pytest.raises(MigrationError, match="Integrity violation in migration 001_first"):
            check_status(mock_conn, tmp_path)


def test_check_status_detects_unrecognized_database_migration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        f1 = tmp_path / "001_first.sql"
        f1.write_text("SELECT 1;", encoding="utf-8")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = [True]
        mock_cursor.fetchall.side_effect = [
            [("version",), ("applied_at",), ("checksum",)],
            [("001_first", "2026-01-01", compute_sha256(f1)),
             ("999_foreign_migration", "2026-01-01", "hash")],
        ]

        with pytest.raises(MigrationError, match="unrecognized migrations not in catalog"):
            check_status(mock_conn, tmp_path)


def test_live_postgres_migrator_status_and_verify():
    dsn = os.environ.get("AAO_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("AAO_TEST_POSTGRES_URL not set")

    # Status should return 0
    assert run(dsn, action="status") == 0
    # Verify should return 0 since all 30 migrations are applied
    assert run(dsn, action="verify") == 0
    # Apply again should be 0 (idempotent)
    assert run(dsn, action="apply") == 0


def test_legacy_unverified_migration_transition_without_fabricated_checksum(tmp_path):
    """Test that migrations applied without checksum tracking remain legacy unverified and are not falsely backfilled."""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_initial.sql").write_text("CREATE TABLE test (id INT);", encoding="utf-8")

    class FakeCursor:
        def __init__(self):
            self.queries = []
            self.schema_exists = True
            self.has_checksum_col = True
            self.applied_rows = [("001_initial", "2026-01-01", None)]  # NULL checksum (legacy)

        def execute(self, query, params=None):
            self.queries.append((query, params))

        def fetchone(self):
            # First query checks if schema_migrations exists
            return (True,)

        def fetchall(self):
            last_query = self.queries[-1][0].strip()
            if "information_schema.columns" in last_query:
                return [("version",), ("applied_at",), ("checksum",)]
            if "FROM schema_migrations" in last_query:
                return self.applied_rows
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeConnection:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

    conn = FakeConnection()
    status = check_status(conn, mig_dir)

    assert status.applied_count == 1
    assert status.pending_count == 0
    assert status.legacy_unverified_versions == ["001_initial"]
    assert status.verified_versions == []

    # Applying when all are applied must NOT backfill or execute UPDATE
    count, applied = apply_migrations(conn, mig_dir)
    assert count == 0
    assert applied == []
    # Verify no UPDATE query was executed to fabricate a backfilled checksum
    update_queries = [q for q, _ in conn.cursor_obj.queries if "UPDATE schema_migrations" in q]
    assert len(update_queries) == 0
