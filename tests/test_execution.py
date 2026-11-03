from datetime import UTC, datetime, timedelta

import pytest


def test_patch_execution_requires_typed_success_and_successful_check():
    from uuid import uuid4

    from aao.execution_queue import result_status

    candidate = "a" * 40
    task = {"type": "aao.agent-patch.v1", "capability_id": "agent",
            "version": "1", "base_sha": "b" * 40}
    limits = {"network": "unshared", "source": "read-only mounted source/tests/config",
              "home_and_secrets": "not mounted; environment allow-listed", "timeout_seconds": 120,
              "memory_bytes": 1_073_741_824, "temporary_filesystem_bytes": 268_435_456}
    good = {
        "kind": "aao.agent-patch.v1", "proposal_id": str(uuid4()),
        "patch_sha256": "c" * 64, "changed_paths": ["src/aao/example.py"],
        "candidate_sha": candidate, "candidate_ref": f"refs/aao/candidates/{candidate}",
        "check": {"kind": "aao.repository-check.v1", "check_id": "core-unit",
                  "extra_tests": [], "candidate_sha": candidate, "conclusion": "success",
                  "exit_code": 0, "duration_ms": 1, "stdout": "", "stderr": "", "limits": limits},
        "conclusion": "success", "exit_status": 0, "elapsed_seconds": 1.0,
    }
    assert result_status(task, good) == "SUCCEEDED"
    assert result_status({"type": "aao.agent-patch.v1", "base_sha": "b" * 40}, good) == "FAILED"
    assert result_status({**task, "base_sha": "not-a-commit"}, good) == "FAILED"
    assert result_status({**task, "version": False}, good) == "FAILED"
    assert result_status({**task, "unexpected": "field"}, good) == "FAILED"
    assert result_status({**task, "capability_id": ""}, good) == "FAILED"
    for bad_check in (
        {**good["check"], "exit_code": False},
        {**good["check"], "duration_ms": True},
        {**good["check"], "limits": {**limits, "timeout_seconds": False}},
        {**good["check"], "limits": {**limits, "unreviewed": "value"}},
    ):
        assert result_status(task, {**good, "check": bad_check}) == "FAILED"
    for bad in (
        {**good, "conclusion": "blocked"},
        {**good, "conclusion": "failure"},
        {**good, "kind": "wrong-kind"},
        {**good, "check": {"conclusion": "failure"}},
        {**good, "candidate_sha": "not-a-commit"},
        {"candidate_sha": "a" * 40},
        {**good, "proposal_id": "x" * 36},
        {**good, "candidate_ref": "refs/heads/main"},
        {**good, "patch_sha256": "bad"},
        {**good, "check": {**good["check"], "candidate_sha": "d" * 40}},
        {**good, "check": {**good["check"], "extra_tests": [None]}},
        {**good, "check": {"conclusion": "success"}},
    ):
        assert result_status(task, bad) == "FAILED"


def test_repository_check_requires_matching_success_result():
    from aao.execution_queue import result_status

    task = {"type": "aao.repository-check.v1", "check_id": "core-unit",
            "capability_id": "checker", "version": "1"}
    limits = {"network": "unshared", "source": "read-only mounted source/tests/config",
              "home_and_secrets": "not mounted; environment allow-listed", "timeout_seconds": 120,
              "memory_bytes": 1_073_741_824, "temporary_filesystem_bytes": 268_435_456}
    good = {"kind": "aao.repository-check.v1", "check_id": "core-unit",
            "capability_id": "checker", "capability_version": "1",
            "candidate_sha": "a" * 40, "conclusion": "success", "exit_code": 0,
            "duration_ms": 1, "extra_tests": [], "stdout": "", "stderr": "", "limits": limits}
    assert result_status(task, good) == "SUCCEEDED"
    assert result_status(task, {"kind": "aao.repository-check.v1", "conclusion": "success"}) == "FAILED"
    assert result_status(task, {**good, "exit_code": 1}) == "FAILED"
    assert result_status(task, {**good, "exit_code": False}) == "FAILED"
    assert result_status(task, {**good, "duration_ms": True}) == "FAILED"
    assert result_status(task, {**good, "limits": {**limits, "network": "shared"}}) == "FAILED"
    assert result_status(task, {"conclusion": "blocked"}) == "FAILED"


def test_inert_execution_marker_compatibility_is_preserved():
    from aao.execution_queue import result_status

    assert result_status({"type": "aao.inert.v1"}, {"kind": "aao.inert-worker.v1"}) == "SUCCEEDED"
    assert result_status({"type": "aao.inert.v1"}, {"conclusion": "failure"}) == "FAILED"
    assert result_status({"type": "aao.future.v1"}, {"conclusion": "success"}) == "FAILED"
    assert result_status("malformed", {"conclusion": "success"}) == "FAILED"

from aao.execution import (
    QueueConflict,
    claim,
    complete,
    enqueue,
    initialize,
    quarantine_expired,
    reconcile,
    state,
)


def test_durable_claim_and_completion(tmp_path):
    path = str(tmp_path / "jobs.db")
    initialize(path)
    work_id = "w1"
    eid = enqueue(path, project_id="p1", work_id=work_id, data={"task": "inert"})
    assert enqueue(path, project_id="p1", work_id=work_id, data={}) == eid
    lease = claim(path, worker_id="worker1")
    assert lease.execution_id == eid
    assert claim(path, worker_id="worker2") is None
    complete(path, lease, {"ok": True})
    assert state(path, eid)["status"] == "SUCCEEDED"
    with pytest.raises(QueueConflict):
        complete(path, lease, {"ok": True})


def test_expiration_is_quarantined_not_retried_automatically(tmp_path):
    path = str(tmp_path / "jobs.db")
    initialize(path)
    base = datetime(2026, 10, 18, tzinfo=UTC)
    eid = enqueue(path, project_id="p1", work_id="w2", data={})
    lease = claim(path, worker_id="worker1", ttl_seconds=10, now=base)
    assert quarantine_expired(path, now=base+timedelta(seconds=11)) == 1
    assert state(path, eid)["status"] == "UNCERTAIN"
    assert claim(path, worker_id="worker2") is None
    with pytest.raises(QueueConflict):
        complete(path, lease, {}, now=base+timedelta(seconds=12))
    assert reconcile(path, eid, safe_to_retry=True) == "QUEUED"
    lease2 = claim(path, worker_id="worker2", now=base+timedelta(seconds=13))
    assert lease2.token != lease.token
    complete(path, lease2, {"ok": True}, now=base+timedelta(seconds=14))


def test_unsafe_work_is_not_retried(tmp_path):
    path = str(tmp_path / "jobs.db")
    initialize(path)
    base = datetime(2026, 10, 18, tzinfo=UTC)
    eid = enqueue(path, project_id="p1", work_id="w3", data={})
    claim(path, worker_id="worker1", ttl_seconds=1, now=base)
    quarantine_expired(path, now=base+timedelta(seconds=2))
    assert reconcile(path, eid, safe_to_retry=False) == "FAILED"
    assert claim(path, worker_id="worker2") is None
