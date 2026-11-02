"""Database-role contract tests for append-only runtime data."""

import hashlib
import os
from uuid import uuid4

import pytest


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_non_owner_runtime_role_can_insert_but_cannot_mutate_evidence(monkeypatch):
    """Exercise evidence permissions as an authenticated, non-owner DB role."""
    import psycopg
    from fastapi.testclient import TestClient
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "runtime-role-ceo")
    ceo = {"X-CEO-Token": "runtime-role-ceo"}
    agent_id = "runtime-role-agent-" + uuid4().hex
    role = "runtime_test_" + uuid4().hex
    password = uuid4().hex + uuid4().hex

    with TestClient(app) as client:
        issued = client.post(
            "/v1/principals/credentials",
            headers=ceo,
            json={
                "principal_id": agent_id,
                "kind": "AGENT",
            },
        )
        assert issued.status_code == 201, issued.text
        mandate = client.post(
            "/v1/mandates",
            headers=ceo,
            json={
                "title": "Runtime role test " + uuid4().hex,
                "objective": "Verify non-owner append-only access",
            },
        ).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post(
            "/v1/projects",
            headers=ceo,
            json={
                "name": "Runtime role test",
                "mandate_id": mandate,
            },
        ).json()["id"]

    with connect_postgres() as db:
        db.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}"
            ).format(sql.Identifier(role), sql.Literal(password))
        )
        db.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(db.info.dbname), sql.Identifier(role)
            )
        )
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        db.execute(
            sql.SQL("GRANT SELECT, INSERT ON TABLE evidence_artifacts TO {}").format(
                sql.Identifier(role)
            )
        )

    dsn = make_conninfo(os.environ["AAO_TEST_POSTGRES_URL"], user=role, password=password)
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    runtime = psycopg.connect(dsn)
    try:
        identity = runtime.execute(
            "SELECT current_user, r.rolsuper, r.rolcreaterole, "
            "pg_get_userbyid(c.relowner), "
            "has_table_privilege(current_user, 'evidence_artifacts', 'INSERT'), "
            "has_table_privilege(current_user, 'evidence_artifacts', 'UPDATE'), "
            "has_table_privilege(current_user, 'evidence_artifacts', 'DELETE'), "
            "has_table_privilege(current_user, 'evidence_artifacts', 'TRIGGER') "
            "FROM pg_roles r CROSS JOIN pg_class c "
            "WHERE r.rolname=current_user AND c.relname='evidence_artifacts'"
        ).fetchone()
        assert identity[:3] == (role, False, False)
        assert identity[3] != role
        assert identity[4:] == (True, False, False, False)

        runtime.execute(
            "INSERT INTO evidence_artifacts(project_id,digest,submitted_by,media_type,content) "
            "VALUES (%s,%s,%s,%s,%s)",
            (project, digest, agent_id, "text/plain", b"runtime-role insert"),
        )
        runtime.commit()

        denied_statements = (
            (
                "UPDATE evidence_artifacts SET media_type='application/json' WHERE digest=%s",
                (digest,),
            ),
            ("DELETE FROM evidence_artifacts WHERE digest=%s", (digest,)),
            ("TRUNCATE evidence_artifacts", ()),
            ("ALTER TABLE evidence_artifacts DISABLE TRIGGER evidence_artifacts_append_only", ()),
            ("DROP TRIGGER evidence_artifacts_append_only ON evidence_artifacts", ()),
        )
        for statement, params in denied_statements:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                runtime.execute(statement, params)
            runtime.rollback()
    finally:
        runtime.close()
        with connect_postgres() as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

    with connect_postgres() as db:
        stored = db.execute(
            "SELECT media_type, content FROM evidence_artifacts WHERE project_id=%s AND digest=%s",
            (project, digest),
        ).fetchone()
    assert stored == ("text/plain", b"runtime-role insert")


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_recovery_grants_cannot_mutate_execution_or_fencing_state(monkeypatch):
    """Apply the bootstrap grant policy and exercise its security boundary."""
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from aao.postgresql_connection import connect_postgres

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    role = "recovery_test_" + uuid4().hex
    password = uuid4().hex + uuid4().hex
    host_id = "recovery-test-host-" + uuid4().hex
    worker_id = "recovery-test-worker-" + uuid4().hex
    grants_path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "bootstrap", "apply_runtime_grants.sql"
    )
    with open(grants_path, encoding="utf-8") as stream:
        grant_sql = stream.read()
    # The bootstrap has host-wide PUBLIC revocations that are inappropriate in
    # the shared CI test DB. Keep and execute the role grants and trigger DDL.
    grant_sql = "\n".join(
        line for line in grant_sql.splitlines() if not line.lstrip().upper().startswith("REVOKE ")
    )
    grant_sql = grant_sql.replace("aao_recovery", role)

    with connect_postgres() as db:
        db.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}"
            ).format(sql.Identifier(role), sql.Literal(password))
        )
        db.commit()
        try:
            db.execute(grant_sql.replace("aao_prod", db.info.dbname))
            db.commit()
            db.execute(
                "INSERT INTO host_worker_bindings(host_id,worker_id,status,fence_epoch) "
                "VALUES (%s,%s,'ACTIVE',1)",
                (host_id, worker_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    runtime = psycopg.connect(
        make_conninfo(
            os.environ["AAO_TEST_POSTGRES_URL"],
            user=role,
            password=password,
        )
    )
    try:
        privileges = runtime.execute(
            "SELECT has_table_privilege(current_user,'execution_queue','UPDATE'), "
            "has_column_privilege(current_user,'project_conversations','updated_at','UPDATE'), "
            "has_column_privilege(current_user,'project_conversations','title','UPDATE'), "
            "has_column_privilege(current_user,'project_conversation_turns','state','UPDATE'), "
            "has_column_privilege(current_user,'project_conversation_turns','created_at','UPDATE'), "
            "has_column_privilege(current_user,'host_worker_bindings','created_at','UPDATE'), "
            "has_column_privilege(current_user,'host_worker_bindings','fence_epoch','UPDATE')"
        ).fetchone()
        assert privileges == (False, True, False, True, False, True, False)

        # The lock read needed for fencing remains possible, but no fencing
        # column can be changed. The granted created_at column is immutable.
        assert runtime.execute(
            "SELECT fence_epoch FROM host_worker_bindings "
            "WHERE host_id=%s AND status='ACTIVE' FOR SHARE",
            (host_id,),
        ).fetchone() == (1,)
        denied = (
            ("UPDATE execution_queue SET status='FAILED' WHERE false",),
            ("UPDATE host_worker_bindings SET fence_epoch=2 WHERE host_id=%s", (host_id,)),
            (
                "UPDATE host_worker_bindings SET created_at=clock_timestamp() WHERE host_id=%s",
                (host_id,),
            ),
        )
        for statement, *params in denied:
            with pytest.raises(
                (psycopg.errors.InsufficientPrivilege, psycopg.errors.RaiseException)
            ):
                runtime.execute(statement, *params)
            runtime.rollback()
    finally:
        runtime.close()
        with connect_postgres() as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            db.execute(
                "DROP TRIGGER IF EXISTS host_worker_bindings_recovery_immutable "
                "ON host_worker_bindings"
            )
            db.execute("DROP FUNCTION IF EXISTS reject_recovery_host_binding_mutation()")
            db.execute("DELETE FROM host_worker_bindings WHERE host_id=%s", (host_id,))
