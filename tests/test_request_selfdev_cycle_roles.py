"""PM-scoped, fixed-grant Self Development cycle provisioner tests."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import request_selfdev_cycle_roles as provisioner

ProvisionError = provisioner.ProvisionError


def _cycle_response(cycle_id):
    expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    return {
        "cycle_id": cycle_id,
        "project_id": "selfdev-id",
        "expires_at": expiry,
        "roles": [
            {
                "principal_id": f"aao-selfdev-impl-{cycle_id}",
                "kind": "AGENT",
                "grants": sorted(provisioner.ROLE_GRANTS[0]),
                "token": "secret-implementer",
            },
            {
                "principal_id": f"aao-selfdev-review-{cycle_id}",
                "kind": "AUDITOR",
                "grants": sorted(provisioner.ROLE_GRANTS[1]),
                "token": "secret-reviewer",
            },
        ],
    }


def _setup(monkeypatch, *, fail_verify=False):
    calls = []
    api_calls = []
    monkeypatch.setattr(provisioner, "read_pm_token", lambda: "pm-secret")
    monkeypatch.setattr(provisioner.common, "local_api_url", lambda value: value)
    monkeypatch.setattr(provisioner, "uuid4", lambda: SimpleNamespace(hex="a" * 32))

    def fake_role_helper(account, token_kind, operation, token=None):
        kwargs = {"token_kind": token_kind, "operation": operation, "token": token}
        calls.append((account, kwargs))
        if fail_verify and operation == "verify":
            raise RuntimeError("verify failed")

    monkeypatch.setattr(provisioner, "_run_token_helper", fake_role_helper)

    def fake_call(api, path, *, token, method="GET", body=None):
        api_calls.append((api, path, token, method, body))
        if method == "POST":
            return _cycle_response(body["cycle_id"])
        return {"revoked": True}

    monkeypatch.setattr(provisioner, "_call", fake_call)
    return calls, api_calls


def test_request_uses_pm_authority_and_installs_fixed_pair(monkeypatch):
    calls, api_calls = _setup(monkeypatch)
    cycle_id, _expiry, principals = provisioner.provision(
        "selfdev-id", api_url="http://127.0.0.1:8001", lifetime_seconds=3600
    )
    assert cycle_id == "a" * 32
    assert principals == [f"aao-selfdev-impl-{cycle_id}", f"aao-selfdev-review-{cycle_id}"]
    assert api_calls[0][2:] == (
        "pm-secret",
        "POST",
        {"cycle_id": cycle_id, "lifetime_seconds": 3600},
    )
    assert [c[0] for c in calls if c[1]["operation"] == "install"] == [
        "aao-impl-codex",
        "aao-auditor",
    ]
    assert [c[1]["token"] for c in calls if c[1]["operation"] == "install"] == [
        "secret-implementer",
        "secret-reviewer",
    ]
    assert all("secret-" not in str(call[0]) for call in calls)


def test_rejects_overlong_lifetime_before_api_or_install(monkeypatch):
    calls, api_calls = _setup(monkeypatch)
    with pytest.raises(ProvisionError, match="between 1 second and 2 hours"):
        provisioner.provision("selfdev-id", api_url="http://127.0.0.1:8001", lifetime_seconds=7201)
    assert calls == []
    assert api_calls == []


def test_install_failure_removes_installed_token_and_revokes_known_cycle(monkeypatch):
    calls, api_calls = _setup(monkeypatch, fail_verify=True)
    with pytest.raises(ProvisionError, match="cycle revoked"):
        provisioner.provision("selfdev-id", api_url="http://127.0.0.1:8001")
    assert any(args["operation"] == "remove" for _, args in calls)
    assert api_calls[-1][3] == "DELETE"
    assert api_calls[-1][1].endswith("/" + "a" * 32)


def test_root_helper_uses_fixed_interpreter_and_token_only_on_stdin(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        provisioner.subprocess,
        "run",
        lambda args, **kwargs: (
            seen.update(args=args, kwargs=kwargs) or SimpleNamespace(returncode=0)
        ),
    )
    provisioner._run_token_helper(
        "aao-impl-codex", "selfdev-implementer", "install", "secret-token"
    )
    assert seen["args"][:2] == ["/usr/bin/sudo", provisioner.ROOT_WRAPPER]
    assert "/usr/bin/python3" not in seen["args"]
    assert "secret-token" not in str(seen["args"])
    assert seen["kwargs"]["input"] == "secret-token\n"


def test_root_helper_rejects_non_allowlisted_target_before_subprocess(monkeypatch):
    monkeypatch.setattr(
        provisioner.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("must not run")
    )
    with pytest.raises(ProvisionError, match="unsupported role-token"):
        provisioner._run_token_helper("root", "arbitrary", "install", "secret")


def test_request_cli_rejects_arbitrary_interpreter_option():
    with pytest.raises(SystemExit) as error:
        provisioner.main(["--project-id", "p", "--python", "/tmp/evil"])
    assert error.value.code == 2


def test_response_with_extra_capability_fails_closed_and_revokes(monkeypatch):
    _calls, api_calls = _setup(monkeypatch)
    original = provisioner._call

    def extra_grant(api, path, *, token, method="GET", body=None):
        result = original(api, path, token=token, method=method, body=body)
        if method == "POST":
            result["roles"][0]["grants"].append("code.publish")
        return result

    monkeypatch.setattr(provisioner, "_call", extra_grant)
    with pytest.raises(ProvisionError, match="invalid cycle role"):
        provisioner.provision("selfdev-id", api_url="http://127.0.0.1:8001")
    assert api_calls[-1][3] == "DELETE"


def test_api_request_model_caps_cycle_lifetime():
    from pydantic import ValidationError

    from aao.work_management_api import SelfDevCycleIssueRequest

    assert SelfDevCycleIssueRequest(cycle_id="b" * 32, lifetime_seconds=7200)
    for invalid in (0, 7201):
        with pytest.raises(ValidationError):
            SelfDevCycleIssueRequest(cycle_id="b" * 32, lifetime_seconds=invalid)


def test_api_only_accepts_expiring_issuer_capability_grant():
    from pydantic import ValidationError

    from aao.work_management_api import GrantRequest

    with pytest.raises(ValidationError, match="explicit expiry"):
        GrantRequest(
            principal_id="aao-pm-coordinator-x", capability="credential.issue_selfdev_cycle_roles"
        )
    with pytest.raises(ValidationError, match="30 days"):
        GrantRequest(
            principal_id="aao-pm-coordinator-x",
            capability="credential.issue_selfdev_cycle_roles",
            expires_at=datetime.now(UTC) + timedelta(days=31),
        )


def test_only_named_pm_coordinator_can_pass_issuer_identity_gate(monkeypatch):
    from fastapi import HTTPException

    from aao import work_management_api as api

    calls = []
    monkeypatch.setattr(api, "require_grant", lambda *args: calls.append(args))
    with pytest.raises(HTTPException) as error:
        api._require_selfdev_cycle_issuer(object(), "ordinary-agent", "selfdev-id")
    assert error.value.status_code == 403
    assert calls == []


class _FakeDb:
    def __init__(self, *, project_rows=None, role_rows=None, retirement_function=True):
        self.project_rows = project_rows
        self.role_rows = role_rows or {}
        self.retirement_function = retirement_function
        self.statements = []
        self.inserted = set()

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if "SELECT name,state FROM projects" in sql:
            return SimpleNamespace(fetchone=lambda: ("AAO — Self Development", "ACTIVE"))
        if "to_regprocedure('public.retire_selfdev_cycle_host_binding(text,uuid)')" in sql:
            value = "retire_selfdev_cycle_host_binding(text,uuid)" if self.retirement_function else None
            return SimpleNamespace(fetchone=lambda: (value,))
        if "SELECT id FROM projects WHERE name=%s" in sql:
            rows = self.project_rows or [(params[0],)]
            return SimpleNamespace(fetchall=lambda: rows)
        if "SELECT clock_timestamp()+%s" in sql:
            return SimpleNamespace(fetchone=lambda: (datetime.now(UTC) + params[0],))
        if "SELECT count(*) FROM principal_credentials" in sql:
            return SimpleNamespace(fetchone=lambda: (len(self.role_rows),))
        if "SELECT c.kind,c.enabled,g.project_id,g.capability" in sql:
            return SimpleNamespace(fetchall=lambda: self.role_rows[params[0]])
        if sql.startswith("INSERT INTO principal_credentials"):
            principal_id = params[0]
            if principal_id in self.inserted:
                return SimpleNamespace(fetchone=lambda: None)
            self.inserted.add(principal_id)
            return SimpleNamespace(fetchone=lambda: (principal_id,))
        if "INSERT INTO" in sql or "UPDATE principal_credentials" in sql:
            return SimpleNamespace(fetchone=lambda: None, fetchall=list)
        return SimpleNamespace(fetchone=lambda: None, fetchall=list)


@contextmanager
def _transaction(db):
    yield db


def test_api_issues_only_fixed_roles_and_audits_without_secrets(monkeypatch):
    from aao import work_management_api as api

    project_id = "selfdev-id"
    db = _FakeDb(project_rows=[(project_id,)])
    grants_checked = []
    events = []
    monkeypatch.setattr(api, "tx", lambda: _transaction(db))
    monkeypatch.setattr(
        api, "require_grant", lambda _db, p, proj, cap: grants_checked.append((str(p), proj, cap))
    )
    monkeypatch.setattr(
        api, "audit", lambda _db, subject, kind, details: events.append((subject, kind, details))
    )
    # Host binding and profile inheritance are covered by the PostgreSQL integration tests.
    monkeypatch.setattr(api, "_bind_selfdev_cycle_implementer", lambda *_args: {"host_id": "h"})
    tokens = iter(("private-impl-token", "private-review-token"))
    monkeypatch.setattr(api.secrets, "token_urlsafe", lambda _n: next(tokens))

    result = api.issue_selfdev_cycle_roles(
        project_id,
        api.SelfDevCycleIssueRequest(cycle_id="c" * 32, lifetime_seconds=3600),
        api.AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT"),
    )

    assert [cap for _p, _proj, cap in grants_checked] == [
        "work.coordinate",
        api.SELFDEV_CYCLE_ISSUER_CAPABILITY,
    ]
    inserted_grants = [
        params[2] for sql, params in db.statements if sql.startswith("INSERT INTO project_grants")
    ]
    assert set(inserted_grants) == set(api.SELFDEV_IMPLEMENTER_GRANTS) | set(
        api.SELFDEV_REVIEWER_GRANTS
    )
    assert [role["kind"] for role in result["roles"]] == ["AGENT", "AUDITOR"]
    assert result["roles"][0]["grants"] == list(api.SELFDEV_IMPLEMENTER_GRANTS)
    assert result["roles"][1]["grants"] == list(api.SELFDEV_REVIEWER_GRANTS)
    assert all("token" not in event[2] and "digest" not in str(event[2]) for event in events)
    assert all("private-" not in str(event) for event in events)


def test_api_refuses_ambiguous_selfdev_project_before_issuing(monkeypatch):
    from fastapi import HTTPException

    from aao import work_management_api as api

    db = _FakeDb(project_rows=[("selfdev-id",), ("other-id",)])
    monkeypatch.setattr(api, "tx", lambda: _transaction(db))
    monkeypatch.setattr(api, "require_grant", lambda *_args: None)
    with pytest.raises(HTTPException) as error:
        api.issue_selfdev_cycle_roles(
            "selfdev-id",
            api.SelfDevCycleIssueRequest(cycle_id="d" * 32, lifetime_seconds=7200),
            api.AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT"),
        )
    assert error.value.status_code == 409
    assert not any("INSERT INTO principal_credentials" in sql for sql, _params in db.statements)


def test_api_revoke_requires_exact_grant_set_before_disabling(monkeypatch):
    from fastapi import HTTPException

    from aao import work_management_api as api

    project_id = "selfdev-id"
    cycle_id = "e" * 32
    expected = (
        (f"aao-selfdev-impl-{cycle_id}", "AGENT", api.SELFDEV_IMPLEMENTER_GRANTS),
        (f"aao-selfdev-review-{cycle_id}", "AUDITOR", api.SELFDEV_REVIEWER_GRANTS),
    )
    expiry = datetime.now(UTC) + timedelta(hours=1)
    role_rows = {
        principal_id: [(kind, True, project_id, cap, expiry, expiry) for cap in grants]
        for principal_id, kind, grants in expected
    }
    db = _FakeDb(role_rows=role_rows)
    monkeypatch.setattr(api, "tx", lambda: _transaction(db))
    monkeypatch.setattr(api, "require_grant", lambda *_args: None)
    monkeypatch.setattr(api, "audit", lambda *_args: None)
    retired = []
    monkeypatch.setattr(
        api, "_retire_selfdev_cycle_implementer", lambda _db, p, _a, _project, **_kwargs: retired.append(p) or {},
    )

    result = api.revoke_selfdev_cycle_roles(
        project_id,
        cycle_id,
        api.AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT"),
    )
    assert result == {"cycle_id": cycle_id, "revoked": True, "already_revoked": False}
    disabled = [sql for sql, _params in db.statements if "UPDATE principal_credentials" in sql]
    assert len(disabled) == 2
    assert all("pending_token_digest=NULL" in sql for sql in disabled)
    assert retired == [expected[0][0]]

    role_rows[expected[0][0]] = [("AGENT", True, project_id, "code.publish", expiry, expiry)]
    db = _FakeDb(role_rows=role_rows)
    monkeypatch.setattr(api, "tx", lambda: _transaction(db))
    with pytest.raises(HTTPException) as error:
        api.revoke_selfdev_cycle_roles(
            project_id,
            cycle_id,
            api.AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT"),
        )
    assert error.value.status_code == 409
    assert not any("UPDATE principal_credentials" in sql for sql, _params in db.statements)


def test_api_revoke_fails_before_disabling_when_retirement_migration_is_missing(monkeypatch):
    from fastapi import HTTPException

    from aao import work_management_api as api

    project_id = "selfdev-id"
    cycle_id = "f" * 32
    expected = (
        (f"aao-selfdev-impl-{cycle_id}", "AGENT", api.SELFDEV_IMPLEMENTER_GRANTS),
        (f"aao-selfdev-review-{cycle_id}", "AUDITOR", api.SELFDEV_REVIEWER_GRANTS),
    )
    expiry = datetime.now(UTC) + timedelta(hours=1)
    role_rows = {
        principal_id: [(kind, True, project_id, cap, expiry, expiry) for cap in grants]
        for principal_id, kind, grants in expected
    }
    db = _FakeDb(role_rows=role_rows, retirement_function=False)
    monkeypatch.setattr(api, "tx", lambda: _transaction(db))
    monkeypatch.setattr(api, "require_grant", lambda *_args: None)

    with pytest.raises(HTTPException) as error:
        api.revoke_selfdev_cycle_roles(
            project_id,
            cycle_id,
            api.AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT"),
        )

    assert error.value.status_code == 503
    assert "migration 041" in error.value.detail
    assert not any("UPDATE principal_credentials" in sql for sql, _params in db.statements)
