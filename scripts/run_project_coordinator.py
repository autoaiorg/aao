#!/usr/bin/env python3
"""Assign unassigned work in already CEO-confirmed groups for one project.

This coordinator only invokes AAO's existing read and ``work.assign`` routes.
It does not create/confirm groups, admit work, dispatch executions, retry,
consolidate results, or change grants. One-shot is the default; ``--watch``
repeats the same bounded pass for an externally supervised PM identity.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import urllib.error
import urllib.parse
import urllib.request

from scripts.run_self_development_worker import WorkerError, _read_agent_token

PM_TOKEN_NAME = "aao-pm.token"
DEFAULT_POLL_INTERVAL_SECONDS = 15.0
MAX_POLL_INTERVAL_SECONDS = 300.0


class CoordinatorError(RuntimeError):
    """Safe-to-display coordinator configuration or API error."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _response, _code, _message, _headers, _new_url):
        return None


def api_call(path: str, *, method: str = "GET") -> dict | list:
    """Call the local/HTTPS API with the PM token read from the private runtime dir."""
    base = os.environ.get("AAO_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise CoordinatorError("AAO_API_BASE_URL must use HTTPS unless it targets localhost")
    if parsed.username or parsed.password or not parsed.hostname:
        raise CoordinatorError("AAO_API_BASE_URL must not contain credentials")
    try:
        token = _read_agent_token(PM_TOKEN_NAME)
    except WorkerError as exc:
        raise CoordinatorError(str(exc)) from None
    request = urllib.request.Request(
        f"{base}{path}", headers={"Accept": "application/json", "X-Agent-Token": token},
        method=method,
    )
    try:
        with urllib.request.build_opener(_RejectRedirects).open(request, timeout=30) as response:
            payload = json.loads(response.read(1_000_001))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise CoordinatorError(f"AAO coordinator request failed ({type(exc).__name__})") from None
    finally:
        del token
    if not isinstance(payload, (dict, list)):
        raise CoordinatorError("AAO coordinator response did not match the expected contract")
    return payload


def coordinate_once(project_id: str, _principal_id: str) -> int:
    """Assign unassigned children, relying on the API for all authorization and locking."""
    if not project_id or not _principal_id:
        raise CoordinatorError("project and principal identifiers are required")
    identity = api_call("/v1/principals/me")
    if not isinstance(identity, dict) or identity.get("principal_id") != _principal_id:
        raise CoordinatorError("Authenticated PM identity does not match configured principal")
    project_path = urllib.parse.quote(project_id, safe="")
    groups = api_call(f"/v1/agent/projects/{project_path}/work-groups")
    if not isinstance(groups, list) or any(not isinstance(group, dict) for group in groups):
        raise CoordinatorError("AAO work-group response did not match the expected contract")
    assigned = 0
    for group in groups:
        children = group.get("children")
        if not isinstance(children, list):
            raise CoordinatorError("AAO work-group children did not match the expected contract")
        if group.get("parent_status") in {"VERIFIED", "DONE"}:
            continue
        if not any(
            isinstance(child, dict)
            and child.get("status") == "INBOX"
            and child.get("assigned_principal_id") is None
            for child in children
        ):
            continue
        group_id = group.get("id")
        if not isinstance(group_id, str) or not group_id:
            raise CoordinatorError("AAO work-group identity did not match the expected contract")
        group_path = urllib.parse.quote(group_id, safe="")
        result = api_call(
            f"/v1/agent/projects/{project_path}/work-groups/{group_path}/assign-unassigned",
            method="POST",
        )
        if not isinstance(result, dict):
            raise CoordinatorError("AAO assignment response did not match the expected contract")
        assigned_rows = result.get("assigned")
        if not isinstance(assigned_rows, list):
            raise CoordinatorError("AAO assignment response did not match the expected contract")
        assigned += len(assigned_rows)
    return assigned


def run_watch(
    project_id: str,
    principal_id: str,
    *,
    poll_interval_seconds: float,
    stop_event: threading.Event,
    wait=None,
) -> int:
    """Repeat bounded coordination passes until stopped by the service supervisor."""
    if not project_id or not principal_id:
        raise CoordinatorError("project and principal identifiers are required")
    if not 0 < poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS:
        raise CoordinatorError(
            f"poll interval must be greater than zero and at most {MAX_POLL_INTERVAL_SECONDS:g} seconds"
        )
    wait = wait or stop_event.wait
    while not stop_event.is_set():
        assigned = coordinate_once(project_id, principal_id)
        if assigned:
            print(f"Assigned {assigned} work item(s) in project {project_id}")
        if stop_event.is_set() or wait(poll_interval_seconds):
            break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    args = parser.parse_args()
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
                    args.project_id, args.principal_id,
                    poll_interval_seconds=args.poll_interval_seconds,
                    stop_event=stop_event,
                )
            finally:
                for signum, handler in previous_handlers.items():
                    signal.signal(signum, handler)
        assigned = coordinate_once(args.project_id, args.principal_id)
        print(f"Assigned {assigned} work item(s) in project {args.project_id}")
        return 0
    except (CoordinatorError, OSError, ValueError) as exc:
        print(f"Coordinator did not complete ({type(exc).__name__}); details withheld.", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
