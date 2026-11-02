"""SQLite development store. Not a distributed or production database."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


def connect(db_path: str):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


@contextmanager
def connection(db_path: str):
    """Yield a SQLite connection and always close it after the transaction scope."""
    db = connect(db_path)
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(db_path: str):
    with connection(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS mandates (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('DRAFT','CONFIRMED')),
            confirmed_by TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mandate_id TEXT NOT NULL REFERENCES mandates(id),
            state TEXT NOT NULL CHECK(state IN ('ACTIVE','PAUSED','CANCELLED'))
        );
        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id),
            title TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN
                ('INBOX','READY','IN_PROGRESS','IN_REVIEW','VERIFIED','DONE')),
            acceptance_criteria TEXT NOT NULL,
            evidence TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(work_items)")}
        if "author_id" not in columns:
            db.execute("ALTER TABLE work_items ADD COLUMN author_id TEXT NOT NULL DEFAULT ''")
        db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id TEXT PRIMARY KEY,
                work_id TEXT NOT NULL REFERENCES work_items(id),
                reviewer_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('APPROVE','REJECT')),
                evidence TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("CREATE TABLE IF NOT EXISTS project_grants (principal_id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id), capability TEXT NOT NULL, PRIMARY KEY(principal_id,project_id,capability))")



@contextmanager
def transaction(db_path: str):
    db = connect(db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def event(db, subject_id: str, kind: str, details: dict):
    db.execute(
        "INSERT INTO events (id,subject_id,kind,details) VALUES (?,?,?,?)",
        (str(uuid4()), subject_id, kind, json.dumps(details, sort_keys=True)),
    )
