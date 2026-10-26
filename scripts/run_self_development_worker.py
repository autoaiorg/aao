#!/usr/bin/env python3
"""Process already-authorized Self Development queue items.

The agent bearer is read only from its private runtime file, never from argv,
environment, or interactive output. Queue authorization remains enforced by
the PostgreSQL execution queue; only its fixed registered adapters are
available. One-shot behavior is the default; --watch polls the same
agent-scoped queue. Optional --dispatch requests one assigned, pre-evaluated
task through the API's existing admission and staging controls.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AGENT_TOKEN_NAME = "aao-self-development-agent.token"
MAX_LEASE_SECONDS = 1800  # agent run plus candidate checks
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MAX_POLL_INTERVAL_SECONDS = 300.0


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Do not forward an agent credential to a redirect target."""

    def redirect_request(self, _request, _response, _code, _message, _headers, _new_url):
        return None


class WorkerError(RuntimeError):
    pass


def _read_agent_token(name: str = AGENT_TOKEN_NAME) -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise WorkerError("XDG_RUNTIME_DIR is required")
    directory = Path(runtime)
    try:
        directory_info = directory.stat()
        if directory_info.st_uid != os.getuid() or stat.S_IMODE(directory_info.st_mode) & 0o077:
            raise WorkerError("XDG_RUNTIME_DIR must be owned by this user and private")
        path = directory / name
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
    os.environ.setdefault("AAO_ENV", "development")
    if os.environ["AAO_ENV"].lower() == "production":
        # Keep production controls intact: local dotenv and test-only host
        # identity overrides must not become available by downgrading mode.
        os.environ.pop("AAO_ENV_FILE", None)
    else:
        os.environ.setdefault("AAO_ENV_FILE", ".env.local")
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


def dispatch_next(project_id: str, principal_id: str, base_sha: str) -> dict:
    """Ask AAO to dispatch one assigned, already-evaluated item for this identity."""
    if not project_id or not principal_id:
        raise WorkerError("project and principal identifiers are required")
    if len(base_sha) != 40 or any(char not in "0123456789abcdef" for char in base_sha):
        raise WorkerError("base SHA must be a lowercase 40-character commit hash")
    api_base = os.environ.get("AAO_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    parsed = urllib.parse.urlparse(api_base)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts):
        raise WorkerError("AAO_API_BASE_URL must use HTTPS unless it targets localhost")
    if parsed.username or parsed.password or not parsed.hostname:
        raise WorkerError("AAO_API_BASE_URL must not contain credentials")
    token = _read_agent_token()
    request = urllib.request.Request(
        f"{api_base}/v1/agent/dispatch-next",
        data=json.dumps({"project_id": project_id, "principal_id": principal_id,
                         "base_sha": base_sha}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Agent-Token": token},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(_RejectRedirects)
        with opener.open(request, timeout=10) as response:
            payload = json.loads(response.read(65536))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise WorkerError(f"AAO dispatch request failed ({type(exc).__name__})") from None
    finally:
        del token
    if not isinstance(payload, dict) or payload.get("status") not in {"IDLE", "BLOCKED", "QUEUED"}:
        raise WorkerError("AAO dispatch response did not match the expected contract")
    return payload


def run_watch(
    project_id: str,
    principal_id: str,
    *,
    poll_interval_seconds: float,
    stop_event: threading.Event,
    wait=None,
    dispatch: bool = False,
    base_sha: str | None = None,
) -> int:
    """Poll only this agent's already staged execution queue until stopped.

    Optional dispatch stays bound to the assigned agent credential and the
    API rechecks the existing admission/staging controls. The loop then invokes
    the existing one-shot queue worker.
    """
    if not project_id or not principal_id:
        raise WorkerError("project and principal identifiers are required")
    if not 0 < poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS:
        raise WorkerError(
            f"poll interval must be greater than zero and at most {MAX_POLL_INTERVAL_SECONDS:g} seconds"
        )
    wait = wait or stop_event.wait
    while not stop_event.is_set():
        if dispatch:
            if not base_sha:
                raise WorkerError("--base-sha is required with --dispatch")
            dispatched = dispatch_next(project_id, principal_id, base_sha)
            if dispatched.get("status") == "QUEUED":
                print(f"Dispatched work {dispatched.get('work_id')}: {dispatched.get('execution_id')}")
            elif dispatched.get("status") == "BLOCKED":
                print(f"Dispatch blocked for {dispatched.get('work_id')}: {dispatched.get('reason')}", file=sys.stderr)
        result = run(project_id, principal_id)
        status = result.get("status", "UNKNOWN")
        if status not in {"IDLE", "SUCCEEDED"}:
            execution_id = result.get("execution_id")
            if execution_id:
                print(f"Execution {execution_id}: {status}", file=sys.stderr)
            else:
                print(f"Worker stopped after status: {status}", file=sys.stderr)
            return 1
        if status == "SUCCEEDED" and result.get("execution_id"):
            print(f"Execution {result['execution_id']}: {status}")
        if stop_event.is_set():
            break
        if wait(poll_interval_seconds):
            break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--watch", action="store_true",
                        help="poll the assigned agent's already staged execution queue")
    parser.add_argument("--dispatch", action="store_true",
                        help="also dispatch one of this agent's assigned, already-evaluated tasks")
    parser.add_argument("--base-sha",
                        help="explicit repository base SHA required with --dispatch")
    parser.add_argument("--poll-interval-seconds", type=float,
                        default=DEFAULT_POLL_INTERVAL_SECONDS,
                        help="watch-mode idle polling interval (default: 5; maximum: 300)")
    args = parser.parse_args()
    if args.dispatch and not args.base_sha:
        parser.error("--dispatch requires --base-sha")
    if args.base_sha and not args.dispatch:
        parser.error("--base-sha requires --dispatch")
    try:
        if args.watch:
            stop_event = threading.Event()
            previous_handlers = {}

            def request_stop(_signum, _frame):
                stop_event.set()

            try:
                for signum in (signal.SIGTERM, signal.SIGINT):
                    previous_handlers[signum] = signal.getsignal(signum)
                    signal.signal(signum, request_stop)
                return run_watch(
                    args.project_id,
                    args.principal_id,
                    poll_interval_seconds=args.poll_interval_seconds,
                    stop_event=stop_event,
                    dispatch=args.dispatch,
                    base_sha=args.base_sha,
                )
            finally:
                for signum, handler in previous_handlers.items():
                    signal.signal(signum, handler)
        if args.dispatch:
            dispatched = dispatch_next(args.project_id, args.principal_id, args.base_sha)
            if dispatched["status"] == "BLOCKED":
                print(f"Dispatch blocked for {dispatched.get('work_id')}: {dispatched.get('reason')}", file=sys.stderr)
            elif dispatched["status"] == "QUEUED":
                print(f"Dispatched work {dispatched.get('work_id')}: {dispatched.get('execution_id')}")
        result = run(args.project_id, args.principal_id)
    except (OSError, RuntimeError, ValueError) as exc:
        # The worker communicates through the API and does not need a database
        # driver. Keep exception details private because network/configuration
        # errors can contain deployment details.
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
