"""Tests for AAO Operations and Doctor diagnostic CLI."""

import os
import pwd
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from aao.ops import (
    check_api_health,
    check_governance_guardrails,
    check_governance_identities,
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
