"""Tests for AAO backup, verification, isolated restoration, and host fencing."""

import json
import tarfile
from unittest.mock import MagicMock, patch

import pytest

from aao.backup import (
    BackupError,
    BackupManifest,
    apply_host_fencing,
    compute_file_sha256,
    restore_backup,
    verify_backup,
)


def test_compute_file_sha256(tmp_path):
    sample = tmp_path / "test.txt"
    sample.write_text("AAO Backup Verification Test", encoding="utf-8")
    h = compute_file_sha256(sample)
    assert len(h) == 64
    assert h == compute_file_sha256(sample)


def test_verify_backup_valid_bundle(tmp_path):
    # Assemble a valid backup archive manually to test verification
    staging = tmp_path / "staging"
    staging.mkdir()
    dump = staging / "database_dump.sql"
    dump.write_text("SELECT 1;", encoding="utf-8")
    dump_hash = compute_file_sha256(dump)

    manifest = BackupManifest(
        version="1.0.0",
        product_version="0.1.0",
        git_revision="abc1234",
        created_at_utc="2026-10-26T12:00:00Z",
        database_dump_file="database_dump.sql",
        database_dump_sha256=dump_hash,
        schema_migration_version="030_conversation_work_group_results",
        artifacts_included=[],
        file_checksums={"database_dump.sql": dump_hash},
    )
    (staging / "manifest.json").write_text(json.dumps(manifest.__dict__), encoding="utf-8")

    archive = tmp_path / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for f in staging.iterdir():
            tar.add(f, arcname=f.name)

    # Verification should succeed and return the manifest
    verified = verify_backup(archive)
    assert verified.database_dump_file == "database_dump.sql"
    assert verified.git_revision == "abc1234"
    assert verified.schema_migration_version == "030_conversation_work_group_results"


def test_verify_backup_detects_tampered_file(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    dump = staging / "database_dump.sql"
    dump.write_text("SELECT 1;", encoding="utf-8")
    dump_hash = compute_file_sha256(dump)

    manifest = BackupManifest(
        version="1.0.0",
        product_version="0.1.0",
        git_revision="abc1234",
        created_at_utc="2026-10-26T12:00:00Z",
        database_dump_file="database_dump.sql",
        database_dump_sha256=dump_hash,
        schema_migration_version="030",
        artifacts_included=[],
        file_checksums={"database_dump.sql": "fake_bad_checksum_0000000000000000000000000000000000000000000000"},
    )
    (staging / "manifest.json").write_text(json.dumps(manifest.__dict__), encoding="utf-8")

    archive = tmp_path / "bad_backup.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for f in staging.iterdir():
            tar.add(f, arcname=f.name)

    with pytest.raises(BackupError, match="Checksum mismatch"):
        verify_backup(archive)


def test_verify_backup_detects_missing_manifest(tmp_path):
    archive = tmp_path / "empty.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass
    with pytest.raises(BackupError, match="missing manifest.json"):
        verify_backup(archive)


def test_restore_refuses_destructive_target_overwrite(tmp_path):
    archive = tmp_path / "dummy.tar.gz"
    with tarfile.open(archive, "w:gz"):
        pass

    with patch("aao.backup.verify_backup") as mock_verify, \
         patch("psycopg.connect") as mock_connect:
        mock_manifest = MagicMock(database_dump_file="db.sql")
        mock_verify.return_value = mock_manifest

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = [15]  # 15 existing tables in target!

        with pytest.raises(BackupError, match="Refusing destructive restore"):
            restore_backup(archive, "postgresql://user:pass@localhost/live_prod", allow_non_empty_target=False)


def test_apply_host_fencing_revokes_claims_and_leases():
    mock_db = MagicMock()
    actions = apply_host_fencing(mock_db)
    assert len(actions) == 2
    assert any("revoked in-flight tasks" in a for a in actions)
    assert any("expired active leases" in a for a in actions)
    assert mock_db.execute.call_count == 2
