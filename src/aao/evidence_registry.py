"""Project-scoped content-addressed evidence for internal reconciliation.

Stored bytes can be integrity-checked; they are not thereby proven truthful or
independently authored. No HTTP upload or external storage adapter is exposed.
"""
import hashlib
import json
import re
from uuid import uuid4

from aao.postgresql_connection import connect_postgres

MAX_EVIDENCE_BYTES = 1_048_576
MAX_EVIDENCE_REFERENCES = 32
_REFERENCE = re.compile(r"^sha256:([0-9a-f]{64})$")


class EvidenceDenied(ValueError):
    pass


def _validate_evidence(content: bytes, media_type: str) -> None:
    if not isinstance(content, bytes) or not content or len(content) > MAX_EVIDENCE_BYTES:
        raise EvidenceDenied("Evidence must contain 1 to 1048576 bytes")
    if not media_type or len(media_type) > 127 or any(ord(char) < 32 for char in media_type):
        raise EvidenceDenied("Invalid evidence media type")


def register_evidence(
    project_id: str,
    content: bytes,
    *,
    agent_id: str,
    agent_credential: str,
    media_type: str = "application/octet-stream",
) -> str:
    """Persist bytes under a digest after checking AGENT identity and grant."""
    _validate_evidence(content, media_type)
    with connect_postgres() as db:
        return register_evidence_in_transaction(
            db, project_id, content, agent_id=agent_id,
            agent_credential=agent_credential, media_type=media_type,
        )


def register_evidence_in_transaction(
    db, project_id: str, content: bytes, *, agent_id: str,
    agent_credential: str, media_type: str = "application/octet-stream",
) -> str:
    """Same credential/grant checks and immutable storage in a caller-owned transaction."""
    _validate_evidence(content, media_type)
    digest = hashlib.sha256(content).hexdigest()
    from aao.principal_credentials import PrincipalDenied, authenticate_in_transaction

    try:
        principal_id = authenticate_in_transaction(
            db, agent_credential, kind="AGENT",
        )
    except PrincipalDenied as exc:
        raise EvidenceDenied("Active agent credential required") from exc
    if principal_id != agent_id:
        raise EvidenceDenied("Credential does not match evidence submitter")
    project = db.execute(
        "SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,),
    ).fetchone()
    if not project or project[0] != "ACTIVE":
        raise EvidenceDenied("Active project required")
    grant = db.execute(
        "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
        "AND capability='evidence.submit' "
        "AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
        (principal_id, project_id),
    ).fetchone()
    if not grant:
        raise EvidenceDenied("Evidence submission grant required")
    inserted = db.execute(
        "INSERT INTO evidence_artifacts(project_id,digest,submitted_by,media_type,content) "
        "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (project_id,digest) DO NOTHING "
        "RETURNING digest",
        (project_id, digest, principal_id, media_type, content),
    ).fetchone()
    if inserted:
        db.execute(
            "INSERT INTO events(id,subject_id,kind,details) "
            "VALUES (%s,%s,'evidence.registered',%s::jsonb)",
            (str(uuid4()), project_id, json.dumps({
                "digest": f"sha256:{digest}", "submitted_by": principal_id,
            })),
        )
    else:
        existing = db.execute(
            "SELECT content FROM evidence_artifacts WHERE project_id=%s AND digest=%s",
            (project_id, digest),
        ).fetchone()
        if not existing or bytes(existing[0]) != content:
            raise EvidenceDenied("Digest collision or corrupted evidence record")
    return f"sha256:{digest}"


def verify_evidence_references(db, project_id: str, references: list[str]) -> list[dict]:
    """Resolve and re-hash project evidence inside the caller's transaction."""
    validate_evidence_references(references)
    verified = []
    for reference in references:
        match = _REFERENCE.fullmatch(reference) if isinstance(reference, str) else None
        if not match:
            raise EvidenceDenied("Evidence reference must be a sha256 digest")
        digest = match.group(1)
        row = db.execute(
            "SELECT content,media_type FROM evidence_artifacts "
            "WHERE project_id=%s AND digest=%s FOR SHARE",
            (project_id, digest),
        ).fetchone()
        if not row:
            raise EvidenceDenied("Evidence artifact not found for project")
        content = bytes(row[0])
        if hashlib.sha256(content).hexdigest() != digest:
            raise EvidenceDenied("Evidence artifact digest mismatch")
        verified.append({
            "reference": reference,
            "size_bytes": len(content),
            "media_type": row[1],
        })
    return verified


def read_evidence(
    project_id: str,
    references: list[str],
    *,
    auditor_credential: str,
    capability: str,
) -> list[dict]:
    """Read project evidence for an individually authenticated reconciler."""
    if capability not in {"execution.reconcile", "effect.reconcile"}:
        raise EvidenceDenied("Evidence review capability required")
    validate_evidence_references(references)
    with connect_postgres() as db:
        from aao.principal_credentials import PrincipalDenied, authenticate_in_transaction

        try:
            reviewer_id = authenticate_in_transaction(
                db, auditor_credential, kind="AUDITOR",
            )
        except PrincipalDenied as exc:
            raise EvidenceDenied("Active auditor credential required") from exc
        grant = db.execute(
            "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability=%s AND (expires_at IS NULL OR expires_at > clock_timestamp()) "
            "FOR SHARE",
            (reviewer_id, project_id, capability),
        ).fetchone()
        if not grant:
            raise EvidenceDenied("Evidence review capability required")
        verified = verify_evidence_references(db, project_id, references)
        artifacts = []
        for descriptor in verified:
            digest = descriptor["reference"].removeprefix("sha256:")
            row = db.execute(
                "SELECT content,submitted_by,created_at FROM evidence_artifacts "
                "WHERE project_id=%s AND digest=%s FOR SHARE",
                (project_id, digest),
            ).fetchone()
            if not row or hashlib.sha256(bytes(row[0])).hexdigest() != digest:
                raise EvidenceDenied("Evidence artifact digest mismatch")
            artifacts.append({
                **descriptor,
                "content": bytes(row[0]),
                "submitted_by": row[1],
                "created_at": row[2],
            })
    return artifacts


def validate_evidence_references(references):
    """Reject malformed evidence references before opening a transaction."""
    if not isinstance(references, list) or not references:
        raise EvidenceDenied("Unique evidence references required")
    if len(references) > MAX_EVIDENCE_REFERENCES:
        raise EvidenceDenied("Too many evidence references")
    if any(
        not isinstance(reference, str) or not _REFERENCE.fullmatch(reference)
        for reference in references
    ):
        raise EvidenceDenied("Evidence reference must be a sha256 digest")
    if len(set(references)) != len(references):
        raise EvidenceDenied("Unique evidence references required")
