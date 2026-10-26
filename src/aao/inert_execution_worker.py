"""One-shot worker for inert markers and one fixed sandboxed repo check."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from aao.execution_queue import ExecutionConflict

_IDENTITY_FIELDS = ("backend", "provider", "model", "backend_version")


def _identity(run: dict) -> dict:
    """Provider, model and CLI release that produced the run, as the runner recorded them."""
    return {k: run.get(k) for k in _IDENTITY_FIELDS}


CHECK_BUDGET_SECONDS = 150  # sandbox hard timeout (120s + kill) plus commit/push margin


class WorkerAPIError(RuntimeError):
    def __init__(self, status: int | None, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _api_request(path: str, agent_credential: str, *, body: dict,
                 method: str = "POST") -> dict:
    base_url = os.environ.get("AAO_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    parsed = urllib.parse.urlparse(base_url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in local_hosts
    ):
        raise WorkerAPIError(None, "AAO_API_BASE_URL must use HTTPS unless it targets localhost")
    if (parsed.username or parsed.password or not parsed.hostname or parsed.path
            or parsed.query or parsed.fragment):
        raise WorkerAPIError(None, "AAO_API_BASE_URL must be an origin without credentials or path")
    if not path.startswith("/") or path.startswith("//"):
        raise WorkerAPIError(None, "AAO worker API path must be origin-relative")
    request = urllib.request.Request(
        f"{base_url}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "X-Agent-Token": agent_credential}, method=method,
    )
    opener = urllib.request.build_opener(_RejectRedirects)
    try:
        with opener.open(request, timeout=15) as response:
            payload = json.loads(response.read(1_048_577))
    except urllib.error.HTTPError as exc:
        raise WorkerAPIError(exc.code, "AAO worker API rejected the operation") from None
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise WorkerAPIError(None, "AAO worker API is unavailable or returned invalid data") from None
    if not isinstance(payload, dict):
        raise WorkerAPIError(None, "AAO worker API returned an invalid response")
    return payload


def run_one(worker_id: str, agent_credential: str, *, project_id: str, seconds: int = 30) -> dict:
    lease = _api_request(
        "/v1/agent/executions/claim", agent_credential,
        body={"project_id": project_id, "seconds": seconds},
    )
    if lease.get("status") == "IDLE":
        return {"status": "IDLE"}
    if lease.get("worker_id") != worker_id:
        raise WorkerAPIError(None, "AAO claim returned a mismatched worker identity")
    execution_id = lease["execution_id"]
    selected = lease.get("input")
    if isinstance(selected, dict) and selected.get("type") == "aao.agent-patch.v1":
        if set(selected) != {"type", "capability_id", "version", "base_sha"}:
            raise ExecutionConflict("Malformed registered agent capability selection")
        context = _api_request(
            f"/v1/agent/executions/{urllib.parse.quote(execution_id, safe='')}/context",
            agent_credential, body={"lease_token": lease["token"]},
        )
        row = (context.get("title"), context.get("description"),
               context.get("acceptance_criteria"), context.get("author_id"))
        profile = context.get("model_profile")
        backend = profile["backend"] if profile else os.getenv("AAO_AGENT_BACKEND", "codex")
        model = profile.get("model") if profile else None
        source = {"capability_id": selected["capability_id"], "capability_version": selected["version"],
                  "backend_source": "capability" if profile else "environment",
                  "cost_estimate_usd": (profile or {}).get("cost_per_attempt_usd", 0)}
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
                                      backend=backend, model=model,
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
                    try:
                        proposal = _api_request(
                            f"/v1/work/{urllib.parse.quote(str(lease.get('work_id')), safe='')}/patch-proposals",
                            agent_credential,
                            body={"base_sha": selected["base_sha"], "patch": run["patch"]},
                        )
                    except WorkerAPIError as proposal_error:
                        # The create may have committed while its response was lost; recover by
                        # the deterministic key, but preserve the original failure otherwise.
                        try:
                            proposal = _api_request(
                                f"/v1/agent/work/{urllib.parse.quote(str(lease.get('work_id')), safe='')}/patch-proposals/lookup",
                                agent_credential,
                                body={"base_sha": selected["base_sha"],
                                      "patch_sha256": run["patch_sha256"]},
                            )
                        except WorkerAPIError:
                            raise proposal_error
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
            except (ValueError, RuntimeError, WorkerAPIError) as exc:
                from aao.agent_runner import backend_identity
                try:
                    identity = backend_identity(backend, model)
                except ValueError:
                    identity = {"backend": backend}
                result = {"kind": selected["type"], "conclusion": "failure", **identity,
                          "elapsed_seconds": round((datetime.now(UTC) - started_at).total_seconds(), 3),
                          "exit_status": None, "error": str(exc)[:500]}
        result.update(source)
        _api_request(
            f"/v1/agent/executions/{urllib.parse.quote(execution_id, safe='')}/complete",
            agent_credential, body={"lease_token": lease["token"], "result": result},
        )
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
        _api_request(
            f"/v1/agent/executions/{urllib.parse.quote(execution_id, safe='')}/complete",
            agent_credential, body={"lease_token": lease["token"], "result": result},
        )
        status = "FAILED" if result.get("conclusion") == "failure" else "SUCCEEDED"
        return {"status": status, "execution_id": execution_id}

    # No arbitrary command, model prompt, or tool input is accepted.
    marker = {"kind": "aao.inert-worker.v1", "execution_id": execution_id,
              "recorded_at": datetime.now(UTC).isoformat()}
    _api_request(
        f"/v1/agent/executions/{urllib.parse.quote(execution_id, safe='')}/complete",
        agent_credential, body={"lease_token": lease["token"], "result": marker},
    )
    return {"status": "SUCCEEDED", "execution_id": execution_id}
