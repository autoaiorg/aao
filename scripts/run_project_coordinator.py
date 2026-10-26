#!/usr/bin/env python3
"""Assign unassigned work in already CEO-confirmed groups for one project.

This coordinator only invokes AAO's existing read, ``work.assign`` and
``work.coordinate`` routes. It does not create/confirm groups, admit work,
dispatch executions, retry or change grants. Factual consolidation is
opt-in via ``--auto-consolidate``. One-shot is the default; ``--watch``
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
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from scripts.run_self_development_worker import WorkerError, _read_agent_token

PM_TOKEN_NAME = "aao-pm.token"
DEFAULT_POLL_INTERVAL_SECONDS = 15.0
MAX_POLL_INTERVAL_SECONDS = 300.0


class CoordinatorError(RuntimeError):
    """Safe-to-display coordinator configuration or API error."""


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _response, _code, _message, _headers, _new_url):
        return None


@dataclass(frozen=True)
class CoordinatorPassResult:
    assigned: int = 0
    consolidated: int = 0


def api_call(path: str, *, method: str = "GET", body: dict | None = None) -> dict | list:
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
    headers = {"Accept": "application/json", "X-Agent-Token": token}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
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


def _consolidation_summary(group: dict) -> str:
    """Build a factual index, not a semantic summary or independent review."""
    rows = []
    for child in group["children"]:
        if not isinstance(child, dict) or not isinstance(child.get("work_id"), str):
            raise CoordinatorError("AAO work-group child identity did not match the expected contract")
        executions = _project_records(
            child.get("executions", []),
            {"id", "status", "worker_id", "result_sha256"},
            "execution",
        )
        reviews = _project_records(
            child.get("reviews", []),
            {"id", "decision", "candidate_sha"},
            "review",
        )
        rows.append({
            "work_id": child["work_id"],
            "status": child.get("status"),
            "assigned_principal_id": child.get("assigned_principal_id"),
            "executions": executions,
            "reviews": reviews,
        })
    evidence_index = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    summary = (
        "Consolidación descriptiva automática; no contiene inferencia semántica ni verificación independiente. "
        f"El grupo persistido {group['id']} tiene {len(rows)} tareas hijas en estado DONE. "
        f"Snapshot fuente SHA-256: {group['source_sha256']}. "
        f"Índice de tareas, ejecuciones y revisiones persistidas: {evidence_index}"
    )
    if len(summary) > 20_000:
        raise CoordinatorError("Persisted group evidence is too large for bounded PM consolidation")
    return summary


def _project_records(records: object, allowed_fields: set[str], label: str) -> list[dict]:
    """Keep only stable identifiers/status hashes; never copy evidence or result bodies."""
    if not isinstance(records, list):
        raise CoordinatorError(f"AAO work-group {label} records did not match the expected contract")
    projected = []
    for record in records:
        if not isinstance(record, dict):
            raise CoordinatorError(f"AAO work-group {label} record did not match the expected contract")
        selected = {}
        for field in sorted(allowed_fields):
            value = record.get(field)
            if value is not None and not isinstance(value, str):
                raise CoordinatorError(f"AAO work-group {label} record did not match the expected contract")
            selected[field] = value
        projected.append(selected)
    return projected


def coordinate_once(
    project_id: str, _principal_id: str, *, auto_consolidate: bool = False,
) -> CoordinatorPassResult:
    """Assign work and, only when opted in, factually consolidate completed groups."""
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
    consolidated = 0
    for group in groups:
        children = group.get("children")
        if not isinstance(children, list):
            raise CoordinatorError("AAO work-group children did not match the expected contract")
        if group.get("parent_status") in {"VERIFIED", "DONE"}:
            continue
        if any(
            isinstance(child, dict)
            and child.get("status") == "INBOX"
            and child.get("assigned_principal_id") is None
            for child in children
        ):
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
            continue
        if not auto_consolidate or group.get("consolidation") is not None:
            continue
        if group.get("consolidation_ready") is not True or not children or any(
            not isinstance(child, dict) or child.get("status") != "DONE" for child in children
        ):
            continue
        group_id = group.get("id")
        if not isinstance(group_id, str) or not group_id:
            raise CoordinatorError("AAO work-group identity did not match the expected contract")
        group_path = urllib.parse.quote(group_id, safe="")
        source_sha256 = group.get("source_sha256")
        if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in source_sha256
        ):
            raise CoordinatorError("AAO work-group source digest did not match the expected contract")
        summary = _consolidation_summary(group)
        idempotency_key = str(uuid5(
            NAMESPACE_URL,
            f"aao:pm-consolidation:{project_id}:{group_id}:{source_sha256}",
        ))
        result = api_call(
            f"/v1/agent/projects/{project_path}/work-groups/{group_path}/consolidation",
            method="POST", body={
                "idempotency_key": idempotency_key,
                "expected_source_sha256": source_sha256,
                "summary": summary,
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("created"), bool):
            raise CoordinatorError("AAO consolidation response did not match the expected contract")
        consolidated += int(result["created"])
    return CoordinatorPassResult(assigned=assigned, consolidated=consolidated)


def run_watch(
    project_id: str,
    principal_id: str,
    *,
    poll_interval_seconds: float,
    stop_event: threading.Event,
    auto_consolidate: bool = False,
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
        result = coordinate_once(project_id, principal_id, auto_consolidate=auto_consolidate)
        if result.assigned or result.consolidated:
            print(
                f"Assigned {result.assigned} work item(s) and recorded {result.consolidated} "
                f"factual consolidation(s) in project {project_id}"
            )
        if stop_event.is_set() or wait(poll_interval_seconds):
            break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument(
        "--auto-consolidate", action="store_true",
        help="persist a factual, non-semantic summary when every child is DONE; default is off",
    )
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
                    auto_consolidate=args.auto_consolidate,
                )
            finally:
                for signum, handler in previous_handlers.items():
                    signal.signal(signum, handler)
        result = coordinate_once(
            args.project_id, args.principal_id, auto_consolidate=args.auto_consolidate,
        )
        print(
            f"Assigned {result.assigned} work item(s) and recorded {result.consolidated} "
            f"factual consolidation(s) in project {args.project_id}"
        )
        return 0
    except (CoordinatorError, OSError, ValueError) as exc:
        print(f"Coordinator did not complete ({type(exc).__name__}); details withheld.", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
