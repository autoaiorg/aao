import pytest

from aao.organization_execution import (
    OrganizationExecutionState,
    OrganizationOperation,
    build_execution_plan,
    validate_execution_transition,
)


def proposal(**overrides):
    value = {
        "id": "prop-123",
        "version": 4,
        "state": "AUTONOMOUS_APPROVED",
        "operation": "organization.squad.create_temporary",
        "project_id": "9f7c4b55-f173-4582-a222-9676d32a5555",
        "scope_description": "Create a short-lived group for the approved project work.",
        "target_unit_id": None,
        "operation_parameters": {
            "conversation_id": "b8e74dad-a3a2-4ad4-bcc7-ef888715b544",
            "work_group_request": {
                "idempotency_key": "19ad6811-aadd-4a9a-9e09-53aa04a33d7d",
                "title": "Approved project task group",
                "acceptance_criteria": ["Persist the approved work"],
                "tasks": [{
                    "key": "task-1", "title": "Implement approved task",
                    "acceptance_criteria": ["Task is persisted"],
                }],
            },
        },
        "budget_ceiling_usd": 0,
    }
    value.update(overrides)
    return value


def test_plan_is_deterministic_and_binds_exact_proposal_version():
    first = build_execution_plan(proposal())
    second = build_execution_plan(proposal())

    assert first == second
    assert first.proposal_id == "prop-123"
    assert first.proposal_version == 4
    assert first.proposal_state == "AUTONOMOUS_APPROVED"
    assert first.sha256 == second.sha256
    assert first.operation == OrganizationOperation.CREATE_TEMPORARY_SQUAD
    assert first.project_id == "9f7c4b55-f173-4582-a222-9676d32a5555"
    assert first.actions == ("create_work_group",)
    assert first.compensation_actions == ("dissolve_work_group_if_empty",)


def test_plan_rejects_unapproved_or_unscoped_proposals():
    with pytest.raises(ValueError, match="approved"):
        build_execution_plan(proposal(state="EVALUATED"))
    with pytest.raises((ValueError, TypeError), match="project scope"):
        build_execution_plan(proposal(project_id=None))
    with pytest.raises(ValueError, match="supported execution operation"):
        build_execution_plan(proposal(operation="organization.mind_control", operation_parameters={}))


def test_plan_requires_operation_specific_parameters_and_rejects_unknown_fields():
    with pytest.raises(ValueError, match="conversation_id"):
        build_execution_plan(proposal(operation_parameters={}))
    with pytest.raises(ValueError, match="unsupported operation parameter"):
        build_execution_plan(proposal(operation_parameters={
            "conversation_id": "b8e74dad-a3a2-4ad4-bcc7-ef888715b544",
            "work_group_request": {"idempotency_key": "19ad6811-aadd-4a9a-9e09-53aa04a33d7d"},
            "grant_admin": True,
        }))


def test_execution_state_machine_has_only_declared_transitions():
    assert validate_execution_transition(
        OrganizationExecutionState.PLANNED,
        OrganizationExecutionState.AWAITING_AUTHORIZATION,
    )
    assert validate_execution_transition(
        OrganizationExecutionState.AUTHORIZED,
        OrganizationExecutionState.EXECUTING,
    )
    assert not validate_execution_transition(
        OrganizationExecutionState.PLANNED,
        OrganizationExecutionState.EXECUTED,
    )
    assert not validate_execution_transition(
        OrganizationExecutionState.EXECUTED,
        OrganizationExecutionState.COMPENSATING,
    )


def test_plan_rejects_non_finite_or_negative_budget():
    with pytest.raises(ValueError, match="budget"):
        build_execution_plan(proposal(budget_ceiling_usd=float("nan")))
    with pytest.raises(ValueError, match="budget"):
        build_execution_plan(proposal(budget_ceiling_usd=-1))


def test_plan_rejects_malformed_effect_parameters():
    with pytest.raises(ValueError, match="conversation_id"):
        build_execution_plan(proposal(operation_parameters={
            "conversation_id": "not-a-uuid",
            "work_group_request": {
                "idempotency_key": "19ad6811-aadd-4a9a-9e09-53aa04a33d7d",
                "title": "Group",
                "acceptance_criteria": ["Done"],
                "tasks": [{"key": "t"}],
            },
        }))


@pytest.mark.parametrize("operation,parameters,message", [
    ("organization.unit.merge", {
        "source_unit_ids": ["unit-a", "unit-a"], "target_unit_id": "unit-c",
    }, "at least two unique"),
    ("organization.unit.merge", {
        "source_unit_ids": ["unit-a", "unit-b"], "target_unit_id": " ",
    }, "non-blank"),
    ("organization.unit.split", {
        "source_unit_id": "unit-a", "new_units": [
            {"unit_id": "u1", "code": "X", "name": "One"},
            {"unit_id": "u2", "code": "X", "name": "Two"},
        ],
    }, "codes must be unique"),
    ("organization.unit.split", {
        "source_unit_id": "unit-a", "new_units": [
            {"unit_id": "u1", "code": "X", "name": "One", "unexpected": "field"},
            {"unit_id": "u2", "code": "Y", "name": "Two"},
        ],
    }, "supported fields"),
])
def test_plan_rejects_ambiguous_unit_reorganization(operation, parameters, message):
    with pytest.raises(ValueError, match=message):
        build_execution_plan(proposal(operation=operation, operation_parameters=parameters))


def test_execution_api_rejects_changed_approved_snapshot_before_any_effect(monkeypatch):
    from contextlib import contextmanager
    from uuid import UUID

    from fastapi import HTTPException

    from aao import work_management_api as api

    class Cursor:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Database:
        def __init__(self):
            self.statements = []

        def execute(self, query, params=None):
            self.statements.append(query)
            return Cursor((
                "prop-123", 4, "AUTONOMOUS_APPROVED", "organization.squad.create_temporary",
                proposal()["project_id"], proposal()["scope_description"],
                proposal()["operation_parameters"], 0.0, 4, "0" * 64,
            ))

    db = Database()

    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setattr(api, "tx", fake_tx)
    request = api.OrganizationExecutionRequest(
        idempotency_key=UUID("19ad6811-aadd-4a9a-9e09-53aa04a33d7d"),
    )
    with pytest.raises(HTTPException, match="snapshot has changed") as caught:
        api.plan_organization_execution("prop-123", request, principal="untrusted")
    assert caught.value.status_code == 409
    assert len(db.statements) == 1


def test_ceo_approval_records_exact_plan_snapshot(monkeypatch):
    from contextlib import contextmanager
    from decimal import Decimal

    from aao import work_management_api as api

    class Cursor:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Database:
        def __init__(self):
            self.update = None

        def execute(self, query, params=None):
            if query.startswith("SELECT version,state,impact,operation"):
                return Cursor((
                    1, "EVALUATED", "OPERATIONAL_TEAM",
                    proposal()["operation"], proposal()["project_id"],
                    proposal()["scope_description"], proposal()["operation_parameters"],
                    Decimal("0.00"),
                ))
            if query.startswith("UPDATE organization_proposals SET"):
                self.update = params
            return Cursor()

    db = Database()

    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setattr(api, "tx", fake_tx)
    monkeypatch.setattr(api, "audit", lambda *_args, **_kwargs: None)
    result = api.transition_organization_proposal(
        "prop-123",
        api.OrganizationProposalTransitionRequest(
            target_state="AUTONOMOUS_APPROVED", expected_version=1,
        ),
        principal=api._CEO_PRINCIPAL,
    )
    assert result["to_state"] == "AUTONOMOUS_APPROVED"
    assert db.update[3] == 2
    assert db.update[4] == build_execution_plan(proposal(version=2)).sha256
    assert db.update[5] == "ceo"


def test_temporary_group_effect_uses_existing_strict_request_contract():
    from aao.work_management_api import (
        OrganizationProposalCreateRequest,
        _validate_organization_effect_parameters,
    )

    with pytest.raises(ValueError, match="invalid temporary-squad request"):
        _validate_organization_effect_parameters(
            "organization.squad.create_temporary",
            {"work_group_request": {"idempotency_key": "not-a-uuid"}},
        )
    with pytest.raises(ValueError, match="finite JSON"):
        OrganizationProposalCreateRequest(
            operation="organization.squad.create_temporary",
            title="Group proposal", scope_description="Project scope",
            demand_summary="Observed workload", criteria={},
            operation_parameters={"budget": float("nan")},
        )
    with pytest.raises(ValueError, match="unsupported work group request field"):
        build_execution_plan(proposal(operation_parameters={
            "conversation_id": "b8e74dad-a3a2-4ad4-bcc7-ef888715b544",
            "work_group_request": {
                "idempotency_key": "19ad6811-aadd-4a9a-9e09-53aa04a33d7d",
                "title": "Group",
                "acceptance_criteria": ["Done"],
                "tasks": [{"key": "t"}],
                "grant_admin": True,
            },
        }))


def test_execution_read_api_is_project_scoped_and_returns_journal_events(monkeypatch):
    from contextlib import contextmanager
    from datetime import UTC, datetime

    from aao import work_management_api as api

    now = datetime.now(UTC)
    execution_id = "cb1152e0-0380-4fd3-9a0d-9c21df14312a"

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Database:
        def execute(self, query, params=None):
            if query.startswith("SELECT 1 FROM projects"):
                return Cursor([(1,)])
            if "FROM organization_executions" in query:
                return Cursor([(
                    execution_id, "proposal-1", 2, "a" * 64, {"actions": []},
                    "PLANNED", None, None, now, now,
                )])
            if "FROM organization_execution_events" in query:
                assert params == ([execution_id],)
                return Cursor([(execution_id, None, "PLANNED", "plan.persisted", {}, now)])
            raise AssertionError(f"Unexpected query: {query}")

    @contextmanager
    def fake_tx():
        yield Database()

    monkeypatch.setattr(api, "tx", fake_tx)
    monkeypatch.setattr(api, "require_grant", lambda *_args: None)
    result = api.list_organization_executions("project-1", principal="reader", limit=10)
    assert len(result) == 1
    assert result[0]["id"] == execution_id
    assert result[0]["events"][0]["event_type"] == "plan.persisted"


def test_execution_read_api_rejects_unbounded_page_size():
    from fastapi import HTTPException

    from aao import work_management_api as api

    with pytest.raises(HTTPException) as caught:
        api.list_organization_executions("project-1", principal="reader", limit=501)
    assert caught.value.status_code == 422


def test_only_unstarted_execution_can_be_cancelled(monkeypatch):
    from contextlib import contextmanager

    from fastapi import HTTPException

    from aao import work_management_api as api

    class Cursor:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Database:
        def __init__(self, state):
            self.state = state
            self.writes = []

        def execute(self, query, params=None):
            if query.startswith("SELECT state,actor_principal_id"):
                return Cursor((self.state, "agent-1", "project-1"))
            self.writes.append(query)
            return Cursor(None)

    db = Database("PLANNED")

    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setattr(api, "tx", fake_tx)
    monkeypatch.setattr(api, "audit", lambda *_args, **_kwargs: None)
    result = api.cancel_organization_execution("exec-1", principal="ceo")
    assert result == {"id": "exec-1", "state": "CANCELLED"}
    assert len(db.writes) == 2

    db.state = "EXECUTING"
    db.writes.clear()
    with pytest.raises(HTTPException) as caught:
        api.cancel_organization_execution("exec-1", principal="ceo")
    assert caught.value.status_code == 409
    assert not db.writes
