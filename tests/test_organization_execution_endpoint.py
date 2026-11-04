"""Focused authorization and replay tests for the execution endpoint."""

from contextlib import contextmanager
from decimal import Decimal

import pytest
from fastapi import HTTPException

from aao import work_management_api as api
from aao.organization_execution import build_execution_plan

PROJECT_ID = "9f7c4b55-f173-4582-a222-9676d32a5555"


def approved_proposal(operation="organization.squad.create_temporary", parameters=None):
    if parameters is None:
        parameters = {
            "conversation_id": "b8e74dad-a3a2-4ad4-bcc7-ef888715b544",
            "work_group_request": {
                "idempotency_key": "19ad6811-aadd-4a9a-9e09-53aa04a33d7d",
                "title": "Approved group",
                "acceptance_criteria": ["Persist the approved work"],
                "tasks": [{
                    "key": "task-1", "title": "Implement task",
                    "acceptance_criteria": ["Task is persisted"],
                }],
            },
        }
    value = {
        "id": "prop-123", "version": 4, "state": "AUTONOMOUS_APPROVED",
        "operation": operation, "project_id": PROJECT_ID,
        "scope_description": "Approved project work", "operation_parameters": parameters,
        "budget_ceiling_usd": 0.0,
    }
    plan = build_execution_plan(value)
    row = (
        value["version"], value["state"], value["operation"], value["project_id"],
        value["scope_description"], value["operation_parameters"], Decimal("0.00"),
        value["version"], plan.sha256, "ceo",
    )
    return value, plan, row


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        if self.row is None:
            return []
        return self.row if isinstance(self.row, list) else [self.row]


class ExecutionDB:
    def __init__(self, execution_row, proposal_row):
        self.execution_row = execution_row
        self.proposal_row = proposal_row
        self.statements = []

    def execute(self, query, params=None):
        self.statements.append((query, params))
        if "SELECT proposal_id,proposal_version,project_id FROM organization_executions" in query:
            return Cursor(("prop-123", 4, PROJECT_ID))
        if "FROM organization_proposals WHERE id=%s FOR UPDATE" in query:
            return Cursor(self.proposal_row)
        if "SELECT state FROM projects" in query:
            return Cursor(("ACTIVE",))
        if "FROM organization_executions WHERE id=%s FOR UPDATE" in query:
            return Cursor(self.execution_row)
        raise AssertionError(f"unexpected SQL: {query}")


def install_db(monkeypatch, db):
    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setattr(api, "tx", fake_tx)


def test_execute_replay_returns_durable_result_json(monkeypatch):
    _proposal, plan, proposal_row = approved_proposal()
    expected_result = {"verified": True, "group_id": "group-1"}
    db = ExecutionDB(
        ("prop-123", 4, PROJECT_ID, plan.sha256, plan.as_dict(), "EXECUTED", expected_result),
        proposal_row,
    )
    install_db(monkeypatch, db)
    monkeypatch.setattr(api, "require_grant", lambda *_args, **_kwargs: None)

    response = api.execute_organization_execution("exec-1", principal="agent-1")

    assert response["idempotent_replay"] is True
    assert response["result"] == expected_result
    assert ["FOR UPDATE" in query for query, _ in db.statements[:4]] == [False, True, True, True]


def test_execute_rechecks_grant_before_any_effect(monkeypatch):
    _proposal, plan, proposal_row = approved_proposal()
    db = ExecutionDB(
        ("prop-123", 4, PROJECT_ID, plan.sha256, plan.as_dict(), "PLANNED", None),
        proposal_row,
    )
    install_db(monkeypatch, db)

    def deny(*_args, **_kwargs):
        raise HTTPException(403, "grant revoked")

    monkeypatch.setattr(api, "require_grant", deny)
    with pytest.raises(HTTPException) as caught:
        api.execute_organization_execution("exec-1", principal="agent-1")

    assert caught.value.status_code == 403
    assert not any(query.startswith(("INSERT", "UPDATE")) for query, _ in db.statements)


def test_execute_fails_closed_when_operation_has_no_executor(monkeypatch):
    parameters = {"source_unit_ids": ["unit-a", "unit-b"], "target_unit_id": "unit-c"}
    _proposal, plan, proposal_row = approved_proposal(
        "organization.unit.merge", parameters,
    )
    db = ExecutionDB(
        ("prop-123", 4, PROJECT_ID, plan.sha256, plan.as_dict(), "PLANNED", None),
        proposal_row,
    )
    install_db(monkeypatch, db)
    monkeypatch.setattr(api, "require_grant", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException, match="No executor is enabled") as caught:
        api.execute_organization_execution("exec-1", principal="agent-1")

    assert caught.value.status_code == 409
    assert not any(query.startswith(("INSERT", "UPDATE")) for query, _ in db.statements)


def test_execute_assignment_reuses_competency_and_grant_checked_work_path(monkeypatch):
    from aao.organization_execution import build_execution_plan

    parameters = {
        "work_id": "57f2415f-e654-426a-846d-34302a305117",
        "assignee_principal_id": "agent-target",
    }
    proposal = {
        "id": "prop-assign", "version": 2, "state": "AUTONOMOUS_APPROVED",
        "operation": "organization.slot.assign", "project_id": PROJECT_ID,
        "scope_description": "Assign an approved project task",
        "operation_parameters": parameters, "budget_ceiling_usd": 0.0,
    }
    plan = build_execution_plan(proposal)
    proposal_row = (
        2, "AUTONOMOUS_APPROVED", proposal["operation"], PROJECT_ID,
        proposal["scope_description"], parameters, Decimal("0.00"),
        2, plan.sha256, "ceo",
    )

    class AssignmentDB(ExecutionDB):
        def execute(self, query, params=None):
            self.statements.append((query, params))
            if "SELECT proposal_id,proposal_version,project_id FROM organization_executions" in query:
                return Cursor((proposal["id"], 2, PROJECT_ID))
            if "FROM organization_proposals WHERE id=%s FOR UPDATE" in query:
                return Cursor(proposal_row)
            if "SELECT state FROM projects" in query:
                return Cursor(("ACTIVE",))
            if "FROM organization_executions WHERE id=%s FOR UPDATE" in query:
                return Cursor((proposal["id"], 2, PROJECT_ID, plan.sha256,
                               plan.as_dict(), "PLANNED", None))
            if query.startswith("UPDATE organization_executions SET state="):
                return Cursor(("exec-assign",))
            if query.startswith("SELECT project_id,parent_work_id,status,required_competencies"):
                return Cursor((PROJECT_ID, "group-parent", "INBOX", ["python"]))
            if query.startswith("SELECT 1 FROM work_groups"):
                return Cursor((1,))
            if query.startswith("SELECT enabled FROM principal_credentials"):
                return Cursor((True,))
            if query.startswith("SELECT capability FROM project_grants"):
                return Cursor([("work.admit",), ("execution.claim",)])
            if "FROM organization_profiles" in query and "FOR SHARE" in query:
                return Cursor((["python", "testing"],))
            if "FROM execution_queue" in query:
                return Cursor(None)
            if query.startswith("SELECT principal_id FROM work_item_assignments"):
                return Cursor(("agent-old",))
            if query.startswith("INSERT INTO work_item_assignments"):
                return Cursor(("agent-target",))
            if "SELECT a.principal_id,w.project_id FROM work_item_assignments" in query:
                return Cursor(("agent-target", PROJECT_ID))
            if query.startswith("UPDATE organization_executions SET result_json="):
                return Cursor(None)
            if query.startswith("INSERT INTO organization_execution_events"):
                return Cursor(None)
            raise AssertionError(f"unexpected SQL: {query}")

    db = AssignmentDB(None, proposal_row)
    install_db(monkeypatch, db)
    grant_calls = []
    monkeypatch.setattr(
        api, "require_grant",
        lambda _db, _principal, _project, capability: grant_calls.append(capability),
    )
    monkeypatch.setattr(api, "audit", lambda *_args, **_kwargs: None)

    response = api.execute_organization_execution("exec-assign", principal="agent-pm")

    assert response["state"] == "EXECUTED"
    assert response["result"] == {
        "verified": True, "work_id": parameters["work_id"],
        "previous_assignee_id": "agent-old", "assignee_id": "agent-target",
        "project_id": PROJECT_ID,
    }
    assert grant_calls == ["organization.slot.assign", "work.assign"]


def test_assignment_executor_rejects_work_outside_approved_project(monkeypatch):
    from fastapi import HTTPException

    class ScopeDB:
        def __init__(self):
            self.statements = []

        def execute(self, query, params=None):
            self.statements.append(query)
            return Cursor(("other-project", "group-parent", "INBOX", ["python"]))

    db = ScopeDB()
    with pytest.raises(HTTPException, match="outside the approved project scope") as caught:
        api._assign_group_child_work(
            "57f2415f-e654-426a-846d-34302a305117",
            api.WorkAssignmentRequest(principal_id="agent-target"),
            assigned_by="agent-pm", database=db, expected_project_id=PROJECT_ID,
        )

    assert caught.value.status_code == 409
    assert len(db.statements) == 1


def test_assignment_rejects_expired_target_identity(monkeypatch):
    from fastapi import HTTPException

    class ExpiredIdentityDB:
        def __init__(self):
            self.statements = []

        def execute(self, query, params=None):
            self.statements.append(query)
            if query.startswith("SELECT project_id,parent_work_id,status,required_competencies"):
                return Cursor((PROJECT_ID, "group-parent", "INBOX", ["python"]))
            if query.startswith("SELECT 1 FROM work_groups"):
                return Cursor((1,))
            if query.startswith("SELECT 1 FROM execution_queue"):
                return Cursor(None)
            if "FROM principal_credentials WHERE principal_id=%s" in query:
                assert "expires_at IS NULL OR expires_at>clock_timestamp()" in query
                return Cursor((False,))
            raise AssertionError(f"unexpected SQL: {query}")

    db = ExpiredIdentityDB()
    with pytest.raises(HTTPException, match="active agent identity") as caught:
        api._assign_group_child_work(
            "57f2415f-e654-426a-846d-34302a305117",
            api.WorkAssignmentRequest(principal_id="agent-expired"),
            assigned_by="ceo", database=db,
        )

    assert caught.value.status_code == 409
    assert not any(query.startswith("INSERT") for query in db.statements)
