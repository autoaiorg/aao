"""Reconcile effect records without ever invoking the external system.

Fail closed: only PROPOSED may be rejected; any other state requires
separate investigation before the executing system can be retried.
"""
import json
from uuid import uuid4

from aao.postgresql_connection import connect_postgres


class EffectReviewDenied(ValueError):
    pass


def reject_unexecuted_proposal(effect_id: str, *, auditor_credential: str, evidence: list[str]):
    if not auditor_credential or not evidence:
        raise EffectReviewDenied("Active auditor credential and meaningful evidence required")
    with connect_postgres() as db:
        from aao.principal_credentials import PrincipalDenied, authenticate_identity_in_transaction
        try:
            reviewer_id = authenticate_identity_in_transaction(
                db, auditor_credential, kind="AUDITOR"
            )
        except PrincipalDenied as exc:
            raise EffectReviewDenied("Active auditor credential required") from exc
        candidate = db.execute(
            "SELECT execution_id FROM external_effects WHERE id=%s",
            (effect_id,),
        ).fetchone()
        if not candidate:
            raise EffectReviewDenied("Only unexecuted proposals may be rejected")
        execution_id = str(candidate[0])
        execution = db.execute(
            "SELECT q.project_id,q.worker_id FROM execution_queue q "
            "JOIN projects p ON p.id=q.project_id WHERE q.id=%s "
            "FOR UPDATE OF q,p", (execution_id,),
        ).fetchone()
        if not execution:
            raise EffectReviewDenied("Only unexecuted proposals may be rejected")
        project_id, worker_id = execution
        effect = db.execute(
            "SELECT status,execution_id FROM external_effects WHERE id=%s FOR UPDATE",
            (effect_id,),
        ).fetchone()
        if not effect or str(effect[1]) != execution_id or effect[0] != "PROPOSED":
            raise EffectReviewDenied("Only unexecuted proposals may be rejected")
        if reviewer_id == worker_id:
            raise EffectReviewDenied("Execution worker may not review own effect")
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='effect.reconcile' "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
            (reviewer_id, project_id),
        ).fetchone()
        if not grant:
            raise EffectReviewDenied("Independent effect capability missing")
        from aao.evidence_registry import EvidenceDenied, verify_evidence_references
        try:
            verified_evidence = verify_evidence_references(db, project_id, evidence)
        except EvidenceDenied as exc:
            raise EffectReviewDenied(str(exc)) from exc
        db.execute("UPDATE external_effects SET status='REJECTED' WHERE id=%s", (effect_id,))
        db.execute(
            "INSERT INTO execution_journal(id,execution_id,kind,details) "
            "VALUES (%s,%s,'effect.rejected',%s::jsonb)",
            (str(uuid4()), execution_id, json.dumps({
                "effect_id": effect_id, "reviewer": reviewer_id,
                "evidence": verified_evidence,
            })),
        )
    return "REJECTED"
