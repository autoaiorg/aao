import base64
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from scripts import manage_workload_identity_binding as binding


def test_certificate_fingerprint_accepts_one_public_pem(tmp_path):
    der = b"small public certificate fixture"
    encoded = base64.b64encode(der).decode("ascii")
    path = tmp_path / "client.pem"
    path.write_text(
        f"-----BEGIN CERTIFICATE-----\n{encoded}\n-----END CERTIFICATE-----\n",
        encoding="ascii",
    )

    assert binding.certificate_fingerprint(path) == binding.hashlib.sha256(der).hexdigest()


@pytest.mark.parametrize(
    "contents",
    [
        b"-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
        b"-----BEGIN CERTIFICATE-----\nnot-base64!\n-----END CERTIFICATE-----\n",
        (
            b"-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----\n"
            b"-----BEGIN CERTIFICATE-----\nZGVm\n-----END CERTIFICATE-----\n"
        ),
    ],
)
def test_certificate_fingerprint_rejects_private_malformed_or_multiple_pems(tmp_path, contents):
    path = tmp_path / "bad.pem"
    path.write_bytes(contents)

    with pytest.raises(binding.BindingError):
        binding.certificate_fingerprint(path)


def test_certificate_fingerprint_rejects_symlink(tmp_path):
    target = tmp_path / "target.pem"
    target.write_text("not a certificate", encoding="ascii")
    link = tmp_path / "client.pem"
    link.symlink_to(target)

    with pytest.raises(binding.BindingError, match="safely"):
        binding.certificate_fingerprint(link)


def test_parse_expiry_requires_future_timezone_aware_timestamp():
    with pytest.raises(binding.BindingError, match="timezone"):
        binding.parse_expiry("2030-01-01T00:00:00")
    with pytest.raises(binding.BindingError, match="future"):
        binding.parse_expiry("2000-01-01T00:00:00Z")


def test_bind_creates_audited_binding_for_enabled_agent(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []
            self.result = None

        def execute(self, sql, params):
            self.calls.append((sql, params))
            if "FROM principal_credentials" in sql:
                self.result = ("AGENT", True, None)
            elif "FROM workload_identity_bindings" in sql:
                self.result = None
            else:
                self.result = None
            return self

        def fetchone(self):
            return self.result

    cursor = Cursor()

    @contextmanager
    def connect():
        yield cursor

    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(binding, "connect_postgres", connect)
    expires = datetime.now(UTC) + timedelta(hours=1)

    assert binding.bind("agent-1", "a" * 64, expires) is True
    assert any("INSERT INTO workload_identity_bindings" in sql for sql, _ in cursor.calls)
    assert any(
        "principal.workload_identity.bound" in params
        for _, params in cursor.calls
        if isinstance(params, (tuple, list))
    )


def test_bind_rejects_nonproduction_before_database(monkeypatch):
    def database_access_is_forbidden():
        raise AssertionError("non-production mode must fail before database access")

    monkeypatch.setenv("AAO_ENV", "development")
    monkeypatch.setattr(binding, "connect_postgres", database_access_is_forbidden)
    with pytest.raises(binding.BindingError, match="production mode"):
        binding.bind("agent-1", "a" * 64, datetime.now(UTC) + timedelta(hours=1))


def test_revoke_disables_only_active_binding_and_audits(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []
            self.result = ("agent-1",)

        def execute(self, sql, params):
            self.calls.append((sql, params))
            return self

        def fetchone(self):
            return self.result

    cursor = Cursor()

    @contextmanager
    def connect():
        yield cursor

    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr(binding, "connect_postgres", connect)

    assert binding.revoke("b" * 64) == "agent-1"
    assert any(
        "enabled=false" in sql and "revoked_at=clock_timestamp()" in sql for sql, _ in cursor.calls
    )
    assert any(
        "principal.workload_identity.revoked" in params
        for _, params in cursor.calls
        if isinstance(params, (tuple, list))
    )
