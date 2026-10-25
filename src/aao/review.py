"""Fail-closed review policy shared by development APIs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewDecision:
    allowed: bool
    reason: str


def evaluate_review(*, author_id: str, reviewer_id: str, evidence: list[str],
                    decision: str, project_active: bool,
                    identity_and_evidence_verified: bool = False) -> ReviewDecision:
    """APPROVE is allowed only for callers that verified the reviewer's separate
    credential and the content-addressed evidence before calling (PostgreSQL API)."""
    if not project_active:
        return ReviewDecision(False, "Project is not active")
    if not author_id or not reviewer_id or author_id == reviewer_id:
        return ReviewDecision(False, "Independent reviewer is required")
    if not evidence or not all(item.strip() for item in evidence):
        return ReviewDecision(False, "Evidence references required")
    if decision not in {"APPROVE", "REJECT", "VETO"}:
        return ReviewDecision(False, "Unknown review decision")
    if decision == "VETO":
        return ReviewDecision(True, "Veto recorded; approval remains blocked")
    if decision == "APPROVE" and not identity_and_evidence_verified:
        return ReviewDecision(
            False,
            "Approval disabled until independent identity and evidence verification exist",
        )
    return ReviewDecision(True, "Independent review recorded")
