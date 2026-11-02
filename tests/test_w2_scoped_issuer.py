from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from fastapi.testclient import TestClient


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
        params for sql, params in calls
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
