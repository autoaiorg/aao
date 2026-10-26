"""Tests for AAO Operations and Doctor diagnostic CLI."""

from unittest.mock import MagicMock, patch

from aao.ops import (
    check_api_health,
    check_governance_guardrails,
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
