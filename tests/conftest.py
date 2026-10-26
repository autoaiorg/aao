"""Load explicit local/test environment before pytest evaluates skip markers.

Does not override existing environment values. Production dotenv is disabled.
"""
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
    monkeypatch.setenv("AAO_RESTORE_AUTHORITY_PUBLIC_KEY", str(public_key))
    return private_key
