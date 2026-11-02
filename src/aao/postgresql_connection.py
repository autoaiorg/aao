"""PostgreSQL backend connectivity and explicit schema bootstrap.

Not enabled in the active SQLite API. Schema creation is a manual development step.
"""
import os
from contextlib import contextmanager
from pathlib import Path

from aao.environment_settings import load_local_env


def database_url() -> str:
    load_local_env()
    url = os.environ.get("AAO_POSTGRES_URL") or os.environ.get("AAO_DATABASE_URL") or ""
    if not url:
        env_file = Path("/etc/aao/aao-api.env")
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("AAO_POSTGRES_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except OSError:
                pass
    if not url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("AAO_POSTGRES_URL must be an explicit PostgreSQL DSN")
    return url


@contextmanager
def connect_postgres(dsn: str | None = None):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install the postgres optional dependencies") from exc
    with psycopg.connect(dsn or database_url(), autocommit=False) as db:
        yield db


def version():
    with connect_postgres() as db:
        return db.execute("SELECT current_setting('server_version')").fetchone()[0]


def migration_status():
    with connect_postgres() as db:
        row = db.execute(
            "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
