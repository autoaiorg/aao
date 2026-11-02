"""Real PostgreSQL checks for restore anti-replay durability.

Requires a disposable authority database pre-provisioned with
db/postgres/restore_authority/001_consumed_restore_authorizations.sql.
"""

from __future__ import annotations

import multiprocessing
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


def _configure_authority(monkeypatch, tmp_path):
    assert AUTHORITY_DSN is not None
    config = tmp_path / "restore-authority.database-url"
    config.write_text(AUTHORITY_DSN, encoding="utf-8")
    config.chmod(0o600)
    monkeypatch.setattr("aao.backup.RESTORE_AUTHORITY_DATABASE_URL_FILE", config)
    monkeypatch.setattr("aao.backup.RESTORE_AUTHORITY_FILE_OWNER_UID", os.geteuid())


def _consume_in_process(nonce: str, target_database: str, start_event, results) -> None:
    start_event.wait(timeout=10)
    results.put(consume_restore_authorization_nonce(nonce, _metadata(nonce), target_database))


def test_postgres_nonce_is_atomic_across_processes_and_persistent(monkeypatch, tmp_path):
    assert AUTHORITY_DSN is not None
    _configure_authority(monkeypatch, tmp_path)
    with psycopg.connect(AUTHORITY_DSN) as conn:
        target_database = f"not_{conn.execute('SELECT current_database()').fetchone()[0]}"
        assert conn.execute("SELECT current_setting('fsync'), current_setting('synchronous_commit')").fetchone() == ("on", "on")

    nonce = f"integration-{uuid.uuid4().hex}"
    ctx = multiprocessing.get_context("fork")
    start_event = ctx.Event()
    results = ctx.Queue()
    workers = [ctx.Process(target=_consume_in_process, args=(nonce, target_database, start_event, results)) for _ in range(8)]
    for worker in workers:
        worker.start()
    start_event.set()
    outcomes = [results.get(timeout=15) for _ in workers]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0
    results.close()

    assert sum(ok for ok, _ in outcomes) == 1
    assert sum(not ok for ok, _ in outcomes) == 7
    # A new connection/transaction sees the durable reservation and denies replay.
    replay_ok, replay_message = consume_restore_authorization_nonce(nonce, _metadata(nonce), target_database)
    assert replay_ok is False
    assert "already been consumed" in replay_message


def test_postgres_nonce_consumer_fails_closed_without_authority_or_for_same_database(monkeypatch, tmp_path):
    ok, message = consume_restore_authorization_nonce("missing-config", _metadata("missing-config"), "target")
    assert not ok
    assert "configuration is unavailable" in message

    assert AUTHORITY_DSN is not None
    _configure_authority(monkeypatch, tmp_path)
    with psycopg.connect(AUTHORITY_DSN) as conn:
        current_database = conn.execute("SELECT current_database()").fetchone()[0]
    ok, message = consume_restore_authorization_nonce(
        f"same-db-{uuid.uuid4().hex}", _metadata("same-db"), current_database,
    )
    assert not ok
    assert "must differ" in message
