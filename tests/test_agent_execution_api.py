"""Contract tests for the API boundary used by the unprivileged worker service."""
from contextlib import contextmanager

from fastapi.testclient import TestClient


def test_worker_execution_api_routes_authenticate_and_fence_operations(monkeypatch):
    from aao import execution_queue
    from aao.principal_credentials import PrincipalDenied
    from aao.work_management_api import app

    monkeypatch.setattr(
        "aao.work_management_api._authenticate_request_principal",
        lambda token, kind: "agent-1" if token == "agent-token" and kind == "AGENT"
        else (_ for _ in ()).throw(PrincipalDenied("denied")),
    )
    calls = []
    monkeypatch.setattr(execution_queue, "claim", lambda *args, **kwargs: calls.append(("claim", args, kwargs))
                        or {"execution_id": "execution-1", "worker_id": args[0], "token": "lease-1"})
    monkeypatch.setattr(execution_queue, "complete", lambda *args, **kwargs: calls.append(("complete", args, kwargs)))

    with TestClient(app) as client:
        denied = client.post("/v1/agent/executions/claim", json={"project_id": "project-1"})
        assert denied.status_code == 403

        headers = {"X-Agent-Token": "agent-token"}
        claim = client.post("/v1/agent/executions/claim", headers=headers,
                            json={"project_id": "project-1", "seconds": 600})
        assert claim.status_code == 200, claim.text
        assert claim.json()["worker_id"] == "agent-1"
        assert calls[0] == ("claim", ("agent-1",), {
            "agent_credential": "agent-token", "project_id": "project-1", "seconds": 600,
        })

        too_long = client.post("/v1/agent/executions/claim", headers=headers,
                               json={"project_id": "project-1", "seconds": 1801})
        assert too_long.status_code == 422

        completed = client.post("/v1/agent/executions/execution-1/complete", headers=headers,
                                json={"lease_token": "lease-1", "result": {"conclusion": "success"}})
        assert completed.status_code == 200, completed.text
        assert calls[1] == (
            "complete", ("execution-1", "lease-1", "agent-1", {"conclusion": "success"}),
            {"agent_credential": "agent-token"},
        )


def test_context_endpoint_requires_owned_unexpired_lease_and_grant(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setattr("aao.work_management_api._authenticate_request_principal", lambda *_: "agent-1")
    row = ("work-1", "project-1", {
        "type": "aao.agent-patch.v1", "capability_id": "agent", "version": "1",
        "base_sha": "a" * 40,
    }, "title", "description", ["criterion"], "agent-1", {"backend": "fixture"})
    executed = []

    class Result:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

    class DB:
        def execute(self, sql, params):
            executed.append((sql, params))
            if sql.startswith("SELECT q.work_id"):
                return Result(row if params == ("execution-1", "agent-1", "lease-1") else None)
            raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def fake_tx():
        yield DB()

    grants = []
    monkeypatch.setattr("aao.work_management_api.tx", fake_tx)
    monkeypatch.setattr("aao.work_management_api.require_grant",
                        lambda db, principal, project, grant: grants.append((principal, project, grant)))
    with TestClient(app) as client:
        headers = {"X-Agent-Token": "agent-token"}
        for execution_id, token in (("execution-1", "stale-token"), ("other", "lease-1")):
            denied = client.post(f"/v1/agent/executions/{execution_id}/context", headers=headers,
                                 json={"lease_token": token})
            assert denied.status_code == 409

        response = client.post("/v1/agent/executions/execution-1/context", headers=headers,
                               json={"lease_token": "lease-1"})
        assert response.status_code == 200, response.text
        assert response.json()["author_id"] == "agent-1"
        assert response.json()["model_profile"] == {"backend": "fixture"}
    assert grants == [("agent-1", "project-1", "execution.claim")]
    sql, _ = executed[-1]
    assert "q.status='RUNNING'" in sql
    assert "q.worker_id=%s" in sql and "q.lease_token=%s" in sql
    assert "q.lease_expires_at>clock_timestamp()" in sql


def test_proposal_lookup_is_limited_to_assigned_agent_with_grant(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setattr("aao.work_management_api._authenticate_request_principal", lambda *_: "agent-1")

    class Result:
        def __init__(self, value):
            self.value = value

        def fetchone(self):
            return self.value

    author_id = "agent-1"

    class DB:
        def execute(self, sql, params):
            if "SELECT project_id,author_id" in sql:
                return Result(("project-1", author_id))
            if "SELECT id FROM patch_proposals" in sql:
                return Result(("proposal-1",))
            raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def fake_tx():
        yield DB()

    grants = []
    monkeypatch.setattr("aao.work_management_api.tx", fake_tx)
    monkeypatch.setattr("aao.work_management_api.require_grant",
                        lambda db, principal, project, grant: grants.append((principal, project, grant)))
    with TestClient(app) as client:
        headers = {"X-Agent-Token": "agent-token"}
        response = client.post("/v1/agent/work/work-1/patch-proposals/lookup", headers=headers,
                               json={"base_sha": "a" * 40, "patch_sha256": "b" * 64})
        assert response.status_code == 200, response.text
        assert response.json()["proposal_id"] == "proposal-1"
        author_id = "agent-2"
        denied = client.post("/v1/agent/work/work-1/patch-proposals/lookup", headers=headers,
                             json={"base_sha": "a" * 40, "patch_sha256": "b" * 64})
        assert denied.status_code == 403
    assert grants == [("agent-1", "project-1", "code.propose"),
                      ("agent-1", "project-1", "code.propose")]
