"""Database-role contract tests for append-only runtime data."""

import hashlib
import os
from pathlib import Path
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


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_bootstrap_removes_preexisting_parent_memberships():
    """A reused cluster cannot retain SET ROLE paths for runtime roles."""
    import re

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    base_dsn = os.environ["AAO_TEST_POSTGRES_URL"]
    source = (Path(__file__).resolve().parents[1] / "scripts/bootstrap/init_postgres.sh").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"(?ms)^DO \$\$\nDECLARE\n  member_role name;.*?^END \$\$;",
        source,
    )
    assert match, "role-membership cleanup block missing from PostgreSQL bootstrap"

    suffix = uuid4().hex
    role_pairs = {
        canonical: (canonical + "_" + suffix, parent)
        for canonical, parent in {
            "aao_runtime": "runtime_parent_" + suffix,
            "aao_recovery": "recovery_parent_" + suffix,
            "aao_fencer": "fencer_parent_" + suffix,
        }.items()
    }
    cleanup_sql = match.group(0)
    for canonical, (member, _parent) in role_pairs.items():
        cleanup_sql = cleanup_sql.replace(f"'{canonical}'", sql.Literal(member).as_string(None))

    with psycopg.connect(base_dsn) as db:
        passwords = {member: uuid4().hex for member, _parent in role_pairs.values()}
        try:
            for member, parent in role_pairs.values():
                db.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}"
                    ).format(sql.Identifier(member), sql.Literal(passwords[member]))
                )
                db.execute(
                    sql.SQL("CREATE ROLE {} NOLOGIN CREATEDB").format(sql.Identifier(parent))
                )
                db.execute(
                    sql.SQL("GRANT {} TO {}").format(sql.Identifier(parent), sql.Identifier(member))
                )
            db.commit()
            # Verify the dangerous path exists before applying the exact bootstrap block.
            for member, parent in role_pairs.values():
                dsn = make_conninfo(
                    base_dsn,
                    user=member,
                    password=passwords[member],
                )
                with psycopg.connect(dsn) as member_db:
                    member_db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(parent)))
                    assert member_db.execute("SELECT current_user").fetchone() == (parent,)

            db.execute(cleanup_sql)
            db.commit()
            # Re-running the block must be harmless and retain the isolation.
            db.execute(cleanup_sql)
            db.commit()
            for member, parent in role_pairs.values():
                assert db.execute(
                    "SELECT pg_has_role(%s, %s, 'MEMBER')", (member, parent)
                ).fetchone() == (False,)
                dsn = make_conninfo(
                    base_dsn,
                    user=member,
                    password=passwords[member],
                )
                with (
                    psycopg.connect(dsn) as member_db,
                    pytest.raises(psycopg.errors.InsufficientPrivilege),
                ):
                    member_db.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(parent)))
        finally:
            db.rollback()
            for member, parent in role_pairs.values():
                existing_roles = {
                    row[0]
                    for row in db.execute(
                        "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
                        ([member, parent],),
                    ).fetchall()
                }
                if member in existing_roles and parent in existing_roles:
                    db.execute(
                        sql.SQL("REVOKE {} FROM {}").format(
                            sql.Identifier(parent), sql.Identifier(member)
                        )
                    )
                if member in existing_roles:
                    db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(member)))
                if member in existing_roles:
                    db.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(member)))
                if parent in existing_roles:
                    db.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(parent)))
            db.commit()
            leftovers = [
                row[0]
                for row in db.execute(
                    "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
                    ([role for pair in role_pairs.values() for role in pair],),
                ).fetchall()
            ]
            assert leftovers == [], f"test roles left behind: {leftovers}"
