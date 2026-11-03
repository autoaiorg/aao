"""Tests for advisory organizational planning contracts."""

import math

import pytest

from aao.autonomous_organization import (
    DemandAnalysisCriteria,
    OrganizationAlternativeKind,
    OrganizationChangeImpact,
    classify_organizational_authority,
    evaluate_organizational_demand,
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


def test_classification_is_advisory_and_never_verifies_delegation():
    res = classify_organizational_authority("organization.unit.create_permanent")
    assert res.impact == OrganizationChangeImpact.CRITICAL
    assert res.requires_ceo_decision is True
    assert res.authorization_verified is False
    assert res.advisory_only is True
    assert "independently verified" in res.rationale


def test_unknown_operation_fails_closed():
    result = classify_organizational_authority("organization.unknown.activate")
    assert result.impact == OrganizationChangeImpact.UNKNOWN
    assert result.requires_ceo_decision is True
    assert result.authorization_verified is False


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
    assert not any(alternative.recommended for alternative in alternatives)
    squad = next(
        a for a in alternatives if a.kind == OrganizationAlternativeKind.CREATE_TEMPORARY_SQUAD
    )
    assert squad.recommended is False


def test_zero_cost_ceiling_blocks_paid_alternatives_even_with_demand():
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
    perm_alt_spike = next(
        a for a in spike_alts if a.kind == OrganizationAlternativeKind.CREATE_PERMANENT_UNIT
    )
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
    assert not any(
        alt.recommended and alt.estimated_cost_overhead_usd > 0 for alt in sustained_alts
    )
    permanent = next(
        a for a in sustained_alts if a.kind == OrganizationAlternativeKind.CREATE_PERMANENT_UNIT
    )
    assert permanent.recommended is False


def test_paid_alternative_requires_explicit_ceiling_and_ceiling_is_not_authority():
    criteria = DemandAnalysisCriteria(
        active_projects_count=4,
        future_commitments_count=3,
        unassigned_tasks_count=8,
        blocked_tasks_count=4,
        specialization_gaps=["frontend", "graphics"],
        coordination_friction_score=0.8,
        budget_utilization_ratio=0.75,
        observation_period_days=65,
    )

    # An offered ceiling does not turn an unknown cost into a verified estimate.
    unpriced = evaluate_organizational_demand(criteria, max_marginal_cost_usd=400)
    permanent_unpriced = next(
        a for a in unpriced if a.kind == OrganizationAlternativeKind.CREATE_PERMANENT_UNIT
    )
    assert permanent_unpriced.is_viable is True
    assert permanent_unpriced.estimated_cost_overhead_usd is None
    assert permanent_unpriced.recommended is False

    # A verifiable input rate permits an explicit cost estimate, not spend authority.
    priced = evaluate_organizational_demand(
        criteria,
        max_marginal_cost_usd=400,
        known_slot_hourly_rate_usd=0.5,
    )
    permanent_priced = next(
        a for a in priced if a.kind == OrganizationAlternativeKind.CREATE_PERMANENT_UNIT
    )
    assert permanent_priced.estimated_cost_overhead_usd == 240.0
    assert permanent_priced.recommended is True
    assert "not spend authority" in evaluate_organizational_demand.__doc__


@pytest.mark.parametrize("ceiling", [-1, math.inf, -math.inf, math.nan])
def test_cost_ceiling_must_be_finite_and_non_negative(ceiling):
    criteria = DemandAnalysisCriteria(1, 0, 0, 0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        evaluate_organizational_demand(criteria, max_marginal_cost_usd=ceiling)
