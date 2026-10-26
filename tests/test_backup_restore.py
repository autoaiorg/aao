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


@pytest.fixture(autouse=True)
def isolated_authorization_store(tmp_path, monkeypatch):
    """Unit tests inject a local stand-in; production never falls back to it."""
    monkeypatch.setenv("AAO_AUTH_STORE_DIR", str(tmp_path / "authorization-store"))
    from aao.backup import consume_authorization_nonce_host

    monkeypatch.setattr(
        "aao.backup.consume_restore_authorization_nonce",
        lambda nonce, metadata, target_database: consume_authorization_nonce_host(nonce, metadata),
    )


def test_nonce_store_rejects_symlink_and_insecure_directory(tmp_path, monkeypatch):
    from aao.backup import consume_authorization_nonce_host

    real = tmp_path / "real-store"
    real.mkdir(mode=0o700)
    link = tmp_path / "linked-store"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("AAO_AUTH_STORE_DIR", str(link))
    ok, reason = consume_authorization_nonce_host("nonce-1", {"nonce": "nonce-1"})
    assert not ok and "real directory" in reason

    insecure = tmp_path / "insecure-store"
    insecure.mkdir(mode=0o755)
    insecure.chmod(0o755)
    monkeypatch.setenv("AAO_AUTH_STORE_DIR", str(insecure))
    ok, reason = consume_authorization_nonce_host("nonce-2", {"nonce": "nonce-2"})
    assert not ok and "permissions" in reason


def test_nonce_rejects_path_traversal(tmp_path, monkeypatch):
    from aao.backup import consume_authorization_nonce_host

    monkeypatch.setenv("AAO_AUTH_STORE_DIR", str(tmp_path / "authority"))
    ok, reason = consume_authorization_nonce_host("../outside", {"nonce": "../outside"})
    assert not ok and "invalid characters" in reason


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


def test_restore_rejects_target_as_its_own_isolation_database(tmp_path):
    archive = tmp_path / "dummy.tar.gz"
    archive.write_bytes(b"unused")
    with patch("aao.backup.verify_backup"), pytest.raises(
        BackupError, match="different database from the restore target"
    ):
        restore_backup(
            archive,
            "postgresql://user:pass@localhost/live_prod",
            allow_non_empty_target=True,
            isolated_dsn="postgresql://user:pass@localhost/live_prod",
        )


def test_apply_host_fencing_targeted():
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [("worker-node-1",)]
    actions = apply_host_fencing(mock_db, host_identifier="node-1", worker_ids=["worker-node-1"])
    assert any("worker-node-1" in a for a in actions)
    assert any("recorded host.fenced audit event" in a for a in actions)


def test_restore_requires_ceo_authorization_on_non_empty_database(tmp_path, monkeypatch, restore_test_signing_key):
    dump_file = tmp_path / "db.sql"
    dump_file.write_text("SELECT 1;", encoding="utf-8")
    archive = tmp_path / "dummy.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dump_file, arcname="db.sql")

    from aao.backup import create_restore_authorization
    bad_auth = create_restore_authorization(archive, "wrong_db", restore_test_signing_key)
    valid_auth = create_restore_authorization(archive, "db", restore_test_signing_key)

    monkeypatch.setenv("AAO_CEO_TOKEN", "valid-ceo-token-1234")

    with patch("aao.backup.verify_backup") as mock_verify, \
         patch("aao.backup.verify_restore_isolated"), \
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

        # The former public boolean was an unsafe caller-controlled bypass.
        with pytest.raises(TypeError, match="pre_verified_isolated"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                pre_verified_isolated=True,
            )

        # 2. Fail if allow_non_empty_target is True but isolated pre-verification is missing
        with pytest.raises(BackupError, match="prior verification in an isolated destination"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
            )

        # 3. An isolated dry run does not replace signed authorization.
        with pytest.raises(BackupError, match="Separation of duties violation"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                isolated_dsn="postgresql://user:pass@localhost/isolated",
                ceo_token="valid-ceo-token-1234",
            )

        # 4. Fail if isolated verification is complete but authorization is invalid.
        with pytest.raises(BackupError, match="Destructive restore over active non-empty database denied"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                isolated_dsn="postgresql://user:pass@localhost/isolated",
                restore_authorization=bad_auth,
                ceo_token="valid-ceo-token-1234",
            )

        # 5. Succeed if isolated verification and valid authorization are provided.
        manifest = restore_backup(
            archive,
            "postgresql://user:pass@localhost/db",
            allow_non_empty_target=True,
            isolated_dsn="postgresql://user:pass@localhost/isolated",
            restore_authorization=valid_auth,
            ceo_token="valid-ceo-token-1234",
        )
        assert manifest == mock_manifest


def test_restore_rolls_back_on_partial_failure(tmp_path, monkeypatch, restore_test_signing_key):
    """Prove that if psql fails during restore, destination is rolled back to safety snapshot."""
    import subprocess
    real_run = subprocess.run
    dump_file = tmp_path / "db.sql"
    dump_file.write_text("SELECT 1;", encoding="utf-8")
    archive = tmp_path / "dummy.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dump_file, arcname="db.sql")

    from aao.backup import create_restore_authorization
    valid_auth = create_restore_authorization(archive, "db", restore_test_signing_key)

    monkeypatch.setenv("AAO_CEO_TOKEN", "valid-ceo-token-1234")

    with patch("aao.backup.verify_backup") as mock_verify, \
         patch("aao.backup.verify_restore_isolated"), \
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
            if cmd[0] == "openssl":
                return real_run(cmd, *args, **kwargs)
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

        with pytest.raises(BackupError, match="safely rolled back to original pre-restoration state"):
            restore_backup(
                archive,
                "postgresql://user:pass@localhost/db",
                allow_non_empty_target=True,
                isolated_dsn="postgresql://user:pass@localhost/isolated",
                restore_authorization=valid_auth,
                ceo_token="valid-ceo-token-1234",
            )


def test_structured_restore_authorization_verification(tmp_path, monkeypatch, restore_test_signing_key):
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

    from aao import backup as backup_module
    from aao.backup import create_restore_authorization, verify_destructive_restore_authorization

    # 1. Valid authorization artifact
    valid_auth = create_restore_authorization(archive, "aao_prod", restore_test_signing_key, valid_minutes=60)
    with pytest.raises(BackupError, match="private regular file"):
        create_restore_authorization(
            archive, "aao_prod", backup_module.RESTORE_AUTHORITY_PUBLIC_KEY_FILE
        )
    ok, msg, nonce = verify_destructive_restore_authorization(None, archive, "aao_prod", valid_auth, ceo_key)
    assert ok is True
    assert nonce is not None

    # 2. Reject mismatched backup archive
    bad_hash_auth = create_restore_authorization(other_archive, "aao_prod", restore_test_signing_key)
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", bad_hash_auth, ceo_key)
    assert ok is False
    assert "backup hash mismatch" in msg

    # 3. Reject mismatched target database
    bad_db_auth = create_restore_authorization(archive, "other_db", restore_test_signing_key)
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", bad_db_auth, ceo_key)
    assert ok is False
    assert "target database mismatch" in msg

    # 4. Reject expired authorization
    with pytest.raises(BackupError, match="1 to 60 minutes"):
        create_restore_authorization(archive, "aao_prod", restore_test_signing_key, valid_minutes=-5)

    # 5. Reject invalid signature
    tampered_auth = dict(valid_auth)
    tampered_auth["ceo_signature"] = "tampered_signature"
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", tampered_auth, ceo_key)
    assert ok is False
    assert "signature verification failed" in msg

    # An independently generated executor key cannot issue artifacts trusted by
    # the configured authority's public verification key.
    import subprocess
    executor_key = tmp_path / "executor-private.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(executor_key)],
        check=True, capture_output=True, timeout=10,
    )
    executor_key.chmod(0o600)
    forged = create_restore_authorization(archive, "aao_prod", executor_key)
    executor_public_key = tmp_path / "executor-public.pem"
    subprocess.run(
        ["openssl", "pkey", "-in", str(executor_key), "-pubout", "-out", str(executor_public_key)],
        check=True, capture_output=True, timeout=10,
    )
    monkeypatch.setenv("AAO_RESTORE_AUTHORITY_PUBLIC_KEY", str(executor_public_key))
    monkeypatch.setenv("AAO_RESTORE_AUTHORITY_ID", "executor-controlled-identity")
    ok, msg, _ = verify_destructive_restore_authorization(None, archive, "aao_prod", forged, ceo_key)
    assert ok is False
    assert "signature verification failed" in msg

    missing_issuer = dict(valid_auth)
    missing_issuer.pop("authority_id")
    ok, msg, _ = verify_destructive_restore_authorization(
        None, archive, "aao_prod", missing_issuer, ceo_key,
    )
    assert ok is False
    assert "issuer identity" in msg

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
    assert "Separation of duties violation" in msg

    # 8. Prove atomic reservation succeeds when nonce is fresh
    fresh_auth = create_restore_authorization(archive, "aao_prod", restore_test_signing_key, valid_minutes=60)
    mock_fresh_db = MagicMock()
    mock_fresh_cursor = MagicMock()
    mock_fresh_cursor.rowcount = 1
    mock_fresh_db.execute.return_value = mock_fresh_cursor
    ok, msg, nonce = verify_destructive_restore_authorization(mock_fresh_db, archive, "aao_prod", fresh_auth, ceo_key)
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
