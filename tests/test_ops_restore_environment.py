from pathlib import Path


def test_restore_uses_environment_for_dsn_values_without_command_arguments(monkeypatch):
    from aao import backup, ops

    archive = Path("/tmp/test-backup.tar.gz")
    target_dsn = "postgresql://target.invalid/restore_target"
    service_dsn = "postgresql://service.invalid/service_database"
    isolated_dsn = "postgresql://isolated.invalid/restore_check"
    calls = {}

    def verify_restore_isolated(path, dsn):
        calls["verify"] = (path, dsn)

    def restore_backup(path, dsn, **kwargs):
        calls["restore"] = (path, dsn, kwargs)
        return type("Manifest", (), {"git_revision": "test-revision"})()

    monkeypatch.setenv("AAO_POSTGRES_URL", service_dsn)
    monkeypatch.setenv("AAO_RESTORE_TARGET_DSN", target_dsn)
    monkeypatch.setenv("AAO_RESTORE_VERIFY_ISOLATED_DSN", isolated_dsn)
    monkeypatch.setattr(backup, "verify_restore_isolated", verify_restore_isolated)
    monkeypatch.setattr(backup, "restore_backup", restore_backup)

    assert ops.main(["restore", str(archive), "--allow-non-empty", "--auth-file", "/tmp/auth.json"]) == 0
    assert "verify" not in calls
    path, dsn, kwargs = calls["restore"]
    assert (path, dsn) == (archive, target_dsn)
    assert kwargs["isolated_dsn"] == isolated_dsn
    assert kwargs["restore_authorization"] == "/tmp/auth.json"
