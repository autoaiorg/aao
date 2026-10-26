"""Durable, deliberately inert execution queue for isolated AAO development.

No model calls, shell commands, network access or external side effects exist here.
Expired leases become UNCERTAIN, never silently requeued: a reconciler must
explicitly establish safety before retrying an externally effectful operation.
"""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


def utcnow():
    return datetime.now(UTC)


@dataclass(frozen=True)
class Lease:
    execution_id: str
    token: str
    worker_id: str
    expires_at: str


class QueueConflict(ValueError):
    pass


def connect(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA foreign_keys=ON")
    return db


@contextmanager
def connection(path: str):
    """Yield a queue database connection and close it after commit or rollback."""
    db = connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path: str):
    with connection(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS execution_queue (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                work_id TEXT NOT NULL,
                input_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'QUEUED','RUNNING','UNCERTAIN','SUCCEEDED','FAILED')),
                lease_token TEXT,
                worker_id TEXT,
                lease_expires_at TEXT,
                attempt INTEGER NOT NULL DEFAULT 0,
                result_json TEXT,
                UNIQUE(work_id)
            );
            CREATE TABLE IF NOT EXISTS execution_journal (
                id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL REFERENCES execution_queue(id),
                event TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)


def record(db, execution_id, event, details):
    db.execute(
        "INSERT INTO execution_journal VALUES (?,?,?,?,?)",
        (str(uuid4()), execution_id, event, json.dumps(details), utcnow().isoformat()),
    )


def enqueue(path: str, *, project_id: str, work_id: str, data: dict):
    if not project_id or not work_id:
        raise QueueConflict("Project and work IDs are required")
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute(
            "SELECT id FROM execution_queue WHERE work_id=?", (work_id,)
        ).fetchone()
        if prior:
            return prior["id"]
        eid = str(uuid4())
        db.execute(
            "INSERT INTO execution_queue(id,project_id,work_id,input_json,status) "
            "VALUES (?,?,?,?,'QUEUED')",
            (eid, project_id, work_id, json.dumps(data)),
        )
        record(db, eid, "queued", {"work_id": work_id})
        return eid


def claim(path: str, *, worker_id: str, ttl_seconds: int = 60, now=None):
    if not worker_id or ttl_seconds < 1:
        raise QueueConflict("Worker identity and positive TTL required")
    at = now or utcnow()
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id,attempt FROM execution_queue WHERE status='QUEUED' "
            "ORDER BY rowid LIMIT 1"
        ).fetchone()
        if not row:
            return None
        token = str(uuid4())
        expires = (at + timedelta(seconds=ttl_seconds)).isoformat()
        db.execute(
            "UPDATE execution_queue SET status='RUNNING',lease_token=?,"
            "worker_id=?,lease_expires_at=?,attempt=attempt+1 WHERE id=?",
            (token, worker_id, expires, row["id"]),
        )
        record(db, row["id"], "claimed", {"worker": worker_id, "attempt": row["attempt"]+1})
        return Lease(row["id"], token, worker_id, expires)


def complete(path: str, lease: Lease, result: dict, *, now=None):
    at = now or utcnow()
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT status,lease_token,lease_expires_at,worker_id "
            "FROM execution_queue WHERE id=?", (lease.execution_id,)
        ).fetchone()
        if (not row or row["status"] != "RUNNING" or
            row["lease_token"] != lease.token or row["worker_id"] != lease.worker_id or
            datetime.fromisoformat(row["lease_expires_at"]) <= at):
            raise QueueConflict("Stale, expired or incorrect lease")
        db.execute(
            "UPDATE execution_queue SET status='SUCCEEDED',result_json=? WHERE id=?",
            (json.dumps(result), lease.execution_id),
        )
        record(db, lease.execution_id, "completed", {"worker": lease.worker_id})


def quarantine_expired(path: str, *, now=None) -> int:
    at = (now or utcnow()).isoformat()
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT id FROM execution_queue WHERE status='RUNNING' "
            "AND lease_expires_at<=?", (at,)
        ).fetchall()
        for row in rows:
            db.execute(
                "UPDATE execution_queue SET status='UNCERTAIN' WHERE id=?", (row["id"],)
            )
            record(db, row["id"], "lease.expired", {"action": "quarantine"})
        return len(rows)


def reconcile(path: str, execution_id: str, *, safe_to_retry: bool):
    """Caller must supply independently verified evidence of safe retry."""
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT status FROM execution_queue WHERE id=?", (execution_id,)
        ).fetchone()
        if not row or row["status"] != "UNCERTAIN":
            raise QueueConflict("Execution is not awaiting reconciliation")
        status = "QUEUED" if safe_to_retry else "FAILED"
        db.execute(
            "UPDATE execution_queue SET status=?,lease_token=NULL,"
            "worker_id=NULL,lease_expires_at=NULL WHERE id=?", (status, execution_id)
        )
        record(db, execution_id, "reconciled", {"status": status})
        return status


def state(path: str, execution_id: str):
    with connection(path) as db:
        row = db.execute("SELECT * FROM execution_queue WHERE id=?", (execution_id,)).fetchone()
        return dict(row) if row else None
