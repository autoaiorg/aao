"""Reconcile UNCERTAIN executions using project-scoped evidence artifacts.

This operation only changes queue state. It NEVER calls tools or retries work.
"""
import json
from uuid import uuid4

from aao.postgresql_connection import connect_postgres


class ReconciliationDenied(ValueError):
    pass


def reconcile(execution_id: str, *, auditor_credential: str, evidence: list[str],
              disposition: str) -> str:
    if disposition not in {"RETRY_CONFIRMED_SAFE", "MARK_FAILED"}:
        raise ReconciliationDenied("Unknown disposition")
    if not auditor_credential:
        raise ReconciliationDenied("Active auditor credential and independent evidence required")
    from aao.evidence_registry import EvidenceDenied, validate_evidence_references

    try:
        validate_evidence_references(evidence)
    except EvidenceDenied as exc:
        raise ReconciliationDenied(
            "Active auditor credential and valid independent evidence required"
        ) from exc
    with connect_postgres() as db:
        from aao.principal_credentials import PrincipalDenied, authenticate_in_transaction
        try:
            reviewer_id = authenticate_in_transaction(
                db, auditor_credential, kind="AUDITOR"
            )
        except PrincipalDenied as exc:
            raise ReconciliationDenied("Active auditor credential required") from exc
        execution = db.execute(
            "SELECT q.status,q.worker_id,q.project_id,p.state,q.work_id "
            "FROM execution_queue q JOIN projects p ON p.id=q.project_id "
            "WHERE q.id=%s FOR UPDATE OF q,p", (execution_id,),
        ).fetchone()
        if not execution or execution[0] != "UNCERTAIN":
            raise ReconciliationDenied("Execution not uncertain")
        status, former_worker, project_id, project_state, work_id = execution
        if reviewer_id == former_worker:
            raise ReconciliationDenied("Worker cannot reconcile own execution")
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='execution.reconcile' "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
            (reviewer_id, project_id),
        ).fetchone()
        if not grant:
            raise ReconciliationDenied("Reconciliation capability required")
        from aao.evidence_registry import verify_evidence_references
        try:
            verified_evidence = verify_evidence_references(db, project_id, evidence)
        except EvidenceDenied as exc:
            raise ReconciliationDenied(str(exc)) from exc
        if disposition == "RETRY_CONFIRMED_SAFE":
            if project_state != "ACTIVE":
                raise ReconciliationDenied("Project must be active to retry")
            effect = db.execute(
                "SELECT 1 FROM external_effects WHERE execution_id=%s "
                "AND status NOT IN ('REJECTED') LIMIT 1", (execution_id,),
            ).fetchone()
            if effect:
                raise ReconciliationDenied(
                    "External effect exists; manual effects reconciliation required"
                )
        quarantine = db.execute(
            "SELECT details->>'protocol_instance_id' FROM events "
            "WHERE subject_id=%s AND kind='work.execution_quarantined' "
            "AND details->>'execution_id'=%s ORDER BY created_at DESC,id DESC LIMIT 1",
            (work_id, execution_id),
        ).fetchone()
        protocol_instance_id = quarantine[0] if quarantine else None
        new_state = "QUEUED" if disposition == "RETRY_CONFIRMED_SAFE" else "FAILED"
        db.execute(
            "UPDATE execution_queue SET status=%s,worker_id=NULL,"
            "lease_token=NULL,lease_expires_at=NULL,project_state_generation=NULL "
            "WHERE id=%s",
            (new_state, execution_id),
        )
        db.execute(
            "INSERT INTO execution_journal(id,execution_id,kind,details) "
            "VALUES (%s,%s,'reconciled',%s::jsonb)",
            (str(uuid4()), execution_id, json.dumps({
                "reviewer": reviewer_id, "disposition": disposition,
                "evidence": verified_evidence, "prior_state": status,
            })),
        )
        db.execute(
            "INSERT INTO events(id,subject_id,kind,details) "
            "VALUES (%s,%s,'work.execution_reconciled',%s::jsonb)",
            (str(uuid4()), str(work_id), json.dumps({
                "execution_id": execution_id,
                "project_id": str(project_id),
                "actor": str(reviewer_id),
                "disposition": disposition,
                "resulting_state": new_state,
                "prior_state": status,
                "evidence": verified_evidence,
                "protocol_instance_id": protocol_instance_id,
            })),
        )
    return new_state
