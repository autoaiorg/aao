"""Advisory Autonomous Organization Manager planning contracts & state engine.

Spec: AAO Autonomous Organization Architecture (V4) & CEO-DEC-ENTERPRISE-MODEL-2026-10-26.
Precedence: Constitution, CEO decisions, confirmed project mandates, applicable policies.

Separates explicitly:
1) Impact & authority classification (Constitutional / Critical / Autonomous Delegate).
2) Multi-dimensional demand analysis (Demand, Capacity, Specialization, Efficiency, Governance).
3) Evaluated organizational alternatives (Reuse, Reassign, Temporary Squad, Unit Expansion, Permanent Unit).
4) Organizational lifecycle, stability periods & anti-thrashing cooldowns.
5) Advisory authority routing; enforcement remains in the policy layer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class OrganizationChangeImpact(StrEnum):
    """Impact tier of an organizational change."""

    CONSTITUTIONAL = "CONSTITUTIONAL"  # Involves Constitution, audit independence, kernel boundaries
    CRITICAL = "CRITICAL"  # Permanent unit creation, capability boundary alteration
    ORDINARY_STRUCTURE = "ORDINARY_STRUCTURE"  # Department split/merge within confirmed mandates
    OPERATIONAL_TEAM = "OPERATIONAL_TEAM"  # Temporary work squad, cross-functional mission team
    SLOT_ASSIGNMENT = "SLOT_ASSIGNMENT"  # Workstation allocation without permission expansion
    UNKNOWN = "UNKNOWN"  # Unknown operation; fail closed


class OrganizationAlternativeKind(StrEnum):
    """Evaluated organizational design alternatives."""

    REUSE_EXISTING_CAPACITY = "REUSE_EXISTING_CAPACITY"
    REASSIGN_AVAILABLE_AGENTS = "REASSIGN_AVAILABLE_AGENTS"
    CREATE_TEMPORARY_SQUAD = "CREATE_TEMPORARY_SQUAD"
    EXPAND_EXISTING_UNIT = "EXPAND_EXISTING_UNIT"
    CREATE_PERMANENT_UNIT = "CREATE_PERMANENT_UNIT"


class ProposalDecisionState(StrEnum):
    """Lifecycle state of an organizational change proposal."""

    DRAFT = "DRAFT"
    ANALYZED = "ANALYZED"
    EVALUATED = "EVALUATED"
    REQUIRES_CEO_APPROVAL = "REQUIRES_CEO_APPROVAL"
    AUTONOMOUS_APPROVED = "AUTONOMOUS_APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    DISSOLVED = "DISSOLVED"


# Strict governed state transitions
VALID_STATE_TRANSITIONS: dict[ProposalDecisionState, set[ProposalDecisionState]] = {
    ProposalDecisionState.DRAFT: {
        ProposalDecisionState.ANALYZED,
        ProposalDecisionState.REJECTED,
    },
    ProposalDecisionState.ANALYZED: {
        ProposalDecisionState.EVALUATED,
        ProposalDecisionState.REJECTED,
    },
    ProposalDecisionState.EVALUATED: {
        ProposalDecisionState.REQUIRES_CEO_APPROVAL,
        ProposalDecisionState.AUTONOMOUS_APPROVED,
        ProposalDecisionState.REJECTED,
    },
    ProposalDecisionState.REQUIRES_CEO_APPROVAL: {
        ProposalDecisionState.AUTONOMOUS_APPROVED,
        ProposalDecisionState.REJECTED,
    },
    ProposalDecisionState.AUTONOMOUS_APPROVED: {
        ProposalDecisionState.REJECTED,
        # EXECUTED is reserved for future execution engine when authority is verified
    },
    ProposalDecisionState.REJECTED: set(),
    ProposalDecisionState.EXECUTED: {
        ProposalDecisionState.DISSOLVED,
    },
    ProposalDecisionState.DISSOLVED: set(),
}


@dataclass(frozen=True)
class DemandAnalysisCriteria:
    """5-dimensional evaluation criteria for organizational needs."""

    active_projects_count: int
    future_commitments_count: int
    unassigned_tasks_count: int
    blocked_tasks_count: int
    specialization_gaps: list[str] = field(default_factory=list)
    coordination_friction_score: float = 0.0  # 0.0 (smooth) to 1.0 (extreme friction)
    budget_utilization_ratio: float = 0.0  # 0.0 to 1.0
    segregation_risk_detected: bool = False
    observation_period_days: int = 14

    def __post_init__(self) -> None:
        if self.active_projects_count < 0 or self.future_commitments_count < 0:
            raise ValueError("Project and commitment counts must be non-negative")
        if self.unassigned_tasks_count < 0 or self.blocked_tasks_count < 0:
            raise ValueError("Task counts must be non-negative")
        if (
            not math.isfinite(self.coordination_friction_score)
            or not (0.0 <= self.coordination_friction_score <= 1.0)
        ):
            raise ValueError("coordination_friction_score must be a finite float between 0.0 and 1.0")
        if (
            not math.isfinite(self.budget_utilization_ratio)
            or not (0.0 <= self.budget_utilization_ratio <= 1.0)
        ):
            raise ValueError("budget_utilization_ratio must be a finite float between 0.0 and 1.0")
        if self.observation_period_days < 0:
            raise ValueError("observation_period_days must be non-negative")


@dataclass(frozen=True)
class EvaluatedAlternative:
    """A scored advisory alternative; cost is an estimate, not accounting evidence."""

    kind: OrganizationAlternativeKind
    description: str
    estimated_cost_overhead_usd: float | None  # None indicates unknown / not determined
    cost_estimation_basis: str  # Grounded rationale for cost estimate
    implementation_delay_hours: float
    governance_risk_level: str  # low, medium, high, critical
    score: float  # Higher is better
    is_viable: bool  # Whether alternative meets criteria
    is_primary_recommendation: bool  # Exactly one or zero primary recommendations
    rationale: str

    @property
    def recommended(self) -> bool:
        """Backward-compatible alias for is_primary_recommendation."""
        return self.is_primary_recommendation


@dataclass
class OrganizationalProposal:
    """Persistent proposal generated by Organization Designer."""

    id: str
    version: int
    title: str
    scope_description: str
    target_unit_id: str | None
    target_unit_code: str | None
    target_unit_name: str | None
    parent_unit_id: str | None
    lead_principal_id: str | None
    proposed_role_title: str | None
    impact: OrganizationChangeImpact
    state: ProposalDecisionState
    demand_summary: str
    criteria: DemandAnalysisCriteria
    alternatives: list[EvaluatedAlternative] = field(default_factory=list)
    chosen_alternative: OrganizationAlternativeKind | None = None
    authority_classification: AuthorityClassificationResult | None = None
    author_principal_id: str = ""
    delegation_authority_id: str | None = None
    rejection_reason: str | None = None
    stability_review_due_at: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class AuthorityClassificationResult:
    """Advisory route classification; it does not verify or grant authority."""

    impact: OrganizationChangeImpact
    requires_ceo_decision: bool
    competent_authority: str
    rationale: str
    authorization_verified: bool = False
    advisory_only: bool = True


def classify_organizational_authority(
    operation: str,
    *,
    affects_audit_or_security: bool = False,
    grants_new_privileges: bool = False,
    is_constitutional_matter: bool = False,
) -> AuthorityClassificationResult:
    """
    Classifies a proposed operation for planning only.

    This function deliberately does not accept caller-asserted delegation booleans
    and never authorizes activation. Callers must verify CEO decisions and scoped,
    live grants through the enforcement policy before performing an operation.
    """
    if is_constitutional_matter or operation in {
        "organization.constitution.change",
        "organization.mission.change",
    }:
        return AuthorityClassificationResult(
            impact=OrganizationChangeImpact.CONSTITUTIONAL,
            requires_ceo_decision=True,
            competent_authority="CEO",
            rationale="Constitutional modification or organization mission alteration is strictly reserved to CEO.",
        )

    if (
        affects_audit_or_security
        or grants_new_privileges
        or operation
        in {
            "security.privilege.expand",
            "audit.independence.alter",
        }
    ):
        return AuthorityClassificationResult(
            impact=OrganizationChangeImpact.CONSTITUTIONAL,
            requires_ceo_decision=True,
            competent_authority="CEO_AND_INDEPENDENT_AUDITOR",
            rationale="Modifying security privileges or audit functional independence cannot be delegated.",
        )

    if operation in {
        "organization.unit.create_permanent",
        "organization.unit.merge",
        "organization.unit.split",
    }:
        return AuthorityClassificationResult(
            impact=OrganizationChangeImpact.CRITICAL,
            requires_ceo_decision=True,
            competent_authority="CEO_OR_VERIFIED_COO_DELEGATE",
            rationale="Permanent unit changes require a real CEO decision or independently verified scoped COO delegation; this classifier verifies neither.",
        )

    if operation in {
        "organization.squad.create_temporary",
        "organization.squad.dissolve",
        "organization.slot.assign",
    }:
        return AuthorityClassificationResult(
            impact=OrganizationChangeImpact.OPERATIONAL_TEAM,
            requires_ceo_decision=False,
            competent_authority="COO_DELEGATE",
            rationale="Advisory classification only; verify current project scope and delegation in the enforcement policy.",
        )

    return AuthorityClassificationResult(
        impact=OrganizationChangeImpact.UNKNOWN,
        requires_ceo_decision=True,
        competent_authority="CEO_GOVERNANCE_REVIEW",
        rationale="Unrecognized operation; fail closed and obtain governance review before any action.",
    )


def evaluate_organizational_demand(
    criteria: DemandAnalysisCriteria,
    *,
    max_marginal_cost_usd: float = 0.0,
    min_permanent_observation_days: int = 60,
    known_slot_hourly_rate_usd: float | None = None,
) -> list[EvaluatedAlternative]:
    """
    Evaluates alternatives for planning only. Input ceiling is not spend authority.
    Cost values are estimates, not accounting evidence. Never reorganizes solely
    for temporary queue spikes.
    """
    if not math.isfinite(max_marginal_cost_usd) or max_marginal_cost_usd < 0:
        raise ValueError("max_marginal_cost_usd must be finite and non-negative")
    if min_permanent_observation_days < 1:
        raise ValueError("min_permanent_observation_days must be at least 1")

    # 1. Alternative: Reuse Existing Capacity
    can_reuse = (
        criteria.unassigned_tasks_count <= 2
        and criteria.coordination_friction_score < 0.3
        and criteria.blocked_tasks_count == 0
    )
    alt_reuse = EvaluatedAlternative(
        kind=OrganizationAlternativeKind.REUSE_EXISTING_CAPACITY,
        description="Reabsorber el flujo de trabajo en los departamentos existentes sin alterar la estructura.",
        estimated_cost_overhead_usd=0.0,
        cost_estimation_basis="Coste marginal cero: reabsorción en capacidad horaria ya provisionada.",
        implementation_delay_hours=0.0,
        governance_risk_level="low",
        score=0.95 if can_reuse else 0.3,
        is_viable=can_reuse,
        is_primary_recommendation=False,
        rationale="La carga actual no justifica costes de coordinación o reestructuración.",
    )

    # 2. Alternative: Reassign Available Agents
    can_reassign = (
        criteria.unassigned_tasks_count > 2
        and len(criteria.specialization_gaps) == 0
        and criteria.coordination_friction_score < 0.5
    )
    alt_reassign = EvaluatedAlternative(
        kind=OrganizationAlternativeKind.REASSIGN_AVAILABLE_AGENTS,
        description="Reubicar agentes con competencias compatibles hacia los puestos saturados.",
        estimated_cost_overhead_usd=0.0,
        cost_estimation_basis="Coste marginal cero: redistribución de asignaciones existentes sin nuevas credenciales ni instancias.",
        implementation_delay_hours=1.0,
        governance_risk_level="low",
        score=0.88 if can_reassign else 0.4,
        is_viable=can_reassign,
        is_primary_recommendation=False,
        rationale="Existen agentes disponibles con competencias adecuadas para balancear la carga.",
    )

    # 3. Alternative: Create Temporary Squad (Escuadra Operativa)
    needs_squad = (
        criteria.active_projects_count >= 2
        and criteria.coordination_friction_score >= 0.4
        and criteria.observation_period_days < min_permanent_observation_days
    )
    squad_cost = (
        known_slot_hourly_rate_usd * 40.0
        if known_slot_hourly_rate_usd is not None
        else None
    )
    squad_basis = (
        f"Estimación basada en tasa horaria de {known_slot_hourly_rate_usd} USD/h x 40h de coordinación."
        if known_slot_hourly_rate_usd is not None
        else "Coste desconocido: falta tarifa horaria verificada."
    )
    alt_squad = EvaluatedAlternative(
        kind=OrganizationAlternativeKind.CREATE_TEMPORARY_SQUAD,
        description="Crear una escuadra operativa temporal multidisciplinar vinculada a los hitos de los proyectos.",
        estimated_cost_overhead_usd=squad_cost,
        cost_estimation_basis=squad_basis,
        implementation_delay_hours=4.0,
        governance_risk_level="medium",
        score=0.85 if needs_squad else 0.45,
        is_viable=needs_squad,
        is_primary_recommendation=False,
        rationale="Demanda interdepartamental transitoria con necesidad de coordinación estrecha.",
    )

    # 4. Alternative: Expand Existing Unit
    needs_unit_expansion = (
        criteria.observation_period_days >= (min_permanent_observation_days // 2)
        and len(criteria.specialization_gaps) == 1
        and criteria.coordination_friction_score < 0.6
    )
    expansion_cost = (
        known_slot_hourly_rate_usd * 160.0
        if known_slot_hourly_rate_usd is not None
        else None
    )
    expansion_basis = (
        f"Estimación basada en tasa horaria de {known_slot_hourly_rate_usd} USD/h x 160h dedicadas."
        if known_slot_hourly_rate_usd is not None
        else "Coste desconocido: falta tarifa horaria verificada."
    )
    alt_expand = EvaluatedAlternative(
        kind=OrganizationAlternativeKind.EXPAND_EXISTING_UNIT,
        description="Crear puestos especializados permanentes dentro del departamento existente correspondiente.",
        estimated_cost_overhead_usd=expansion_cost,
        cost_estimation_basis=expansion_basis,
        implementation_delay_hours=12.0,
        governance_risk_level="medium",
        score=0.80 if needs_unit_expansion else 0.4,
        is_viable=needs_unit_expansion,
        is_primary_recommendation=False,
        rationale="La especialización requerida pertenece naturalmente al mandato del departamento existente.",
    )

    # 5. Alternative: Create Permanent Unit
    needs_permanent_unit = (
        criteria.observation_period_days >= min_permanent_observation_days
        and len(criteria.specialization_gaps) >= 2
        and criteria.coordination_friction_score >= 0.7
        and criteria.budget_utilization_ratio >= 0.6
        and not criteria.segregation_risk_detected
    )
    perm_cost = (
        known_slot_hourly_rate_usd * 480.0
        if known_slot_hourly_rate_usd is not None
        else None
    )
    perm_basis = (
        f"Estimación de departamento permanente basada en {known_slot_hourly_rate_usd} USD/h x 480h."
        if known_slot_hourly_rate_usd is not None
        else "Coste desconocido: falta plan financiero verificado."
    )
    alt_permanent = EvaluatedAlternative(
        kind=OrganizationAlternativeKind.CREATE_PERMANENT_UNIT,
        description="Constituir un nuevo departamento permanente con mandato y responsabilidad orgánica delimitada.",
        estimated_cost_overhead_usd=perm_cost,
        cost_estimation_basis=perm_basis,
        implementation_delay_hours=48.0,
        governance_risk_level="high",
        score=0.92 if needs_permanent_unit else 0.25,
        is_viable=needs_permanent_unit,
        is_primary_recommendation=False,
        rationale="Necesidad estructural sostenida que excede los mandatos vigentes.",
    )

    raw_list = [alt_reuse, alt_reassign, alt_squad, alt_expand, alt_permanent]
    # Filter viable options whose cost does not exceed max_marginal_cost_usd
    viable_candidates = [
        alt
        for alt in raw_list
        if alt.is_viable
        and (
            alt.estimated_cost_overhead_usd is not None
            and alt.estimated_cost_overhead_usd <= max_marginal_cost_usd
        )
    ]

    # Select single primary recommendation by highest score among viable within budget
    best_candidate_kind = None
    if viable_candidates:
        best_candidate = max(viable_candidates, key=lambda a: a.score)
        best_candidate_kind = best_candidate.kind

    # Return sorted alternatives with exactly one primary recommendation marked
    results = [
        EvaluatedAlternative(
            kind=alt.kind,
            description=alt.description,
            estimated_cost_overhead_usd=alt.estimated_cost_overhead_usd,
            cost_estimation_basis=alt.cost_estimation_basis,
            implementation_delay_hours=alt.implementation_delay_hours,
            governance_risk_level=alt.governance_risk_level,
            score=alt.score,
            is_viable=alt.is_viable,
            is_primary_recommendation=(alt.kind == best_candidate_kind),
            rationale=alt.rationale,
        )
        for alt in raw_list
    ]
    results.sort(key=lambda a: a.score, reverse=True)
    return results


def validate_proposal_transition(
    current_state: ProposalDecisionState,
    target_state: ProposalDecisionState,
) -> bool:
    """Validates whether a lifecycle transition is permitted by governance rules."""
    allowed = VALID_STATE_TRANSITIONS.get(current_state, set())
    return target_state in allowed
