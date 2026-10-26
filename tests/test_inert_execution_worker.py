import pytest

from aao import inert_execution_worker as worker
from aao.execution_queue import ExecutionConflict
from aao.sandboxed_repository_checks import RepositoryCheckError


def _lease(selection):
    return {
        "execution_id": "execution-1", "token": "lease-1", "worker_id": "agent-1",
        "work_id": "work-1", "input": selection,
    }


def _api_stub(monkeypatch, selection, *, context=None, proposals=None):
    calls = []
    lease = _lease(selection)
    responses = proposals if proposals is not None else {}

    def api(path, credential, *, body, method="POST"):
        calls.append((path, credential, body, method))
        if path == "/v1/agent/executions/claim":
            return lease
        if path.endswith("/context"):
            return context or {
                "title": "task from API", "description": "task desc",
                "acceptance_criteria": ["criterion"], "author_id": "agent-1",
                "model_profile": None,
            }
        if path.endswith(("/patch-proposals", "/patch-proposals/lookup")):
            key = (path, body.get("base_sha"), body.get("patch_sha256"))
            response = responses.get(key)
            if isinstance(response, Exception):
                raise response
            if response:
                return response
            return {"proposal_id": "proposal-1"}
        if path.endswith("/complete"):
            return {"execution_id": "execution-1", "status": "COMPLETED"}
        raise AssertionError(f"unexpected API request: {path}")

    monkeypatch.setattr(worker, "_api_request", api)
    return calls


def test_worker_runs_only_registered_fixed_check_and_persists_exact_capability(monkeypatch):
    selection = {
        "type": "aao.repository-check.v1", "check_id": "core-unit",
        "capability_id": "aao.repo-check", "version": "1.0.0",
    }
    calls = _api_stub(monkeypatch, selection)
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/candidate")
    result = {
        "kind": "aao.repository-check.v1", "check_id": "core-unit",
        "candidate_sha": "a" * 40, "conclusion": "success", "exit_code": 0,
    }
    monkeypatch.setattr(
        "aao.sandboxed_repository_checks.run_repository_check",
        lambda repository, check_id: result.copy(),
    )

    outcome = worker.run_one("agent-1", "individual", project_id="project-1")

    assert outcome == {"status": "SUCCEEDED", "execution_id": "execution-1"}
    completion = next(call[2]["result"] for call in calls if call[0].endswith("/complete"))
    assert completion["capability_id"] == "aao.repo-check"
    assert completion["capability_version"] == "1.0.0"
    assert completion["candidate_sha"] == "a" * 40
    assert all(call[1] == "individual" for call in calls)


def test_worker_refuses_malformed_capability_selection(monkeypatch):
    calls = _api_stub(monkeypatch, {
        "type": "aao.repository-check.v1", "check_id": "core-unit",
        "capability_id": "aao.repo-check", "version": "1.0.0", "command": "evil",
    })
    with pytest.raises(ExecutionConflict, match="Malformed"):
        worker.run_one("agent-1", "individual", project_id="project-1")
    assert not any(path.endswith("/complete") for path, *_ in calls)


def test_worker_records_check_failure_as_failed_not_success(monkeypatch):
    selection = {
        "type": "aao.repository-check.v1", "check_id": "core-unit",
        "capability_id": "aao.repo-check", "version": "1.0.0",
    }
    calls = _api_stub(monkeypatch, selection)
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/candidate")

    def fail(*_args):
        raise RepositoryCheckError("candidate must be clean")

    monkeypatch.setattr("aao.sandboxed_repository_checks.run_repository_check", fail)
    outcome = worker.run_one("agent-1", "individual", project_id="project-1")

    assert outcome["status"] == "FAILED"
    completion = next(call[2]["result"] for call in calls if call[0].endswith("/complete"))
    assert completion["conclusion"] == "failure"
    assert "candidate_sha" not in completion


def test_agent_worker_reads_context_and_persists_proposal_via_api(monkeypatch):
    selection = {"type": "aao.agent-patch.v1", "capability_id": "agent", "version": "1",
                 "base_sha": "a" * 40}
    context = {"title": "from API", "description": "task desc",
               "acceptance_criteria": ["criterion"], "author_id": "agent-1",
               "model_profile": None}
    calls = _api_stub(monkeypatch, selection, context=context)
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/repository")
    monkeypatch.setenv("AAO_CANDIDATE_REPOSITORY", "/candidates.git")
    monkeypatch.setenv("AAO_AGENT_BACKEND", "fixture")
    captured = {}

    def runner(repository, base, instructions, **kwargs):
        captured["instructions"] = instructions
        captured.update(kwargs)
        return {"patch": "patch", "patch_sha256": "b" * 64, "changed_paths": ["src/aao/x.py"],
                "candidate_sha": "c" * 40, "candidate_ref": "refs/aao/candidates/" + "c" * 40,
                "check": {"conclusion": "success"}, "backend": "fixture", "provider": "fixture",
                "model": None, "backend_version": "fixture-v1", "elapsed_seconds": .01, "exit_status": 0}

    monkeypatch.setattr("aao.agent_runner.run_agent_patch", runner)
    assert worker.run_one("agent-1", "credential", project_id="project-1", seconds=30)["status"] == "FAILED"
    failed = next(call[2]["result"] for call in calls if call[0].endswith("/complete"))
    assert "lease must exceed" in failed["error"]
    assert (failed["backend"], failed["provider"], failed["backend_version"]) == (
        "fixture", "fixture", "fixture-v1")

    calls.clear()
    outcome = worker.run_one("agent-1", "credential", project_id="project-1", seconds=400)
    assert outcome["status"] == "SUCCEEDED"
    assert captured["candidate_store"] == "/candidates.git" and captured["check_id"] == "core-unit"
    assert captured["timeout"] == 400 - worker.CHECK_BUDGET_SECONDS
    assert "from API" in captured["instructions"] and "task desc" in captured["instructions"]
    assert "queue" not in captured["instructions"].lower()
    completed = next(call[2]["result"] for call in calls if call[0].endswith("/complete"))
    assert completed["proposal_id"] == "proposal-1"
    assert {k: completed[k] for k in ("backend", "provider", "model", "backend_version")} == {
        "backend": "fixture", "provider": "fixture", "model": None, "backend_version": "fixture-v1"}
    assert completed["backend_source"] == "environment"
    assert any(path.endswith("/context") for path, *_ in calls)
    assert any(path == "/v1/work/work-1/patch-proposals" for path, *_ in calls)


def test_agent_worker_empty_diff_fails_without_proposal(monkeypatch):
    selection = {"type": "aao.agent-patch.v1", "capability_id": "agent", "version": "1",
                 "base_sha": "a" * 40}
    calls = _api_stub(monkeypatch, selection)
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/repository")
    monkeypatch.setenv("AAO_AGENT_BACKEND", "fixture")
    monkeypatch.setattr("aao.agent_runner.run_agent_patch", lambda *a, **kw: {
        "patch": "", "backend": "fixture", "backend_version": "fixture-v1",
        "elapsed_seconds": .01, "exit_status": 0})
    assert worker.run_one("agent-1", "credential", project_id="project-1")["status"] == "FAILED"
    completion = next(call[2]["result"] for call in calls if call[0].endswith("/complete"))
    assert completion["conclusion"] == "failure"
    assert not any("patch-proposals" in call[0] for call in calls)


def test_agent_worker_runs_the_backend_and_model_of_the_staged_capability(monkeypatch):
    selection = {"type": "aao.agent-patch.v1", "capability_id": "aao.agent-runner.codex", "version": "1.0.0",
                 "base_sha": "a" * 40}
    profile = {"backend": "codex", "provider": "openai", "model": "gpt-6-luna", "seats": ["patch.tests"]}
    calls = _api_stub(monkeypatch, selection, context={
        "title": "task", "description": "", "acceptance_criteria": [],
        "author_id": "agent-1", "model_profile": profile})
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/repository")
    monkeypatch.setenv("AAO_CANDIDATE_REPOSITORY", "/candidates.git")
    monkeypatch.setenv("AAO_AGENT_BACKEND", "fixture")
    captured = {}

    def runner(repository, base, instructions, **kwargs):
        captured.update(kwargs)
        return {"patch": "", "backend": kwargs["backend"], "provider": "openai", "model": kwargs["model"],
                "backend_version": "codex-cli x", "elapsed_seconds": .01, "exit_status": 0}

    monkeypatch.setattr("aao.agent_runner.run_agent_patch", runner)
    worker.run_one("agent-1", "credential", project_id="project-1", seconds=400)
    assert (captured["backend"], captured["model"]) == ("codex", "gpt-6-luna")
    completion = next(call[2]["result"] for call in calls if call[0].endswith("/complete"))
    assert completion["backend_source"] == "capability" and completion["model"] == "gpt-6-luna"
    assert (completion["capability_id"], completion["capability_version"]) == (
        "aao.agent-runner.codex", "1.0.0")


def test_worker_rejects_mismatched_principal_returned_by_api(monkeypatch):
    lease = _lease({"type": "other"})
    lease["worker_id"] = "other-agent"
    monkeypatch.setattr(worker, "_api_request", lambda *_args, **_kwargs: lease)
    with pytest.raises(worker.WorkerAPIError, match="mismatched"):
        worker.run_one("agent-1", "credential", project_id="project-1")
