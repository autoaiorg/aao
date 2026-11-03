from __future__ import annotations

import os

import pytest

from aao.workload_api_server import build_config


def test_workload_listener_refuses_non_production(monkeypatch, tmp_path):
    monkeypatch.setenv("AAO_ENV", "development")
    with pytest.raises(RuntimeError, match="AAO_ENV=production"):
        build_config(credentials_dir=str(tmp_path))


def test_workload_listener_refuses_unset_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("AAO_ENV", raising=False)
    with pytest.raises(RuntimeError, match="AAO_ENV=production"):
        build_config(credentials_dir=str(tmp_path))


def test_workload_listener_requires_systemd_credentials(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    with pytest.raises(RuntimeError, match="credential directory"):
        build_config()


def test_workload_listener_requires_all_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("AAO_ENV", "production")
    for name in ("server-cert", "server-key", "client-ca"):
        (tmp_path / name).write_text("placeholder")
    (tmp_path / "client-ca").unlink()

    with pytest.raises(RuntimeError, match="client-ca"):
        build_config(credentials_dir=str(tmp_path))


def test_workload_listener_is_loopback_and_requires_client_certificates(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AAO_ENV", "production")
    for name in ("server-cert", "server-key", "client-ca"):
        (tmp_path / name).write_text("placeholder")

    config = build_config(credentials_dir=str(tmp_path))

    assert config.host == "127.0.0.1"
    assert config.port == 8443
    assert config.http.__name__ == "MtlsH11Protocol"
    assert config.ssl_cert_reqs == 2
    assert config.ssl_ca_certs == os.fspath(tmp_path / "client-ca")
