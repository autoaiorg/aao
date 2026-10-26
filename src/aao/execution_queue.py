"""PostgreSQL inert execution queue with atomic claims and quarantine.

No tool adapter or language model execution is provided. A failed lease is
UNCERTAIN and must be reconciled by a separate authorized procedure.
"""
import hmac
import json
from uuid import uuid4

from aao.postgresql_connection import connect_postgres
from aao.principal_credentials import digest_token
from aao.protocol_instances import start_work_protocol


class ExecutionConflict(ValueError):
    pass


def journal(db, execution_id: str, kind: str, details: dict):
    db.execute(
        "INSERT INTO execution_journal(id,execution_id,kind,details) VALUES (%s,%s,%s,%s::jsonb)",
        (str(uuid4()), execution_id, kind, json.dumps(details)),
    )


def verify_execution_principal(db, worker_id, agent_credential):
    row = db.execute(
        "SELECT token_digest,enabled FROM principal_credentials "
        "WHERE principal_id=%s AND kind='AGENT' FOR SHARE", (worker_id,)
    ).fetchone()
    if not row or not row[1] or not hmac.compare_digest(
        digest_token(agent_credential), row[0]
    ):
        raise ExecutionConflict("Individual agent credential invalid or revoked")


def claim(worker_id: str, *, agent_credential: str, project_id: str,
          seconds: int = 60):
    if not worker_id or not project_id or seconds < 1:
        raise ExecutionConflict("Worker and positive lease duration required")
    with connect_postgres() as db:
        verify_execution_principal(db, worker_id, agent_credential)
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='execution.claim' "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
            (worker_id, project_id),
        ).fetchone()
        if not grant:
            raise ExecutionConflict("Project execution claim grant required")
        row = db.execute(
            "SELECT q.id,q.work_id,q.input_json FROM execution_queue q "
            "JOIN projects p ON p.id=q.project_id "
            "JOIN work_items w ON w.id=q.work_id "
            "LEFT JOIN work_item_assignments a ON a.project_id=q.project_id AND a.work_id=q.work_id "
            "WHERE q.status='QUEUED' AND p.state='ACTIVE' AND q.project_id=%s "
            "AND (w.parent_work_id IS NULL OR a.principal_id=%s) "
            "ORDER BY q.created_at,q.id FOR UPDATE OF q SKIP LOCKED LIMIT 1",
            (project_id, worker_id),
        ).fetchone()
        if not row:
            return None
        eid, work_id, input_data = str(row[0]), str(row[1]), row[2]
        project_id = db.execute(
            "SELECT project_id FROM execution_queue WHERE id=%s", (eid,)
        ).fetchone()[0]
        project = db.execute(
            "SELECT state,state_generation FROM projects WHERE id=%s FOR UPDATE",
            (project_id,),
        ).fetchone()
        if not project or project[0] != "ACTIVE":
            return None
        if isinstance(input_data, str):
            input_data = json.loads(input_data)
        if isinstance(input_data, dict) and input_data.get("type") == "aao.repository-check.v1":
            if set(input_data) != {"type", "check_id", "capability_id", "version"}:
                raise ExecutionConflict("Repository check selection is malformed")
            capability = db.execute(
                "SELECT capability_type,status,contract->>'entrypoint' "
                "FROM capability_versions WHERE project_id=%s AND capability_id=%s "
                "AND version=%s FOR SHARE",
                (project_id, input_data["capability_id"], input_data["version"]),
            ).fetchone()
            if (not capability or capability[0] != "cli_script"
                    or capability[1] != "registered_local"
                    or capability[2] != "aao.sandboxed_repository_checks:core-unit"):
                raise ExecutionConflict("Selected repository-check capability is unavailable")
            if input_data["check_id"] != "core-unit":
                raise ExecutionConflict("Repository check is not allow-listed")
        token = str(uuid4())
        expiry = db.execute(
            "UPDATE execution_queue SET status='RUNNING',lease_token=%s,"
            "worker_id=%s,lease_expires_at=clock_timestamp()+make_interval(secs => %s),"
            "project_state_generation=%s,attempts=attempts+1 "
            "WHERE id=%s RETURNING lease_expires_at",
            (token, worker_id, seconds, project[1], eid),
        ).fetchone()[0]
        journal(db, eid, "claimed", {"worker_id": worker_id})
    return {"execution_id": eid, "work_id": work_id, "input": input_data,
            "token": token, "worker_id": worker_id,
            "expires_at": expiry.isoformat()}


def complete(execution_id: str, token: str, worker_id: str, result: dict,
             *, agent_credential: str):
    with connect_postgres() as db:
        verify_execution_principal(db, worker_id, agent_credential)
        execution = db.execute(
            "SELECT project_id,project_state_generation FROM execution_queue "
            "WHERE id=%s FOR UPDATE",
            (execution_id,),
        ).fetchone()
        if not execution:
            raise ExecutionConflict("Execution not found")
        assignment = db.execute(
            "SELECT w.parent_work_id,a.principal_id FROM execution_queue q "
            "JOIN work_items w ON w.id=q.work_id "
            "LEFT JOIN work_item_assignments a ON a.project_id=q.project_id AND a.work_id=q.work_id "
            "WHERE q.id=%s FOR SHARE OF w", (execution_id,),
        ).fetchone()
        if assignment and assignment[0] is not None and (
            assignment[1] is None or str(assignment[1]) != worker_id
        ):
            raise ExecutionConflict("Execution worker does not own the work assignment")
        project = db.execute(
            "SELECT state,state_generation FROM projects WHERE id=%s FOR UPDATE",
            (execution[0],),
        ).fetchone()
        if not project or project[0] != "ACTIVE":
            raise ExecutionConflict("Project is not active")
        if execution[1] is None or execution[1] != project[1]:
            raise ExecutionConflict("Project state changed after this lease was issued")
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='execution.claim' "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
            (worker_id, str(execution[0])),
        ).fetchone()
        if not grant:
            raise ExecutionConflict("Project execution claim grant revoked")
        final_status = "FAILED" if result.get("conclusion") == "failure" else "SUCCEEDED"
        updated = db.execute(
            "UPDATE execution_queue SET status=%s,result_json=%s::jsonb "
            "WHERE id=%s AND status='RUNNING' AND lease_token=%s "
            "AND worker_id=%s AND lease_expires_at>clock_timestamp() AND EXISTS (SELECT 1 FROM projects p WHERE p.id=execution_queue.project_id AND p.state='ACTIVE') RETURNING id",
            (final_status, json.dumps(result), execution_id, token, worker_id),
        ).fetchone()
        if not updated:
            raise ExecutionConflict("Lease stale, expired, or execution not running")
        journal(db, execution_id, "completed", {
            "worker_id": worker_id, "status": final_status,
        })


def quarantine_expired() -> int:
    """Quarantine expired leases and pin an auditable escalation episode.

    This system transition does not retry, assign, reconcile, or authorize work.
    """
    with connect_postgres() as db:
        rows = db.execute(
            "UPDATE execution_queue SET status='UNCERTAIN' "
            "WHERE status='RUNNING' AND lease_expires_at<=clock_timestamp() "
            "RETURNING id,work_id,project_id,worker_id,attempts",
        ).fetchall()
        for row in rows:
            execution_id, work_id, project_id, worker_id, attempts = row
            execution_id = str(execution_id)
            work_id = str(work_id)
            protocol_instance_id = start_work_protocol(
                db,
                protocol_id="blockage-escalation",
                work_id=work_id,
                started_by="system:execution_queue.quarantine_expired",
                subject_type="work_item",
                idempotency_key=(
                    f"blockage-escalation:work_item:{work_id}:execution:{execution_id}:"
                    f"attempt:{attempts}"
                ),
                request={
                    "execution_id": execution_id,
                    "project_id": str(project_id),
                    "worker_id": worker_id,
                    "attempt": attempts,
                    "reason": "lease expired; execution outcome uncertain",
                },
            )
            journal(db, execution_id, "quarantined", {
                "reason": "lease expired",
                "protocol_instance_id": protocol_instance_id,
            })
            db.execute(
                "INSERT INTO events(id,subject_id,kind,details) "
                "VALUES (%s,%s,'work.execution_quarantined',%s::jsonb)",
                (str(uuid4()), work_id, json.dumps({
                    "execution_id": execution_id,
                    "project_id": str(project_id),
                    "former_worker_id": worker_id,
                    "attempt": attempts,
                    "protocol_instance_id": protocol_instance_id,
                    "next_action": (
                        "An independent auditor with the existing execution.reconcile grant "
                        "must review evidence before disposition; do not retry automatically."
                    ),
                })),
            )
        return len(rows)


def state(execution_id: str):
    with connect_postgres() as db:
        row = db.execute(
            "SELECT id,work_id,project_id,status,attempts,lease_expires_at "
            "FROM execution_queue WHERE id=%s", (execution_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": str(row[0]), "work_id": str(row[1]),
                "project_id": str(row[2]), "status": row[3],
                "attempts": row[4], "lease_expires_at": row[5]}
