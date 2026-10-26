"""Minimal AAO API: CEO-confirmed mandates, projects and evidence-gated Kanban."""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from aao.environment_settings import load_local_env

load_local_env()

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from aao.execution import initialize as initialize_queue
from aao.planner import Admission, decide_admission
from aao.policy import Verdict, authorize
from aao.review import evaluate_review
from aao.sqlite_storage import connection, event, initialize, transaction

DB_PATH = os.getenv("AAO_DB_PATH", "./data/aao.sqlite3")
CEO_TOKEN = os.getenv("AAO_CEO_TOKEN")
WORK_TOKEN = os.getenv("AAO_WORK_TOKEN")
REVIEW_TOKEN = os.getenv("AAO_REVIEW_TOKEN")
SANDBOX_QUEUE_ENABLED = os.getenv("AAO_SANDBOX_QUEUE_ENABLED", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize(DB_PATH)
    initialize_queue(DB_PATH)
    yield


app = FastAPI(title="AAO Core", version="0.1.0", lifespan=lifespan)


def require_ceo(x_ceo_token: str | None = Header(default=None)):
    if not CEO_TOKEN:
        raise HTTPException(503, "CEO token not configured: reserved writes disabled")
    import secrets
    if not x_ceo_token or not secrets.compare_digest(x_ceo_token, CEO_TOKEN):
        raise HTTPException(403, "CEO authentication required")
    return True


def require_worker(x_work_token: str | None = Header(default=None)):
    """Development-only write gate, distinct from CEO authentication."""
    if not WORK_TOKEN:
        raise HTTPException(503, "Worker token not configured: work writes disabled")
    import secrets
    if not x_work_token or not secrets.compare_digest(x_work_token, WORK_TOKEN):
        raise HTTPException(403, "Worker authentication required")
    return True


def require_reviewer(x_review_token: str | None = Header(default=None)):
    if not REVIEW_TOKEN:
        raise HTTPException(503, "Reviewer token not configured")
    import secrets
    if not x_review_token or not secrets.compare_digest(x_review_token, REVIEW_TOKEN):
        raise HTTPException(403, "Reviewer authorization required")
    return True

class GrantIn(BaseModel):
    principal_id: str = Field(min_length=1)
    capability: str = Field(pattern=r'^(work\.create|work\.transition|work\.review)$')




class ReviewIn(BaseModel):
    reviewer_id: str = Field(min_length=1)
    decision: str
    evidence: list[str] = Field(min_length=1)

class MandateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=5000)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mandate_id: str


class WorkIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    acceptance_criteria: list[str] = Field(min_length=1)
    author_id: str = Field(min_length=1)


class TransitionIn(BaseModel):
    status: str
    evidence: list[str] = Field(default_factory=list)


@app.get("/", include_in_schema=False)
def workboard_ui():
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "index.html")


@app.get("/assets/control-center.css", include_in_schema=False)
def control_center_stylesheet():
    return FileResponse(
        Path(__file__).resolve().parents[2] / "frontend" / "control-center.css",
        media_type="text/css",
    )


@app.get("/assets/control-center.js", include_in_schema=False)
def control_center_script():
    return FileResponse(
        Path(__file__).resolve().parents[2] / "frontend" / "control-center.js",
        media_type="text/javascript",
    )


@app.get("/health")
def health():
    return {"status": "ok", "autonomous_execution": False}


@app.post("/v1/mandates", status_code=201)
def draft_mandate(payload: MandateIn, _: bool = Depends(require_ceo)):
    mid = str(uuid4())
    with transaction(DB_PATH) as db:
        db.execute("INSERT INTO mandates(id,title,objective,status) VALUES (?,?,?,'DRAFT')",
                   (mid, payload.title, payload.objective))
        event(db, mid, "mandate.drafted", {"title": payload.title})
    return {"id": mid, "status": "DRAFT"}


@app.post("/v1/mandates/{mandate_id}/confirm")
def confirm_mandate(mandate_id: str, _: bool = Depends(require_ceo)):
    with transaction(DB_PATH) as db:
        row = db.execute("SELECT status FROM mandates WHERE id=?", (mandate_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Mandate not found")
        if row["status"] != "DRAFT":
            raise HTTPException(409, "Mandate already confirmed")
        db.execute("UPDATE mandates SET status='CONFIRMED',confirmed_by='CEO' WHERE id=?",
                   (mandate_id,))
        event(db, mandate_id, "mandate.confirmed", {"authority": "CEO"})
    return {"id": mandate_id, "status": "CONFIRMED"}


@app.post("/v1/projects", status_code=201)
def create_project(payload: ProjectIn, _: bool = Depends(require_ceo)):
    decision = authorize("project.create", is_ceo=True, confirmed_mandate=True)
    if decision.verdict != Verdict.ALLOW:
        raise HTTPException(403, decision.reason)
    pid = str(uuid4())
    with transaction(DB_PATH) as db:
        mandate = db.execute("SELECT status FROM mandates WHERE id=?",
                             (payload.mandate_id,)).fetchone()
        if not mandate or mandate["status"] != "CONFIRMED":
            raise HTTPException(409, "Confirmed mandate required")
        existing = db.execute("SELECT id FROM projects WHERE mandate_id=?",
                              (payload.mandate_id,)).fetchone()
        if existing:
            raise HTTPException(409, "Mandate already used by a project")
        db.execute("INSERT INTO projects(id,name,mandate_id,state) VALUES (?,?,?,'ACTIVE')",
                   (pid, payload.name, payload.mandate_id))
        event(db, pid, "project.created", {"mandate_id": payload.mandate_id})
    return {"id": pid, "state": "ACTIVE"}


@app.get("/v1/projects")
def list_projects():
    with connection(DB_PATH) as db:
        return [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY rowid")]


@app.post("/v1/projects/{project_id}/work", status_code=201)
def create_work(project_id: str, payload: WorkIn, _: bool = Depends(require_worker)):
    wid = str(uuid4())
    with transaction(DB_PATH) as db:
        project = db.execute("SELECT state FROM projects WHERE id=?",
                             (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found")
        if project["state"] != "ACTIVE":
            raise HTTPException(409, "Project not active")
        db.execute("""INSERT INTO work_items
            (id,project_id,title,status,acceptance_criteria,author_id)
            VALUES (?,?,?,'INBOX',?,?)""",
            (wid, project_id, payload.title, json.dumps(payload.acceptance_criteria), payload.author_id))
        event(db, wid, "work.created", {"project_id": project_id})
    return {"id": wid, "status": "INBOX"}


@app.get("/v1/projects/{project_id}/board")
def board(project_id: str):
    with connection(DB_PATH) as db:
        if not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        rows = db.execute("SELECT * FROM work_items WHERE project_id=? ORDER BY rowid",
                          (project_id,)).fetchall()
        return [{**dict(r), "evidence": json.loads(r["evidence"]),
                 "acceptance_criteria": json.loads(r["acceptance_criteria"])} for r in rows]


ALLOWED_NEXT = {
    "INBOX": {"READY"}, "READY": {"IN_PROGRESS"},
    "IN_PROGRESS": {"IN_REVIEW"}, "IN_REVIEW": {"VERIFIED"},
    "VERIFIED": {"DONE"}, "DONE": set(),
}


@app.post("/v1/work/{work_id}/transition")
def transition(work_id: str, payload: TransitionIn, _: bool = Depends(require_worker)):
    if payload.status not in {s for opts in ALLOWED_NEXT.values() for s in opts}:
        raise HTTPException(422, "Unknown target state")
    with transaction(DB_PATH) as db:
        row = db.execute("SELECT * FROM work_items WHERE id=?", (work_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Work item not found")
        project = db.execute("SELECT state FROM projects WHERE id=?",
                             (row["project_id"],)).fetchone()
        if project["state"] != "ACTIVE":
            raise HTTPException(409, "Project not active")
        if payload.status not in ALLOWED_NEXT[row["status"]]:
            raise HTTPException(409, "Invalid state transition")
        evidence = json.loads(row["evidence"])
        evidence += payload.evidence
        if payload.status in {"VERIFIED", "DONE"} and not evidence:
            raise HTTPException(409, "Evidence required")
        # Review states remain workflow placeholders, not verified approval.
        if payload.status == "VERIFIED":
            raise HTTPException(409, "Reviewer must verify")
        if payload.status == "DONE":
            raise HTTPException(
                409,
                "Completion disabled until independent approval verification exists",
            )
        db.execute("UPDATE work_items SET status=?, evidence=? WHERE id=?",
                   (payload.status, json.dumps(evidence), work_id))
        event(db, work_id, "work.transitioned", {"from": row["status"], "to": payload.status})
    return {"id": work_id, "status": payload.status}


@app.get("/v1/events")
def list_events():
    with connection(DB_PATH) as db:
        return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY rowid")]

@app.post("/v1/work/{work_id}/reviews", status_code=201)
def submit_review(work_id: str, payload: ReviewIn, _: bool = Depends(require_reviewer)):
    with transaction(DB_PATH) as db:
        work = db.execute("SELECT * FROM work_items WHERE id=?", (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project = db.execute("SELECT state FROM projects WHERE id=?", (work["project_id"],)).fetchone()
        if work["status"] != "IN_REVIEW":
            raise HTTPException(409, "Work not pending review")
        decision = evaluate_review(author_id=work["author_id"],
                                   reviewer_id=payload.reviewer_id,
                                   evidence=payload.evidence, decision=payload.decision,
                                   project_active=project["state"] == "ACTIVE")
        if not decision.allowed:
            raise HTTPException(409, decision.reason)
        review_id = str(uuid4())
        db.execute("INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence) VALUES (?,?,?,?,?)",
                   (review_id, work_id, payload.reviewer_id, payload.decision,
                    json.dumps(payload.evidence)))
        target = "VERIFIED" if payload.decision == "APPROVE" else "IN_PROGRESS"
        db.execute("UPDATE work_items SET status=?, evidence=? WHERE id=?",
                   (target, json.dumps(payload.evidence), work_id))
        event(db, work_id, "work.reviewed", {"decision": payload.decision, "review_id": review_id})
    return {"review_id": review_id, "status": target}


def change_project_state(project_id: str, expected: str | None, target: str):
    with transaction(DB_PATH) as db:
        project = db.execute("SELECT state FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(404, "Project not found")
        if project["state"] == "CANCELLED" or (expected and project["state"] != expected):
            raise HTTPException(409, "Invalid project transition")
        db.execute("UPDATE projects SET state=? WHERE id=?", (target, project_id))
        event(db, project_id, "project.state.changed", {"from": project["state"], "to": target})
    return {"id": project_id, "state": target}


@app.post("/v1/projects/{project_id}/pause")
def pause_project(project_id: str, _: bool = Depends(require_worker)):
    return change_project_state(project_id, "ACTIVE", "PAUSED")


@app.post("/v1/projects/{project_id}/resume")
def resume_project(project_id: str, _: bool = Depends(require_worker)):
    return change_project_state(project_id, "PAUSED", "ACTIVE")


@app.post("/v1/projects/{project_id}/cancel")
def cancel_project(project_id: str, _: bool = Depends(require_ceo)):
    return change_project_state(project_id, None, "CANCELLED")

@app.post("/v1/work/{work_id}/sandbox-queue", status_code=202)
def sandbox_queue_work(work_id: str, _: bool = Depends(require_worker)):
    """Atomically enqueue inert development work, never commands or LLM calls.

    This route cannot run arbitrary work: it accepts no tool or model arguments.
    Real project grants, risk assessment and budget gates remain future work.
    """
    if not SANDBOX_QUEUE_ENABLED:
        raise HTTPException(503, "Inert sandbox queue is disabled")
    with transaction(DB_PATH) as db:
        work = db.execute("SELECT * FROM work_items WHERE id=?", (work_id,)).fetchone()
        if not work:
            raise HTTPException(404, "Work not found")
        project = db.execute(
            "SELECT p.state,m.status AS mandate_status FROM projects p "
            "JOIN mandates m ON m.id=p.mandate_id WHERE p.id=?",
            (work["project_id"],),
        ).fetchone()
        # Sandbox admission permits only harmless inert payloads. No external
        # operations can be requested by this endpoint.
        verdict = decide_admission(
            project_active=project["state"] == "ACTIVE",
            mandate_confirmed=project["mandate_status"] == "CONFIRMED",
            authorized=True, dependencies_satisfied=True,
            capacity_available=True, within_budget=True,
            residual_risk="low", emergency_stop=False,
        )
        if verdict.status != Admission.READY or work["status"] != "READY":
            raise HTTPException(409, "Work not ready for inert sandbox admission")
        prior = db.execute(
            "SELECT id FROM execution_queue WHERE work_id=?", (work_id,),
        ).fetchone()
        if prior:
            return {"execution_id": prior["id"], "status": "QUEUED_OR_EXISTING"}
        execution_id = str(uuid4())
        db.execute(
            "INSERT INTO execution_queue(id,project_id,work_id,input_json,status) "
            "VALUES (?,?,?,?,'QUEUED')",
            (execution_id, work["project_id"], work_id,
             json.dumps({"kind": "aao.inert-sandbox.v1", "title": work["title"]})),
        )
        event(db, execution_id, "sandbox.queued", {"work_id": work_id})
        return {"execution_id": execution_id, "status": "QUEUED"}


@app.post("/v1/projects/{project_id}/grants", status_code=201)
def create_grant(project_id: str, payload: GrantIn, _: bool = Depends(require_ceo)):
    with transaction(DB_PATH) as db:
        if not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        db.execute("INSERT OR IGNORE INTO project_grants(principal_id,project_id,capability) VALUES (?,?,?)", (payload.principal_id, project_id, payload.capability))
        event(db, project_id, "grant.created", {"principal": payload.principal_id, "capability": payload.capability})
    return {"project_id": project_id, "principal_id": payload.principal_id, "capability": payload.capability}


def check_grant(db, principal_id: str, project_id: str, capability: str):
    if not db.execute("SELECT 1 FROM project_grants WHERE principal_id=? AND project_id=? AND capability=?", (principal_id, project_id, capability)).fetchone():
        raise HTTPException(403, "Project capability not granted")
