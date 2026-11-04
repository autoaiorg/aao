"""Concurrency and lifecycle tests against the explicit disposable PG database."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

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


@pytest.fixture
def runtime_role(monkeypatch):
    """Provision the disposable cluster role so ACL tests cannot silently pass."""
    import psycopg

    from aao.postgresql_connection import connect_postgres

    dsn = os.environ["AAO_TEST_POSTGRES_URL"]
    monkeypatch.setenv("AAO_POSTGRES_URL", dsn)
    with connect_postgres() as db:
        exists = db.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aao_runtime')"
        ).fetchone()[0]
        created = not exists
        if not exists:
            db.execute("CREATE ROLE aao_runtime NOLOGIN")
    # The migration is deliberately rerun after role creation: migrations must
    # grant only the bounded API functions, and tests must observe real ACLs.
    migration = Path(__file__).parents[1] / "db/postgres/046_selfdev_cycle_mtls_intents.sql"
    with connect_postgres() as db:
        db.execute(migration.read_text())
        db.commit()
    yield
    if created:
        with connect_postgres() as db:
            db.execute("DROP OWNED BY aao_runtime")
            db.commit()
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute("DROP ROLE aao_runtime")


def test_real_migrator_accepts_legacy_045_ledger_and_applies_current_045_046(monkeypatch):
    """Exercise the actual migrator against a cloned disposable legacy ledger."""
    import psycopg
    from psycopg.conninfo import make_conninfo

    from aao.migrator import apply_migrations, check_status

    base_dsn = os.environ["AAO_TEST_POSTGRES_URL"]
    monkeypatch.setenv("AAO_POSTGRES_URL", base_dsn)
    parts = psycopg.conninfo.conninfo_to_dict(base_dsn)
    base_db = parts.get("dbname") or parts.get("database")
    assert base_db, "test DSN must identify the disposable source database"
    clone_db = "aao_mtls_legacy_" + uuid.uuid4().hex[:12]
    admin_dsn = make_conninfo(base_dsn, dbname="postgres")
    clone_dsn = make_conninfo(base_dsn, dbname=clone_db)

    # This test requires the disposable CI/local PostgreSQL owner to have
    # CREATEDB; fail explicitly rather than reporting a skipped migration gate.
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{clone_db}" TEMPLATE "{base_db}"')
    try:
        monkeypatch.setenv("AAO_POSTGRES_URL", clone_dsn)
        from aao.postgresql_connection import connect_postgres

        with connect_postgres(clone_dsn) as db:
            # Reconstruct the schema/ledger left by the earlier published draft
            # that used 045 for cycle mTLS before 045 was reassigned.
            db.execute("DELETE FROM schema_migrations WHERE version IN (%s,%s)", (
                "045_organization_execution",
                "046_selfdev_cycle_mtls_intents",
            ))
            db.execute("DELETE FROM schema_migrations WHERE version=%s", (
                "045_selfdev_cycle_mtls_intents",
            ))
            db.execute(
                "ALTER TABLE selfdev_cycle_mtls_intents "
                "DROP CONSTRAINT IF EXISTS selfdev_cycle_mtls_intents_principal_id_key"
            )
            db.execute(
                "INSERT INTO schema_migrations(version) VALUES (%s)",
                ("045_selfdev_cycle_mtls_intents",),
            )
            db.commit()
            count, applied = apply_migrations(db)
            assert count == 2
            assert applied == ["045_organization_execution", "046_selfdev_cycle_mtls_intents"]
            rows = db.execute(
                "SELECT version FROM schema_migrations WHERE version IN (%s,%s) ORDER BY version",
                ("045_organization_execution", "046_selfdev_cycle_mtls_intents"),
            ).fetchall()
            assert [row[0] for row in rows] == [
                "045_organization_execution",
                "046_selfdev_cycle_mtls_intents",
            ]
            status = check_status(db)
            assert "045_selfdev_cycle_mtls_intents" in status.legacy_unverified_versions
            assert "045_selfdev_cycle_mtls_intents" not in status.verified_versions
            assert "045_organization_execution" in status.applied_versions
            assert "045_organization_execution" not in status.pending_versions
            assert db.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_constraint "
                "WHERE conrelid='selfdev_cycle_mtls_intents'::regclass "
                "AND conname='selfdev_cycle_mtls_intents_principal_id_key' AND contype='u')"
            ).fetchone()[0]
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid <> pg_backend_pid()",
                (clone_db,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{clone_db}"')


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


def test_migration_upgrades_legacy_runtime_column_grants_and_principal_uniqueness(
    monkeypatch, runtime_role
):
    """Table-level REVOKE alone does not remove an older column ACL."""
    from aao.postgresql_connection import connect_postgres

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    with connect_postgres() as db:
        # Recreate the legacy ACL, then run the idempotent migration as an
        # upgrade would. This proves the migration removes existing column ACLs.
        db.execute(
            "GRANT UPDATE(enabled,revoked_at) ON workload_identity_bindings TO aao_runtime"
        )
        db.execute(
            "ALTER TABLE selfdev_cycle_mtls_intents "
            "DROP CONSTRAINT selfdev_cycle_mtls_intents_principal_id_key"
        )
        migration = Path(__file__).parents[1] / "db/postgres/046_selfdev_cycle_mtls_intents.sql"
        db.execute(migration.read_text())
        db.commit()
        assert db.execute(
            "SELECT has_column_privilege('aao_runtime',"
            "'workload_identity_bindings','enabled','UPDATE'), "
            "has_column_privilege('aao_runtime',"
            "'workload_identity_bindings','revoked_at','UPDATE')"
        ).fetchone() == (False, False)
        assert db.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conrelid='selfdev_cycle_mtls_intents'::regclass "
            "AND conname='selfdev_cycle_mtls_intents_principal_id_key' "
            "AND contype='u')"
        ).fetchone()[0]


def test_concurrent_identical_intent_creation_is_idempotent(seeded_intent):
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    barrier = threading.Barrier(8)

    def create(_):
        barrier.wait(timeout=10)
        return repo.create_intent(seeded_intent)

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(result == seeded_intent for result in pool.map(create, range(8)))


def test_principal_cannot_be_reused_by_another_cycle(seeded_intent):
    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    repo.create_intent(seeded_intent)
    with connect_postgres() as db:
        with pytest.raises(Exception) as denied:
            db.execute(
                "SELECT create_selfdev_cycle_mtls_intent(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid.uuid4(),
                    seeded_intent.project_id,
                    uuid.uuid4().hex,
                    seeded_intent.principal_id,
                    seeded_intent.kind,
                    seeded_intent.not_before,
                    seeded_intent.not_after,
                ),
            )
        # The canonical principal/cycle binding rejects reuse before the unique
        # constraint is reached, with a check-violation SQLSTATE.
        assert getattr(denied.value, "sqlstate", None) == "23514"


def test_create_function_rejects_noncanonical_cycle_principal(seeded_intent):
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        with pytest.raises(Exception) as denied:
            db.execute(
                "SELECT create_selfdev_cycle_mtls_intent(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid.uuid4(),
                    seeded_intent.project_id,
                    seeded_intent.cycle_id,
                    "arbitrary-disabled-principal",
                    seeded_intent.kind,
                    seeded_intent.not_before,
                    seeded_intent.not_after,
                ),
            )
        assert getattr(denied.value, "sqlstate", None) == "23514"


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
    with pytest.raises(CycleMtlError, match="expired"):
        repo.complete_binding(old, "c" * 64, "d" * 64)
    assert repo.get_pending_intent(old.intent_id) is None
    with connect_postgres() as db:
        assert (
            db.execute(
                "SELECT state FROM selfdev_cycle_mtls_intents WHERE intent_id=%s", (old.intent_id,)
            ).fetchone()[0]
            == "EXPIRED"
        )


def test_principal_expiring_at_intent_deadline_cannot_create_intent(seeded_intent):
    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls import CycleMtlError
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    with connect_postgres() as db:
        db.execute(
            "UPDATE principal_credentials SET expires_at=%s WHERE principal_id=%s",
            (seeded_intent.not_after, seeded_intent.principal_id),
        )

    with pytest.raises(CycleMtlError, match="not eligible"):
        PostgresCycleIntentRepository().create_intent(seeded_intent)


def test_future_not_before_is_not_misclassified_as_expired(seeded_intent):
    from dataclasses import replace

    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    future = replace(
        seeded_intent,
        not_before=datetime.now(UTC) + timedelta(minutes=5),
        not_after=datetime.now(UTC) + timedelta(minutes=30),
    )
    repo = PostgresCycleIntentRepository()
    repo.create_intent(future)
    with connect_postgres() as db:
        status = db.execute(
            "SELECT complete_selfdev_cycle_mtls_binding(%s,%s,%s)",
            (future.intent_id, "c" * 64, "d" * 64),
        ).fetchone()[0]
        state = db.execute(
            "SELECT state FROM selfdev_cycle_mtls_intents WHERE intent_id=%s",
            (future.intent_id,),
        ).fetchone()[0]
    assert status == "NOT_YET_VALID"
    assert state == "PENDING"


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


def test_concurrent_completion_and_revoke_leave_cycle_revoked(seeded_intent):
    """A completion racing a revoke cannot resurrect a runnable identity."""
    from aao.postgresql_connection import connect_postgres
    from aao.selfdev_cycle_mtls import CycleMtlError
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository

    repo = PostgresCycleIntentRepository()
    intent = repo.create_intent(seeded_intent)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait(timeout=10)
        try:
            repo.complete_binding(intent, "a" * 64, "b" * 64)
        except CycleMtlError:
            # Revoke may acquire the intent lock first; then completion must
            # fail closed rather than restore the principal.
            return

    def revoke():
        barrier.wait(timeout=10)
        return repo.revoke(intent.intent_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        completion = pool.submit(complete)
        revocation = pool.submit(revoke)
        completion.result(timeout=10)
        assert revocation.result(timeout=10) is True

    with connect_postgres() as db:
        assert db.execute(
            "SELECT state FROM selfdev_cycle_mtls_intents WHERE intent_id=%s",
            (intent.intent_id,),
        ).fetchone()[0] == "REVOKED"
        assert db.execute(
            "SELECT enabled FROM principal_credentials WHERE principal_id=%s",
            (intent.principal_id,),
        ).fetchone()[0] is False
        assert db.execute(
            "SELECT count(*) FROM workload_identity_bindings "
            "WHERE intent_id=%s AND enabled AND revoked_at IS NULL "
            "AND expires_at>clock_timestamp()",
            (intent.intent_id,),
        ).fetchone()[0] == 0


def test_runtime_cannot_write_binding_or_complete_intent(seeded_intent, runtime_role):
    """Exercise actual PostgreSQL role privileges, not SQL-text expectations."""
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        role_exists = db.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='aao_runtime')"
        ).fetchone()[0]
        assert role_exists, "runtime_role fixture must provision aao_runtime"
        privileges = db.execute(
            "SELECT has_table_privilege('aao_runtime','workload_identity_bindings','INSERT'),"
            "has_table_privilege('aao_runtime','workload_identity_bindings','UPDATE'),"
            "has_table_privilege('aao_runtime','selfdev_cycle_mtls_intents','INSERT'),"
            "has_function_privilege('aao_runtime',"
            "'complete_selfdev_cycle_mtls_binding(uuid,text,text)','EXECUTE')"
        ).fetchone()
    assert privileges == (False, False, False, False)

    with connect_postgres() as db:
        db.execute("SET LOCAL ROLE aao_runtime")
        db.execute(
            "SELECT create_selfdev_cycle_mtls_intent(%s,%s,%s,%s,%s,%s,%s)",
            (
                seeded_intent.intent_id,
                seeded_intent.project_id,
                seeded_intent.cycle_id,
                seeded_intent.principal_id,
                seeded_intent.kind,
                seeded_intent.not_before,
                seeded_intent.not_after,
            ),
        )
        db.execute(
            "SELECT revoke_selfdev_cycle_mtls_intent(%s)",
            (seeded_intent.intent_id,),
        )
    with connect_postgres() as db:
        assert (
            db.execute(
                "SELECT state FROM selfdev_cycle_mtls_intents WHERE intent_id=%s",
                (seeded_intent.intent_id,),
            ).fetchone()[0]
            == "REVOKED"
        )

    with connect_postgres() as db:
        db.execute("SET LOCAL ROLE aao_runtime")
        with pytest.raises(Exception) as denied:
            db.execute(
                "INSERT INTO workload_identity_bindings"
                "(certificate_sha256,principal_id,enabled,issued_at,expires_at)"
                " VALUES (%s,%s,true,clock_timestamp(),clock_timestamp()+interval '1 hour')",
                ("1" * 64, seeded_intent.principal_id),
            )
        assert getattr(denied.value, "sqlstate", None) == "42501"

    with connect_postgres() as db:
        db.execute("SET LOCAL ROLE aao_runtime")
        with pytest.raises(Exception) as denied:
            db.execute(
                "SELECT complete_selfdev_cycle_mtls_binding(%s,%s,%s)",
                (seeded_intent.intent_id, "1" * 64, "2" * 64),
            )
        assert getattr(denied.value, "sqlstate", None) == "42501"
