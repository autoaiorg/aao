"""AAO local configuration bootstrap and validation.

Only the explicitly selected dotenv file is loaded. Existing environment
variables take precedence. Local dotenv is disabled for production.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, field_validator

ROOT = Path(__file__).resolve().parents[2]
_ALLOWED = {".env.local", ".env.test"}


def load_local_env() -> Path | None:
    mode = os.getenv("AAO_ENV", "development").lower()
    requested = os.getenv("AAO_ENV_FILE", ".env.local")
    if mode not in {"development", "test"}:
        if requested not in (".env.local", "") and os.getenv("AAO_ENV_FILE"):
            raise RuntimeError("Dotenv files are disabled outside development/test")
        return None
    if requested not in _ALLOWED:
        raise RuntimeError("AAO_ENV_FILE must be .env.local or .env.test")
    target = ROOT / requested
    if target.is_file():
        load_dotenv(target, override=False)
        return target
    return None


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    environment: str = "development"
    database_url: str | None = None
    test_database_url: str | None = None
    test_db_disposable: bool = False
    sandbox_queue_enabled: bool = False
    static_dir: str | None = None
    self_dev_repository: str | None = None
    candidate_repository: str | None = None
    ceo_session_allowed_origins: str | None = None
    agent_provider: str = "fixture"
    conversation_provider: str = "dummy"
    conversation_recovery_enabled: bool = False

    @field_validator("environment")
    @classmethod
    def known_environment(cls, value: str) -> str:
        if value not in {"development", "test", "production"}:
            raise ValueError("Unrecognized AAO_ENV")
        return value

    @field_validator("database_url", "test_database_url")
    @classmethod
    def postgres_dsn(cls, value: str | None) -> str | None:
        if value and not value.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgreSQL DSN required")
        return value


def current_settings() -> Settings:
    load_local_env()
    return Settings(
        environment=os.getenv("AAO_ENV", "development"),
        database_url=os.getenv("AAO_POSTGRES_URL") or None,
        test_database_url=os.getenv("AAO_TEST_POSTGRES_URL") or None,
        test_db_disposable=os.getenv("AAO_TEST_DB_DISPOSABLE") == "yes",
        sandbox_queue_enabled=os.getenv("AAO_SANDBOX_QUEUE_ENABLED", "false").lower() == "true",
        static_dir=os.getenv("AAO_STATIC_DIR") or None,
        self_dev_repository=os.getenv("AAO_SELF_DEV_REPOSITORY") or None,
        candidate_repository=os.getenv("AAO_CANDIDATE_REPOSITORY") or None,
        ceo_session_allowed_origins=os.getenv("AAO_CEO_SESSION_ALLOWED_ORIGINS") or None,
        agent_provider=os.getenv("AAO_AGENT_PROVIDER", "fixture"),
        conversation_provider=os.getenv("AAO_CONVERSATION_PROVIDER", "dummy"),
        conversation_recovery_enabled=os.getenv("AAO_CONVERSATION_RECOVERY_ENABLED", "false").lower() == "true",
    )


# Run on import so the existing API modules can keep their current env reads.
load_local_env()
