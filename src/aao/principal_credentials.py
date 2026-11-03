"""Per-principal development credential verification, fail closed.

These are bearer-token development credentials, not production identities.
"""
import hashlib
import hmac
import os

from aao.postgresql_connection import connect_postgres


class PrincipalDenied(ValueError):
    pass


def _development_credentials_enabled() -> bool:
    return os.getenv("AAO_ENV", "").strip().lower() in {
        "development", "test",
    }


def digest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(token: str | None, *, kind: str) -> str:
    if not _development_credentials_enabled():
        raise PrincipalDenied("Development principal credentials are unavailable")
    if kind not in {"AGENT", "AUDITOR"} or not token:
        raise PrincipalDenied("Principal credential required")
    digest = digest_token(token)
    with connect_postgres() as db:
        rows = db.execute(
            "SELECT principal_id,token_digest FROM principal_credentials "
            "WHERE kind=%s AND enabled=true "
            "AND (expires_at IS NULL OR expires_at > clock_timestamp())",
            (kind,),
        ).fetchall()
    for principal, stored_digest in rows:
        if hmac.compare_digest(digest, stored_digest):
            return principal
    raise PrincipalDenied("Principal credential invalid or revoked")


def authenticate_mtls(fingerprint: str | None, *, kind: str) -> tuple[str, str]:
    """Resolve a TLS-verified client certificate to an enabled principal.

    ``fingerprint`` must come from the private ASGI extension populated by the
    Uvicorn TLS protocol adapter, never from a request header. The returned
    digest is the principal's current credential digest so existing
    transaction-level locks continue to serialize authorization with
    credential revocation/expiry.
    """
    if os.getenv("AAO_ENV", "").strip().lower() != "production":
        raise PrincipalDenied("Production workload identity is unavailable")
    if kind not in {"AGENT", "AUDITOR"} or not isinstance(fingerprint, str):
        raise PrincipalDenied("Workload identity required")
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise PrincipalDenied("Workload identity malformed")
    with connect_postgres() as db:
        row = db.execute(
            "SELECT c.principal_id,c.token_digest FROM workload_identity_bindings b "
            "JOIN principal_credentials c ON c.principal_id=b.principal_id "
            "WHERE b.certificate_sha256=%s AND b.enabled=true AND b.revoked_at IS NULL "
            "AND b.expires_at>clock_timestamp() AND c.kind=%s AND c.enabled=true "
            "AND (c.expires_at IS NULL OR c.expires_at>clock_timestamp())",
            (fingerprint, kind),
        ).fetchone()
    if not row:
        raise PrincipalDenied("Workload identity invalid or revoked")
    return row[0], row[1]


def authenticate_mtls_in_transaction(
    db, fingerprint: str | None, *, principal_id: str, token_digest: str, kind: str,
) -> bool:
    """Lock and revalidate the workload binding and principal in the caller's tx.

    Request-entry authentication alone is insufficient: a binding can be
    revoked after TLS authentication but before a protected mutation commits.
    Locking both authoritative rows makes binding/principal revocation serialize
    with the operation when callers invoke this before their protected work.
    """
    if os.getenv("AAO_ENV", "").strip().lower() != "production":
        raise PrincipalDenied("Production workload identity is unavailable")
    if (
        kind not in {"AGENT", "AUDITOR"}
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(c not in "0123456789abcdef" for c in fingerprint)
    ):
        raise PrincipalDenied("Workload identity malformed")
    row = db.execute(
        "SELECT c.principal_id,c.token_digest FROM workload_identity_bindings b "
        "JOIN principal_credentials c ON c.principal_id=b.principal_id "
        "WHERE b.certificate_sha256=%s AND b.principal_id=%s AND b.enabled=true "
        "AND b.revoked_at IS NULL AND b.expires_at>clock_timestamp() "
        "AND c.kind=%s AND c.enabled=true "
        "AND (c.expires_at IS NULL OR c.expires_at>clock_timestamp()) "
        "FOR SHARE OF b,c",
        (fingerprint, principal_id, kind),
    ).fetchone()
    if not row or row[0] != principal_id or not hmac.compare_digest(row[1], token_digest):
        raise PrincipalDenied("Workload identity invalid or revoked")
    return True


def authenticate_in_transaction(db, token: str | None, *, kind: str) -> str:
    """Resolve and lock an enabled principal credential in the caller's tx."""
    if not _development_credentials_enabled():
        raise PrincipalDenied("Development principal credentials are unavailable")
    if kind not in {"AGENT", "AUDITOR"} or not token:
        raise PrincipalDenied("Principal credential required")
    row = db.execute(
        "SELECT principal_id FROM principal_credentials "
        "WHERE kind=%s AND token_digest=%s AND enabled=true "
        "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
        (kind, digest_token(token)),
    ).fetchone()
    if not row:
        raise PrincipalDenied("Principal credential invalid or revoked")
    return row[0]


def authenticate_identity_in_transaction(db, identity, *, kind: str) -> str:
    """Revalidate a request-authenticated principal inside a protected transaction.

    Production workload routes pass the AuthenticatedPrincipal returned by the
    mTLS dependency. Development/test callers may continue passing a bearer
    token. A production string is deliberately sent through the development
    bearer validator, which rejects it.
    """
    fingerprint = getattr(identity, "workload_fingerprint", None)
    principal_id = str(identity) if fingerprint is not None else None
    if principal_id is not None:
        identity_kind = getattr(identity, "kind", None)
        digest = getattr(identity, "token_digest", None)
        if identity_kind != kind or not isinstance(digest, str):
            raise PrincipalDenied("Workload identity context invalid")
        authenticate_mtls_in_transaction(
            db, fingerprint, principal_id=principal_id,
            token_digest=digest, kind=kind,
        )
        return principal_id
    # Development/test request dependencies attach the exact bearer digest to
    # their context. Production may never fall back to this branch.
    context_digest = getattr(identity, "token_digest", None)
    if context_digest is not None:
        if os.getenv("AAO_ENV", "").strip().lower() == "production":
            raise PrincipalDenied("Production workload identity is unavailable")
        if getattr(identity, "kind", None) != kind or not isinstance(context_digest, str):
            raise PrincipalDenied("Principal identity context invalid")
        row = db.execute(
            "SELECT principal_id FROM principal_credentials WHERE principal_id=%s "
            "AND token_digest=%s AND kind=%s AND enabled=true "
            "AND (expires_at IS NULL OR expires_at>clock_timestamp()) FOR SHARE",
            (str(identity), context_digest, kind),
        ).fetchone()
        if not row:
            raise PrincipalDenied("Principal credential invalid or revoked")
        return row[0]
    return authenticate_in_transaction(db, identity, kind=kind)


def lock_pending_agent_rotation(db, token: str | None) -> str:
    """Resolve and lock the AGENT whose unexpired pending digest matches ``token``.

    Only the self-rotation confirm path may call this; pending tokens never
    authenticate anything else.
    """
    if not _development_credentials_enabled():
        raise PrincipalDenied("Development principal credentials are unavailable")
    if not token:
        raise PrincipalDenied("Principal credential required")
    row = db.execute(
        "SELECT principal_id FROM principal_credentials "
        "WHERE pending_token_digest=%s AND pending_expires_at>clock_timestamp() "
        "AND kind='AGENT' AND enabled=true "
        "AND (expires_at IS NULL OR expires_at>clock_timestamp()) FOR UPDATE",
        (digest_token(token),),
    ).fetchone()
    if not row:
        raise PrincipalDenied("Pending rotation invalid or expired")
    return row[0]
