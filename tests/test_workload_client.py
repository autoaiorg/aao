import pytest

from aao.workload_client import (
    WorkloadTransportError,
    validate_workload_origin,
    workload_headers,
)


def test_production_requires_https_and_never_emits_bearer(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", "/systemd/credentials")

    validate_workload_origin("https://127.0.0.1:8443")
    assert workload_headers("must-not-be-sent") == {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with pytest.raises(WorkloadTransportError, match="must use HTTPS"):
        validate_workload_origin("http://127.0.0.1:8001")


def test_production_fails_closed_without_systemd_credentials(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)

    with pytest.raises(WorkloadTransportError, match="credentials are unavailable"):
        workload_headers("must-not-be-sent")


def test_development_keeps_private_bearer_auth_and_loopback_http(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "development")

    validate_workload_origin("http://127.0.0.1:8001")
    assert workload_headers("dev-token") == {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Agent-Token": "dev-token",
    }


def test_non_loopback_http_is_never_allowed(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "development")

    with pytest.raises(WorkloadTransportError, match="unless it targets localhost"):
        validate_workload_origin("http://192.0.2.10:8001")
