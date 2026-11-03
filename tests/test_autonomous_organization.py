"""Tests for Autonomous Organization Manager Contracts & Authority Engine."""
import pytest
from aao.autonomous_organization import (
    classify_organizational_authority,
    evaluate_organizational_demand,
    DemandAnalysisCriteria,
    OrganizationAlternativeKind,
    OrganizationChangeImpact,
)


def test_classify_constitutional_and_security_matters():
    # Modifying constitution requires CEO
    res = classify_organizational_authority("organization.constitution.change")
    assert res.impact == OrganizationChangeImpact.CONSTITUTIONAL
    assert res.requires_ceo_decision is True
    assert res.competent_authority == "CEO"

    # Modifying audit or security boundary requires CEO and Independent Auditor
    res_sec = classify_organizational_authority(
        "organization.unit.create_permanent", affects_audit_or_security=True
    )
    assert res_sec.impact == OrganizationChangeImpact.CONSTITUTIONAL
    assert res_sec.requires_ceo_decision is True
    assert res_sec.competent_authority == "CEO_AND_INDEPENDENT_AUDITOR"


def test_classify_permanent_unit_creation_without_delegation_blocks_activation():
    # Attempting to create a permanent department without active COO delegation blocks activation
    res = classify_organizational_authority(
        "organization.unit.create_permanent", has_coo_delegation=False
    )
    assert res.impact == OrganizationChangeImpact.CRITICAL
    assert res.requires_ceo_decision is True
    assert res.activation_blocked is True
    assert "Falta delegación formal vigente" in (res.blocker_reason or "")

    # With formal COO delegation, it becomes an ordinary structure operation
    res_delegated = classify_organizational_authority(
        "organization.unit.create_permanent", has_coo_delegation=True
    )
    assert res_delegated.impact == OrganizationChangeImpact.ORDINARY_STRUCTURE
    assert res_delegated.requires_ceo_decision is False
    assert res_delegated.activation_blocked is False


def test_evaluate_demand_favors_reuse_when_load_is_low():
    criteria = DemandAnalysisCriteria(
        active_projects_count=1,
        future_commitments_count=1,
        unassigned_tasks_count=1,
        blocked_tasks_count=0,
        coordination_friction_score=0.1,
    )
    alternatives = evaluate_organizational_demand(criteria)
    recommended = next(a for a in alternatives if a.recommended)
    assert recommended.kind == OrganizationAlternativeKind.REUSE_EXISTING_CAPACITY


def test_evaluate_demand_favors_temporary_squad_for_cross_project_friction():
    criteria = DemandAnalysisCriteria(
        active_projects_count=3,
        future_commitments_count=2,
        unassigned_tasks_count=5,
        blocked_tasks_count=2,
        coordination_friction_score=0.55,
        observation_period_days=10,
    )
    alternatives = evaluate_organizational_demand(criteria)
    recommended = next(a for a in alternatives if a.recommended)
    assert recommended.kind == OrganizationAlternativeKind.CREATE_TEMPORARY_SQUAD


def test_evaluate_demand_requires_60_days_observation_and_budget_for_permanent_unit():
    # Spurious spike of 5 days does NOT create a permanent department
    spike_criteria = DemandAnalysisCriteria(
        active_projects_count=4,
        future_commitments_count=3,
        unassigned_tasks_count=8,
        blocked_tasks_count=4,
        specialization_gaps=["frontend", "graphics"],
        coordination_friction_score=0.8,
        observation_period_days=5,
    )
    spike_alts = evaluate_organizational_demand(spike_criteria)
    perm_alt_spike = next(a for a in spike_alts if a.kind == OrganizationAlternativeKind.CREATE_PERMANENT_UNIT)
    assert perm_alt_spike.recommended is False

    # Sustained demand over 60 days with high friction and budget supports permanent unit
    sustained_criteria = DemandAnalysisCriteria(
        active_projects_count=4,
        future_commitments_count=3,
        unassigned_tasks_count=8,
        blocked_tasks_count=4,
        specialization_gaps=["frontend", "graphics"],
        coordination_friction_score=0.8,
        budget_utilization_ratio=0.75,
        observation_period_days=65,
        segregation_risk_detected=False,
    )
    sustained_alts = evaluate_organizational_demand(sustained_criteria)
    recommended = next(a for a in sustained_alts if a.recommended)
    assert recommended.kind == OrganizationAlternativeKind.CREATE_PERMANENT_UNIT
