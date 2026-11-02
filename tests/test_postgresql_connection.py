"""Production connection selection must use the explicit runtime DSN."""

import pytest


def test_database_url_does_not_fall_back_to_migration_owner_secret(monkeypatch):
    from aao import postgresql_connection

    monkeypatch.delenv("AAO_POSTGRES_URL", raising=False)
    monkeypatch.delenv("AAO_DATABASE_URL", raising=False)
    monkeypatch.setattr(postgresql_connection, "load_local_env", lambda: None)
    monkeypatch.setattr(postgresql_connection.Path, "is_file", lambda _self: False)

    with pytest.raises(RuntimeError, match="explicit PostgreSQL DSN"):
        postgresql_connection.database_url()
