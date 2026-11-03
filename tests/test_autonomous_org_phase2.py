"""Tests for Autonomous Organization Manager Phase 2: Persistence & Governance API."""
import pytest
from aao.autonomous_organization import (
    DemandAnalysisCriteria,
    OrganizationAlternativeKind,
    OrganizationChangeImpact,
    ProposalDecisionState,
    classify_organizational_authority,
    evaluate_organizational_demand,
    validate_proposal_transition,
)


def test_demand_criteria_validations():
    # Negative counts rejected
    with pytest.raises(ValueError, match="must be non-negative"):
        DemandAnalysisCriteria(
            active_projects_count=-1,
            future_commitments_count=0,
            unassigned_tasks_count=0,
            blocked_tasks_count=0,
        )

    # Friction score out of [0.0, 1.0] range rejected
    with pytest.raises(ValueError, match="coordination_friction_score"):
        DemandAnalysisCriteria(
            active_projects_count=1,
            future_commitments_count=1,
            unassigned_tasks_count=1,
            blocked_tasks_count=0,
            coordination_friction_score=1.5,
        )

    # Non-finite ratio rejected
    with pytest.raises(ValueError, match="budget_utilization_ratio"):
        DemandAnalysisCriteria(
            active_projects_count=1,
            future_commitments_count=1,
            unassigned_tasks_count=1,
            blocked_tasks_count=0,
            budget_utilization_ratio=float("nan"),
        )


def test_evaluate_demand_returns_exactly_one_primary_recommendation():
    criteria = DemandAnalysisCriteria(
        active_projects_count=1,
        future_commitments_count=1,
        unassigned_tasks_count=1,
        blocked_tasks_count=0,
        coordination_friction_score=0.1,
    )
    alternatives = evaluate_organizational_demand(criteria)
    primary = [a for a in alternatives if a.is_primary_recommendation]
    assert len(primary) == 1
    assert primary[0].kind == OrganizationAlternativeKind.REUSE_EXISTING_CAPACITY
    assert primary[0].estimated_cost_overhead_usd == 0.0
    assert "Coste marginal cero" in primary[0].cost_estimation_basis


def test_evaluate_demand_grounded_cost_with_known_hourly_rate():
    criteria = DemandAnalysisCriteria(
        active_projects_count=3,
        future_commitments_count=2,
        unassigned_tasks_count=5,
        blocked_tasks_count=2,
        coordination_friction_score=0.55,
        observation_period_days=10,
    )
    # When hourly rate is known (e.g. 50 USD/h), squad cost is 50 * 40 = 2000 USD
    alternatives = evaluate_organizational_demand(
        criteria,
        known_slot_hourly_rate_usd=50.0,
        max_marginal_cost_usd=5000.0,
    )
    squad_alt = next(a for a in alternatives if a.kind == OrganizationAlternativeKind.CREATE_TEMPORARY_SQUAD)
    assert squad_alt.estimated_cost_overhead_usd == 2000.0
    assert "50.0 USD/h x 40h" in squad_alt.cost_estimation_basis
    assert squad_alt.is_primary_recommendation is True


def test_evaluate_demand_default_cost_when_hourly_rate_unconfigured():
    criteria = DemandAnalysisCriteria(
        active_projects_count=3,
        future_commitments_count=2,
        unassigned_tasks_count=5,
        blocked_tasks_count=2,
        coordination_friction_score=0.55,
        observation_period_days=10,
    )
    # When unconfigured, base estimate is provided
    alternatives = evaluate_organizational_demand(criteria)
    squad_alt = next(a for a in alternatives if a.kind == OrganizationAlternativeKind.CREATE_TEMPORARY_SQUAD)
    assert squad_alt.estimated_cost_overhead_usd == 60.0
    assert "Estimación base de 60.0 USD" in squad_alt.cost_estimation_basis


def test_proposal_lifecycle_transitions():
    # Valid flow
    assert validate_proposal_transition(ProposalDecisionState.DRAFT, ProposalDecisionState.ANALYZED) is True
    assert validate_proposal_transition(ProposalDecisionState.ANALYZED, ProposalDecisionState.EVALUATED) is True
    assert validate_proposal_transition(ProposalDecisionState.EVALUATED, ProposalDecisionState.REQUIRES_CEO_APPROVAL) is True
    assert validate_proposal_transition(ProposalDecisionState.REQUIRES_CEO_APPROVAL, ProposalDecisionState.AUTONOMOUS_APPROVED) is True
    assert validate_proposal_transition(ProposalDecisionState.AUTONOMOUS_APPROVED, ProposalDecisionState.REJECTED) is True

    # Invalid illegal jumps
    assert validate_proposal_transition(ProposalDecisionState.DRAFT, ProposalDecisionState.EXECUTED) is False
    assert validate_proposal_transition(ProposalDecisionState.DRAFT, ProposalDecisionState.AUTONOMOUS_APPROVED) is False
    assert validate_proposal_transition(ProposalDecisionState.REJECTED, ProposalDecisionState.AUTONOMOUS_APPROVED) is False
    assert validate_proposal_transition(ProposalDecisionState.DISSOLVED, ProposalDecisionState.DRAFT) is False
