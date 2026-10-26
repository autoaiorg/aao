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
    actions = apply_host_fencing(mock_db, host_identifier="node-1")
    assert len(actions) == 4
    assert any("revoked active agent credentials" in a for a in actions)
    assert any("revoked in-flight tasks" in a for a in actions)
    assert any("expired active leases" in a for a in actions)
    assert any("recorded host.fenced audit event" in a for a in actions)
    assert mock_db.execute.call_count == 4


def test_restore_requires_ceo_authorization_on_non_empty_database(tmp_path):
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
        mock_cursor.fetchone.return_value = [10]  # 10 tables exist

        # Fail if allow_non_empty_target is False
        with pytest.raises(BackupError, match="Refusing destructive restore"):
            restore_backup(archive, "postgresql://user:pass@localhost/db", allow_non_empty_target=False)

        # Fail if allow_non_empty_target is True but authorized_by_ceo is False
        with pytest.raises(BackupError, match="requires explicit CEO authorization"):
            restore_backup(archive, "postgresql://user:pass@localhost/db", allow_non_empty_target=True, authorized_by_ceo=False)


def test_backup_includes_candidate_repository(tmp_path, monkeypatch):
    cand_repo = tmp_path / "candidates.git"
    cand_repo.mkdir()
    (cand_repo / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    monkeypatch.setenv("AAO_CANDIDATE_REPOSITORY", str(cand_repo))

    out_dir = tmp_path / "backups"
    with patch("aao.backup.connect_postgres") as mock_conn, \
         patch("aao.backup.get_git_revision", return_value="deadbeef1234"), \
         patch("subprocess.run") as mock_run:
        mock_conn.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = ["030_version"]
        mock_run.return_value = MagicMock(returncode=0)
        from aao.backup import create_backup
        bundle = create_backup(out_dir, database_url="postgresql://user:pass@localhost/db")

        manifest = verify_backup(bundle)
        assert any("candidates.git/HEAD" in a for a in manifest.artifacts_included)
