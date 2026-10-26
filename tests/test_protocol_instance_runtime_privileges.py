"""PostgreSQL role contract for immutable protocol-instance metadata."""
import os
from uuid import uuid4

import pytest


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL")
    or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_runtime_role_can_create_protocol_instance_but_cannot_rewrite_it(monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    from aao.postgresql_connection import connect_postgres

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    role = "protocol_runtime_" + uuid4().hex
    password = uuid4().hex + uuid4().hex
    instance_id = uuid4()
    subject_id = uuid4()

    try:
        with connect_postgres() as db:
            db.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOINHERIT PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(password))
            )
            db.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
                .format(sql.Identifier(db.info.dbname), sql.Identifier(role))
            )
            db.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            db.execute(sql.SQL(
                "GRANT SELECT, INSERT ON TABLE protocol_instances TO {}"
            ).format(sql.Identifier(role)))

        with psycopg.connect(make_conninfo(
            os.environ["AAO_TEST_POSTGRES_URL"], user=role, password=password,
        )) as runtime:
            privileges = runtime.execute(
                "SELECT r.rolsuper, r.rolcreaterole, pg_get_userbyid(c.relowner), "
                "has_table_privilege(current_user, 'protocol_instances', 'INSERT'), "
                "has_table_privilege(current_user, 'protocol_instances', 'UPDATE'), "
                "has_table_privilege(current_user, 'protocol_instances', 'DELETE'), "
                "has_table_privilege(current_user, 'protocol_instances', 'TRUNCATE'), "
                "has_table_privilege(current_user, 'protocol_instances', 'TRIGGER') "
                "FROM pg_roles r CROSS JOIN pg_class c "
                "WHERE r.rolname=current_user AND c.relname='protocol_instances'"
            ).fetchone()
            assert privileges[0:2] == (False, False)
            assert privileges[2] != role
            assert privileges[3:] == (True, False, False, False, False)

            insert = (
                "INSERT INTO protocol_instances "
                "(id, protocol_id, protocol_version, subject_type, subject_id, "
                "idempotency_key, request_sha256, started_by) "
                "VALUES (%s, 'implementation', '1.0.0', 'work_item', %s, %s, %s, %s)"
            )
            key = "start-" + instance_id.hex
            runtime.execute(insert, (instance_id, subject_id, key, "a" * 64, "agent-1"))
            runtime.commit()

            with pytest.raises(psycopg.errors.UniqueViolation):
                runtime.execute(
                    insert, (uuid4(), subject_id, key, "a" * 64, "agent-1"),
                )
            runtime.rollback()

            for statement in (
                "UPDATE protocol_instances SET protocol_version='2.0.0' WHERE id=%s",
                "DELETE FROM protocol_instances WHERE id=%s",
                "TRUNCATE protocol_instances",
                "ALTER TABLE protocol_instances ADD COLUMN mutable text",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    runtime.execute(statement, (instance_id,)) if "%s" in statement else runtime.execute(statement)
                runtime.rollback()
    finally:
        with connect_postgres() as db:
            db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

    with connect_postgres() as db:
        row = db.execute(
            "SELECT protocol_id, protocol_version, request_sha256, started_by "
            "FROM protocol_instances WHERE id=%s",
            (instance_id,),
        ).fetchone()
    assert row == ("implementation", "1.0.0", "a" * 64, "agent-1")
