import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

needs_pg = pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
CEO = {"X-CEO-Token": "w2-scoped-issuer-ceo"}


def test_w2_issuer_fixes_project_grants_ttl_and_audits(monkeypatch):
    from aao.work_management_api import AuthenticatedPrincipal, app

    issuer = AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT")
    monkeypatch.setattr(
        "aao.work_management_api._authenticate_request_principal", lambda *_: issuer
    )
    calls = []
    expiry = datetime.now(UTC) + timedelta(hours=8)

    class Result:
        def __init__(self, value=None):
            self.value = value

        def fetchone(self):
            return self.value

        def fetchall(self):
            return self.value or []

    class DB:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            if "SELECT name,state FROM projects" in sql:
                return Result(("AAO — Self Development", "ACTIVE"))
            if "SELECT c.principal_id FROM project_grants g JOIN principal_credentials" in sql:
                return Result([])
            if "SELECT clock_timestamp()+%s" in sql:
                assert params == (timedelta(hours=8),)
                return Result((expiry,))
            return Result()

    @contextmanager
    def fake_tx():
        yield DB()

    audit_rows = []
    monkeypatch.setattr("aao.work_management_api.tx", fake_tx)
    monkeypatch.setattr(
        "aao.work_management_api.require_grant",
        lambda db, principal, project, capability: audit_rows.append(
            (principal, project, capability)
        ),
    )
    monkeypatch.setattr(
        "aao.work_management_api.audit",
        lambda db, subject, kind, details: audit_rows.append((subject, kind, details)),
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/project-1/w2-publishers/aao-impl-codex/issue",
            headers={"X-Agent-Token": "pm-token"},
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["account"] == "aao-impl-codex"
    assert body["kind"] == "AGENT"
    assert body["principal_id"].startswith("aao-publisher-impl-")
    assert body["grants"] == ["project.read", "code.publish"]
    assert datetime.fromisoformat(body["expires_at"]) == expiry
    assert audit_rows[0] == (str(issuer), "project-1", "credential.issue_publisher")
    assert audit_rows[1][1] == "principal.w2_publisher.issued"
    assert audit_rows[1][2]["grants"] == ["project.read", "code.publish"]
    assert body["token"] not in repr(calls)
    inserted = [params for sql, params in calls if sql.startswith("INSERT INTO project_grants")]
    assert [params[2] for params in inserted] == ["project.read", "code.publish"]
    assert all(params[3] == expiry for params in inserted)


def test_w2_issuer_replaces_existing_credential_after_lost_response(monkeypatch):
    """Retrying issuance recovers from a committed DB transaction/lost HTTP body."""
    from aao.work_management_api import AuthenticatedPrincipal, app

    issuer = AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT")
    monkeypatch.setattr(
        "aao.work_management_api._authenticate_request_principal", lambda *_: issuer
    )
    calls = []
    expiry = datetime.now(UTC) + timedelta(hours=8)

    class Result:
        def __init__(self, value=None):
            self.value = value

        def fetchone(self):
            return self.value

        def fetchall(self):
            return self.value or []

    class DB:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            if "SELECT name,state FROM projects" in sql:
                return Result(("AAO — Self Development", "ACTIVE"))
            if "SELECT c.principal_id FROM project_grants g JOIN principal_credentials" in sql:
                return Result([("aao-publisher-pm-orphaned",)])
            if "SELECT clock_timestamp()+%s" in sql:
                return Result((expiry,))
            return Result()

    @contextmanager
    def fake_tx():
        yield DB()

    monkeypatch.setattr("aao.work_management_api.tx", fake_tx)
    monkeypatch.setattr("aao.work_management_api.require_grant", lambda *_: None)
    monkeypatch.setattr("aao.work_management_api.audit", lambda *_: None)

    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/project-1/w2-publishers/aao-pm/issue",
            headers={"X-Agent-Token": "pm-token"},
        )

    assert response.status_code == 201, response.text
    disabled = [
        params
        for sql, params in calls
        if sql.startswith("UPDATE principal_credentials SET enabled=false")
    ]
    assert disabled == [("aao-publisher-pm-orphaned",)]
    assert any(sql.startswith("INSERT INTO principal_credentials") for sql, _ in calls)


def test_w2_issuer_rejects_non_pm_and_unknown_account_before_database(monkeypatch):
    from aao.work_management_api import AuthenticatedPrincipal, app

    issuer = AuthenticatedPrincipal("ordinary-agent", "digest", "AGENT")
    monkeypatch.setattr(
        "aao.work_management_api._authenticate_request_principal", lambda *_: issuer
    )

    def forbidden_tx():
        raise AssertionError("issuer identity/account must be checked before DB access")

    monkeypatch.setattr("aao.work_management_api.tx", forbidden_tx)
    with TestClient(app) as client:
        denied = client.post(
            "/v1/projects/project-1/w2-publishers/aao-pm/issue",
            headers={"X-Agent-Token": "agent-token"},
        )
        unknown = client.post(
            "/v1/projects/project-1/w2-publishers/aao-supervisor/issue",
            headers={"X-Agent-Token": "agent-token"},
        )
    assert denied.status_code == 403
    assert unknown.status_code == 404


def test_w2_issuer_requires_explicit_grant_and_does_not_issue_on_denial(monkeypatch):
    from aao.work_management_api import AuthenticatedPrincipal, app

    issuer = AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT")
    monkeypatch.setattr(
        "aao.work_management_api._authenticate_request_principal", lambda *_: issuer
    )
    calls = []

    class Result:
        def fetchone(self):
            return ("AAO — Self Development", "ACTIVE")

    class DB:
        def execute(self, sql, params=()):
            calls.append(sql)
            return Result()

    @contextmanager
    def fake_tx():
        yield DB()

    def deny_grant(*_args):
        raise HTTPException(403, "Project grant required")

    monkeypatch.setattr("aao.work_management_api.tx", fake_tx)
    monkeypatch.setattr("aao.work_management_api.require_grant", deny_grant)
    with TestClient(app) as client:
        response = client.post(
            "/v1/projects/project-1/w2-publishers/aao-pm/issue",
            headers={"X-Agent-Token": "pm-token"},
        )

    assert response.status_code == 403
    assert not any(sql.startswith("INSERT INTO") for sql in calls)


def test_grant_request_accepts_scoped_issuer_capability():
    from aao.work_management_api import GrantRequest

    assert GrantRequest(principal_id="pm", capability="credential.issue_publisher")


@needs_pg
def test_w2_issuer_replaces_orphaned_credential_after_lost_response(monkeypatch):
    """Exercise the locking, grants and retry path against disposable PostgreSQL."""
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_CEO_TOKEN", CEO["X-CEO-Token"])
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    with TestClient(app) as client:
        mandate = client.post(
            "/v1/mandates",
            headers=CEO,
            json={
                "title": "W2 issuer " + uuid4().hex,
                "objective": "Exercise bounded W2 publisher issuance",
            },
        )
        assert mandate.status_code == 201, mandate.text
        mandate_id = mandate.json()["id"]
        assert client.post(f"/v1/mandates/{mandate_id}/confirm", headers=CEO).status_code == 200
        project = client.post(
            "/v1/projects",
            headers=CEO,
            json={
                "name": "AAO — Self Development",
                "mandate_id": mandate_id,
            },
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        coordinator_id = "aao-pm-coordinator-w2-test-" + uuid4().hex[:12]
        coordinator = client.post(
            "/v1/principals/credentials",
            headers=CEO,
            json={
                "principal_id": coordinator_id,
                "kind": "AGENT",
            },
        )
        assert coordinator.status_code == 201, coordinator.text
        coordinator_token = coordinator.json()["token"]
        grant = client.post(
            f"/v1/projects/{project_id}/grants",
            headers=CEO,
            json={
                "principal_id": coordinator_id,
                "capability": "credential.issue_publisher",
            },
        )
        assert grant.status_code == 201, grant.text
        headers = {"X-Agent-Token": coordinator_token}
        endpoint = f"/v1/projects/{project_id}/w2-publishers/aao-pm/issue"

        first = client.post(endpoint, headers=headers)
        assert first.status_code == 201, first.text
        first_body = first.json()
        assert first_body["grants"] == ["project.read", "code.publish"]
        assert datetime.fromisoformat(first_body["expires_at"]) <= datetime.now(UTC) + timedelta(
            hours=8
        )

        # Simulate the response being lost after its database transaction committed.
        second = client.post(endpoint, headers=headers)
        assert second.status_code == 201, second.text
        second_body = second.json()
        assert second_body["principal_id"] != first_body["principal_id"]
        assert second_body["token"] != first_body["token"]

        with connect_postgres() as db:
            credentials = db.execute(
                "SELECT principal_id,enabled FROM principal_credentials "
                "WHERE principal_id IN (%s,%s) ORDER BY principal_id",
                (first_body["principal_id"], second_body["principal_id"]),
            ).fetchall()
            grants = db.execute(
                "SELECT principal_id,capability,expires_at FROM project_grants "
                "WHERE principal_id IN (%s,%s) ORDER BY principal_id,capability",
                (first_body["principal_id"], second_body["principal_id"]),
            ).fetchall()
        assert dict(credentials) == {
            first_body["principal_id"]: False,
            second_body["principal_id"]: True,
        }
        assert len(grants) == 4
        assert {row[1] for row in grants} == {"project.read", "code.publish"}
        assert all(row[2] <= datetime.now(UTC) + timedelta(hours=8) for row in grants)
