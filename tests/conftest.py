"""Load explicit local/test environment before pytest evaluates skip markers.

Does not override existing environment values. Production dotenv is disabled.
"""
import os
import subprocess

import pytest

from aao.environment_settings import load_local_env

load_local_env()


@pytest.fixture
def restore_test_signing_key(tmp_path, monkeypatch):
    """Generate issuer-only ephemeral signing material for restore tests."""
    private_key = tmp_path / "restore-test-private.pem"
    public_key = tmp_path / "restore-test-public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private_key)],
        check=True, capture_output=True, timeout=10,
    )
    private_key.chmod(0o600)
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True, capture_output=True, timeout=10,
    )
    public_key.chmod(0o644)
    monkeypatch.setattr("aao.backup.RESTORE_AUTHORITY_PUBLIC_KEY_FILE", public_key)
    monkeypatch.setattr("aao.backup.RESTORE_AUTHORITY_FILE_OWNER_UID", os.geteuid())
    return private_key


@pytest.fixture(autouse=True)
def test_local_host_identity(monkeypatch):
    """Give disposable local tests a deterministic host separate from prod config."""
    monkeypatch.setenv("AAO_TEST_HOST_ID", "integration-test-host")
