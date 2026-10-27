"""Unit-only metadata/SQL preflight guarantees; no PG mutations or host installation."""

import json
import os
from contextlib import nullcontext
from pathlib import Path

import pytest

from scripts import pm_deployment_preflight as preflight


class Rows:
    def __init__(self, values):
        self.values = values

    def fetchone(self):
        return self.values[0] if self.values else None

    def fetchall(self):
        return self.values


class Database:
    def __init__(self, *, identity=("AGENT", True), grants=None, elevated=False):
        self.calls = []
        self.identity = identity
        self.grants = grants if grants is not None else preflight.REQUIRED_GRANTS
        self.elevated = elevated

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql == "SET TRANSACTION READ ONLY":
            return Rows([])
        assert self.calls[0][0] == "SET TRANSACTION READ ONLY"
        assert sql.startswith("SELECT ")
        assert "token_digest" not in sql
        if "schema_migrations" in sql:
            return Rows([(p.stem,) for p in (preflight.ROOT / "db/postgres").glob("*.sql")])
        if "FROM projects" in sql:
            return Rows([("ACTIVE", "CONFIRMED")])
        if "principal_credentials" in sql:
            return Rows([self.identity] if self.identity else [])
        if "project_grants" in sql:
            assert "expires_at IS NULL" in sql and "expires_at > clock_timestamp()" in sql
            return Rows([(g,) for g in self.grants])
        if "current_user" in sql:
            return Rows([("developer", True)])
        if "rolcanlogin" in sql:
            return Rows([(self.elevated, False, False, False, False, True)])
        if "FROM pg_class" in sql:
            return Rows([(False, False, False)])
        if "has_table_privilege" in sql:
            return Rows([(len(params) == 3,)])
        raise AssertionError(sql)


def by_name(rows):
    return {r["check"]: r for r in rows}


def test_readonly_sql_and_no_inferred_principal_or_runtime_role():
    db = Database()
    rows = by_name(preflight.database_checks(db, preflight.PROJECT_ID, None, None))
    assert rows["db:migrations-001-035"]["status"] == "PASS"
    assert rows["db:project"]["status"] == "PASS"
    assert rows["db:pm-identity-grants"]["status"] == "UNVERIFIED"
    assert rows["db:runtime-role"]["status"] == "UNVERIFIED"
    assert not any("principal_credentials" in sql for sql, _ in db.calls)
    assert "NOT runtime" in rows["db:inspection-connection"]["detail"]


@pytest.mark.parametrize(
    "identity,grants,status",
    [
        (("AGENT", True), preflight.REQUIRED_GRANTS, "PASS"),
        (("AGENT", False), preflight.REQUIRED_GRANTS, "MISSING"),
        (("AUDITOR", True), preflight.REQUIRED_GRANTS, "MISSING"),
        (None, preflight.REQUIRED_GRANTS, "MISSING"),
        (("AGENT", True), {"project.read"}, "MISSING"),
    ],
)
def test_live_grants_require_enabled_agent(identity, grants, status):
    db = Database(identity=identity, grants=grants)
    rows = by_name(preflight.database_checks(db, preflight.PROJECT_ID, "registered-pm", None))
    assert rows["db:pm-grants"]["status"] == status
    assert all(not sql.startswith(("INSERT", "UPDATE", "DELETE", "GRANT")) for sql, _ in db.calls)


def test_elevated_runtime_role_rejected():
    db = Database(elevated=True)
    db.execute("SET TRANSACTION READ ONLY")
    rows = preflight.runtime_checks(db, "runtime")
    # Set up READ ONLY as caller would.
    assert rows[0]["status"] == "MISSING"


def test_path_metadata_never_opens_secret(tmp_path, monkeypatch):
    secret = tmp_path / "token"
    secret.write_text("NEVER-READ")
    secret.chmod(0o600)
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("secret read"))
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("secret read"))
    check = preflight.path_check("token", secret, os.getuid(), 0o600)
    # /tmp has a shared writable ancestor, deliberately not trusted.
    assert check["status"] == "MISSING"
    link = tmp_path / "link"
    link.symlink_to(secret)
    assert preflight.path_check("token", link, os.getuid(), 0o600)["status"] == "MISSING"
    assert preflight.path_check("absent", tmp_path / "absent", os.getuid())["status"] == "MISSING"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:SECRET@example.org/db",
        "dbname=test",
        "host=localhost,evil dbname=test",
        "host=/tmp,evil dbname=test",
        "service=remote",
    ],
)
def test_remote_or_implicit_db_rejected(url, monkeypatch):
    for key in ("PGHOST", "PGHOSTADDR", "PGSERVICE"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError):
        preflight.local_connection_options(url)


def test_libpq_remote_override_rejected(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    with pytest.raises(ValueError):
        preflight.local_connection_options("postgresql://localhost/test")


def test_connection_failure_never_serializes_credentials(monkeypatch, capsys):
    import psycopg

    import aao.postgresql_connection

    monkeypatch.setattr(preflight, "host_checks", lambda _: [])
    monkeypatch.setattr(
        aao.postgresql_connection, "database_url", lambda: "postgresql://user:SECRET@localhost/test"
    )
    monkeypatch.setattr(
        psycopg, "connect", lambda **_: (_ for _ in ()).throw(RuntimeError("SECRET tokenCEO"))
    )
    assert preflight.main([]) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output and "tokenCEO" not in output
    data = json.loads(output)
    assert data["readOnly"] is True and data["ready"] is False
    assert data["checks"][0]["status"] == "UNVERIFIED"


def test_runtime_table_privileges_checked_individually():
    db = Database()
    db.execute("SET TRANSACTION READ ONLY")
    rows = by_name(preflight.runtime_checks(db, "runtime"))
    for table in ("protocol_instances", "project_routines", "routine_occurrences"):
        assert rows[f"db:runtime:{table}"]["status"] == "PASS"
    assert rows["db:runtime-complete"]["status"] == "UNVERIFIED"
    assert any(params == ("runtime", "public.project_routines", "UPDATE") for _, params in db.calls)


@pytest.mark.parametrize(
    "unsafe", [(True, False, False), (False, True, False), (False, False, True)]
)
def test_runtime_rejects_delete_owner_or_public(unsafe):
    db = Database()
    db.execute("SET TRANSACTION READ ONLY")
    execute = db.execute

    def modified(sql, params=()):
        if "FROM pg_class" in sql:
            return Rows([unsafe])
        return execute(sql, params)

    db.execute = modified
    rows = by_name(preflight.runtime_checks(db, "runtime"))
    assert rows["db:runtime:protocol_instances"]["status"] == "MISSING"


def test_missing_migration_reported(monkeypatch):
    db = Database()
    execute = db.execute

    def modified(sql, params=()):
        if "schema_migrations" in sql:
            return Rows([])
        return execute(sql, params)

    db.execute = modified
    rows = by_name(preflight.database_checks(db, preflight.PROJECT_ID, None, None))
    assert rows["db:migrations-001-035"]["status"] == "MISSING"
    assert "035_project_routines" in rows["db:migrations-001-035"]["detail"]


def test_metadata_permissions_pass_and_fail(monkeypatch):
    import stat
    from types import SimpleNamespace

    info = SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=1001)
    ancestor = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0)
    path = Path("/private/pm/token")
    monkeypatch.setattr(Path, "lstat", lambda p: info if p == path else ancestor)
    assert preflight.path_check("token", path, 1001, 0o600)["status"] == "PASS"
    info.st_mode = stat.S_IFREG | 0o644
    assert preflight.path_check("token", path, 1001, 0o600)["status"] == "MISSING"
    info.st_mode = stat.S_IFREG | 0o600
    ancestor.st_uid = 1002
    assert preflight.path_check("token", path, 1001, 0o600)["status"] == "MISSING"


@pytest.mark.parametrize("manifest", ["absent", "empty", "missing-035", "duplicate-035"])
def test_incomplete_or_duplicate_local_migration_manifest_never_passes(
    monkeypatch, tmp_path, manifest
):
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    directory = tmp_path / "db/postgres"
    if manifest != "absent":
        directory.mkdir(parents=True)
    if manifest in ("missing-035", "duplicate-035"):
        for number in range(1, 36 if manifest == "duplicate-035" else 35):
            (directory / f"{number:03d}_migration.sql").touch()
    if manifest == "duplicate-035":
        (directory / "035_duplicate.sql").touch()
    rows = by_name(preflight.database_checks(Database(), preflight.PROJECT_ID, None, None))
    check = rows["db:migrations-001-035"]
    assert check["status"] == "UNVERIFIED"
    assert "manifest" in check["detail"].lower()
    assert "All 001..035 recorded" not in check["detail"]


@pytest.mark.parametrize("table", ["protocol_instances", "project_routines", "routine_occurrences"])
def test_runtime_rejects_truncate(table):
    db = Database()
    db.execute("SET TRANSACTION READ ONLY")
    execute = db.execute

    def modified(sql, params=()):
        if (
            "has_table_privilege" in sql
            and "'TRUNCATE'" in sql
            and params == ("runtime", f"public.{table}")
        ):
            return Rows([(True,)])
        return execute(sql, params)

    db.execute = modified
    rows = by_name(preflight.runtime_checks(db, "runtime"))
    assert rows[f"db:runtime:{table}"]["status"] == "MISSING"


def test_runtime_public_acl_check_includes_truncate():
    db = Database()
    db.execute("SET TRANSACTION READ ONLY")
    preflight.runtime_checks(db, "runtime")
    acl_queries = [sql for sql, _ in db.calls if "FROM pg_class" in sql]
    assert len(acl_queries) == 3
    assert all("'TRUNCATE'" in sql.split("a.privilege_type IN", 1)[1] for sql in acl_queries)
