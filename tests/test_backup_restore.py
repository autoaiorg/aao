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
        mock_manifest = MagicMock(database_dump_file="db.sql", git_revision="rev123", database_dump_sha256="sha123")
        mock_verify.return_value = mock_manifest

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = [15]  # 15 existing tables in target!

        with pytest.raises(BackupError, match="Refusing destructive restore"):
            restore_backup(archive, "postgresql://user:pass@localhost/live_prod", allow_non_empty_target=False)


def test_apply_host_fencing_targeted():
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [("worker-node-1",)]
    actions = apply_host_fencing(mock_db, host_identifier="node-1", worker_ids=["worker-node-1"])
    assert any("worker-node-1" in a for a in actions)
    assert any("recorded host.fenced audit event" in a for a in actions)


def test_restore_requires_ceo_authorization_on_non_empty_database(tmp_path, monkeypatch):
    dump_file = tmp_path / "db.sql"
    dump_file.write_text("SELECT 1;", encoding="utf-8")
    archive = tmp_path / "dummy.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dump_file, arcname="db.sql")

    monkeypatch.setenv("AAO_CEO_TOKEN", "valid-ceo-token-1234")

    with patch("aao.backup.verify_backup") as mock_verify, \
         patch("psycopg.connect") as mock_connect, \
         patch("subprocess.run") as mock_run:
        mock_manifest = MagicMock(database_dump_file="db.sql", git_revision="rev123", database_dump_sha256="sha123")
        mock_verify.return_value = mock_manifest

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = mock_cursor
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        def fake_fetchone():
            query = str(mock_cursor.execute.call_args[0][0])
            if "information_schema.tables" in query:
                return [10]
            return [0]

        mock_cursor.fetchone.side_effect = fake_fetchone
        mock_run.return_value = MagicMock(returncode=0)

        # 1. Fail if allow_non_empty_target is False
        with pytest.raises(BackupError, match="Refusing destructive restore"):
            restore_backup(archive, "postgresql://user:pass@localhost/db", allow_non_empty_target=False)

        # 2. Fail if allow_non_empty_target is True but isolated pre-verification is missing
        with pytest.raises(BackupError, match="prior verification in an isolated destination"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                pre_verified_isolated=False,
            )

        # 3. Fail if pre_verified_isolated is True but authorization artifact is missing (token alone is not authorization)
        with pytest.raises(BackupError, match="requires an explicit, pre-issued structured CEO authorization artifact"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                pre_verified_isolated=True,
                ceo_token="valid-ceo-token-1234",
            )

        # 4. Fail if pre_verified_isolated is True but authorization is invalid
        from aao.backup import create_restore_authorization
        bad_auth = create_restore_authorization(archive, "wrong_db", "valid-ceo-token-1234")
        with pytest.raises(BackupError, match="Destructive restore over active non-empty database denied"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                pre_verified_isolated=True,
                restore_authorization=bad_auth,
                ceo_token="valid-ceo-token-1234",
            )

        # 5. Succeed if pre_verified_isolated is True and valid authorization is provided
        valid_auth = create_restore_authorization(archive, "db", "valid-ceo-token-1234")
        manifest = restore_backup(
            archive,
            "postgresql://user:pass@localhost/db",
            allow_non_empty_target=True,
            pre_verified_isolated=True,
            restore_authorization=valid_auth,
            ceo_token="valid-ceo-token-1234",
        )
        assert manifest == mock_manifest


def test_restore_rolls_back_on_partial_failure(tmp_path, monkeypatch):
    """Prove that if psql fails during restore, destination is rolled back to safety snapshot."""
    import subprocess
    dump_file = tmp_path / "db.sql"
    dump_file.write_text("SELECT 1;", encoding="utf-8")
    archive = tmp_path / "dummy.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dump_file, arcname="db.sql")

    monkeypatch.setenv("AAO_CEO_TOKEN", "valid-ceo-token-1234")

    with patch("aao.backup.verify_backup") as mock_verify, \
         patch("psycopg.connect") as mock_connect, \
         patch("subprocess.run") as mock_run:
        mock_manifest = MagicMock(database_dump_file="db.sql", git_revision="rev123", database_dump_sha256="sha123")
        mock_verify.return_value = mock_manifest

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = mock_cursor
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        def fake_fetchone():
            query = str(mock_cursor.execute.call_args[0][0])
            if "information_schema.tables" in query:
                return [10]
            return [0]

        mock_cursor.fetchone.side_effect = fake_fetchone

        call_count = 0
        def fake_run(cmd, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if cmd[0] == "pg_dump":
                return MagicMock(returncode=0)
            elif cmd[0] == "psql" and call_count == 2:
                # First psql call is applying the dump -> simulate error
                raise subprocess.CalledProcessError(1, cmd, stderr="ERROR: syntax error at end of input")
            elif cmd[0] == "psql" and call_count == 3:
                # Second psql call is restoring the safety snapshot -> succeeds
                return MagicMock(returncode=0)
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_run

        from aao.backup import create_restore_authorization
        valid_auth = create_restore_authorization(archive, "db", "valid-ceo-token-1234")
        with pytest.raises(BackupError, match="safely rolled back to original pre-restoration state"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                pre_verified_isolated=True,
                restore_authorization=valid_auth,
                ceo_token="valid-ceo-token-1234",
            )


def test_structured_restore_authorization_verification(tmp_path, monkeypatch):
    """Test full matrix of structured CEO authorization controls (Finding A-08)."""
    dump_file = tmp_path / "db.sql"
    dump_file.write_text("SELECT 1;", encoding="utf-8")
    archive = tmp_path / "target_backup.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dump_file, arcname="db.sql")

    other_archive = tmp_path / "other_backup.tar.gz"
    with tarfile.open(other_archive, "w:gz") as tar:
        tar.add(dump_file, arcname="db.sql")

    ceo_key = "secure-ceo-secret-key-999"
    monkeypatch.setenv("AAO_CEO_TOKEN", ceo_key)

    from aao.backup import create_restore_authorization, verify_destructive_restore_authorization

    # 1. Valid authorization artifact
    valid_auth = create_restore_authorization(archive, "aao_prod", ceo_key, valid_minutes=60)
    ok, msg, nonce = verify_destructive_restore_authorization(None, archive, "aao_prod", valid_auth, ceo_key)
    assert ok is True
    assert nonce is not None

    # 2. Reject mismatched backup archive
    bad_hash_auth = create_restore_authorization(other_archive, "aao_prod", ceo_key)
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", bad_hash_auth, ceo_key)
    assert ok is False
    assert "backup hash mismatch" in msg

    # 3. Reject mismatched target database
    bad_db_auth = create_restore_authorization(archive, "other_db", ceo_key)
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", bad_db_auth, ceo_key)
    assert ok is False
    assert "target database mismatch" in msg

    # 4. Reject expired authorization
    expired_auth = create_restore_authorization(archive, "aao_prod", ceo_key, valid_minutes=-5)
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", expired_auth, ceo_key)
    assert ok is False
    assert "expired" in msg

    # 5. Reject invalid signature
    tampered_auth = dict(valid_auth)
    tampered_auth["ceo_signature"] = "tampered_signature"
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", tampered_auth, ceo_key)
    assert ok is False
    assert "signature verification failed" in msg

    # 6. Reject replay if nonce was already consumed in database
    mock_db = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 0  # 0 rows inserted due to unique constraint collision
    mock_db.execute.return_value = mock_cursor
    ok, msg, _ = verify_destructive_restore_authorization(mock_db, archive, "aao_prod", valid_auth, ceo_key)
    assert ok is False
    assert "already been consumed" in msg or "locked by a concurrent restore" in msg

    # 7. Reject when authorization artifact is omitted entirely (token alone is not authorization)
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", None, ceo_key)
    assert ok is False
    assert "requires an explicit, pre-issued structured CEO authorization artifact" in msg

    # 8. Prove atomic reservation succeeds when nonce is fresh (1 row inserted)
    mock_fresh_db = MagicMock()
    mock_fresh_cursor = MagicMock()
    mock_fresh_cursor.rowcount = 1
    mock_fresh_db.execute.return_value = mock_fresh_cursor
    ok, msg, nonce = verify_destructive_restore_authorization(mock_fresh_db, archive, "aao_prod", valid_auth, ceo_key)
    assert ok is True
    assert nonce is not None


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
