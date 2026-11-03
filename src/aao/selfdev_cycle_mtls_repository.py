"""PostgreSQL persistence for typed Self Development cycle mTLS intents.

This is only the API-side persistence boundary. It does not sign certificates,
create CA material, or make an HTTP route available.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from aao.postgresql_connection import connect_postgres
from aao.selfdev_cycle_mtls import CycleMtlError, CycleSigningIntent


class PostgresCycleIntentRepository:
    """Transactional implementation of the cycle mTLS intent contract."""

    def create_intent(self, intent: CycleSigningIntent) -> CycleSigningIntent:
        """Persist an intent for an existing disabled, fixed-cycle principal.

        Repeating an identical intent is idempotent. Reusing its cycle/kind for
        different fields conflicts instead of silently extending validity.
        """
        with connect_postgres() as db:
            # Lock in the same order used by completion/revocation: intent,
            # then principal. The transaction-scoped advisory lock also
            # serializes first inserts for the unique project/cycle/kind key.
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"selfdev-cycle-mtls:{intent.project_id}:{intent.cycle_id}:{intent.kind}",),
            )
            existing = db.execute(
                "SELECT intent_id, project_id, principal_id, not_before, not_after, state "
                "FROM selfdev_cycle_mtls_intents WHERE project_id=%s AND cycle_id=%s "
                "AND kind=%s FOR UPDATE",
                (intent.project_id, intent.cycle_id, intent.kind),
            ).fetchone()
            if existing:
                if (
                    existing[0] == intent.intent_id
                    and existing[1] == intent.project_id
                    and existing[2] == intent.principal_id
                    and existing[3] == intent.not_before
                    and existing[4] == intent.not_after
                    and existing[5] == "PENDING"
                ):
                    return intent
                raise CycleMtlError("cycle intent already exists")
            principal = db.execute(
                "SELECT kind, enabled, expires_at FROM principal_credentials "
                "WHERE principal_id=%s FOR UPDATE",
                (intent.principal_id,),
            ).fetchone()
            if not principal or principal[0] != intent.kind or principal[1]:
                raise CycleMtlError("cycle principal is not pending")
            if principal[2] is not None and principal[2] <= intent.not_after:
                raise CycleMtlError("cycle principal expires before its intent")
            db.execute(
                "INSERT INTO selfdev_cycle_mtls_intents "
                "(intent_id,project_id,cycle_id,principal_id,kind,not_before,not_after) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    intent.intent_id,
                    intent.project_id,
                    intent.cycle_id,
                    intent.principal_id,
                    intent.kind,
                    intent.not_before,
                    intent.not_after,
                ),
            )
        return intent

    def get_pending_intent(self, intent_id: uuid.UUID) -> CycleSigningIntent | None:
        with connect_postgres() as db:
            expired = db.execute(
                "UPDATE selfdev_cycle_mtls_intents SET state='EXPIRED' "
                "WHERE intent_id=%s AND state='PENDING' AND not_after<=clock_timestamp() "
                "RETURNING intent_id",
                (intent_id,),
            ).fetchone()
            if expired:
                return None
            row = db.execute(
                "SELECT i.intent_id,i.project_id,i.cycle_id,i.principal_id,i.kind,"
                "i.not_before,i.not_after FROM selfdev_cycle_mtls_intents i "
                "JOIN principal_credentials c USING (principal_id) "
                "WHERE i.intent_id=%s AND i.state='PENDING' "
                "AND i.not_before<=clock_timestamp() AND i.not_after>clock_timestamp() "
                "AND c.kind=i.kind AND c.enabled=false "
                "AND (c.expires_at IS NULL OR c.expires_at>clock_timestamp())",
                (intent_id,),
            ).fetchone()
        return _intent(row) if row else None

    def get_completed_binding(self, intent_id: uuid.UUID) -> tuple[str, str] | None:
        with connect_postgres() as db:
            row = db.execute(
                "SELECT b.certificate_sha256,b.csr_sha256 FROM "
                "workload_identity_bindings b JOIN selfdev_cycle_mtls_intents i USING(intent_id) "
                "WHERE i.intent_id=%s AND i.state='COMPLETED' AND b.enabled=true "
                "AND b.revoked_at IS NULL AND b.expires_at>clock_timestamp()",
                (intent_id,),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def complete_binding(
        self, intent: CycleSigningIntent, fingerprint: str, csr_sha256: str
    ) -> None:
        """Atomically bind verified public identity and enable its principal."""
        with connect_postgres() as db:
            current = db.execute(
                "SELECT project_id,cycle_id,principal_id,kind,not_before,not_after,state "
                "FROM selfdev_cycle_mtls_intents WHERE intent_id=%s FOR UPDATE",
                (intent.intent_id,),
            ).fetchone()
            if not current:
                raise CycleMtlError("pending cycle intent not found")
            if current[6] == "COMPLETED":
                existing = db.execute(
                    "SELECT certificate_sha256,csr_sha256 FROM workload_identity_bindings "
                    "WHERE intent_id=%s",
                    (intent.intent_id,),
                ).fetchone()
                if existing == (fingerprint, csr_sha256):
                    return
                raise CycleMtlError("cycle intent already completed differently")
            if current[6] != "PENDING" or tuple(current[:6]) != (
                intent.project_id,
                intent.cycle_id,
                intent.principal_id,
                intent.kind,
                intent.not_before,
                intent.not_after,
            ):
                raise CycleMtlError("cycle intent is no longer pending")
            principal = db.execute(
                "SELECT kind,enabled,expires_at FROM principal_credentials "
                "WHERE principal_id=%s FOR UPDATE",
                (intent.principal_id,),
            ).fetchone()
            if (
                not principal
                or principal[0] != intent.kind
                or principal[1]
                or (principal[2] is not None and principal[2] <= intent.not_after)
            ):
                raise CycleMtlError("cycle principal is no longer pending")
            active = db.execute(
                "SELECT 1 FROM selfdev_cycle_mtls_intents WHERE intent_id=%s "
                "AND state='PENDING' AND not_before<=clock_timestamp() "
                "AND not_after>clock_timestamp()",
                (intent.intent_id,),
            ).fetchone()
            if not active:
                db.execute(
                    "UPDATE selfdev_cycle_mtls_intents SET state='EXPIRED' "
                    "WHERE intent_id=%s AND state='PENDING'",
                    (intent.intent_id,),
                )
                raise CycleMtlError("cycle intent expired")
            db.execute(
                "INSERT INTO workload_identity_bindings "
                "(certificate_sha256,principal_id,enabled,issued_at,expires_at,intent_id,csr_sha256) "
                "VALUES (%s,%s,true,clock_timestamp(),%s,%s,%s)",
                (fingerprint, intent.principal_id, intent.not_after, intent.intent_id, csr_sha256),
            )
            db.execute(
                "UPDATE selfdev_cycle_mtls_intents SET state='COMPLETED',completed_at=clock_timestamp() "
                "WHERE intent_id=%s AND state='PENDING'",
                (intent.intent_id,),
            )
            db.execute(
                "UPDATE principal_credentials SET enabled=true WHERE principal_id=%s",
                (intent.principal_id,),
            )

    def revoke(self, intent_id: uuid.UUID) -> bool:
        """Revoke intent, binding, and principal in one transaction; repeat-safe."""
        with connect_postgres() as db:
            row = db.execute(
                "SELECT principal_id,state FROM selfdev_cycle_mtls_intents "
                "WHERE intent_id=%s FOR UPDATE",
                (intent_id,),
            ).fetchone()
            if not row:
                return False
            principal_id = row[0]
            db.execute(
                "UPDATE workload_identity_bindings SET enabled=false,revoked_at=COALESCE(revoked_at,clock_timestamp()) "
                "WHERE intent_id=%s AND enabled=true",
                (intent_id,),
            )
            db.execute(
                "UPDATE principal_credentials SET enabled=false WHERE principal_id=%s",
                (principal_id,),
            )
            db.execute(
                "UPDATE selfdev_cycle_mtls_intents SET state='REVOKED',revoked_at=COALESCE(revoked_at,clock_timestamp()) "
                "WHERE intent_id=%s AND state<>'REVOKED'",
                (intent_id,),
            )
        return True


def _intent(row) -> CycleSigningIntent:
    return CycleSigningIntent(
        intent_id=row[0],
        project_id=row[1],
        cycle_id=row[2],
        principal_id=row[3],
        kind=row[4],
        not_before=_utc(row[5]),
        not_after=_utc(row[6]),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
