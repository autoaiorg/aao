"""PostgreSQL-backed isolated API for AAO's mandate/project/work lifecycle.

This is a separate development service, not a transparent migration of the
SQLite API. No agent execution or external side effects are enabled.
"""
import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from aao.environment_settings import load_local_env

load_local_env()

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from aao.capability_contracts import missing_contract_fields, model_profile_errors
from aao.capability_evaluation import recommend
from aao.planner import Admission, decide_admission
from aao.review import evaluate_review


def _ceo_bearer_enabled() -> bool:
    mode = os.getenv("AAO_ENV", "").strip().lower()
    return mode in {"development", "test"}


def require_ceo(x_ceo_token: str | None = Header(None)):
    if not _ceo_bearer_enabled():
        raise HTTPException(503, "CEO development bearer is unavailable in this environment")
    expected = os.getenv("AAO_CEO_TOKEN")
    if not expected:
        raise HTTPException(503, "CEO credential not configured")
    if not x_ceo_token or not secrets.compare_digest(expected, x_ceo_token):
        raise HTTPException(403, "CEO authentication required")
    return "ceo"


def require_reviewer(
    x_auditor_token: str | None = Header(None),
):
    from aao.principal_credentials import PrincipalDenied
    try:
        return _authenticate_request_principal(x_auditor_token, "AUDITOR")
    except PrincipalDenied as exc:
        raise HTTPException(403, "Individual auditor credential rejected") from exc


def require_worker(
    x_agent_token: str | None = Header(None),
):
    from aao.principal_credentials import PrincipalDenied
    try:
        return _authenticate_request_principal(x_agent_token, "AGENT")
    except PrincipalDenied as exc:
        raise HTTPException(403, "Individual agent credential rejected") from exc


@contextmanager
def tx():
    from aao.postgresql_connection import connect_postgres
    with connect_postgres() as db:
        yield db


def audit(db, subject: str, kind: str, details: dict):
    db.execute(
        "INSERT INTO events(id,subject_id,kind,details) VALUES (%s,%s,%s,%s::jsonb)",
        (str(uuid4()), subject, kind, json.dumps(details)),
    )


class MandateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=5000)


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mandate_id: str


class ProjectStateRequest(BaseModel):
    action: str = Field(pattern=r"^(pause|resume|cancel)$")


class WorkRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author_id: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    description: str = Field(default="", max_length=5000)


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT|VETO)$")
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    evidence: list[str] = Field(min_length=1)


class PatchProposalRequest(BaseModel):
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    patch: str = Field(min_length=1, max_length=65_536)


class PrincipalCredentialRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: str = Field(pattern=r"^(AGENT|AUDITOR)$")


class GrantRequest(BaseModel):
    principal_id: str = Field(min_length=1)
    capability: str = Field(pattern=r"^(?:work\.(?:create|admit|review|progress)|project\.read|execution\.claim|execution\.reconcile|effect\.(?:propose|reconcile)|evidence\.submit|code\.(?:propose|publish))$")
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def future_timezone_aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Grant expiry must include a timezone")
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("Grant expiry must be in the future")
        return value

    @model_validator(mode="after")
    def bounded_code_proposal_grant(self):
        if self.capability == "code.propose":
            if self.expires_at is None:
                raise ValueError("code.propose grants require an explicit expiry")
            if self.expires_at > datetime.now(UTC) + timedelta(hours=24):
                raise ValueError("code.propose grants may not exceed 24 hours")
        return self


class CapabilityRequest(BaseModel):
    capability_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str = Field(min_length=1, max_length=64)
    capability_type: str = Field(pattern=r"^(cli_script|library|application_service|agent|agent_skill|knowledge_procedure|workflow)$")
    provenance: dict
    contract: dict
    required_permissions: list[str] = Field(default_factory=list, max_length=32)
    risks: list[str] = Field(default_factory=list, max_length=32)
    dependencies: list[str] = Field(default_factory=list, max_length=64)
    tests: list[str] = Field(default_factory=list, max_length=64)
    compatibility: dict = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=64)
    status: str = Field(default="registered_local", pattern=r"^registered_local$")


class CapabilityOption(BaseModel):
    choice: str = Field(pattern=r"^(reuse|adapt|build)$")
    fit: int = Field(ge=0, le=5)
    security: int = Field(ge=0, le=5)
    cost: int = Field(ge=0, le=5)
    time: int = Field(ge=0, le=5)
    tokens: int = Field(ge=0, le=5)
    maintenance: int = Field(ge=0, le=5)


class CapabilityEvaluationRequest(BaseModel):
    task_id: str
    options: list[CapabilityOption] = Field(min_length=3, max_length=3)
    rationale: str = Field(min_length=1, max_length=2000)
    evidence: list[str] = Field(min_length=1, max_length=32)
    capability_id: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=64)


class AgentRunRequest(BaseModel):
    capability_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str = Field(min_length=1, max_length=64)
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class ExternalResolutionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    pr_number: int = Field(ge=1)
    merge_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class RepositoryCheckRequest(BaseModel):
    capability_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")
    version: str = Field(min_length=1, max_length=64)
    check_id: str = Field(pattern=r"^core-unit$")


class OrganizationUnitRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=64)
    parent_id: str | None = Field(default=None, max_length=128)
    lead_principal_id: str | None = Field(default=None, max_length=128)
    enabled: bool = True


class OrganizationProfileRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=200)
    role_title: str = Field(min_length=1, max_length=200)
    unit_id: str | None = Field(default=None, max_length=128)
    manager_principal_id: str | None = Field(default=None, max_length=128)
    enabled: bool = True


app = FastAPI(title="AAO PostgreSQL development core", version="0.2.0")
_CEO_PRINCIPAL = object()

class AuthenticatedPrincipal(str):
    """Principal ID plus the exact bearer digest for transaction-time recheck."""

    def __new__(cls, principal_id: str, token_digest: str, kind: str):
        value = super().__new__(cls, principal_id)
        value.token_digest = token_digest
        value.kind = kind
        return value


def _authenticate_request_principal(token: str | None, kind: str):
    from aao.principal_credentials import authenticate, digest_token

    principal_id = authenticate(token, kind=kind)
    return AuthenticatedPrincipal(principal_id, digest_token(token), kind)



@app.get("/", include_in_schema=False)
def workboard_ui():
    """Serve the workboard from the same origin as the PostgreSQL API."""
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "index.html")


@app.get("/assets/control-center.css", include_in_schema=False)
def control_center_stylesheet():
    """Serve the Control Center stylesheet from the same origin."""
    return FileResponse(
        Path(__file__).resolve().parents[2] / "frontend" / "control-center.css",
        media_type="text/css",
    )


@app.get("/assets/control-center.js", include_in_schema=False)
def control_center_script():
    """Serve the Control Center client from the same origin."""
    return FileResponse(
        Path(__file__).resolve().parents[2] / "frontend" / "control-center.js",
        media_type="text/javascript",
    )


@app.get("/health")
def health():
    return {"service": "postgres-dev", "autonomous_execution": False}


@app.get("/ready")
def readiness():
    """Read-only readiness probe with a sanitized PostgreSQL connection result."""
    try:
        import psycopg
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )
    try:
        with tx() as db:
            db.execute("SELECT 1")
    except (psycopg.Error, RuntimeError):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return {"status": "ready", "database": "available"}


@app.post("/v1/principals/credentials", status_code=201)
def issue_principal_credential(
    payload: PrincipalCredentialRequest, _: str = Depends(require_ceo)
):
    """CEO-only development issuance. Secret returned once, digest persisted."""
    from aao.principal_credentials import digest_token

    token = secrets.token_urlsafe(32)
    with tx() as db:
        if db.execute(
            "SELECT 1 FROM principal_credentials WHERE principal_id=%s FOR UPDATE",
            (payload.principal_id,),
        ).fetchone():
            raise HTTPException(409, "Principal already registered; use rotation")
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,%s,%s,true)",
            (payload.principal_id, payload.kind, digest_token(token)),
        )
        audit(db, str(uuid4()), "principal.credential.issued",
              {"principal_id": payload.principal_id, "kind": payload.kind})
    return {"principal_id": payload.principal_id, "kind": payload.kind, "token": token}


@app.get("/v1/principals/me")
def current_principal(principal: Annotated[AuthenticatedPrincipal, Depends(require_worker)]):
    """Return the authenticated agent identity without disclosing credential material."""
    with tx() as db:
        row = db.execute(
            "SELECT kind,enabled FROM principal_credentials "
            "WHERE principal_id=%s AND token_digest=%s FOR SHARE",
            (principal, principal.token_digest),
        ).fetchone()
        if not row or row[0] != "AGENT" or not row[1]:
            raise HTTPException(403, "Individual agent credential invalid or revoked")
    return {"principal_id": str(principal), "kind": "AGENT", "enabled": True}


@app.get("/v1/principals/me/grants")
def current_principal_grants(
    principal: Annotated[AuthenticatedPrincipal, Depends(require_worker)],
):
    """List only the authenticated agent's project grants; this grants no authority."""
    with tx() as db:
        credential = db.execute(
            "SELECT kind,enabled FROM principal_credentials "
            "WHERE principal_id=%s AND token_digest=%s FOR SHARE",
            (principal, principal.token_digest),
        ).fetchone()
        if not credential or credential[0] != "AGENT" or not credential[1]:
            raise HTTPException(403, "Individual agent credential invalid or revoked")
        rows = db.execute(
            "SELECT project_id,capability,expires_at,"
            "(expires_at IS NULL OR expires_at>clock_timestamp()) AS active "
            "FROM project_grants WHERE principal_id=%s "
            "ORDER BY project_id,capability FOR SHARE",
            (principal,),
        ).fetchall()
    return [
        {
            "principal_id": str(principal),
            "project_id": str(row[0]),
            "capability": row[1],
            "expires_at": row[2].isoformat() if row[2] else None,
            "active": row[3],
        }
        for row in rows
    ]


@app.get("/v1/auditors/me/grants")
def current_auditor_grants(
    principal: Annotated[AuthenticatedPrincipal, Depends(require_reviewer)],
):
    """List only the authenticated auditor's project grants; no authority is granted."""
    with tx() as db:
        credential = db.execute(
            "SELECT kind,enabled FROM principal_credentials "
            "WHERE principal_id=%s AND token_digest=%s FOR SHARE",
            (principal, principal.token_digest),
        ).fetchone()
        if not credential or credential[0] != "AUDITOR" or not credential[1]:
            raise HTTPException(403, "Individual auditor credential invalid or revoked")
        rows = db.execute(
            "SELECT project_id,capability,expires_at,"
            "(expires_at IS NULL OR expires_at>clock_timestamp()) AS active "
            "FROM project_grants WHERE principal_id=%s "
            "ORDER BY project_id,capability FOR SHARE",
            (principal,),
        ).fetchall()
    return [
        {
            "principal_id": str(principal),
            "project_id": str(row[0]),
            "capability": row[1],
            "expires_at": row[2].isoformat() if row[2] else None,
            "active": row[3],
        }
        for row in rows
    ]


@app.post("/v1/principals/{principal_id}/revoke")
def revoke_principal(principal_id: str, _: str = Depends(require_ceo)):
    """Revocation prevents new authentication and lease completion."""
    with tx() as db:
        row = db.execute(
            "UPDATE principal_credentials SET enabled=false "
            "WHERE principal_id=%s AND enabled=true RETURNING kind",
            (principal_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Active principal credential not found")
        audit(db, str(uuid4()), "principal.credential.revoked",
              {"principal_id": principal_id, "kind": row[0]})
    return {"principal_id": principal_id, "enabled": False}


@app.post("/v1/principals/{principal_id}/rotate")
def rotate_principal(principal_id: str, _: str = Depends(require_ceo)):
    """Atomic rotation invalidates the previous token."""
    from aao.principal_credentials import digest_token

    token = secrets.token_urlsafe(32)
    with tx() as db:
        row = db.execute(
            "UPDATE principal_credentials SET token_digest=%s "
            "WHERE principal_id=%s AND enabled=true RETURNING kind",
            (digest_token(token), principal_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Active principal credential not found")
        audit(db, str(uuid4()), "principal.credential.rotated",
              {"principal_id": principal_id, "kind": row[0]})
    return {"principal_id": principal_id, "kind": row[0], "token": token}


@app.post("/v1/mandates", status_code=201)
def create_mandate(payload: MandateRequest, _: str = Depends(require_ceo)):
    mid = str(uuid4())
    with tx() as db:
        db.execute("INSERT INTO mandates(id,title,objective,status) VALUES (%s,%s,%s,'DRAFT')",
                   (mid, payload.title, payload.objective))
        audit(db, mid, "mandate.drafted", {"title": payload.title})
    return {"id": mid, "status": "DRAFT"}


@app.get("/v1/mandates")
def list_mandates(_: str = Depends(require_ceo)):
    """CEO-only mandate and lifecycle-event inventory for safe local bootstrap."""
    with tx() as db:
        rows = db.execute(
            "SELECT m.id,m.title,m.objective,m.status,p.id,p.name,p.state, "
            "COALESCE(json_agg(json_build_object('id',e.id,'subject_id',e.subject_id, "
            "'kind',e.kind,'created_at',e.created_at) ORDER BY e.created_at) "
            "FILTER (WHERE e.id IS NOT NULL), '[]'::json) "
            "FROM mandates m LEFT JOIN projects p ON p.mandate_id=m.id "
            "LEFT JOIN events e ON e.subject_id=m.id OR e.subject_id=p.id "
            "GROUP BY m.id,p.id ORDER BY m.created_at,m.id"
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "title": row[1],
            "objective": row[2],
            "status": row[3],
            "project": None if row[4] is None else {
                "id": str(row[4]), "name": row[5], "state": row[6],
            },
            "events": [
                {
                    "id": str(event["id"]),
                    "subject_id": str(event["subject_id"]),
                    "kind": event["kind"],
                    "created_at": str(event["created_at"]),
                }
                for event in row[7]
            ],
        }
        for row in rows
    ]


@app.post("/v1/mandates/{mandate_id}/confirm")
def confirm_mandate(mandate_id: str, _: str = Depends(require_ceo)):
    with tx() as db:
        updated = db.execute(
            "UPDATE mandates SET status='CONFIRMED',confirmed_by='ceo' "
            "WHERE id=%s AND status='DRAFT' RETURNING id", (mandate_id,),
        ).fetchone()
        if not updated:
            raise HTTPException(409, "Mandate missing or not draft")
        audit(db, mandate_id, "mandate.confirmed", {"authority": "ceo"})
    return {"id": mandate_id, "status": "CONFIRMED"}


@app.post("/v1/projects", status_code=201)
def create_project(payload: ProjectRequest, _: str = Depends(require_ceo)):
    pid = str(uuid4())
    with tx() as db:
        mandate = db.execute("SELECT status FROM mandates WHERE id=%s FOR UPDATE",
                             (payload.mandate_id,)).fetchone()
        if not mandate or mandate[0] != "CONFIRMED":
            raise HTTPException(409, "Confirmed mandate required")
        if db.execute("SELECT 1 FROM projects WHERE mandate_id=%s",
                      (payload.mandate_id,)).fetchone():
            raise HTTPException(409, "Mandate already bound to project")
        db.execute(
            "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,%s,%s,'ACTIVE')",
            (pid, payload.name, payload.mandate_id),
        )
        audit(db, pid, "project.created", {"mandate_id": payload.mandate_id})
    return {"id": pid, "state": "ACTIVE"}


@app.post("/v1/projects/{project_id}/state")
def change_project_state(
    project_id: str,
    payload: ProjectStateRequest,
    _: str = Depends(require_ceo),
):
    """CEO-controlled suspension state transition for the inert PostgreSQL path."""
    transitions = {
        ("ACTIVE", "pause"): "PAUSED",
        ("PAUSED", "resume"): "ACTIVE",
        ("ACTIVE", "cancel"): "CANCELLED",
        ("PAUSED", "cancel"): "CANCELLED",
    }
    with tx() as db:
        row = db.execute(
            "SELECT state FROM projects WHERE id=%s FOR UPDATE", (project_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Project not found")
        next_state = transitions.get((row[0], payload.action))
        if not next_state:
            raise HTTPException(409, "Invalid project state transition")
        db.execute(
            "UPDATE projects SET state=%s WHERE id=%s", (next_state, project_id),
        )
        audit(db, project_id, "project.state_changed", {
            "from": row[0], "to": next_state, "authority": "ceo",
        })
    return {"id": project_id, "state": next_state}


def read_principal(
    x_ceo_token: str | None = Header(None),
    x_agent_token: str | None = Header(None),
):
    ceo = os.getenv("AAO_CEO_TOKEN")
    if (_ceo_bearer_enabled() and ceo and x_ceo_token
            and secrets.compare_digest(ceo, x_ceo_token)):
        return _CEO_PRINCIPAL
    if x_agent_token is not None:
        from aao.principal_credentials import PrincipalDenied
        try:
            return _authenticate_request_principal(x_agent_token, "AGENT")
        except PrincipalDenied as exc:
            raise HTTPException(403, "Individual reader credential rejected") from exc
    raise HTTPException(403, "Authenticated reader required")


@app.get("/v1/projects")
def projects(principal: str = Depends(read_principal)):
    with tx() as db:
        if principal is _CEO_PRINCIPAL:
            rows = db.execute("SELECT id,name,state FROM projects ORDER BY name,id").fetchall()
        else:
            if not isinstance(principal, AuthenticatedPrincipal):
                raise HTTPException(403, "Individual reader credential required")
            credential = db.execute(
                "SELECT kind,enabled FROM principal_credentials "
                "WHERE principal_id=%s AND token_digest=%s FOR SHARE",
                (principal, principal.token_digest),
            ).fetchone()
            if not credential or credential[0] != "AGENT" or not credential[1]:
                raise HTTPException(403, "Individual reader invalid or revoked")
            rows = db.execute(
                "SELECT p.id,p.name,p.state FROM projects p JOIN project_grants g ON g.project_id=p.id "
                "WHERE g.principal_id=%s AND g.capability='project.read' "
                "AND (g.expires_at IS NULL OR g.expires_at > clock_timestamp()) ORDER BY p.name,p.id "
                "FOR SHARE OF g",
                (principal,),
            ).fetchall()
        return [{"id": r[0], "name": r[1], "state": r[2]} for r in rows]


@app.put("/v1/organization/units")
def put_organization_unit(payload: OrganizationUnitRequest, _: str = Depends(require_ceo)):
    """Declare organizational placement; it does not create or change grants."""
    with tx() as db:
        if payload.parent_id and not db.execute(
            "SELECT 1 FROM organization_units WHERE id=%s AND enabled", (payload.parent_id,)
        ).fetchone():
            raise HTTPException(404, "Parent organization unit not found")
        if payload.lead_principal_id and not db.execute(
            "SELECT 1 FROM principal_credentials WHERE principal_id=%s", (payload.lead_principal_id,)
        ).fetchone():
            raise HTTPException(404, "Unit lead principal not found")
        if payload.parent_id == payload.id:
            raise HTTPException(409, "Organization unit cannot parent itself")
        if payload.parent_id and db.execute(
            "WITH RECURSIVE descendants(id) AS ("
            "SELECT id FROM organization_units WHERE parent_id=%s UNION ALL "
            "SELECT child.id FROM organization_units child JOIN descendants d "
            "ON child.parent_id=d.id) SELECT 1 FROM descendants WHERE id=%s LIMIT 1",
            (payload.id, payload.parent_id),
        ).fetchone():
            raise HTTPException(409, "Organization unit hierarchy cannot contain a cycle")
        db.execute(
            "INSERT INTO organization_units(id,name,code,parent_id,lead_principal_id,enabled) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET "
            "name=EXCLUDED.name,code=EXCLUDED.code,parent_id=EXCLUDED.parent_id,"
            "lead_principal_id=EXCLUDED.lead_principal_id,enabled=EXCLUDED.enabled,"
            "updated_at=clock_timestamp()",
            (payload.id, payload.name, payload.code, payload.parent_id,
             payload.lead_principal_id, payload.enabled),
        )
        audit(db, str(uuid4()), "organization.unit_declared", payload.model_dump())
    return payload.model_dump()


@app.put("/v1/organization/profiles")
def put_organization_profile(payload: OrganizationProfileRequest, _: str = Depends(require_ceo)):
    """Declare a principal's organizational profile, independent of its permissions."""
    with tx() as db:
        if not db.execute(
            "SELECT 1 FROM principal_credentials WHERE principal_id=%s", (payload.principal_id,)
        ).fetchone():
            raise HTTPException(404, "Profile principal not found")
        if payload.manager_principal_id and not db.execute(
            "SELECT 1 FROM principal_credentials WHERE principal_id=%s", (payload.manager_principal_id,)
        ).fetchone():
            raise HTTPException(404, "Manager principal not found")
        if payload.unit_id and not db.execute(
            "SELECT 1 FROM organization_units WHERE id=%s AND enabled", (payload.unit_id,)
        ).fetchone():
            raise HTTPException(404, "Organization unit not found")
        if payload.manager_principal_id == payload.principal_id:
            raise HTTPException(409, "Profile cannot manage itself")
        db.execute(
            "INSERT INTO organization_profiles(principal_id,display_name,role_title,unit_id,"
            "manager_principal_id,enabled) VALUES (%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(principal_id) DO UPDATE SET display_name=EXCLUDED.display_name,"
            "role_title=EXCLUDED.role_title,unit_id=EXCLUDED.unit_id,"
            "manager_principal_id=EXCLUDED.manager_principal_id,enabled=EXCLUDED.enabled,"
            "updated_at=clock_timestamp()",
            (payload.principal_id, payload.display_name, payload.role_title,
             payload.unit_id, payload.manager_principal_id, payload.enabled),
        )
        audit(db, str(uuid4()), "organization.profile_declared", payload.model_dump())
    return payload.model_dump()


@app.get("/v1/organization")
def organization(principal: str = Depends(read_principal)):
    """Read-only office projection from persisted principals, work, and executions.

    Organizational placement and heartbeat are intentionally unknown until AAO
    has canonical persisted sources for them.
    """
    with tx() as db:
        if principal is _CEO_PRINCIPAL:
            projects_rows = db.execute(
                "SELECT id,name FROM projects ORDER BY id",
            ).fetchall()
        else:
            if not isinstance(principal, AuthenticatedPrincipal):
                raise HTTPException(403, "Individual reader credential required")
            credential = db.execute(
                "SELECT kind,enabled FROM principal_credentials "
                "WHERE principal_id=%s AND token_digest=%s FOR SHARE",
                (principal, principal.token_digest),
            ).fetchone()
            if not credential or credential[0] != "AGENT" or not credential[1]:
                raise HTTPException(403, "Individual reader invalid or revoked")
            projects_rows = db.execute(
                "SELECT p.id,p.name FROM projects p JOIN project_grants g "
                "ON g.project_id=p.id WHERE g.principal_id=%s "
                "AND g.capability='project.read' AND "
                "(g.expires_at IS NULL OR g.expires_at > clock_timestamp()) "
                "ORDER BY p.id FOR SHARE OF g",
                (principal,),
            ).fetchall()

        projects_by_id = {str(row[0]): row[1] for row in projects_rows}
        project_ids = list(projects_by_id)
        profile_query = (
            "SELECT p.principal_id,p.display_name,p.role_title,p.unit_id,p.manager_principal_id "
            "FROM organization_profiles p WHERE p.enabled ORDER BY p.principal_id"
            if principal is _CEO_PRINCIPAL else
            "SELECT p.principal_id,p.display_name,p.role_title,p.unit_id,p.manager_principal_id "
            "FROM organization_profiles p WHERE p.enabled AND p.principal_id=%s"
        )
        profile_rows = db.execute(
            profile_query, () if principal is _CEO_PRINCIPAL else (str(principal),),
        ).fetchall()
        profile_by_id = {str(row[0]): row[1:] for row in profile_rows}
        visible_unit_ids = {str(row[3]) for row in profile_rows if row[3] is not None}
        if principal is _CEO_PRINCIPAL:
            unit_rows = db.execute(
                "SELECT id,name,code,parent_id,lead_principal_id FROM organization_units "
                "WHERE enabled ORDER BY id"
            ).fetchall()
        elif visible_unit_ids:
            unit_rows = db.execute(
                "SELECT id,name,code,parent_id,lead_principal_id FROM organization_units "
                "WHERE enabled AND id=ANY(%s) ORDER BY id", (list(visible_unit_ids),)
            ).fetchall()
        else:
            unit_rows = []
        unit_by_id = {str(row[0]): row for row in unit_rows}
        units = [{
            "id": "unit-unassigned", "name": "Adscripción desconocida",
            "code": "UNKNOWN", "parentId": None, "leadRole": "Desconocido",
            "leadAgentId": None,
            "description": "Agrupación visual; no representa un departamento persistido.",
            "standingCount": 0, "ephemeralCount": 0, "activeProjectsCount": 0,
        }]
        units.extend({
            "id": str(row[0]), "name": row[1], "code": row[2],
            "parentId": row[3], "leadAgentId": row[4],
            "leadRole": "Responsable declarado" if row[4] else "Sin responsable declarado",
            "description": "Unidad organizativa declarada por CEO.",
            "standingCount": 0, "ephemeralCount": 0, "activeProjectsCount": 0,
        } for row in unit_rows)
        if not project_ids:
            agents = [{
                "id": principal_id, "name": profile[0], "type": "UNKNOWN",
                "roleTitle": profile[1], "unitId": str(profile[2]) if profile[2] else "unit-unassigned",
                "unitName": unit_by_id[str(profile[2])][1] if profile[2] and str(profile[2]) in unit_by_id else "Adscripción desconocida",
                "managerId": profile[3], "capabilities": [], "heartbeatStatus": "UNKNOWN",
                "lastHeartbeatAt": None, "status": "UNKNOWN", "operationalState": "REGISTRADO",
                "currentAssignments": [], "executionHistory": [],
                "authorityBoundary": "El perfil organizativo no concede permisos.",
                "isSyntheticDemo": False, "evidenceDescription": "Perfil organizativo persistido.",
                "lastEvidenceAt": None,
            } for principal_id, profile in profile_by_id.items()]
            return {"units": units, "agents": agents, "totalStandingAgents": 0,
                    "totalEphemeralAgents": 0, "totalUnknownAgents": len(agents),
                    "activeAssignmentsCount": 0,
                    "coverage": {"totalProjects": 0, "inspectedProjects": 0,
                                 "failedProjects": 0, "isPartial": False}}

        placeholders = ",".join(["%s"] * len(project_ids))
        rows = db.execute(
            "SELECT q.id,q.work_id,q.project_id,w.title,q.status,q.attempts,"
            "q.created_at,q.worker_id,q.lease_expires_at,q.result_json "
            "FROM execution_queue q JOIN work_items w ON w.id=q.work_id "
            f"WHERE q.project_id IN ({placeholders}) ORDER BY q.created_at,q.id",
            tuple(project_ids),
        ).fetchall()
        review_rows = db.execute(
            "SELECT r.reviewer_id,r.created_at "
            "FROM reviews r JOIN work_items w ON w.id=r.work_id "
            "JOIN projects p ON p.id=w.project_id "
            f"WHERE w.project_id IN ({placeholders}) ORDER BY r.created_at",
            tuple(project_ids),
        ).fetchall()

    agents: dict[str, dict] = {}
    active_count = 0
    for row in rows:
        execution_id, work_id, project_id = str(row[0]), str(row[1]), str(row[2])
        title, status, attempts, created, worker_id, lease, result = row[3:]
        if not worker_id:
            continue
        worker_id = str(worker_id)
        agent = agents.setdefault(worker_id, {
            "id": worker_id, "name": worker_id, "type": "UNKNOWN",
            "roleTitle": "Principal observado en ejecución",
            "unitId": "unit-unassigned", "unitName": "Adscripción desconocida",
            "capabilities": [], "heartbeatStatus": "UNKNOWN",
            "lastHeartbeatAt": None, "status": "UNKNOWN",
            "operationalState": "DESCONOCIDO", "currentAssignments": [],
            "executionHistory": [],
            "authorityBoundary": "La autoridad depende de grants por proyecto; identidad organizativa desconocida.",
            "isSyntheticDemo": False,
            "evidenceDescription": "Identidad derivada de ejecuciones persistidas.",
            "lastEvidenceAt": None,
        })
        active = status == "RUNNING" and lease is not None and lease > datetime.now(UTC)
        assignment_status = "ACTIVE" if active else "EXPIRED" if status == "RUNNING" and lease else "COMPLETED" if status != "RUNNING" else "UNKNOWN"
        if active:
            active_count += 1
            agent["status"], agent["operationalState"] = "BUSY", "EJECUTANDO"
        agent["currentAssignments"].append({
            "id": execution_id, "projectId": project_id,
            "projectName": projects_by_id[project_id], "taskId": str(work_id),
            "taskTitle": title, "assignedAt": created.isoformat(),
            "leaseExpiresAt": lease.isoformat() if lease else None,
            "status": assignment_status,
        })
        parsed_result = result if isinstance(result, dict) else {}
        agent["executionHistory"].append({
            "id": execution_id, "taskId": str(work_id), "taskTitle": title,
            "projectId": project_id, "projectName": projects_by_id[project_id],
            "status": status, "attempts": attempts,
            "createdAt": created.isoformat(),
            "leaseExpiresAt": lease.isoformat() if lease else None,
            "workerId": worker_id,
            "provider": parsed_result.get("provider"),
            "model": parsed_result.get("model"), "rawResult": result,
        })
        if not agent["lastEvidenceAt"] or created.isoformat() > agent["lastEvidenceAt"]:
            agent["lastEvidenceAt"] = created.isoformat()
    for row in review_rows:
        reviewer, created = row
        reviewer = str(reviewer)
        agents.setdefault(reviewer, {
            "id": reviewer, "name": reviewer, "type": "UNKNOWN",
            "roleTitle": "Principal observado como revisor",
            "unitId": "unit-unassigned", "unitName": "Adscripción desconocida",
            "capabilities": [], "heartbeatStatus": "UNKNOWN",
            "lastHeartbeatAt": None, "status": "UNKNOWN",
            "operationalState": "DESCONOCIDO", "currentAssignments": [],
            "executionHistory": [],
            "authorityBoundary": "La revisión registrada no implica rol organizativo ni autoridad vigente.",
            "isSyntheticDemo": False, "evidenceDescription": "Identidad derivada de una revisión persistida.",
            "lastEvidenceAt": created.isoformat(),
        })
    if principal is not _CEO_PRINCIPAL:
        principal_id = str(principal)
        agents.setdefault(principal_id, {
            "id": principal_id, "name": principal_id, "type": "UNKNOWN",
            "roleTitle": "Principal autenticado; perfil organizativo desconocido",
            "unitId": "unit-unassigned", "unitName": "Adscripción desconocida",
            "capabilities": [], "heartbeatStatus": "UNKNOWN",
            "lastHeartbeatAt": None, "status": "UNKNOWN",
            "operationalState": "REGISTRADO", "currentAssignments": [],
            "executionHistory": [],
            "authorityBoundary": "La autenticación no amplía los grants ni determina adscripción organizativa.",
            "isSyntheticDemo": False,
            "evidenceDescription": "Principal autenticado por credencial individual activa.",
            "lastEvidenceAt": None,
        })
    for profile_id, profile in profile_by_id.items():
        agent = agents.setdefault(profile_id, {
            "id": profile_id, "name": profile_id, "type": "UNKNOWN",
            "roleTitle": "Principal registrado", "unitId": "unit-unassigned",
            "unitName": "Adscripción desconocida", "capabilities": [],
            "heartbeatStatus": "UNKNOWN", "lastHeartbeatAt": None,
            "status": "UNKNOWN", "operationalState": "REGISTRADO",
            "currentAssignments": [], "executionHistory": [],
            "authorityBoundary": "El perfil organizativo no concede permisos.",
            "isSyntheticDemo": False,
            "evidenceDescription": "Perfil organizativo persistido.", "lastEvidenceAt": None,
        })
        unit_id = str(profile[2]) if profile[2] else None
        agent.update({
            "name": profile[0], "roleTitle": profile[1],
            "unitId": unit_id if unit_id else "unit-unassigned",
            "unitName": unit_by_id[unit_id][1] if unit_id and unit_id in unit_by_id else "Adscripción desconocida",
            "managerId": profile[3],
            "evidenceDescription": "Perfil organizativo persistido; actividad derivada de ejecuciones y revisiones.",
        })
    return {"units": units, "agents": list(agents.values()),
            "totalStandingAgents": 0, "totalEphemeralAgents": 0,
            "totalUnknownAgents": len(agents), "activeAssignmentsCount": active_count,
            "coverage": {"totalProjects": len(project_ids),
                         "inspectedProjects": len(project_ids),
                         "failedProjects": 0, "isPartial": False}}


@app.get("/v1/projects/{project_id}/grants")
def project_grants(project_id: str, _: str = Depends(require_ceo)):
    """CEO-only inventory of project-scoped grants; never returns credential material."""
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        rows = db.execute(
            "SELECT g.principal_id,c.kind,c.enabled,g.capability,g.expires_at "
            "FROM project_grants g JOIN principal_credentials c "
            "ON c.principal_id=g.principal_id WHERE g.project_id=%s "
            "ORDER BY g.principal_id,g.capability",
            (project_id,),
        ).fetchall()
    return [
        {
            "principal_id": row[0],
            "kind": row[1],
            "credential_enabled": row[2],
            "capability": row[3],
            "expires_at": row[4].isoformat() if row[4] else None,
        }
        for row in rows
    ]


@app.post("/v1/projects/{project_id}/grants")
def grant(project_id: str, payload: GrantRequest, _: str = Depends(require_ceo)):
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        principal = db.execute(
            "SELECT kind,enabled FROM principal_credentials "
            "WHERE principal_id=%s FOR SHARE", (payload.principal_id,),
        ).fetchone()
        if not principal:
            raise HTTPException(404, "Principal not found")
        if not principal[1]:
            raise HTTPException(409, "Principal credential is disabled")
        required_kind = (
            "AUDITOR" if payload.capability in {
                "work.review", "execution.reconcile", "effect.reconcile",
            } else "AGENT"
        )
        if principal[0] != required_kind:
            raise HTTPException(
                422, f"Capability requires a {required_kind} principal",
            )
        inserted = db.execute(
            "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
            "VALUES (%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING RETURNING project_id",
            (payload.principal_id, project_id, payload.capability, payload.expires_at),
        ).fetchone()
        if inserted:
            audit(db, project_id, "grant.created",
                  {"principal_id": payload.principal_id, "capability": payload.capability,
                   "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
                   "authority": "ceo", "scope": {"project_id": project_id}})
    return JSONResponse(
        status_code=201 if inserted else 200,
        content={
            "project_id": project_id,
            "capability": payload.capability,
            "created": bool(inserted),
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        },
    )


@app.delete("/v1/projects/{project_id}/grants/{principal_id}/{capability}", status_code=204)
def revoke_grant(
    project_id: str,
    principal_id: str,
    capability: str,
    _: str = Depends(require_ceo),
):
    """Revoke one project grant; row-locking protected operations serialize with this."""
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        deleted = db.execute(
            "DELETE FROM project_grants WHERE project_id=%s AND principal_id=%s "
            "AND capability=%s RETURNING principal_id",
            (project_id, principal_id, capability),
        ).fetchone()
        if not deleted:
            raise HTTPException(404, "Project grant not found")
        audit(db, project_id, "grant.revoked",
              {"principal_id": principal_id, "capability": capability})
    return Response(status_code=204)


def require_grant(db, principal: str, project_id: str, capability: str):
    """Recheck the presented credential and grant through the protected transaction."""
    if not isinstance(principal, AuthenticatedPrincipal):
        raise HTTPException(403, "Individual principal credential required")
    row = db.execute(
        "SELECT kind,enabled FROM principal_credentials "
        "WHERE principal_id=%s AND token_digest=%s FOR SHARE",
        (principal, principal.token_digest),
    ).fetchone()
    expected_kind = "AUDITOR" if capability in {"work.review", "execution.reconcile", "effect.reconcile"} else "AGENT"
    if not row or row[0] != expected_kind or row[0] != principal.kind or not row[1]:
        raise HTTPException(403, "Individual principal invalid or revoked")
    if not db.execute(
        "SELECT 1 FROM project_grants WHERE principal_id=%s AND project_id=%s "
        "AND capability=%s AND (expires_at IS NULL OR expires_at > clock_timestamp()) FOR SHARE",
        (principal, project_id, capability),
    ).fetchone():
        raise HTTPException(403, "Project grant required")


@app.post("/v1/projects/{project_id}/work", status_code=201)
def create_work(project_id: str, payload: WorkRequest,
                principal: str = Depends(require_worker)):
    wid = str(uuid4())
    with tx() as db:
        row = db.execute("SELECT state FROM projects WHERE id=%s FOR UPDATE",
                         (project_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Project not found")
        if row[0] != "ACTIVE":
            raise HTTPException(409, "Project not active")
        require_grant(db, principal, project_id, "work.create")
        db.execute(
            "INSERT INTO work_items(id,project_id,title,description,author_id,status,acceptance_criteria) "
            "VALUES (%s,%s,%s,%s,%s,'INBOX',%s::jsonb)",
            (wid, project_id, payload.title, payload.description, principal,
             json.dumps(payload.acceptance_criteria)),
        )
        audit(db, wid, "work.created", {"project_id": project_id})
    return {"id": wid, "status": "INBOX"}


@app.get("/v1/projects/{project_id}/board")
def board(project_id: str, principal: str = Depends(read_principal)):
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        if principal is not _CEO_PRINCIPAL:
            require_grant(db, principal, project_id, "project.read")
        rows = db.execute(
            "SELECT w.id,w.title,w.status,w.acceptance_criteria,w.evidence,"
            "COALESCE((SELECT json_agg(json_build_object('id',q.id,'status',q.status,"
            "'worker_id',q.worker_id,'attempts',q.attempts,'created_at',q.created_at,"
            "'result',q.result_json) ORDER BY q.created_at,q.id) FROM execution_queue q "
            "WHERE q.work_id=w.id),'[]'::json) "
            "FROM work_items w "
            "WHERE w.project_id=%s ORDER BY w.id", (project_id,),
        ).fetchall()
        review_rows = db.execute(
            "SELECT id,work_id,reviewer_id,decision,candidate_sha,evidence,created_at "
            "FROM reviews WHERE work_id IN (SELECT id FROM work_items WHERE project_id=%s) "
            "ORDER BY created_at,id", (project_id,),
        ).fetchall()
        reviews_by_work: dict[str, list[dict]] = {}
        for review_row in review_rows:
            reviews_by_work.setdefault(str(review_row[1]), []).append({
                "id": str(review_row[0]), "reviewer_id": review_row[2],
                "decision": review_row[3], "candidate_sha": review_row[4],
                "evidence": review_row[5], "created_at": review_row[6].isoformat(),
                "sha_bound": review_row[4] is not None,
            })
        patch_rows = db.execute(
            "SELECT p.id,p.work_id,p.proposer_id,p.base_sha,p.patch_sha256,p.changed_paths,p.status,p.created_at "
            "FROM patch_proposals p WHERE p.project_id=%s ORDER BY p.created_at,p.id",
            (project_id,),
        ).fetchall()
        validation_rows = db.execute(
            "SELECT v.proposal_id,v.id,v.validator_id,v.candidate_tree,v.created_at "
            "FROM patch_proposal_validations v JOIN patch_proposals p ON p.id=v.proposal_id "
            "WHERE p.project_id=%s ORDER BY v.created_at,v.id",
            (project_id,),
        ).fetchall()
        validations_by_proposal: dict[str, list[dict]] = {}
        for validation_row in validation_rows:
            validations_by_proposal.setdefault(str(validation_row[0]), []).append({
                "id": str(validation_row[1]), "validator_id": validation_row[2],
                "candidate_tree": validation_row[3],
                "created_at": validation_row[4].isoformat(),
            })
        prs_by_work: dict[str, list[dict]] = {}
        resolutions: dict[str, dict] = {}
        for subject, kind, details, created in db.execute(
            "SELECT subject_id,kind,details,created_at FROM events WHERE kind IN "
            "('work.pr_opened','work.pr_closed','work.completed','work.resolved_outside_cycle') "
            "AND subject_id IN (SELECT id FROM work_items WHERE project_id=%s) ORDER BY created_at",
            (project_id,),
        ).fetchall():
            prs = prs_by_work.setdefault(str(subject), [])
            if kind == "work.pr_opened":
                prs.append({**details, "state": "OPEN", "created_at": created.isoformat()})
            elif kind == "work.resolved_outside_cycle":
                resolutions[str(subject)] = {**details, "created_at": created.isoformat()}
            else:  # closed or merged: annotate the PR it refers to
                for pr in prs:
                    if pr.get("pr_number") == details.get("pr_number"):
                        pr["state"] = "MERGED" if kind == "work.completed" else "CLOSED_UNMERGED"
                        if kind == "work.completed":
                            pr["merge_commit_sha"] = details.get("merge_commit_sha")
        patches_by_work: dict[str, list[dict]] = {}
        for patch_row in patch_rows:
            proposal_id = str(patch_row[0])
            patches_by_work.setdefault(str(patch_row[1]), []).append({
                "id": proposal_id, "proposer_id": patch_row[2],
                "base_sha": patch_row[3], "patch_sha256": patch_row[4],
                "changed_paths": patch_row[5], "status": patch_row[6],
                "created_at": patch_row[7].isoformat(),
                "applied": False,
                "validations": validations_by_proposal.get(proposal_id, []),
            })
        return [
            {"id": r[0], "title": r[1], "status": r[2],
             "acceptance_criteria": r[3], "evidence": r[4],
             "executions": r[5], "reviews": reviews_by_work.get(str(r[0]), []),
             "patch_proposals": patches_by_work.get(str(r[0]), []),
             "pull_requests": prs_by_work.get(str(r[0]), []),
             "resolution": resolutions.get(str(r[0]))}
            for r in rows
        ]


@app.get("/v1/projects/{project_id}/activity")
def activity(project_id: str, principal: str = Depends(read_principal), limit: int = 100):
    """Newest-first project activity: audit events of the project, its work and executions,
    plus the execution journal (claims, completions, effects)."""
    if not 1 <= limit <= 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        if principal is not _CEO_PRINCIPAL:
            require_grant(db, principal, project_id, "project.read")
        rows = db.execute(
            "SELECT id,subject_id,kind,details,created_at FROM ("
            " SELECT e.id,e.subject_id,e.kind,e.details,e.created_at FROM events e"
            " WHERE e.subject_id=%(p)s"
            " OR e.subject_id IN (SELECT id FROM work_items WHERE project_id=%(p)s)"
            " OR e.subject_id IN (SELECT id FROM execution_queue WHERE project_id=%(p)s)"
            " UNION ALL"
            " SELECT j.id,j.execution_id,'execution.'||j.kind,j.details,j.occurred_at FROM execution_journal j"
            " JOIN execution_queue q ON q.id=j.execution_id WHERE q.project_id=%(p)s"
            ") a ORDER BY created_at DESC,id LIMIT %(n)s",
            {"p": project_id, "n": limit},
        ).fetchall()
    return [{"id": str(r[0]), "subject_id": str(r[1]), "kind": r[2], "details": r[3],
             "created_at": r[4].isoformat()} for r in rows]


@app.get("/v1/projects/{project_id}/capabilities")
def list_capabilities(
    project_id: str, principal: str = Depends(read_principal),
    query: str | None = None, capability_type: str | None = None,
):
    """Discover real project-local capability versions; listing grants no execution authority."""
    allowed_types = {
        "cli_script", "library", "application_service", "agent", "agent_skill",
        "knowledge_procedure", "workflow",
    }
    if capability_type is not None and capability_type not in allowed_types:
        raise HTTPException(422, "Unknown capability type")
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        if principal is not _CEO_PRINCIPAL:
            require_grant(db, principal, project_id, "project.read")
        rows = db.execute(
            "SELECT capability_id,version,capability_type,status,provenance,contract,"
            "required_permissions,risks,dependencies,tests,compatibility,evidence,created_by,created_at "
            "FROM capability_versions WHERE project_id=%s "
            "AND (%s::text IS NULL OR capability_type=%s) "
            "AND (%s::text IS NULL OR capability_id ILIKE %s OR contract::text ILIKE %s) "
            "ORDER BY capability_id,version",
            (project_id, capability_type, capability_type, query,
             f"%{query}%" if query else None, f"%{query}%" if query else None),
        ).fetchall()
        return [{
            "capability_id": str(row[0]), "version": row[1], "capability_type": row[2],
            "status": row[3], "provenance": row[4], "contract": row[5],
            "required_permissions": row[6], "risks": row[7], "dependencies": row[8],
            "tests": row[9], "compatibility": row[10], "evidence": row[11],
            "created_by": row[12], "created_at": row[13].isoformat(),
            "execution_authorized": False,
        } for row in rows]


@app.post("/v1/projects/{project_id}/capabilities", status_code=201)
def register_capability(
    project_id: str, payload: CapabilityRequest,
    principal: str = Depends(require_worker),
):
    """Record project-owned capability metadata, not an executable authorization."""
    if not payload.provenance or not payload.contract:
        raise HTTPException(422, "Capability provenance and contract are required")
    missing_fields = missing_contract_fields(payload.capability_type, payload.contract)
    if missing_fields:
        raise HTTPException(
            422, "Capability contract is incomplete: " + ", ".join(sorted(missing_fields)),
        )
    profile_errors = model_profile_errors(payload.contract) if payload.capability_type == "agent" else []
    if profile_errors:
        raise HTTPException(422, "; ".join(profile_errors))
    if not payload.tests or not payload.evidence:
        raise HTTPException(422, "At least one test reference and evidence reference are required")
    with tx() as db:
        project = db.execute(
            "SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,),
        ).fetchone()
        if not project:
            raise HTTPException(404, "Project not found")
        if project[0] != "ACTIVE":
            raise HTTPException(409, "Capabilities can only be registered in active projects")
        require_grant(db, principal, project_id, "work.create")
        inserted = db.execute(
            "INSERT INTO capability_versions(project_id,capability_id,version,capability_type,"
            "status,provenance,contract,required_permissions,risks,dependencies,tests,"
            "compatibility,evidence,created_by) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,"
            "%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s) "
            "ON CONFLICT (project_id,capability_id,version) DO NOTHING RETURNING version",
            (project_id, payload.capability_id, payload.version, payload.capability_type,
             "registered_local", json.dumps(payload.provenance), json.dumps(payload.contract),
             json.dumps(payload.required_permissions), json.dumps(payload.risks),
             json.dumps(payload.dependencies), json.dumps(payload.tests),
             json.dumps(payload.compatibility), json.dumps(payload.evidence), principal),
        ).fetchone()
        if not inserted:
            raise HTTPException(409, "Capability version already exists and is immutable")
        audit(db, project_id, "capability.version_registered", {
            "capability_id": payload.capability_id, "version": payload.version,
            "capability_type": payload.capability_type, "created_by": principal,
            "execution_authorized": False,
        })
    return {"project_id": project_id, "capability_id": payload.capability_id,
            "version": payload.version, "status": "registered_local",
            "execution_authorized": False}


@app.post("/v1/projects/{project_id}/capability-evaluations", status_code=201)
def evaluate_capabilities(
    project_id: str, payload: CapabilityEvaluationRequest,
    principal: str = Depends(require_worker),
):
    """Compare reuse/adapt/build for a real project task and audit the recommendation."""
    choices = [option.choice for option in payload.options]
    if sorted(choices) != ["adapt", "build", "reuse"]:
        raise HTTPException(422, "Exactly one reuse, adapt, and build option is required")
    if not payload.rationale.strip() or any(not item.strip() for item in payload.evidence):
        raise HTTPException(422, "Rationale and evidence references must be non-blank")
    selected_options = [option.model_dump() for option in payload.options]
    recommendation, scores = recommend(selected_options)
    if recommendation in {"reuse", "adapt"}:
        if not payload.capability_id or not payload.version:
            raise HTTPException(422, "Reuse or adaptation requires a registered capability version")
    elif payload.capability_id or payload.version:
        raise HTTPException(422, "Build comparison must not claim an existing capability version")

    with tx() as db:
        project = db.execute(
            "SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,),
        ).fetchone()
        if not project:
            raise HTTPException(404, "Project not found")
        if project[0] != "ACTIVE":
            raise HTTPException(409, "Capability evaluation requires an active project")
        require_grant(db, principal, project_id, "work.create")
        task = db.execute(
            "SELECT 1 FROM work_items WHERE id=%s AND project_id=%s FOR SHARE",
            (payload.task_id, project_id),
        ).fetchone()
        if not task:
            raise HTTPException(404, "Task not found in this project")
        if recommendation in {"reuse", "adapt"}:
            capability = db.execute(
                "SELECT status FROM capability_versions WHERE project_id=%s "
                "AND capability_id=%s AND version=%s FOR SHARE",
                (project_id, payload.capability_id, payload.version),
            ).fetchone()
            if not capability or capability[0] != "registered_local":
                raise HTTPException(409, "Selected capability version is unavailable locally")
        details = {
            "project_id": project_id, "task_id": payload.task_id,
            "principal_id": principal, "options": selected_options,
            "scores": scores, "recommendation": recommendation,
            "capability_id": payload.capability_id, "version": payload.version,
            "rationale": payload.rationale, "evidence": payload.evidence,
            "score_method": "equal-weighted mean of six caller-assessed 0-5 dimensions",
            "execution_authorized": False,
        }
        audit(db, payload.task_id, "capability.evaluated", details)
    return {"task_id": payload.task_id, "recommendation": recommendation,
            "scores": scores, "capability_id": payload.capability_id,
            "version": payload.version, "execution_authorized": False}


@app.get("/v1/projects/{project_id}/capability-evaluations")
def list_capability_evaluations(
    project_id: str, principal: str = Depends(read_principal),
):
    with tx() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        if principal is not _CEO_PRINCIPAL:
            require_grant(db, principal, project_id, "project.read")
        rows = db.execute(
            "SELECT e.subject_id,e.details,e.created_at,w.title FROM events e "
            "JOIN work_items w ON w.id=e.subject_id AND w.project_id=%s "
            "WHERE e.kind='capability.evaluated' ORDER BY e.created_at DESC",
            (project_id,),
        ).fetchall()
        return [{"task_id": str(row[0]), "details": row[1],
                 "created_at": row[2].isoformat(), "task_title": row[3]}
                for row in rows]


@app.post("/v1/work/{work_id}/resolve-outside-cycle")
def resolve_outside_cycle(work_id: str, payload: ExternalResolutionRequest, principal: str = Depends(require_ceo)):
    """CEO-only: close work whose change reached main outside the agent cycle, keeping that fact explicit."""
    with tx() as db:
        row = db.execute("SELECT status FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Work not found")
        if row[0] == "DONE":
            raise HTTPException(409, "Work is already DONE")
        if db.execute("SELECT 1 FROM execution_queue WHERE work_id=%s AND status IN ('QUEUED','RUNNING','UNCERTAIN')",
                      (work_id,)).fetchone():
            raise HTTPException(409, "An execution is still active for this work")
        db.execute("UPDATE work_items SET status='DONE' WHERE id=%s", (work_id,))
        audit(db, work_id, "work.resolved_outside_cycle", {
            "from": row[0], "reason": payload.reason, "pr_number": payload.pr_number,
            "merge_commit_sha": payload.merge_commit_sha, "resolved_by": principal,
            "agent_cycle": False})
    return {"id": work_id, "status": "DONE", "resolved_outside_cycle": True}


@app.post("/v1/work/{work_id}/admit")
def admit(work_id: str, principal: str = Depends(require_worker)):
    with tx() as db:
        work = db.execute("SELECT project_id,status FROM work_items WHERE id=%s FOR UPDATE",
                          (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id, current = work
        project = db.execute(
            "SELECT p.state,m.status FROM projects p JOIN mandates m ON "
            "p.mandate_id=m.id WHERE p.id=%s", (project_id,),
        ).fetchone()
        require_grant(db, principal, project_id, "work.admit")
        decision = decide_admission(
            project_active=project[0] == "ACTIVE",
            mandate_confirmed=project[1] == "CONFIRMED",
            authorized=True, dependencies_satisfied=True,
            capacity_available=True, within_budget=True,
            residual_risk="low", emergency_stop=False,
        )
        if current != "INBOX" or decision.status != Admission.READY:
            raise HTTPException(409, f"Admission rejected: {decision.reason}")
        db.execute("UPDATE work_items SET status='READY' WHERE id=%s", (work_id,))
        audit(db, work_id, "work.admitted", {"principal_id": principal})
    return {"id": work_id, "status": "READY"}


@app.post("/v1/work/{work_id}/progress")
def progress(work_id: str, principal: str = Depends(require_worker)):
    with tx() as db:
        row = db.execute("SELECT project_id,status FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Work not found")
        project_id, status = row
        require_grant(db, principal, project_id, "work.progress")
        active = db.execute("SELECT state FROM projects WHERE id=%s", (project_id,)).fetchone()
        if not active or active[0] != "ACTIVE":
            raise HTTPException(409, "Project not active")
        transition = {"READY": "IN_PROGRESS", "IN_PROGRESS": "IN_REVIEW", "VERIFIED": "DONE"}
        if status not in transition:
            raise HTTPException(409, "Invalid progression; independent review required")
        if status == "VERIFIED":
            raise HTTPException(
                409,
                "Completion disabled until independent approval verification exists",
            )
        next_state = transition[status]
        db.execute("UPDATE work_items SET status=%s WHERE id=%s", (next_state, work_id))
        audit(db, work_id, "work.progressed", {"from": status, "to": next_state})
    return {"id": work_id, "status": next_state}


def persist_patch_proposal(work_id: str, principal: str, base_sha: str, patch: str) -> dict:
    """Shared authorization and bounded persistence path for API and worker proposals."""
    from aao.patch_proposals import PatchProposalError, inspect_patch
    try:
        proposal = inspect_patch(patch)
    except PatchProposalError as exc:
        raise HTTPException(422, str(exc)) from exc
    with tx() as db:
        work = db.execute("SELECT project_id,status,author_id FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id, status, author_id = work
        require_grant(db, principal, project_id, "code.propose")
        active = db.execute("SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,)).fetchone()
        if status != "IN_PROGRESS" or author_id != principal or not active or active[0] != "ACTIVE":
            raise HTTPException(409, "Only the assigned agent may propose a patch for in-progress work in an active project")
        proposal_id = str(uuid4())
        inserted = db.execute(
            "INSERT INTO patch_proposals(id,work_id,project_id,proposer_id,base_sha,patch_sha256,patch_bytes,changed_paths) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT (work_id,base_sha,patch_sha256) DO NOTHING RETURNING id",
            (proposal_id, work_id, project_id, principal, base_sha, proposal["patch_sha256"], patch.encode("utf-8"), json.dumps(proposal["changed_paths"])),
        ).fetchone()
        if not inserted:
            raise HTTPException(409, "Identical patch proposal already exists")
        audit(db, work_id, "work.patch_proposed", {"proposal_id": proposal_id, "proposer": principal,
            "base_sha": base_sha, "patch_sha256": proposal["patch_sha256"], "changed_paths": proposal["changed_paths"]})
    return {"proposal_id": proposal_id, "work_id": work_id, "status": "PROPOSED", "base_sha": base_sha, **proposal,
            "validated_in_disposable_clone": False, "applied_to_canonical_checkout": False}

@app.post("/v1/work/{work_id}/patch-proposals", status_code=201)
def propose_patch(work_id: str, payload: PatchProposalRequest, principal: str = Depends(require_worker)):
    """Persist a bounded proposal; validation and application are separate operations."""
    return persist_patch_proposal(work_id, principal, payload.base_sha, payload.patch)


@app.post("/v1/work/{work_id}/patch-proposals/{proposal_id}/validate", status_code=201)
def validate_patch_proposal(
    work_id: str, proposal_id: str,
    principal: str = Depends(require_worker),
):
    """Apply a stored patch only in a disposable clone and record its tree hash."""
    from aao.patch_proposals import PatchProposalError, validate_patch

    with tx() as db:
        row = db.execute(
            "SELECT p.project_id,p.base_sha,p.patch_sha256,p.patch_bytes,p.changed_paths "
            "FROM patch_proposals p WHERE p.id=%s AND p.work_id=%s",
            (proposal_id, work_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Patch proposal not found")
        project_id, base_sha, expected_digest, patch_bytes, changed_paths = row
        require_grant(db, principal, project_id, "code.propose")
        work = db.execute(
            "SELECT status,author_id FROM work_items WHERE id=%s AND project_id=%s",
            (work_id, project_id),
        ).fetchone()
        active = db.execute("SELECT state FROM projects WHERE id=%s", (project_id,)).fetchone()
        if not work or work[0] != "IN_PROGRESS" or work[1] != principal:
            raise HTTPException(409, "Only the assigned agent may validate a patch for in-progress work")
        if not active or active[0] != "ACTIVE":
            raise HTTPException(409, "Project is not active")

    if hashlib.sha256(patch_bytes).hexdigest() != expected_digest:
        raise HTTPException(409, "Stored patch integrity check failed")
    repository = os.getenv("AAO_SELF_DEV_REPOSITORY")
    if not repository:
        raise HTTPException(503, "Self-development repository is not configured")
    try:
        validation = validate_patch(repository, base_sha, patch_bytes.decode("utf-8"))
    except (PatchProposalError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "Stored patch failed isolated validation") from exc
    if validation["patch_sha256"] != expected_digest or validation["changed_paths"] != changed_paths:
        raise HTTPException(409, "Stored patch metadata differs from isolated validation")

    with tx() as db:
        locked = db.execute(
            "SELECT p.project_id,p.base_sha,p.patch_sha256,w.status,w.author_id "
            "FROM patch_proposals p JOIN work_items w ON w.id=p.work_id "
            "WHERE p.id=%s AND p.work_id=%s FOR UPDATE OF w",
            (proposal_id, work_id),
        ).fetchone()
        if not locked:
            raise HTTPException(404, "Patch proposal not found")
        current_project, current_base, current_digest, current_status, current_author = locked
        require_grant(db, principal, current_project, "code.propose")
        if (current_project != project_id or current_base != base_sha
                or current_digest != expected_digest or current_status != "IN_PROGRESS"
                or current_author != principal):
            raise HTTPException(409, "Patch authorization or state changed during validation")
        active = db.execute(
            "SELECT state FROM projects WHERE id=%s FOR SHARE", (current_project,),
        ).fetchone()
        if not active or active[0] != "ACTIVE":
            raise HTTPException(409, "Project is not active")
        validation_id = str(uuid4())
        inserted = db.execute(
            "INSERT INTO patch_proposal_validations(id,proposal_id,validator_id,base_sha,patch_sha256,candidate_tree) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (proposal_id,candidate_tree) DO NOTHING RETURNING id",
            (validation_id, proposal_id, principal, base_sha, expected_digest,
             validation["candidate_tree"]),
        ).fetchone()
        if not inserted:
            raise HTTPException(409, "Identical patch validation already exists")
        audit(db, work_id, "work.patch_validated", {
            "proposal_id": proposal_id, "validation_id": validation_id,
            "validator": principal, "base_sha": base_sha,
            "patch_sha256": expected_digest,
            "candidate_tree": validation["candidate_tree"],
        })
    return {
        "validation_id": validation_id, "proposal_id": proposal_id,
        "base_sha": base_sha, "patch_sha256": expected_digest,
        "changed_paths": changed_paths, "candidate_tree": validation["candidate_tree"],
        "validated_in_disposable_clone": True,
        "applied_to_canonical_checkout": False,
    }


@app.get("/v1/work/{work_id}/patch-proposals/{proposal_id}")
def read_patch_proposal(
    work_id: str, proposal_id: str,
    principal: str = Depends(require_reviewer),
):
    """Expose the exact stored diff to a project auditor only while work is in review."""
    with tx() as db:
        row = db.execute(
            "SELECT p.project_id,p.proposer_id,p.base_sha,p.patch_sha256,p.patch_bytes,"
            "p.changed_paths,p.created_at,w.status,w.author_id "
            "FROM patch_proposals p JOIN work_items w ON w.id=p.work_id "
            "WHERE p.id=%s AND p.work_id=%s FOR SHARE OF w",
            (proposal_id, work_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Patch proposal not found")
        project_id, proposer_id, base_sha, expected_digest, patch_bytes, paths, created_at, status, author_id = row
        require_grant(db, principal, project_id, "work.review")
        active = db.execute(
            "SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,),
        ).fetchone()
        if not active or active[0] != "ACTIVE" or status != "IN_REVIEW":
            raise HTTPException(409, "Patch proposal is available only for active work in review")
        if principal == proposer_id or principal == author_id:
            raise HTTPException(403, "Patch author cannot act as its auditor")
        if db.execute(
            "SELECT 1 FROM execution_journal WHERE kind='claimed' "
            "AND details->>'worker_id'=%s AND execution_id IN "
            "(SELECT id FROM execution_queue WHERE work_id=%s) LIMIT 1",
            (principal, work_id),
        ).fetchone():
            raise HTTPException(403, "Execution worker cannot inspect its own work as auditor")
        validations = db.execute(
            "SELECT id,validator_id,candidate_tree,created_at FROM patch_proposal_validations "
            "WHERE proposal_id=%s ORDER BY created_at,id",
            (proposal_id,),
        ).fetchall()
        if hashlib.sha256(patch_bytes).hexdigest() != expected_digest:
            raise HTTPException(409, "Stored patch integrity check failed")
        try:
            patch = patch_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(409, "Stored patch is not valid UTF-8") from exc
    return {
        "proposal_id": proposal_id, "work_id": work_id,
        "proposer_id": proposer_id, "base_sha": base_sha,
        "patch_sha256": expected_digest, "changed_paths": paths,
        "patch": patch, "created_at": created_at.isoformat(),
        "validations": [
            {
                "id": str(validation[0]), "validator_id": validation[1],
                "candidate_tree": validation[2],
                "created_at": validation[3].isoformat(),
            }
            for validation in validations
        ],
        "applied": False,
    }


@app.post("/v1/work/{work_id}/reviews", status_code=201)
def review(work_id: str, payload: ReviewRequest, principal: str = Depends(require_reviewer)):
    from aao.evidence_registry import EvidenceDenied, verify_evidence_references

    with tx() as db:
        work = db.execute("SELECT project_id,status,author_id FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id, status, author = work
        require_grant(db, principal, project_id, "work.review")
        active = db.execute("SELECT state FROM projects WHERE id=%s", (project_id,)).fetchone()
        if not active or active[0] != "ACTIVE" or status != "IN_REVIEW":
            raise HTTPException(409, "Work not reviewable")
        if principal == author:
            raise HTTPException(403, "Author cannot review own work")
        try:
            verified_evidence = verify_evidence_references(
                db, project_id, payload.evidence,
            )
        except EvidenceDenied as exc:
            raise HTTPException(409, str(exc)) from exc
        candidate_execution = db.execute(
            "SELECT id,status FROM execution_queue WHERE work_id=%s "
            "AND result_json->>'candidate_sha'=%s FOR SHARE",
            (work_id, payload.candidate_sha),
        ).fetchall()
        if not candidate_execution:
            raise HTTPException(409, "Candidate SHA has no linked execution")
        if db.execute(
            "SELECT 1 FROM reviews WHERE work_id=%s AND decision='VETO' LIMIT 1",
            (work_id,),
        ).fetchone() and payload.decision == "APPROVE":
            raise HTTPException(409, "Active veto blocks approval; CEO disposition required")
        executions = db.execute(
            "SELECT id,status FROM execution_queue WHERE work_id=%s FOR UPDATE",
            (work_id,),
        ).fetchall()
        # Earlier failed attempts do not block approval; the reviewed candidate's own
        # execution must have succeeded and no attempt may still be active.
        if payload.decision == "APPROVE" and (
            all(execution_status != "SUCCEEDED" for _, execution_status in candidate_execution)
            or any(execution_status in ("QUEUED", "RUNNING", "UNCERTAIN")
                   for _, execution_status in executions)
        ):
            raise HTTPException(409, "Execution must succeed before work review")
        if db.execute(
            "SELECT 1 FROM execution_journal j "
            "JOIN execution_queue q ON q.id=j.execution_id "
            "WHERE q.work_id=%s AND j.kind='claimed' "
            "AND j.details->>'worker_id'=%s LIMIT 1",
            (work_id, principal),
        ).fetchone():
            raise HTTPException(403, "Execution worker cannot review own work")
        review_decision = evaluate_review(
            author_id=author,
            reviewer_id=principal,
            evidence=payload.evidence,
            decision=payload.decision,
            project_active=active[0] == "ACTIVE",
            # require_reviewer authenticated a separate AUDITOR credential, authorship and
            # execution separation were checked, and verify_evidence_references resolved the evidence.
            identity_and_evidence_verified=True,
        )
        if not review_decision.allowed:
            raise HTTPException(409, review_decision.reason)
        rid = str(uuid4())
        db.execute(
            "INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence,candidate_sha) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,%s)",
            (rid, work_id, principal, payload.decision,
             json.dumps(payload.evidence), payload.candidate_sha),
        )
        next_state = {
            "APPROVE": "VERIFIED", "REJECT": "IN_PROGRESS", "VETO": "IN_REVIEW",
        }[payload.decision]
        if payload.decision != "VETO":
            db.execute(
                "UPDATE work_items SET status=%s,evidence=%s::jsonb WHERE id=%s",
                (next_state, json.dumps(payload.evidence), work_id),
            )
        audit(db, work_id, "work.reviewed", {
            "review_id": rid, "decision": payload.decision, "reviewer": principal,
            "candidate_sha": payload.candidate_sha,
            "verified_evidence": verified_evidence,
        })
    return {"review_id": rid, "status": next_state, "candidate_sha": payload.candidate_sha}

@app.post("/v1/work/{work_id}/stage-inert", status_code=202)
def stage_inert(work_id: str, principal: str = Depends(require_worker)):
    """Enqueue a fixed inert payload; no model or external action is possible."""
    if os.getenv("AAO_SANDBOX_QUEUE_ENABLED") != "true":
        raise HTTPException(503, "Sandbox queue disabled")
    with tx() as db:
        work = db.execute(
            "SELECT project_id,status FROM work_items WHERE id=%s FOR UPDATE",
            (work_id,),
        ).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id, status = work
        project = db.execute(
            "SELECT state FROM projects WHERE id=%s", (project_id,)
        ).fetchone()
        if not project or project[0] != "ACTIVE" or status != "READY":
            raise HTTPException(409, "Work not ready in active project")
        require_grant(db, principal, project_id, "work.admit")
        require_grant(db, principal, project_id, "execution.claim")
        existing = db.execute(
            "SELECT id,status FROM execution_queue WHERE work_id=%s", (work_id,)
        ).fetchone()
        if existing:
            return {"execution_id": str(existing[0]), "status": existing[1]}
        execution_id = str(uuid4())
        db.execute(
            "INSERT INTO execution_queue(id,work_id,project_id,status,input_json) "
            "VALUES (%s,%s,%s,'QUEUED',%s::jsonb)",
            (execution_id, work_id, project_id, json.dumps({"type": "aao.inert.v1"})),
        )
        audit(db, execution_id, "execution.staged", {"work_id": work_id})
    return {"execution_id": execution_id, "status": "QUEUED"}


@app.post("/v1/work/{work_id}/stage-repository-check", status_code=202)
def stage_repository_check(
    work_id: str, payload: RepositoryCheckRequest,
    principal: str = Depends(require_worker),
):
    """Stage only the fixed repository-check tool selected from this project's registry."""
    if os.getenv("AAO_SANDBOX_QUEUE_ENABLED") != "true":
        raise HTTPException(503, "Sandbox queue disabled")
    job = {
        "type": "aao.repository-check.v1", "check_id": payload.check_id,
        "capability_id": payload.capability_id, "version": payload.version,
    }
    with tx() as db:
        work = db.execute(
            "SELECT project_id,status FROM work_items WHERE id=%s FOR UPDATE",
            (work_id,),
        ).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id, status = work
        project = db.execute(
            "SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,),
        ).fetchone()
        if not project or project[0] != "ACTIVE" or status != "READY":
            raise HTTPException(409, "Work not ready in active project")
        require_grant(db, principal, project_id, "work.admit")
        require_grant(db, principal, project_id, "execution.claim")
        capability = db.execute(
            "SELECT capability_type,status,contract->>'entrypoint' "
            "FROM capability_versions WHERE project_id=%s AND capability_id=%s "
            "AND version=%s FOR SHARE",
            (project_id, payload.capability_id, payload.version),
        ).fetchone()
        if (not capability or capability[0] != "cli_script"
                or capability[1] != "registered_local"
                or capability[2] != "aao.sandboxed_repository_checks:core-unit"):
            raise HTTPException(409, "Selected repository-check capability is unavailable")
        evaluation = db.execute(
            "SELECT 1 FROM events WHERE subject_id=%s AND kind='capability.evaluated' "
            "AND details->>'capability_id'=%s AND details->>'version'=%s "
            "AND details->>'recommendation' IN ('reuse','adapt') LIMIT 1",
            (work_id, payload.capability_id, payload.version),
        ).fetchone()
        if not evaluation:
            raise HTTPException(409, "Capability must be selected for this task before staging")
        existing = db.execute(
            "SELECT id,status,input_json FROM execution_queue WHERE work_id=%s",
            (work_id,),
        ).fetchone()
        if existing:
            if existing[2] != job:
                raise HTTPException(409, "A different execution is already recorded")
            return {"execution_id": str(existing[0]), "status": existing[1]}
        execution_id = str(uuid4())
        db.execute(
            "INSERT INTO execution_queue(id,work_id,project_id,status,input_json) "
            "VALUES (%s,%s,%s,'QUEUED',%s::jsonb)",
            (execution_id, work_id, project_id, json.dumps(job)),
        )
        audit(db, execution_id, "execution.staged", {
            "work_id": work_id, "capability_id": payload.capability_id,
            "version": payload.version, "check_id": payload.check_id,
        })
    return {"execution_id": execution_id, "status": "QUEUED",
            "capability_id": payload.capability_id, "version": payload.version}



def _agent_budget_left(db, project_id) -> float | None:
    """Daily agent budget the CEO set for this API (AAO_AGENT_DAILY_BUDGET_USD) minus today's estimated spend of
    the project's staged agent attempts. None when no budget is set. An unreadable value fails closed (0)."""
    raw = os.getenv("AAO_AGENT_DAILY_BUDGET_USD")
    if raw is None:
        return None
    try:
        budget = float(raw)
    except ValueError:
        budget = 0.0
    spent = db.execute("SELECT coalesce(sum((e.details->>'cost_estimate_usd')::numeric),0) FROM events e "
                       "JOIN execution_queue q ON q.id=e.subject_id WHERE e.kind='execution.staged' "
                       "AND q.project_id=%s AND e.created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') "
                       "AT TIME ZONE 'UTC'", (project_id,)).fetchone()[0]
    return round(budget - float(spent), 6)


class RouteModelRequest(BaseModel):
    seat: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
    role: str = Field(default="implementer", pattern=r"^[a-z_]{1,32}$")
    exclude_providers: list[str] = Field(default_factory=list, max_length=8)


@app.post("/v1/work/{work_id}/route-model")
def route_model(work_id: str, payload: RouteModelRequest, principal: str = Depends(require_worker)):
    """Recommend an agent capability from the project catalog and record why. Authorizes nothing: staging
    re-checks the grant, the capability and provider activation independently."""
    from aao.agent_runner import activated_backends
    from aao.model_router import Requirements, route
    with tx() as db:
        work = db.execute("SELECT project_id FROM work_items WHERE id=%s FOR SHARE", (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id = work[0]
        require_grant(db, principal, project_id, "work.admit")
        rows = db.execute("SELECT capability_id,version,contract->'compatible_roles',contract->'model_profile' "
                          "FROM capability_versions WHERE project_id=%s AND capability_type='agent' AND "
                          "status='registered_local' AND contract->>'entrypoint'='aao.agent_runner:patch' "
                          "ORDER BY capability_id,version", (project_id,)).fetchall()
        candidates = [{"capability_id": r[0], "version": r[1], "compatible_roles": r[2] or [], "model_profile": r[3]}
                      for r in rows]
        activated = activated_backends()
        budget_left = _agent_budget_left(db, project_id)
        decision = route(Requirements(seat=payload.seat, role=payload.role,
                                      exclude_providers=frozenset(payload.exclude_providers)),
                         candidates, activated=activated, budget_left=budget_left)
        details = {"capability_id": decision.capability_id, "version": decision.version,
                   "reasons": list(decision.reasons), "rejected": [list(r) for r in decision.rejected],
                   "seat": payload.seat, "role": payload.role, "exclude_providers": payload.exclude_providers,
                   "activated_backends": sorted(activated), "budget_left_usd": budget_left,
                   "principal_id": principal, "execution_authorized": False}
        audit(db, work_id, "model.routed", details)
    return details


def _attempt_outcome(result: dict | None) -> tuple:
    """What an agent attempt produced: its patch and how it ended (an identical patch that now passes is progress)."""
    r = result or {}
    check = r.get("check") or {}
    return (r.get("patch_sha256"), r.get("conclusion"), r.get("error"), check.get("conclusion"), check.get("error"))


@app.post("/v1/work/{work_id}/stage-agent-run", status_code=202)
def stage_agent_run(work_id: str, payload: AgentRunRequest, principal: str = Depends(require_worker)):
    if os.getenv("AAO_AGENT_QUEUE_ENABLED") != "true":
        raise HTTPException(503, "Agent queue disabled")
    job = {"type": "aao.agent-patch.v1", "capability_id": payload.capability_id,
           "version": payload.version, "base_sha": payload.base_sha}
    with tx() as db:
        work = db.execute("SELECT project_id,status FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project_id, status = work
        project = db.execute("SELECT state FROM projects WHERE id=%s FOR SHARE", (project_id,)).fetchone()
        # READY for the first run; IN_PROGRESS to re-run after a failed or rejected attempt.
        if not project or project[0] != "ACTIVE" or status not in ("READY", "IN_PROGRESS"):
            raise HTTPException(409, "Work not ready in active project")
        require_grant(db, principal, project_id, "work.admit")
        require_grant(db, principal, project_id, "execution.claim")
        cap = db.execute("SELECT capability_type,status,contract->>'entrypoint',contract->'model_profile'->>'backend',coalesce((contract->'model_profile'->>'cost_per_attempt_usd')::numeric,0) FROM capability_versions WHERE project_id=%s AND capability_id=%s AND version=%s FOR SHARE", (project_id, payload.capability_id, payload.version)).fetchone()
        if not cap or cap[0] != "agent" or cap[1] != "registered_local" or cap[2] != "aao.agent_runner:patch":
            raise HTTPException(409, "Selected agent-runner capability is unavailable")
        # Authorization is checked here on its own, whatever any routing recommendation said.
        from aao.agent_runner import activated_backends
        if cap[3] not in (None, "fixture") and cap[3] not in activated_backends():
            raise HTTPException(409, f"Agent backend {cap[3]} is not activated; CEO provider activation required")
        ev = db.execute("SELECT 1 FROM events WHERE subject_id=%s AND kind='capability.evaluated' AND details->>'capability_id'=%s AND details->>'version'=%s AND details->>'recommendation' IN ('reuse','adapt') LIMIT 1", (work_id, payload.capability_id, payload.version)).fetchone()
        if not ev:
            raise HTTPException(409, "Capability must be selected for this task before staging")
        existing = db.execute("SELECT id,status,input_json FROM execution_queue WHERE work_id=%s "
                              "AND status IN ('QUEUED','RUNNING','UNCERTAIN')", (work_id,)).fetchone()
        if existing:
            if existing[2] != job:
                raise HTTPException(409, "A different execution is still active for this work")
            return {"execution_id": str(existing[0]), "status": existing[1]}
        # Effective retry limit: every agent attempt for this work counts, whatever its outcome.
        attempts = db.execute("SELECT count(*) FROM execution_queue WHERE work_id=%s "
                              "AND input_json->>'type'='aao.agent-patch.v1'", (work_id,)).fetchone()[0]
        limit = int(os.getenv("AAO_AGENT_MAX_ATTEMPTS", "3"))
        if attempts >= limit:
            raise HTTPException(409, f"Agent attempt limit reached ({attempts}/{limit}); CEO or PM decision required")
        # No progress: two consecutive finished attempts with the same outcome (same patch and same result or
        # failure) would only burn attempts; stop and leave the decision to the PM (new task or CEO resolution).
        last = db.execute("SELECT result_json FROM execution_queue WHERE work_id=%s AND input_json->>'type'="
                          "'aao.agent-patch.v1' AND status IN ('SUCCEEDED','FAILED') ORDER BY created_at DESC LIMIT 2",
                          (work_id,)).fetchall()
        if len(last) == 2 and _attempt_outcome(last[0][0]) == _attempt_outcome(last[1][0]):
            raise HTTPException(409, "No progress: the last two agent attempts had the same outcome; PM decision required")
        # Budget: going over it is reserved to the CEO (policy budget.exceed), never silently downgraded.
        # ponytail: concurrent stagings in one project may both pass the check; per-project lock if that matters.
        estimate = float(cap[4])
        budget_left = _agent_budget_left(db, project_id)
        if budget_left is not None and estimate > budget_left:
            raise HTTPException(409, f"Daily agent budget exceeded (estimate {estimate}, left {budget_left}); "
                                     "CEO decision required (budget.exceed)")
        execution_id = str(uuid4())
        db.execute("INSERT INTO execution_queue(id,work_id,project_id,status,input_json) VALUES (%s,%s,%s,'QUEUED',%s::jsonb)", (execution_id, work_id, project_id, json.dumps(job)))
        audit(db, execution_id, "execution.staged", {"work_id": work_id, "capability_id": payload.capability_id, "version": payload.version, "base_sha": payload.base_sha, "cost_estimate_usd": estimate})
    return {"execution_id": execution_id, "status": "QUEUED", "capability_id": payload.capability_id, "version": payload.version}
