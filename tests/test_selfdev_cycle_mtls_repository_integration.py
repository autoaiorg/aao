"""Concurrency and lifecycle tests against the explicit disposable PG database."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)


@pytest.fixture(params=["AGENT", "AUDITOR"])
def seeded_intent(monkeypatch, request):
    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls import CycleSigningIntent

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    suffix = uuid.uuid4().hex
    cycle = suffix[:32]
    project_id, principal_id, owned_project = _project_and_principal(suffix, request.param)
    now = datetime.now(UTC).replace(microsecond=0)
    intent = CycleSigningIntent(
        intent_id=uuid.uuid4(),
        project_id=project_id,
        cycle_id=cycle,
        principal_id=principal_id,
        kind=request.param,
        not_before=now - timedelta(seconds=1),
        not_after=now + timedelta(minutes=30),
    )
    yield intent
    with connect_postgres() as db:
        db.execute("DELETE FROM workload_identity_bindings WHERE intent_id=%s", (intent.intent_id,))
        db.execute("DELETE FROM selfdev_cycle_mtls_intents WHERE intent_id=%s", (intent.intent_id,))
        db.execute("DELETE FROM principal_credentials WHERE principal_id=%s", (principal_id,))
        if owned_project:
            mandate_id = db.execute(
                "DELETE FROM projects WHERE id=%s RETURNING mandate_id", (project_id,)
            ).fetchone()[0]
            db.execute("DELETE FROM mandates WHERE id=%s", (mandate_id,))


def _project_and_principal(suffix, kind):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token

    with connect_postgres() as db:
        row = db.execute(
            "SELECT id FROM projects WHERE name='AAO — Self Development' AND state='ACTIVE'"
        ).fetchone()
        if row:
            project_id, owned_project = row[0], False
        else:
            mandate_id, project_id = uuid.uuid4(), uuid.uuid4()
            db.execute(
                "INSERT INTO mandates(id,title,objective,status,confirmed_by) VALUES (%s,%s,%s,'CONFIRMED','integration-test')",
                (mandate_id, "mTLS repository integration test", "disposable"),
            )
            db.execute(
                "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,'AAO — Self Development',%s,'ACTIVE')",
                (project_id, mandate_id),
            )
            owned_project = True
        prefix = "aao-selfdev-review-" if kind == "AUDITOR" else "aao-selfdev-impl-"
        principal_id = f"{prefix}{suffix[:32]}"
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) VALUES (%s,%s,%s,false)",
            (principal_id, kind, digest_token("not-used-test-token-" + suffix)),
        )
    return project_id, principal_id, owned_project


def test_create_intent_replay_and_concurrent_completion_are_idempotent(seeded_intent):
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    intent = repo.create_intent(seeded_intent)
    assert repo.create_intent(seeded_intent) == intent
    assert repo.get_pending_intent(intent.intent_id) == intent

    barrier = threading.Barrier(8)

    def complete(_):
        barrier.wait(timeout=10)
        repo.complete_binding(intent, "a" * 64, "b" * 64)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(complete, range(8)))
    assert repo.get_completed_binding(intent.intent_id) == ("a" * 64, "b" * 64)
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM workload_identity_bindings WHERE intent_id=%s",
                (intent.intent_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT enabled FROM principal_credentials WHERE principal_id=%s",
                (intent.principal_id,),
            ).fetchone()[0]
            is True
        )


def test_concurrent_identical_intent_creation_is_idempotent(seeded_intent):
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    barrier = threading.Barrier(8)

    def create(_):
        barrier.wait(timeout=10)
        return repo.create_intent(seeded_intent)

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(result == seeded_intent for result in pool.map(create, range(8)))


def test_completion_waits_for_intent_row_lock_before_commit(seeded_intent):
    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    repo.create_intent(seeded_intent)
    pool = ThreadPoolExecutor(max_workers=1)
    with connect_postgres() as blocker:
        blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
        blocker.execute(
            "SELECT intent_id FROM selfdev_cycle_mtls_intents WHERE intent_id=%s FOR UPDATE",
            (seeded_intent.intent_id,),
        )
        future = pool.submit(repo.complete_binding, seeded_intent, "a" * 64, "b" * 64)
        blocked = False
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            blocker.execute("SELECT pg_stat_clear_snapshot()")
            pids = blocker.execute(
                "SELECT pid,wait_event_type,wait_event,query FROM pg_stat_activity "
                "WHERE wait_event_type='Lock' AND %s=ANY(pg_blocking_pids(pid))",
                (blocker_pid,),
            ).fetchall()
            if pids:
                blocked = True
                break
            time.sleep(0.02)
        assert blocked, "completion did not wait on the held intent row lock"
        # Leaving the context commits/releases the row lock; the worker then
        # completes normally. Await only after release to avoid deadlocking.
    future.result(timeout=5)
    pool.shutdown(wait=True)
    assert repo.get_completed_binding(seeded_intent.intent_id) == ("a" * 64, "b" * 64)


def test_expired_intent_cannot_be_loaded_or_completed(seeded_intent):
    from dataclasses import replace

    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls import CycleMtlError
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    old = replace(
        seeded_intent,
        not_before=datetime.now(UTC) - timedelta(hours=1),
        not_after=datetime.now(UTC) - timedelta(seconds=1),
    )
    repo.create_intent(old)
    assert repo.get_pending_intent(old.intent_id) is None
    with pytest.raises(CycleMtlError, match="no longer pending"):
        repo.complete_binding(old, "c" * 64, "d" * 64)
    with connect_postgres() as db:
        assert (
            db.execute(
                "SELECT state FROM selfdev_cycle_mtls_intents WHERE intent_id=%s", (old.intent_id,)
            ).fetchone()[0]
            == "EXPIRED"
        )


def test_revoke_disables_binding_and_principal_atomically(seeded_intent):
    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    intent = repo.create_intent(seeded_intent)
    repo.complete_binding(intent, "e" * 64, "f" * 64)
    assert repo.revoke(intent.intent_id) is True
    assert repo.revoke(intent.intent_id) is True
    assert repo.get_completed_binding(intent.intent_id) is None
    with connect_postgres() as db:
        assert db.execute(
            "SELECT enabled,revoked_at IS NOT NULL FROM workload_identity_bindings WHERE intent_id=%s",
            (intent.intent_id,),
        ).fetchone() == (False, True)
        assert (
            db.execute(
                "SELECT enabled FROM principal_credentials WHERE principal_id=%s",
                (intent.principal_id,),
            ).fetchone()[0]
            is False
        )
