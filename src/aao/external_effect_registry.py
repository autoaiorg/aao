"""Fail-closed external-effect ledger: *recording only*, no effects are executed."""
import hashlib
import json
from uuid import uuid4

from aao.postgresql_connection import connect_postgres


class EffectConflict(ValueError):
    pass


def canonical_digest(value: dict) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def propose(*, execution_id: str, worker_id: str, lease_token: str,
            agent_credential: str, idempotency_key: str, capability: str,
            request: dict):
    """Record an inert proposal from the AGENT holding the live execution lease."""
    if not all((execution_id, worker_id, lease_token, agent_credential,
                idempotency_key, capability)):
        raise EffectConflict("Execution, worker, lease, credential, key and capability required")
    if len(idempotency_key) > 200:
        raise EffectConflict("Idempotency key too long")
    digest = canonical_digest(request)
    with connect_postgres() as db:
        from aao.principal_credentials import PrincipalDenied, authenticate_in_transaction
        try:
            principal_id = authenticate_in_transaction(
                db, agent_credential, kind="AGENT",
            )
        except PrincipalDenied as exc:
            raise EffectConflict("Active agent credential required") from exc
        if principal_id != worker_id:
            raise EffectConflict("Credential does not match execution worker")

        # Check host-worker binding and cutover fencing status (Finding A-07)
        has_table = db.execute(
            "SELECT to_regclass('public.host_worker_bindings')"
        ).fetchone()[0]
        if has_table:
            host_row = db.execute(
                """
                SELECT host_id, status FROM host_worker_bindings
                WHERE worker_id = %s
                ORDER BY created_at DESC LIMIT 1
                FOR SHARE
                """,
                (worker_id,),
            ).fetchone()
            if host_row and host_row[1] == "FENCED":
                raise EffectConflict(
                    f"Worker '{worker_id}' is bound to fenced host '{host_row[0]}'. "
                    "Authority has been revoked via cutover fencing."
                )

        execution = db.execute(
            "SELECT q.status,q.project_id,q.worker_id,q.lease_token,"
            "q.lease_expires_at,p.state,q.project_state_generation,"
            "p.state_generation FROM execution_queue q "
            "JOIN projects p ON p.id=q.project_id WHERE q.id=%s "
            "FOR UPDATE OF q,p",
            (execution_id,),
        ).fetchone()
        if not execution:
            raise EffectConflict("Unknown execution")
        (status, project_id, owner, current_token, expires_at, project_state,
         claimed_generation, current_generation) = execution
        if (status != "RUNNING" or owner != worker_id or str(current_token) != lease_token
                or expires_at is None or project_state != "ACTIVE"
                or claimed_generation is None or claimed_generation != current_generation):
            raise EffectConflict("Execution lease is not active for this worker")
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='effect.propose' "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
            (principal_id, str(project_id)),
        ).fetchone()
        if not grant:
            raise EffectConflict("Project effect proposal grant required")
        live = db.execute(
            "SELECT lease_expires_at > clock_timestamp() FROM execution_queue "
            "WHERE id=%s",
            (execution_id,),
        ).fetchone()[0]
        if not live:
            raise EffectConflict("Execution lease expired")
        row = db.execute(
            "SELECT id,execution_id,capability,request_digest,status FROM external_effects "
            "WHERE idempotency_key=%s FOR UPDATE", (idempotency_key,)
        ).fetchone()
        if row:
            if str(row[1]) != execution_id or row[2] != capability or row[3] != digest:
                raise EffectConflict("Idempotency key reused with different request")
            if row[4] != "PROPOSED":
                raise EffectConflict("Effect proposal is no longer active")
            return {"id": str(row[0]), "status": "PROPOSED_OR_EXISTING"}
        effect_id = str(uuid4())
        inserted = db.execute(
            "INSERT INTO external_effects(id,execution_id,idempotency_key,capability,status,request_digest) "
            "VALUES (%s,%s,%s,%s,'PROPOSED',%s) "
            "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
            (effect_id, execution_id, idempotency_key, capability, digest),
        ).fetchone()
        if not inserted:
            # A concurrent proposal for a different execution can win the
            # unique key after the SELECT above found no row. Under PostgreSQL
            # READ COMMITTED, this statement sees that committed winner.
            row = db.execute(
                "SELECT id,execution_id,capability,request_digest,status FROM external_effects "
                "WHERE idempotency_key=%s FOR UPDATE", (idempotency_key,),
            ).fetchone()
            if not row:
                raise EffectConflict("Idempotency-key race could not be resolved")
            if str(row[1]) != execution_id or row[2] != capability or row[3] != digest:
                raise EffectConflict("Idempotency key reused with different request")
            if row[4] != "PROPOSED":
                raise EffectConflict("Effect proposal is no longer active")
            return {"id": str(row[0]), "status": "PROPOSED_OR_EXISTING"}
        db.execute(
            "INSERT INTO execution_journal(id,execution_id,kind,details) "
            "VALUES (%s,%s,'effect.proposed',%s::jsonb)",
            (str(uuid4()), execution_id, json.dumps({
                "proposed_by": principal_id,
                "capability": capability,
                "request_digest": digest,
            })),
        )
        return {"id": effect_id, "status": "PROPOSED"}
