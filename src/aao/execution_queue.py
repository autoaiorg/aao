"""PostgreSQL inert execution queue with atomic claims and quarantine.

No tool adapter or language model execution is provided. A failed lease is
UNCERTAIN and must be reconciled by a separate authorized procedure.
"""
import json
from uuid import UUID, uuid4

from aao.host_identity import HostIdentityError, current_host_id
from aao.postgresql_connection import connect_postgres
from aao.protocol_instances import start_work_protocol


class ExecutionConflict(ValueError):
    pass


def journal(db, execution_id: str, kind: str, details: dict):
    db.execute(
        "INSERT INTO execution_journal(id,execution_id,kind,details) VALUES (%s,%s,%s,%s::jsonb)",
        (str(uuid4()), execution_id, kind, json.dumps(details)),
    )


def result_status(input_data: object, result: object) -> str:
    """Classify only recognized, structurally valid results as successful."""
    if isinstance(input_data, str):
        try:
            input_data = json.loads(input_data)
        except json.JSONDecodeError:
            input_data = None
    if not isinstance(input_data, dict) or not isinstance(result, dict):
        return "FAILED"

    task_type = input_data.get("type")
    if task_type == "aao.inert.v1":
        return "SUCCEEDED" if result.get("kind") == "aao.inert-worker.v1" else "FAILED"
    if result.get("kind") != task_type or result.get("conclusion") != "success":
        return "FAILED"

    def is_sha(value: object) -> bool:
        return (isinstance(value, str) and len(value) == 40
                and all(char in "0123456789abcdef" for char in value))

    if task_type == "aao.repository-check.v1":
        limits = result.get("limits")
        expected_limits = {
            "network": "unshared",
            "source": "read-only mounted source/tests/config",
            "home_and_secrets": "not mounted; environment allow-listed",
            "timeout_seconds": 120,
            "memory_bytes": 1_073_741_824,
            "temporary_filesystem_bytes": 268_435_456,
        }
        return "SUCCEEDED" if (
            set(input_data) == {"type", "check_id", "capability_id", "version"}
            and set(result) == {
                "kind", "check_id", "capability_id", "capability_version",
                "extra_tests", "candidate_sha", "conclusion", "exit_code",
                "duration_ms", "stdout", "stderr", "limits",
            }
            and result.get("check_id") == input_data.get("check_id")
            and result.get("capability_id") == input_data.get("capability_id")
            and result.get("capability_version") == input_data.get("version")
            and is_sha(result.get("candidate_sha"))
            and type(result.get("exit_code")) is int
            and result.get("exit_code") == 0
            and type(result.get("duration_ms")) is int
            and result["duration_ms"] >= 0
            and isinstance(result.get("extra_tests"), list)
            and all(isinstance(path, str) for path in result["extra_tests"])
            and isinstance(result.get("stdout"), str)
            and isinstance(result.get("stderr"), str)
            and limits == expected_limits
        ) else "FAILED"

    if task_type == "aao.agent-patch.v1":
        task_capability = input_data.get("capability_id")
        task_version = input_data.get("version")
        task_base_sha = input_data.get("base_sha")
        check = result.get("check")
        candidate = result.get("candidate_sha")
        proposal_id = result.get("proposal_id")
        paths = result.get("changed_paths")
        patch_sha = result.get("patch_sha256")
        return "SUCCEEDED" if (
            set(input_data) == {"type", "capability_id", "version", "base_sha"}
            and isinstance(task_capability, str) and bool(task_capability)
            and isinstance(task_version, str) and bool(task_version)
            and is_sha(task_base_sha)
            and isinstance(result.get("kind"), str)
            and is_sha(candidate)
            and result.get("candidate_ref") == f"refs/aao/candidates/{candidate}"
            and isinstance(proposal_id, str)
            and _is_uuid(proposal_id)
            and isinstance(patch_sha, str)
            and len(patch_sha) == 64
            and all(char in "0123456789abcdef" for char in patch_sha)
            and isinstance(paths, list)
            and all(isinstance(path, str) and path for path in paths)
            and isinstance(check, dict)
            and check.get("kind") == "aao.repository-check.v1"
            and check.get("conclusion") == "success"
            and check.get("candidate_sha") == candidate
            and isinstance(check.get("check_id"), str)
            and type(check.get("exit_code")) is int
            and check.get("exit_code") == 0
            and type(check.get("duration_ms")) is int
            and check["duration_ms"] >= 0
            and isinstance(check.get("extra_tests"), list)
            and all(isinstance(path, str) for path in check["extra_tests"])
            and isinstance(check.get("stdout"), str)
            and isinstance(check.get("stderr"), str)
            and check.get("limits") == {
                "network": "unshared",
                "source": "read-only mounted source/tests/config",
                "home_and_secrets": "not mounted; environment allow-listed",
                "timeout_seconds": 120,
                "memory_bytes": 1_073_741_824,
                "temporary_filesystem_bytes": 268_435_456,
            }
            and type(result.get("exit_status")) is int
            and result.get("exit_status") == 0
            and type(result.get("elapsed_seconds")) in (float, int)
            and result["elapsed_seconds"] >= 0
        ) else "FAILED"

    # Unknown task/result kinds cannot assert successful execution.
    return "FAILED"


def _is_uuid(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def verify_execution_principal(db, worker_id, agent_credential):
    from aao.principal_credentials import PrincipalDenied, authenticate_identity_in_transaction
    try:
        principal_id = authenticate_identity_in_transaction(
            db, agent_credential, kind="AGENT",
        )
    except PrincipalDenied as exc:
        raise ExecutionConflict("Individual agent credential invalid or revoked") from exc
    if principal_id != worker_id:
        raise ExecutionConflict("Individual agent credential invalid or revoked")


def active_host_fence_epoch(db, worker_id: str) -> int:
    """Return the local active binding epoch or fail closed for a worker."""
    if not db.execute("SELECT to_regclass('public.host_worker_bindings')").fetchone()[0]:
        raise ExecutionConflict("Host fencing registry unavailable; execution rejected")
    if not db.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name='execution_queue' AND column_name='claim_fence_epoch'"
    ).fetchone():
        raise ExecutionConflict("Execution fencing epoch schema unavailable; execution rejected")
    rows = db.execute(
        "SELECT host_id,status,fence_epoch FROM host_worker_bindings "
        "WHERE worker_id=%s ORDER BY created_at DESC FOR SHARE", (worker_id,),
    ).fetchall()
    active = [row for row in rows if row[1] == "ACTIVE"]
    if len(active) != 1:
        raise ExecutionConflict(
            f"Worker '{worker_id}' must have exactly one active host binding; execution rejected."
        )
    try:
        local_host_id = current_host_id()
    except HostIdentityError as exc:
        raise ExecutionConflict("Trusted local host identity unavailable; execution rejected") from exc
    host_id, _status, epoch = active[0]
    if host_id != local_host_id:
        raise ExecutionConflict("Active worker binding belongs to a different host; execution rejected")
    if not isinstance(epoch, int) or epoch < 1:
        raise ExecutionConflict("Host fencing epoch is missing or invalid; execution rejected")
    return epoch


def validate_live_lease(db, execution_id: str, worker_id: str, token: str, *, lock: str = "share"):
    """Validate a live lease against the current host binding and fencing epoch.

    Callers must use the returned project id for grant checks in this same transaction.
    """
    if lock not in {"share", "update"}:
        raise ValueError("unsupported lease lock mode")
    epoch = active_host_fence_epoch(db, worker_id)
    suffix = " FOR UPDATE OF q" if lock == "update" else " FOR SHARE OF q"
    row = db.execute(
        "SELECT q.project_id,q.claim_fence_epoch,q.project_state_generation "
        "FROM execution_queue q WHERE q.id=%s AND q.status='RUNNING' AND q.worker_id=%s "
        "AND q.lease_token=%s AND q.lease_expires_at>clock_timestamp()" + suffix,
        (execution_id, worker_id, token),
    ).fetchone()
    if not row or row[1] is None or row[1] != epoch:
        raise ExecutionConflict("Execution lease is stale, not owned, or fenced by a changed host epoch")
    project = db.execute(
        "SELECT state,state_generation FROM projects WHERE id=%s FOR SHARE", (row[0],),
    ).fetchone()
    if not project or project[0] != "ACTIVE" or project[1] != row[2]:
        raise ExecutionConflict("Execution lease project is inactive or changed")
    return row[0]


def claim(worker_id: str, *, agent_credential: str, project_id: str,
          seconds: int = 60):
    if not worker_id or not project_id or seconds < 1:
        raise ExecutionConflict("Worker and positive lease duration required")
    with connect_postgres() as db:
        verify_execution_principal(db, worker_id, agent_credential)

        host_fence_epoch = active_host_fence_epoch(db, worker_id)

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
            "ORDER BY CASE w.priority WHEN 'HIGH' THEN 0 ELSE 1 END,q.created_at,q.id "
            "FOR UPDATE OF q SKIP LOCKED LIMIT 1",
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
            "project_state_generation=%s,attempts=attempts+1,claim_fence_epoch=%s "
            "WHERE id=%s RETURNING lease_expires_at",
            (token, worker_id, seconds, project[1], host_fence_epoch, eid),
        ).fetchone()[0]
        journal(db, eid, "claimed", {"worker_id": worker_id})
    return {"execution_id": eid, "work_id": work_id, "input": input_data,
            "token": token, "worker_id": worker_id,
            "expires_at": expiry.isoformat()}


def complete(execution_id: str, token: str, worker_id: str, result: dict,
             *, agent_credential: str):
    with connect_postgres() as db:
        verify_execution_principal(db, worker_id, agent_credential)

        # Keep the specific diagnostics of each fail-closed check (assignment, project state,
        # grant) and compare the claim epoch explicitly; the final UPDATE re-checks token/expiry.
        host_fence_epoch = active_host_fence_epoch(db, worker_id)
        execution = db.execute(
            "SELECT project_id,project_state_generation,input_json,work_id FROM execution_queue "
            "WHERE id=%s FOR UPDATE",
            (execution_id,),
        ).fetchone()
        if not execution:
            raise ExecutionConflict("Execution not found")
        epoch_row = db.execute(
            "SELECT claim_fence_epoch FROM execution_queue WHERE id=%s", (execution_id,)
        ).fetchone()
        if not epoch_row or epoch_row[0] is None or epoch_row[0] != host_fence_epoch:
            raise ExecutionConflict("Host fencing epoch is missing or changed; lease invalidated")
        project_id = execution[0]
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
            (project_id,),
        ).fetchone()
        if not project or project[0] != "ACTIVE":
            raise ExecutionConflict("Project is not active")
        if execution[1] is None or execution[1] != project[1]:
            raise ExecutionConflict("Project state changed after this lease was issued")
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='execution.claim' "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
            (worker_id, str(project_id)),
        ).fetchone()
        if not grant:
            raise ExecutionConflict("Project execution claim grant revoked")
        final_status = result_status(execution[2], result)
        if final_status == "SUCCEEDED" and isinstance(execution[2], dict) and (
            execution[2].get("type") == "aao.agent-patch.v1"
        ):
            proposal_id = result.get("proposal_id") if isinstance(result, dict) else None
            proposal = db.execute(
                "SELECT 1 FROM patch_proposals WHERE id=%s AND work_id=%s "
                "AND project_id=%s AND base_sha=%s AND patch_sha256=%s",
                (proposal_id, execution[3], project_id, execution[2].get("base_sha"),
                 result.get("patch_sha256")),
            ).fetchone()
            if not proposal:
                final_status = "FAILED"
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
