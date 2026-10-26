import pytest

from aao.host_identity import HostIdentityError, current_host_id


def test_test_host_identity_is_isolated_from_production(monkeypatch, tmp_path):
    monkeypatch.setenv("AAO_TEST_HOST_ID", "test-host-a")
    monkeypatch.setenv("AAO_ENV", "test")
    assert current_host_id() == "test-host-a"

    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setattr("aao.host_identity.HOST_ID_FILE", tmp_path / "missing-host-id")
    with pytest.raises(HostIdentityError):
        current_host_id()


@pytest.mark.parametrize("value", ["", "x" * 256, "host\nattacker"])
def test_test_host_identity_rejects_malformed_values(monkeypatch, value):
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_TEST_HOST_ID", value)
    with pytest.raises(HostIdentityError):
        current_host_id()


def test_host_identity_rejects_embedded_null():
    from aao.host_identity import _validate

    with pytest.raises(HostIdentityError):
        _validate("host\x00id")
