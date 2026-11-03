from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from aao import work_management_api as api


class _Row:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class _Db:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "FROM principal_credentials" in sql:
            return _Row(("AGENT", True))
        if "FROM project_grants" in sql:
            return _Row((1,))
        return _Row(None)


def test_coordinator_presence_requires_pm_identity_and_project_grant(monkeypatch):
    db = _Db()

    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setattr(api, "tx", fake_tx)
    principal = api.AuthenticatedPrincipal("aao-pm-coordinator-test", "digest", "AGENT")
    result = api.update_coordinator_presence(
        api.UUID("9d17d6c1-d644-424a-a425-fe7e084c3d91"),
        api.CoordinatorPresenceRequest(state="COORDINATING"), principal,
    )
    assert result["state"] == "COORDINATING"
    assert any("INSERT INTO pm_coordinator_presence" in sql for sql, _ in db.calls)
    assert any("work.coordinate" in params for _, params in db.calls)


def test_other_agent_cannot_publish_coordinator_presence(monkeypatch):
    @contextmanager
    def fake_tx():
        yield _Db()

    monkeypatch.setattr(api, "tx", fake_tx)
    principal = api.AuthenticatedPrincipal("ordinary-agent", "digest", "AGENT")
    with pytest.raises(HTTPException) as error:
        api.update_coordinator_presence(
            api.UUID("9d17d6c1-d644-424a-a425-fe7e084c3d91"),
            api.CoordinatorPresenceRequest(state="WAITING"), principal,
        )
    assert error.value.status_code == 403


def test_presence_contract_rejects_arbitrary_states():
    with pytest.raises(ValueError):
        api.CoordinatorPresenceRequest(state="EXECUTING")
