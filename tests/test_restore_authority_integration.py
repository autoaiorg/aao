"""Real PostgreSQL checks for restore anti-replay durability.

Requires a disposable authority database pre-provisioned with
db/postgres/restore_authority/001_consumed_restore_authorizations.sql.
"""

from __future__ import annotations

import concurrent.futures
import os
import uuid

import psycopg
import pytest

from aao.backup import consume_restore_authorization_nonce

AUTHORITY_DSN = os.getenv("AAO_TEST_RESTORE_AUTHORITY_URL")
pytestmark = pytest.mark.skipif(
    not AUTHORITY_DSN or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="requires explicitly disposable, provisioned PostgreSQL restore-authority DB",
)


def _metadata(nonce: str) -> dict[str, str]:
    return {
        "nonce": nonce,
        "action": "database.destructive_restore",
        "authority_id": "integration-test-authority",
        "backup_sha256": "a" * 64,
    }


def test_postgres_nonce_is_atomic_and_persistent(monkeypatch):
    assert AUTHORITY_DSN is not None
    monkeypatch.setenv("AAO_RESTORE_AUTHORITY_DATABASE_URL", AUTHORITY_DSN)
    with psycopg.connect(AUTHORITY_DSN) as conn:
        target_database = f"not_{conn.execute('SELECT current_database()').fetchone()[0]}"
        assert conn.execute("SELECT current_setting('fsync'), current_setting('synchronous_commit')").fetchone() == ("on", "on")

    nonce = f"integration-{uuid.uuid4().hex}"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: consume_restore_authorization_nonce(nonce, _metadata(nonce), target_database), range(8)))

    assert sum(ok for ok, _ in outcomes) == 1
    assert sum(not ok for ok, _ in outcomes) == 7
    # A new connection/transaction sees the durable reservation and denies replay.
    replay_ok, replay_message = consume_restore_authorization_nonce(nonce, _metadata(nonce), target_database)
    assert replay_ok is False
    assert "already been consumed" in replay_message


def test_postgres_nonce_consumer_fails_closed_without_authority_or_for_same_database(monkeypatch):
    monkeypatch.delenv("AAO_RESTORE_AUTHORITY_DATABASE_URL", raising=False)
    ok, message = consume_restore_authorization_nonce("missing-config", _metadata("missing-config"), "target")
    assert not ok
    assert "not configured" in message

    assert AUTHORITY_DSN is not None
    monkeypatch.setenv("AAO_RESTORE_AUTHORITY_DATABASE_URL", AUTHORITY_DSN)
    with psycopg.connect(AUTHORITY_DSN) as conn:
        current_database = conn.execute("SELECT current_database()").fetchone()[0]
    ok, message = consume_restore_authorization_nonce(
        f"same-db-{uuid.uuid4().hex}", _metadata("same-db"), current_database,
    )
    assert not ok
    assert "must differ" in message
