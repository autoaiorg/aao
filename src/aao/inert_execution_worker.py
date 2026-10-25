"""One-shot worker for inert markers and one fixed sandboxed repo check."""
import os
from datetime import UTC, datetime

from fastapi import HTTPException

from aao.execution_queue import ExecutionConflict, claim, complete, state

_IDENTITY_FIELDS = ("backend", "provider", "model", "backend_version")


def _identity(run: dict) -> dict:
    """Provider, model and CLI release that produced the run, as the runner recorded them."""
    return {k: run.get(k) for k in _IDENTITY_FIELDS}


CHECK_BUDGET_SECONDS = 150  # sandbox hard timeout (120s + kill) plus commit/push margin


def run_one(worker_id: str, agent_credential: str, *, project_id: str, seconds: int = 30) -> dict:
    lease = claim(worker_id, agent_credential=agent_credential, project_id=project_id, seconds=seconds)
    if lease is None:
        return {"status": "IDLE"}
    execution_id = lease["execution_id"]
    info = state(execution_id)
    if not info or info["status"] != "RUNNING":
        return {"status": "UNCERTAIN", "execution_id": execution_id}
    selected = lease.get("input")
    if isinstance(selected, dict) and selected.get("type") == "aao.agent-patch.v1":
        if set(selected) != {"type", "capability_id", "version", "base_sha"}:
            raise ExecutionConflict("Malformed registered agent capability selection")
        from aao.work_management_api import (
            _authenticate_request_principal,
            persist_patch_proposal,
            tx,
        )
        with tx() as db:
            row = db.execute("SELECT w.title,w.description,w.acceptance_criteria,w.author_id FROM work_items w JOIN execution_queue q ON q.work_id=w.id WHERE q.id=%s", (execution_id,)).fetchone()
        if not row or str(row[3]) != worker_id:
            result = {"kind": selected["type"], "conclusion": "failure", "error": "assigned agent mismatch"}
        else:
            started_at = datetime.now(UTC)
            title, description, criteria, _ = row
            instructions = "Task: " + title + "\nDescription: " + (description or "") + "\nAcceptance criteria: " + "; ".join(criteria or [])
            repository = os.getenv("AAO_SELF_DEV_REPOSITORY")
            store = os.getenv("AAO_CANDIDATE_REPOSITORY")
            try:
                if not repository or not store:
                    raise ValueError("repository or candidate store path not configured")
                # The lease covers the agent and the candidate checks; completion after expiry is refused.
                agent_timeout = seconds - CHECK_BUDGET_SECONDS
                if agent_timeout < 1:
                    raise ValueError(f"lease must exceed {CHECK_BUDGET_SECONDS}s to run the agent and its checks")
                from aao.agent_runner import run_agent_patch
                run = run_agent_patch(repository, selected["base_sha"], instructions,
                                      backend=os.getenv("AAO_AGENT_BACKEND", "codex"),
                                      timeout=agent_timeout, patch_file=os.getenv("AAO_AGENT_FIXTURE_PATCH"),
                                      candidate_store=store, author_email=f"{worker_id}@agents.aao.invalid",
                                      commit_message=f"{title}\n\nAAO-Work: {lease.get('work_id')}\n"
                                                     f"AAO-Execution: {execution_id}\n",
                                      check_id="core-unit")
                if not run["patch"]:
                    result = {"kind": selected["type"], "conclusion": "failure", **_identity(run),
                              "elapsed_seconds": run["elapsed_seconds"],
                              "exit_status": run["exit_status"], "error": "empty patch"}
                else:
                    # Same authorization as the API: the proposal is made by the authenticated agent credential,
                    # never by a bare worker id (require_grant re-checks the credential digest and kind).
                    principal = _authenticate_request_principal(agent_credential, "AGENT")
                    if principal != worker_id:
                        raise ValueError("worker credential does not authenticate the claiming agent")
                    try:
                        proposal = persist_patch_proposal(str(lease.get("work_id")), principal, selected["base_sha"], run["patch"])
                    except HTTPException as exc:
                        # A retry that reproduces an earlier attempt's patch reuses that proposal.
                        if exc.status_code != 409 or not str(exc.detail).startswith("Identical patch proposal"):
                            raise
                        with tx() as db:
                            existing = db.execute(
                                "SELECT id FROM patch_proposals WHERE work_id=%s AND base_sha=%s AND patch_sha256=%s",
                                (str(lease.get("work_id")), selected["base_sha"], run["patch_sha256"])).fetchone()
                        if not existing:
                            raise
                        proposal = {"proposal_id": str(existing[0])}
                    tested = run["check"].get("conclusion") == "success"
                    result = {"kind": selected["type"], "proposal_id": proposal["proposal_id"],
                              "patch_sha256": run["patch_sha256"], "changed_paths": run["changed_paths"],
                              "candidate_sha": run["candidate_sha"], "candidate_ref": run["candidate_ref"],
                              "check": run["check"],
                              **_identity(run),
                              "elapsed_seconds": run["elapsed_seconds"], "exit_status": run["exit_status"],
                              "conclusion": "success" if tested else "failure"}
                    if not tested:
                        result["error"] = "candidate checks failed"
            except (ValueError, RuntimeError, HTTPException) as exc:
                from aao.agent_runner import backend_identity
                try:
                    identity = backend_identity(os.getenv("AAO_AGENT_BACKEND", "codex"))
                except ValueError:
                    identity = {"backend": os.getenv("AAO_AGENT_BACKEND", "codex")}
                result = {"kind": selected["type"], "conclusion": "failure", **identity,
                          "elapsed_seconds": round((datetime.now(UTC) - started_at).total_seconds(), 3),
                          "exit_status": None, "error": str(exc)[:500]}
        complete(execution_id, lease["token"], worker_id, result, agent_credential=agent_credential)
        status = "FAILED" if result.get("conclusion") == "failure" else "SUCCEEDED"
        return {"status": status, "execution_id": execution_id}

    if isinstance(selected, dict) and selected.get("type") == "aao.repository-check.v1":
        if set(selected) != {"type", "check_id", "capability_id", "version"}:
            raise ExecutionConflict("Malformed registered capability selection")
        repository = os.getenv("AAO_SELF_DEV_REPOSITORY")
        if not repository:
            result = {
                "kind": "aao.repository-check.v1", "check_id": selected["check_id"],
                "capability_id": selected["capability_id"],
                "capability_version": selected["version"],
                "conclusion": "failure", "error": "repository path not configured",
            }
        else:
            from aao.sandboxed_repository_checks import (
                RepositoryCheckError,
                run_repository_check,
            )

            try:
                result = run_repository_check(repository, selected["check_id"])
                result["capability_id"] = selected["capability_id"]
                result["capability_version"] = selected["version"]
            except RepositoryCheckError as exc:
                # Do not represent a blocked or unsafe launch as a successful check.
                result = {
                    "kind": "aao.repository-check.v1", "check_id": selected["check_id"],
                    "capability_id": selected["capability_id"],
                    "capability_version": selected["version"], "conclusion": "failure",
                    "error": str(exc)[:500],
                }
        complete(execution_id, lease["token"], worker_id, result,
                 agent_credential=agent_credential)
        status = "FAILED" if result.get("conclusion") == "failure" else "SUCCEEDED"
        return {"status": status, "execution_id": execution_id}

    # No arbitrary command, model prompt, or tool input is accepted.
    marker = {"kind": "aao.inert-worker.v1", "execution_id": execution_id,
              "recorded_at": datetime.now(UTC).isoformat()}
    complete(execution_id, lease["token"], worker_id, marker, agent_credential=agent_credential)
    return {"status": "SUCCEEDED", "execution_id": execution_id}
