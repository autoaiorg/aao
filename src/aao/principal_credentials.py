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
            "WHERE kind=%s AND enabled=true", (kind,)
        ).fetchall()
    for principal, stored_digest in rows:
        if hmac.compare_digest(digest, stored_digest):
            return principal
    raise PrincipalDenied("Principal credential invalid or revoked")


def authenticate_in_transaction(db, token: str | None, *, kind: str) -> str:
    """Resolve and lock an enabled principal credential in the caller's tx."""
    if not _development_credentials_enabled():
        raise PrincipalDenied("Development principal credentials are unavailable")
    if kind not in {"AGENT", "AUDITOR"} or not token:
        raise PrincipalDenied("Principal credential required")
    row = db.execute(
        "SELECT principal_id FROM principal_credentials "
        "WHERE kind=%s AND token_digest=%s AND enabled=true FOR SHARE",
        (kind, digest_token(token)),
    ).fetchone()
    if not row:
        raise PrincipalDenied("Principal credential invalid or revoked")
    return row[0]


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
        "AND kind='AGENT' AND enabled=true FOR UPDATE",
        (digest_token(token),),
    ).fetchone()
    if not row:
        raise PrincipalDenied("Pending rotation invalid or expired")
    return row[0]
