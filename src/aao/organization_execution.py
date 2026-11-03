"""Deterministic contracts for governed organizational-change execution.

This module plans effects only. It neither grants authority nor performs database
writes; callers must revalidate identity, decision, grants, resources, and current
state in the transaction that performs each effect.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID


class OrganizationOperation(StrEnum):
    CREATE_TEMPORARY_SQUAD = "organization.squad.create_temporary"
    DISSOLVE_TEMPORARY_SQUAD = "organization.squad.dissolve"
    ASSIGN_SLOT = "organization.slot.assign"
    CREATE_PERMANENT_UNIT = "organization.unit.create_permanent"
    MERGE_UNITS = "organization.unit.merge"
    SPLIT_UNIT = "organization.unit.split"


class OrganizationExecutionState(StrEnum):
    PLANNED = "PLANNED"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    AUTHORIZED = "AUTHORIZED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    CANCELLED = "CANCELLED"


EXECUTION_TRANSITIONS: dict[OrganizationExecutionState, frozenset[OrganizationExecutionState]] = {
    OrganizationExecutionState.PLANNED: frozenset({
        OrganizationExecutionState.AWAITING_AUTHORIZATION,
        OrganizationExecutionState.CANCELLED,
    }),
    OrganizationExecutionState.AWAITING_AUTHORIZATION: frozenset({
        OrganizationExecutionState.AUTHORIZED,
        OrganizationExecutionState.CANCELLED,
    }),
    OrganizationExecutionState.AUTHORIZED: frozenset({
        OrganizationExecutionState.EXECUTING,
        OrganizationExecutionState.CANCELLED,
    }),
    OrganizationExecutionState.EXECUTING: frozenset({
        OrganizationExecutionState.EXECUTED,
        OrganizationExecutionState.FAILED,
        OrganizationExecutionState.RECONCILIATION_REQUIRED,
        OrganizationExecutionState.COMPENSATING,
    }),
    OrganizationExecutionState.FAILED: frozenset({
        OrganizationExecutionState.AWAITING_AUTHORIZATION,
        OrganizationExecutionState.CANCELLED,
    }),
    OrganizationExecutionState.RECONCILIATION_REQUIRED: frozenset({
        OrganizationExecutionState.EXECUTED,
        OrganizationExecutionState.FAILED,
        OrganizationExecutionState.COMPENSATING,
    }),
    OrganizationExecutionState.COMPENSATING: frozenset({
        OrganizationExecutionState.COMPENSATED,
        OrganizationExecutionState.RECONCILIATION_REQUIRED,
        OrganizationExecutionState.FAILED,
    }),
    OrganizationExecutionState.EXECUTED: frozenset(),
    OrganizationExecutionState.COMPENSATED: frozenset(),
    OrganizationExecutionState.CANCELLED: frozenset(),
}


def validate_execution_transition(
    current: OrganizationExecutionState,
    target: OrganizationExecutionState,
) -> bool:
    """Return whether a system-defined execution transition is legal."""
    return target in EXECUTION_TRANSITIONS[current]


@dataclass(frozen=True)
class OrganizationExecutionPlan:
    proposal_id: str
    proposal_version: int
    proposal_state: str
    operation: OrganizationOperation
    project_id: str
    purpose: str
    affected_entity_ids: tuple[str, ...]
    preconditions: tuple[str, ...]
    dependencies: tuple[str, ...]
    authority_required: str
    budget_ceiling_usd: float
    risk: str
    reversible: bool
    actions: tuple[str, ...]
    success_conditions: tuple[str, ...]
    compensation_actions: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    operation_parameters_json: str

    @property
    def operation_parameters(self) -> dict[str, Any]:
        """Return a fresh copy so callers cannot mutate the hashed plan."""
        return json.loads(self.operation_parameters_json)

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "proposal_state": self.proposal_state,
            "operation": self.operation.value,
            "project_id": self.project_id,
            "purpose": self.purpose,
            "affected_entity_ids": list(self.affected_entity_ids),
            "preconditions": list(self.preconditions),
            "dependencies": list(self.dependencies),
            "authority_required": self.authority_required,
            "budget_ceiling_usd": self.budget_ceiling_usd,
            "risk": self.risk,
            "reversible": self.reversible,
            "actions": list(self.actions),
            "success_conditions": list(self.success_conditions),
            "compensation_actions": list(self.compensation_actions),
            "evidence_requirements": list(self.evidence_requirements),
            "operation_parameters": self.operation_parameters,
        }

    @property
    def sha256(self) -> str:
        encoded = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


_OPERATION_SPECS: dict[OrganizationOperation, dict[str, Any]] = {
    OrganizationOperation.CREATE_TEMPORARY_SQUAD: {
        "parameters": {"conversation_id", "work_group_request"},
        "required": {"conversation_id", "work_group_request"},
        "authority": "organization.squad.create_temporary",
        "risk": "low",
        "reversible": True,
        "actions": ("create_work_group",),
        "success": ("work_group_persisted", "work_group_matches_approved_request"),
        "compensation": ("dissolve_work_group_if_empty",),
    },
    OrganizationOperation.DISSOLVE_TEMPORARY_SQUAD: {
        "parameters": {"work_group_id"},
        "required": {"work_group_id"},
        "authority": "organization.squad.dissolve",
        "risk": "low",
        "reversible": True,
        "actions": ("archive_work_group",),
        "success": ("work_group_archived", "history_and_evidence_retained"),
        "compensation": (),
    },
    OrganizationOperation.ASSIGN_SLOT: {
        "parameters": {"work_id", "assignee_principal_id"},
        "required": {"work_id", "assignee_principal_id"},
        "authority": "organization.slot.assign",
        "risk": "low",
        "reversible": True,
        "actions": ("assign_work_item",),
        "success": ("assignment_persisted", "assignee_competence_and_grants_current"),
        "compensation": ("restore_previous_assignment_if_unchanged",),
    },
    OrganizationOperation.CREATE_PERMANENT_UNIT: {
        "parameters": {"unit_id", "code", "name", "parent_id", "lead_principal_id"},
        "required": {"unit_id", "code", "name"},
        "authority": "organization.unit.create_permanent",
        "risk": "high",
        "reversible": False,
        "actions": ("create_organization_unit",),
        "success": ("unit_persisted", "parent_and_lead_references_valid"),
        "compensation": ("disable_unit_only_if_unused",),
    },
    OrganizationOperation.MERGE_UNITS: {
        "parameters": {"source_unit_ids", "target_unit_id"},
        "required": {"source_unit_ids", "target_unit_id"},
        "authority": "organization.unit.merge",
        "risk": "high",
        "reversible": False,
        "actions": ("merge_organization_units",),
        "success": ("all_references_reconciled", "source_units_archived"),
        "compensation": ("reconciliation_required_on_partial_failure",),
    },
    OrganizationOperation.SPLIT_UNIT: {
        "parameters": {"source_unit_id", "new_units"},
        "required": {"source_unit_id", "new_units"},
        "authority": "organization.unit.split",
        "risk": "high",
        "reversible": False,
        "actions": ("split_organization_unit",),
        "success": ("all_references_reconciled", "source_unit_archived"),
        "compensation": ("reconciliation_required_on_partial_failure",),
    },
}


def build_execution_plan(proposal: dict[str, Any]) -> OrganizationExecutionPlan:
    """Build the same immutable plan for the same approved proposal snapshot.

    This function recognizes only enumerated operations and exact top-level
    operation parameters. It is not an authorization decision.
    """
    proposal_id = proposal.get("id")
    version = proposal.get("version")
    state = proposal.get("state")
    project_id = proposal.get("project_id")
    purpose = proposal.get("scope_description")
    budget = proposal.get("budget_ceiling_usd")
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ValueError("proposal id is required")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("proposal version must be a positive integer")
    if state != "AUTONOMOUS_APPROVED":
        raise ValueError("proposal must be approved before execution planning")
    if not isinstance(project_id, str):
        raise TypeError("proposal project scope is required")
    try:
        normalized_project_id = str(UUID(project_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("proposal project scope must be a UUID") from exc
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("proposal scope description is required")
    if isinstance(budget, bool) or not isinstance(budget, (float, int)):
        raise TypeError("proposal budget ceiling must be finite and non-negative")
    budget_value = float(budget)
    if not math.isfinite(budget_value) or budget_value < 0:
        raise ValueError("proposal budget ceiling must be finite and non-negative")

    try:
        operation = OrganizationOperation(proposal.get("operation"))
    except (ValueError, TypeError) as exc:
        raise ValueError("unsupported execution operation") from exc
    spec = _OPERATION_SPECS[operation]
    parameters = proposal.get("operation_parameters")
    if not isinstance(parameters, dict):
        raise TypeError("operation parameters must be an object")
    unknown = set(parameters) - spec["parameters"]
    if unknown:
        raise ValueError(f"unsupported operation parameter: {min(unknown)}")
    missing = spec["required"] - set(parameters)
    if missing:
        raise ValueError(f"missing operation parameter: {min(missing)}")
    normalized_parameters = json.loads(json.dumps(parameters, sort_keys=True, allow_nan=False))
    _validate_operation_parameters(operation, normalized_parameters)

    entity_values = _affected_entities(operation, normalized_parameters)
    return OrganizationExecutionPlan(
        proposal_id=proposal_id,
        proposal_version=version,
        proposal_state=state,
        operation=operation,
        project_id=normalized_project_id,
        purpose=purpose.strip(),
        affected_entity_ids=entity_values,
        preconditions=(
            "proposal_version_and_approval_snapshot_unchanged",
            "authenticated_actor_and_current_project_grant_verified",
            "project_active_and_entities_in_scope",
            "current_capacity_and_competence_verified",
            "operation_not_constitutionally_reserved",
        ),
        dependencies=("project", "organization_proposals", "project_grants", "principal_credentials"),
        authority_required=spec["authority"],
        budget_ceiling_usd=budget_value,
        risk=spec["risk"],
        reversible=spec["reversible"],
        actions=spec["actions"],
        success_conditions=spec["success"],
        compensation_actions=spec["compensation"],
        evidence_requirements=(
            "approved_proposal_digest",
            "current_identity_and_grant",
            "execution_journal",
            "persisted_result_reconciliation",
        ),
        operation_parameters_json=json.dumps(
            normalized_parameters, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ),
    )


def _affected_entities(operation: OrganizationOperation, parameters: dict[str, Any]) -> tuple[str, ...]:
    if operation == OrganizationOperation.CREATE_TEMPORARY_SQUAD:
        return (_require_uuid(parameters["conversation_id"], "conversation_id"),)
    if operation == OrganizationOperation.DISSOLVE_TEMPORARY_SQUAD:
        return (_require_uuid(parameters["work_group_id"], "work_group_id"),)
    if operation == OrganizationOperation.ASSIGN_SLOT:
        return (_require_uuid(parameters["work_id"], "work_id"), parameters["assignee_principal_id"])
    if operation == OrganizationOperation.CREATE_PERMANENT_UNIT:
        return (str(parameters["unit_id"]),)
    if operation == OrganizationOperation.MERGE_UNITS:
        return (*tuple(parameters["source_unit_ids"]), str(parameters["target_unit_id"]))
    if operation == OrganizationOperation.SPLIT_UNIT:
        return (str(parameters["source_unit_id"]),)
    raise ValueError("unsupported execution operation")


def _validate_operation_parameters(
    operation: OrganizationOperation, parameters: dict[str, Any],
) -> None:
    """Reject malformed identifiers and non-contract payloads before hashing."""
    if operation == OrganizationOperation.CREATE_TEMPORARY_SQUAD:
        _require_uuid(parameters["conversation_id"], "conversation_id")
        request = parameters["work_group_request"]
        if not isinstance(request, dict):
            raise ValueError("work_group_request must be an object")
        allowed = {
            "idempotency_key", "based_on_message_ids", "title", "description",
            "acceptance_criteria", "due_date", "tasks",
        }
        unknown = set(request) - allowed
        if unknown:
            raise ValueError(f"unsupported work group request field: {min(unknown)}")
        for field in ("idempotency_key", "title", "acceptance_criteria", "tasks"):
            if field not in request:
                raise ValueError(f"missing work group request field: {field}")
        _require_uuid(request["idempotency_key"], "idempotency_key")
        if not isinstance(request["title"], str) or not request["title"].strip():
            raise ValueError("work group title must be non-blank")
        if (not isinstance(request["acceptance_criteria"], list)
                or not request["acceptance_criteria"]
                or any(not isinstance(value, str) or not value.strip()
                       for value in request["acceptance_criteria"])):
            raise ValueError("work group acceptance_criteria must be a non-empty list of non-blank strings")
        if not isinstance(request["tasks"], list) or not request["tasks"]:
            raise ValueError("work group tasks must be a non-empty list")
    elif operation == OrganizationOperation.DISSOLVE_TEMPORARY_SQUAD:
        _require_uuid(parameters["work_group_id"], "work_group_id")
    elif operation == OrganizationOperation.ASSIGN_SLOT:
        _require_uuid(parameters["work_id"], "work_id")
        if not isinstance(parameters["assignee_principal_id"], str) or not parameters["assignee_principal_id"].strip():
            raise ValueError("assignee_principal_id must be non-blank")
    elif operation == OrganizationOperation.CREATE_PERMANENT_UNIT:
        for field in ("unit_id", "code", "name"):
            if not isinstance(parameters[field], str) or not parameters[field].strip():
                raise ValueError(f"{field} must be non-blank")
        for field in ("parent_id", "lead_principal_id"):
            value = parameters.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field} must be null or a non-blank string")
    elif operation == OrganizationOperation.MERGE_UNITS:
        source_ids = parameters["source_unit_ids"]
        target_id = parameters["target_unit_id"]
        if (not isinstance(source_ids, list) or len(source_ids) < 2
                or any(not isinstance(item, str) or not item.strip() for item in source_ids)
                or len(set(source_ids)) != len(source_ids)
                or not isinstance(target_id, str) or target_id in source_ids):
            raise ValueError("merge requires at least two unique source units and a distinct target")
        if any(not item.strip() for item in source_ids) or not target_id.strip():
            raise ValueError("merge unit identifiers must be non-blank")
    elif operation == OrganizationOperation.SPLIT_UNIT:
        if not isinstance(parameters["source_unit_id"], str) or not parameters["source_unit_id"].strip():
            raise ValueError("source_unit_id must be non-blank")
        new_units = parameters["new_units"]
        if not isinstance(new_units, list) or len(new_units) < 2:
            raise ValueError("split requires at least two new units")
        seen_codes: set[str] = set()
        for unit in new_units:
            if not isinstance(unit, dict) or set(unit) - {"unit_id", "code", "name", "lead_principal_id"}:
                raise ValueError("each split unit must be an object with supported fields")
            for field in ("unit_id", "code", "name"):
                if not isinstance(unit.get(field), str) or not unit[field].strip():
                    raise ValueError(f"each split unit requires a non-blank {field}")
            if unit["code"] in seen_codes:
                raise ValueError("split unit codes must be unique")
            seen_codes.add(unit["code"])
            lead = unit.get("lead_principal_id")
            if lead is not None and (not isinstance(lead, str) or not lead.strip()):
                raise ValueError("split lead_principal_id must be null or non-blank")


def _require_uuid(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a UUID")
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(f"{name} must be a UUID") from exc
