import pytest

from aao import inert_execution_worker as worker
from aao.execution_queue import ExecutionConflict
from aao.sandboxed_repository_checks import RepositoryCheckError


def _lease(selection):
    return {
        "execution_id": "execution-1", "token": "lease-1", "worker_id": "agent-1",
        "input": selection,
    }


def test_worker_runs_only_registered_fixed_check_and_persists_exact_capability(monkeypatch):
    selection = {
        "type": "aao.repository-check.v1", "check_id": "core-unit",
        "capability_id": "aao.repo-check", "version": "1.0.0",
    }
    monkeypatch.setattr(worker, "claim", lambda *args, **kwargs: _lease(selection))
    monkeypatch.setattr(worker, "state", lambda _: {"status": "RUNNING"})
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/candidate")
    result = {
        "kind": "aao.repository-check.v1", "check_id": "core-unit",
        "candidate_sha": "a" * 40, "conclusion": "success", "exit_code": 0,
    }
    monkeypatch.setattr(
        "aao.sandboxed_repository_checks.run_repository_check",
        lambda repository, check_id: result.copy(),
    )
    completions = []
    monkeypatch.setattr(worker, "complete", lambda *args, **kwargs: completions.append(args))

    outcome = worker.run_one("agent-1", "individual", project_id="project-1")

    assert outcome == {"status": "SUCCEEDED", "execution_id": "execution-1"}
    assert completions[0][3]["capability_id"] == "aao.repo-check"
    assert completions[0][3]["capability_version"] == "1.0.0"
    assert completions[0][3]["candidate_sha"] == "a" * 40


def test_worker_refuses_malformed_capability_selection(monkeypatch):
    monkeypatch.setattr(worker, "claim", lambda *args, **kwargs: _lease({
        "type": "aao.repository-check.v1", "check_id": "core-unit",
        "capability_id": "aao.repo-check", "version": "1.0.0", "command": "evil",
    }))
    monkeypatch.setattr(worker, "state", lambda _: {"status": "RUNNING"})
    with pytest.raises(ExecutionConflict, match="Malformed"):
        worker.run_one("agent-1", "individual", project_id="project-1")


def test_worker_records_check_failure_as_failed_not_success(monkeypatch):
    selection = {
        "type": "aao.repository-check.v1", "check_id": "core-unit",
        "capability_id": "aao.repo-check", "version": "1.0.0",
    }
    monkeypatch.setattr(worker, "claim", lambda *args, **kwargs: _lease(selection))
    monkeypatch.setattr(worker, "state", lambda _: {"status": "RUNNING"})
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/candidate")

    def fail(*_args):
        raise RepositoryCheckError("candidate must be clean")

    monkeypatch.setattr("aao.sandboxed_repository_checks.run_repository_check", fail)
    completions = []
    monkeypatch.setattr(worker, "complete", lambda *args, **kwargs: completions.append(args))

    outcome = worker.run_one("agent-1", "individual", project_id="project-1")

    assert outcome["status"] == "FAILED"
    assert completions[0][3]["conclusion"] == "failure"
    assert "candidate_sha" not in completions[0][3]


def test_agent_worker_reads_task_instructions_and_persists_proposal(monkeypatch):
    from contextlib import contextmanager

    from aao import inert_execution_worker as worker
    selection = {"type": "aao.agent-patch.v1", "capability_id": "agent", "version": "1", "base_sha": "a" * 40}
    monkeypatch.setattr(worker, "claim", lambda *args, **kwargs: _lease(selection))
    monkeypatch.setattr(worker, "state", lambda _: {"status": "RUNNING"})
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/repository")
    monkeypatch.setenv("AAO_AGENT_BACKEND", "fixture")
    captured = {}
    class DB:
        def execute(self, *_args):
            class Q:
                def fetchone(self): return ("from DB", "task desc", ["criterion"], "agent-1")
            return Q()
    @contextmanager
    def tx(): yield DB()
    monkeypatch.setattr("aao.work_management_api.tx", tx)
    def runner(repository, base, instructions, **kwargs):
        captured["instructions"] = instructions
        return {"patch": "patch", "patch_sha256": "b" * 64, "changed_paths": ["src/aao/x.py"],
                "backend": "fixture", "backend_version": "fixture-v1", "elapsed_seconds": .01, "exit_status": 0}
    monkeypatch.setattr("aao.agent_runner.run_agent_patch", runner)
    monkeypatch.setattr("aao.work_management_api.persist_patch_proposal", lambda *args: {"proposal_id": "proposal-1"})
    # The worker authenticates its own credential before proposing (same check as the API).
    monkeypatch.setattr("aao.work_management_api._authenticate_request_principal", lambda token, kind: "agent-1")
    completed = []
    monkeypatch.setattr(worker, "complete", lambda *args, **kwargs: completed.append(args))
    outcome = worker.run_one("agent-1", "credential", project_id="project-1")
    assert outcome["status"] == "SUCCEEDED"
    assert "from DB" in captured["instructions"] and "task desc" in captured["instructions"]
    assert "queue" not in captured["instructions"].lower()
    assert completed[0][3]["proposal_id"] == "proposal-1"


def test_agent_worker_empty_diff_fails_without_proposal(monkeypatch):
    from contextlib import contextmanager

    from aao import inert_execution_worker as worker
    selection = {"type": "aao.agent-patch.v1", "capability_id": "agent", "version": "1", "base_sha": "a" * 40}
    monkeypatch.setattr(worker, "claim", lambda *args, **kwargs: _lease(selection))
    monkeypatch.setattr(worker, "state", lambda _: {"status": "RUNNING"})
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", "/repository")
    monkeypatch.setenv("AAO_AGENT_BACKEND", "fixture")
    class DB:
        def execute(self, *_args):
            class Q:
                def fetchone(self): return ("task", "", [], "agent-1")
            return Q()
    @contextmanager
    def tx(): yield DB()
    monkeypatch.setattr("aao.work_management_api.tx", tx)
    monkeypatch.setattr("aao.agent_runner.run_agent_patch", lambda *a, **kw: {
        "patch": "", "backend": "fixture", "backend_version": "fixture-v1", "elapsed_seconds": .01, "exit_status": 0})
    monkeypatch.setattr("aao.work_management_api.persist_patch_proposal", lambda *a: pytest.fail("proposal must not be created"))
    completed = []
    monkeypatch.setattr(worker, "complete", lambda *args, **kwargs: completed.append(args))
    assert worker.run_one("agent-1", "credential", project_id="project-1")["status"] == "FAILED"
    assert completed[0][3]["conclusion"] == "failure"
