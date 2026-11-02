"""Tests for AAO Operations and Doctor diagnostic CLI."""

import os
import pwd
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from aao.ops import (
    check_api_health,
    check_governance_guardrails,
    check_governance_identities,
    main,
    run_doctor,
)


def test_check_api_health_pass():
    with patch("aao.ops.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = check_api_health("http://127.0.0.1:8001")
        assert result.status == "PASS"
        assert "Responsive" in result.message


def test_check_api_health_warn_on_unreachable():
    result = check_api_health("http://127.0.0.1:59999")
    assert result.status == "WARN"
    assert "not reachable" in result.message


def test_check_governance_guardrails_pass_when_integrator_off():
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "inactive\n"
        mock_run.return_value = mock_res

        result = check_governance_guardrails()
        assert result.status == "PASS"
        assert "Integrator is OFF" in result.message


def test_check_governance_guardrails_fail_when_integrator_active():
    with patch("shutil.which", return_value="/bin/systemctl"), \
         patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.stdout = "active\n"
        mock_run.return_value = mock_res

        result = check_governance_guardrails()
        assert result.status == "FAIL"
        assert "Integrator timer is ACTIVE" in result.message


def test_run_doctor_aggregates_checks():
    checks = run_doctor("http://127.0.0.1:59999")
    assert len(checks) >= 5
    names = {c.name for c in checks}
    assert "PostgreSQL Connection" in names
    assert "Schema Migrations" in names
    assert "API Service" in names
    assert "Control Center Bundle" in names
    assert "Governance Guardrails" in names


def _allow_required_governance_users(monkeypatch):
    monkeypatch.setattr(
        pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=os.getuid())
    )


def test_governance_key_with_fake_pem_headers_is_not_verified(tmp_path, monkeypatch):
    _allow_required_governance_users(monkeypatch)
    fake_key = tmp_path / "fake.pem"
    fake_key.write_text(
        "-----BEGIN RSA PRIVATE KEY-----\nnot a key\n-----END RSA PRIVATE KEY-----\n"
    )
    fake_key.chmod(0o600)

    result = check_governance_identities([fake_key])

    assert result.status == "WARN"
    assert "INSTALLED_UNVERIFIED" in result.message
    assert "cryptographic key parse failed" in result.message


def test_valid_local_pem_is_not_claimed_operational(tmp_path, monkeypatch):
    _allow_required_governance_users(monkeypatch)
    key = tmp_path / "valid.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
         "-out", str(key)],
        check=True, capture_output=True,
    )
    key.chmod(0o600)

    result = check_governance_identities([key])

    assert result.status == "WARN"
    assert "INSTALLED_UNVERIFIED" in result.message
    assert "GitHub App identity, revocation, and live authentication were not verified" in result.message


def test_valid_key_in_replaceable_parent_directory_remains_unverified(tmp_path, monkeypatch):
    _allow_required_governance_users(monkeypatch)
    key_dir = tmp_path / "replaceable"
    key_dir.mkdir(mode=0o700)
    key = key_dir / "app.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
         "-out", str(key)], check=True, capture_output=True,
    )
    key.chmod(0o600)
    key_dir.chmod(0o755)

    result = check_governance_identities([key])

    assert result.status == "WARN"
    assert "INSTALLED_UNVERIFIED" in result.message
    assert "parent directory is not private" in result.message


def test_host_worker_cli_defaults_to_protected_identity(monkeypatch):
    from aao import backup

    monkeypatch.setattr("aao.ops.current_host_id", lambda: "protected-host-id")
    db_context = MagicMock()
    monkeypatch.setattr("aao.ops.connect_postgres", lambda: db_context)
    register = MagicMock()
    monkeypatch.setattr(backup, "register_host_worker", register)

    assert main(["register-host-worker", "--worker-id", "agent-1"]) == 0
    register.assert_called_once_with(
        db_context.__enter__.return_value,
        host_id="protected-host-id",
        worker_id="agent-1",
    )


def test_host_worker_cli_rejects_identity_override(monkeypatch):
    monkeypatch.setattr("aao.ops.current_host_id", lambda: "protected-host-id")
    connect = MagicMock()
    monkeypatch.setattr("aao.ops.connect_postgres", connect)

    assert main([
        "register-host-worker", "--worker-id", "agent-1", "--host-id", "other-host",
    ]) == 1
    connect.assert_not_called()


def test_fence_host_cli_uses_protected_identity_and_rejects_worker_override(monkeypatch):
    from aao import backup

    monkeypatch.setattr("aao.ops.os.geteuid", lambda: 0)
    monkeypatch.setattr("aao.ops.current_host_id", lambda: "protected-host-id")
    monkeypatch.setattr("aao.ops.shutil.which", lambda _name: None)
    monkeypatch.setattr("aao.ops._fencer_database_url", lambda: "postgresql://fencer@localhost/db")
    db_context = MagicMock()
    monkeypatch.setattr("aao.ops.connect_postgres", lambda _dsn: db_context)
    fence = MagicMock(return_value=[])
    monkeypatch.setattr(backup, "apply_host_fencing", fence)

    assert main(["fence-host"]) == 0
    fence.assert_called_once_with(db_context.__enter__.return_value, host_identifier="protected-host-id")

    with pytest.raises(SystemExit):
        main(["fence-host", "--worker-ids", "unbound-worker"])


def test_fence_host_does_not_stop_units_when_database_fencing_fails(monkeypatch):
    from aao import backup

    monkeypatch.setattr("aao.ops.os.geteuid", lambda: 0)
    monkeypatch.setattr("aao.ops.current_host_id", lambda: "protected-host-id")
    monkeypatch.setattr("aao.ops._fencer_database_url", lambda: "postgresql://fencer@localhost/db")
    monkeypatch.setattr("aao.ops.shutil.which", lambda _name: "/usr/bin/systemctl")
    db_context = MagicMock()
    monkeypatch.setattr("aao.ops.connect_postgres", lambda _dsn: db_context)
    monkeypatch.setattr(backup, "apply_host_fencing", MagicMock(side_effect=RuntimeError("denied")))
    run = MagicMock()
    monkeypatch.setattr("aao.ops.subprocess.run", run)

    assert main(["fence-host"]) == 1
    run.assert_not_called()


def test_fence_host_requires_root_before_reading_credentials(monkeypatch):
    monkeypatch.setattr("aao.ops.os.geteuid", lambda: 1000)
    read_dsn = MagicMock()
    monkeypatch.setattr("aao.ops._fencer_database_url", read_dsn)

    assert main(["fence-host"]) == 1
    read_dsn.assert_not_called()


def test_fencer_database_url_requires_private_root_owned_regular_file(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from aao.ops import _fencer_database_url

    env_file = tmp_path / "fencer.env"
    env_file.write_text("AAO_FENCER_POSTGRES_URL=postgresql://fencer@localhost/db\n")
    env_file.chmod(0o600)

    with pytest.raises(RuntimeError, match="root-owned regular file"):
        _fencer_database_url(env_file)

    original_lstat = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda path: SimpleNamespace(st_mode=original_lstat(path).st_mode, st_uid=0)
        if path == env_file else original_lstat(path),
    )
    assert _fencer_database_url(env_file) == "postgresql://fencer@localhost/db"

    env_file.chmod(0o640)
    with pytest.raises(RuntimeError, match="root-owned regular file"):
        _fencer_database_url(env_file)
