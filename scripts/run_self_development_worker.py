#!/usr/bin/env python3
"""Process at most one already-authorized Self Development queue item.

The agent bearer is read only from its private runtime file, never from argv,
environment, or interactive output. Queue authorization remains enforced by
the PostgreSQL execution queue; only its fixed inert/repository-check adapters
are available.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AGENT_TOKEN_NAME = "aao-self-development-agent.token"
MAX_LEASE_SECONDS = 1800  # agent run plus candidate checks


class WorkerError(RuntimeError):
    pass


def _read_agent_token() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise WorkerError("XDG_RUNTIME_DIR is required")
    directory = Path(runtime)
    try:
        directory_info = directory.stat()
        if directory_info.st_uid != os.getuid() or stat.S_IMODE(directory_info.st_mode) & 0o077:
            raise WorkerError("XDG_RUNTIME_DIR must be owned by this user and private")
        path = directory / AGENT_TOKEN_NAME
        if path.is_symlink():
            raise WorkerError("agent token file must not be a symbolic link")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            os.close(descriptor)
            raise WorkerError("agent token file must be a regular file owned by this user with mode 0600")
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            content = stream.read(4097)
    except OSError:
        raise WorkerError("private agent token file is unavailable") from None
    token = content.removesuffix("\n")
    if (
        not token or len(content) > 4096 or "\n" in token or "\r" in token
        or token != token.strip()
    ):
        raise WorkerError("private agent token file has an invalid format")
    return token


def run(project_id: str, principal_id: str) -> dict:
    if not project_id or not principal_id:
        raise WorkerError("project and principal identifiers are required")
    token = _read_agent_token()
    os.environ["AAO_ENV"] = "development"
    os.environ["AAO_ENV_FILE"] = ".env.local"
    os.environ["AAO_SANDBOX_QUEUE_ENABLED"] = "true"
    os.environ["AAO_SELF_DEV_REPOSITORY"] = str(ROOT)
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    os.environ.setdefault("AAO_CANDIDATE_REPOSITORY", str(data_home / "aao" / "candidates.git"))
    from aao.inert_execution_worker import run_one

    try:
        return run_one(
            principal_id, token, project_id=project_id, seconds=MAX_LEASE_SECONDS,
        )
    finally:
        del token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", required=True)
    args = parser.parse_args()
    try:
        import psycopg
    except ImportError:
        print("Worker did not complete (PostgreSQL dependency unavailable).", file=sys.stderr)
        return 1
    try:
        result = run(args.project_id, args.principal_id)
    except (OSError, RuntimeError, ValueError, psycopg.Error) as exc:
        # Do not print exception text: a driver or configuration exception can
        # include connection details. Type is enough to direct local diagnosis.
        print(f"Worker did not complete ({type(exc).__name__}); details withheld.", file=sys.stderr)
        return 1
    status = result.get("status", "UNKNOWN")
    execution_id = result.get("execution_id")
    if execution_id:
        print(f"Execution {execution_id}: {status}")
    else:
        print(f"No queued execution: {status}")
    print("Agent credential was not displayed.")
    return 0 if status in {"IDLE", "SUCCEEDED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
