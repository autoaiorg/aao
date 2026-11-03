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
            self.create_intent_in_transaction(db, intent)
        return intent

    @staticmethod
    def create_intent_in_transaction(db, intent: CycleSigningIntent) -> None:
        """Create an intent using the caller's transaction and narrow DB function."""
        try:
            db.execute(
                "SELECT create_selfdev_cycle_mtls_intent(%s,%s,%s,%s,%s,%s,%s)",
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
        except Exception as exc:
            if getattr(exc, "sqlstate", None) in {"23505", "23514"}:
                raise CycleMtlError("cycle principal or intent is not eligible") from exc
            raise

    def get_pending_intent(self, intent_id: uuid.UUID) -> CycleSigningIntent | None:
        with connect_postgres() as db:
            expired = db.execute(
                "SELECT expire_selfdev_cycle_mtls_intent(%s)", (intent_id,)
            ).fetchone()[0]
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

    def get_completed_binding(self, intent_id: uuid.UUID) -> tuple[str, str, bytes] | None:
        with connect_postgres() as db:
            row = db.execute(
                "SELECT b.certificate_sha256,b.csr_sha256,b.certificate_chain_pem FROM "
                "workload_identity_bindings b JOIN selfdev_cycle_mtls_intents i USING(intent_id) "
                "WHERE i.intent_id=%s AND i.state='COMPLETED' AND b.enabled=true "
                "AND b.revoked_at IS NULL AND b.expires_at>clock_timestamp()",
                (intent_id,),
            ).fetchone()
        return (
            (row[0], row[1], row[2].encode("ascii") if isinstance(row[2], str) else row[2])
            if row
            else None
        )

    def get_active_certificate(
        self, principal_id: str, token_digest: str, kind: str, fingerprint: str
    ) -> tuple[bytes, str, datetime] | None:
        """Return this authenticated workload's active public chain only."""
        with connect_postgres() as db:
            row = db.execute(
                "SELECT certificate_chain_pem,certificate_sha256,expires_at "
                "FROM get_selfdev_cycle_mtls_certificate(%s,%s,%s,%s)",
                (principal_id, token_digest, kind, fingerprint),
            ).fetchone()
        if not row:
            return None
        chain = row[0]
        if isinstance(chain, str):
            chain = chain.encode("ascii", errors="strict")
        return chain, row[1], _utc(row[2])

    def complete_binding(
        self,
        intent: CycleSigningIntent,
        fingerprint: str,
        csr_sha256: str,
        certificate_chain_pem: bytes,
    ) -> None:
        """Atomically bind verified public identity and enable its principal."""
        with connect_postgres() as db:
            status = self.complete_binding_in_transaction(
                db, intent, fingerprint, csr_sha256, certificate_chain_pem
            )
        if status == "EXPIRED":
            raise CycleMtlError("cycle intent expired")
        if status == "NOT_YET_VALID":
            raise CycleMtlError("cycle intent is not yet valid")
        if status == "NOT_FOUND":
            raise CycleMtlError("pending cycle intent not found")
        if status in {"CONFLICT", "REVOKED", "PRINCIPAL_NOT_PENDING", "PENDING", "EXPIRED"}:
            raise CycleMtlError("cycle intent is no longer pending")

    @staticmethod
    def complete_binding_in_transaction(
        db,
        intent: CycleSigningIntent,
        fingerprint: str,
        csr_sha256: str,
        certificate_chain_pem: bytes,
    ) -> str:
        row = db.execute(
            "SELECT project_id,cycle_id,principal_id,kind,not_before,not_after "
            "FROM selfdev_cycle_mtls_intents WHERE intent_id=%s",
            (intent.intent_id,),
        ).fetchone()
        if not row or tuple(row) != (
            intent.project_id,
            intent.cycle_id,
            intent.principal_id,
            intent.kind,
            intent.not_before,
            intent.not_after,
        ):
            raise CycleMtlError("cycle intent identity mismatch")
        chain = certificate_chain_pem.decode("ascii")
        return db.execute(
            "SELECT complete_selfdev_cycle_mtls_binding(%s,%s,%s,%s)",
            (intent.intent_id, fingerprint, csr_sha256, chain),
        ).fetchone()[0]

    def revoke(self, intent_id: uuid.UUID) -> bool:
        """Revoke intent, binding, and principal in one transaction; repeat-safe."""
        with connect_postgres() as db:
            return self.revoke_in_transaction(db, intent_id)

    @staticmethod
    def revoke_in_transaction(db, intent_id: uuid.UUID) -> bool:
        """Revoke exact intent in caller transaction (for cycle-wide atomic revoke)."""
        return bool(
            db.execute("SELECT revoke_selfdev_cycle_mtls_intent(%s)", (intent_id,)).fetchone()[0]
        )


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
