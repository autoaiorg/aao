"""PostgreSQL integration tests, opt-in for explicitly disposable databases."""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _register_test_worker(worker_id):
    """Give integration workers an explicit host binding before exercising claims."""
    from aao.backup import register_host_worker
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        register_host_worker(db, "integration-test-host", worker_id)


def _registered_evidence(project_id, agent_id, credential):
    from aao.evidence_registry import register_evidence

    return register_evidence(
        project_id, b"AAO inert execution evidence for integration coverage",
        agent_id=agent_id, agent_credential=credential,
        media_type="text/plain",
    )


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_reconciliation_requires_distinct_granted_reviewer(monkeypatch):
    from aao.execution_queue import claim, complete, quarantine_expired, state
    from aao.execution_reconciliation import ReconciliationDenied, reconcile
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "reconcile-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "reconcile-ceo"}
    worker_id = "worker-" + str(uuid4())
    auditor_id = "audit-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        secret = issued.json()["token"]
        _register_test_worker(worker_id)
        worker = {"X-Agent-Token": secret}
        auditor_issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor_id, "kind": "AUDITOR",
        })
        assert auditor_issued.status_code == 201, auditor_issued.text
        auditor_secret = auditor_issued.json()["token"]
        mid = client.post("/v1/mandates", headers=ceo, json={
            "title": "Recovery " + str(uuid4()), "objective": "Development only"
        }).json()["id"]
        client.post(f"/v1/mandates/{mid}/confirm", headers=ceo)
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Recovery project", "mandate_id": mid
        }).json()["id"]
        for principal_id, capability in (
            (worker_id, "work.create"),
            (worker_id, "work.admit"),
            (worker_id, "execution.claim"),
            (worker_id, "effect.propose"),
            (worker_id, "evidence.submit"),
        ):
            client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal_id, "capability": capability
            })
        evidence_ref = _registered_evidence(project, worker_id, secret)
        import psycopg

        from aao.postgresql_connection import connect_postgres

        digest = evidence_ref.removeprefix("sha256:")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"), \
                connect_postgres() as db:
            db.execute(
                "UPDATE evidence_artifacts SET media_type='application/json' "
                "WHERE project_id=%s AND digest=%s", (project, digest),
            )
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"), \
                connect_postgres() as db:
            db.execute(
                "DELETE FROM evidence_artifacts WHERE project_id=%s AND digest=%s",
                (project, digest),
            )
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"), \
                connect_postgres() as db:
            db.execute("TRUNCATE evidence_artifacts")
        wid = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Inert recovery", "author_id": worker_id,
            "acceptance_criteria": ["Recorded"]
        }).json()["id"]
        client.post(f"/v1/work/{wid}/admit", headers=worker)
        eid = client.post(f"/v1/work/{wid}/stage-inert", headers=worker).json()["execution_id"]
        other_wid = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Concurrent proposal", "author_id": worker_id,
            "acceptance_criteria": ["Recorded"]
        }).json()["id"]
        client.post(f"/v1/work/{other_wid}/admit", headers=worker)
        other_eid = client.post(
            f"/v1/work/{other_wid}/stage-inert", headers=worker,
        ).json()["execution_id"]
        race_wid = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Concurrent proposal peer", "author_id": worker_id,
            "acceptance_criteria": ["Recorded"]
        }).json()["id"]
        client.post(f"/v1/work/{race_wid}/admit", headers=worker)
        race_eid = client.post(
            f"/v1/work/{race_wid}/stage-inert", headers=worker,
        ).json()["execution_id"]
    lease = claim(worker_id, agent_credential=secret, project_id=project, seconds=1)
    assert lease["execution_id"] == eid
    other_lease = claim(worker_id, agent_credential=secret, project_id=project)
    assert other_lease["execution_id"] == other_eid
    race_lease = claim(worker_id, agent_credential=secret, project_id=project)
    assert race_lease["execution_id"] == race_eid
    from aao.external_effect_registry import EffectConflict, propose
    from aao.postgresql_connection import connect_postgres

    start = threading.Barrier(2)

    # Both calls must use the same key; generate it outside the worker threads.
    race_key = "cross-execution-race-" + str(uuid4())

    def propose_with_shared_key(execution_id, lease_token):
        start.wait(timeout=5)
        try:
            return propose(
                execution_id=execution_id, worker_id=worker_id,
                lease_token=lease_token, agent_credential=secret,
                idempotency_key=race_key, capability="test.inert",
                request={"kind": "test-only"},
            )
        except EffectConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        raced = [
            pool.submit(propose_with_shared_key, other_eid, other_lease["token"]),
            pool.submit(propose_with_shared_key, race_eid, race_lease["token"]),
        ]
        results = [future.result(timeout=10) for future in raced]
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, EffectConflict) for result in results) == 1

    with connect_postgres() as db:
        db.execute("UPDATE projects SET state='PAUSED' WHERE id=%s", (project,))
        db.execute("UPDATE projects SET state='ACTIVE' WHERE id=%s", (project,))
    with pytest.raises(EffectConflict, match="lease is not active"):
        propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential=secret, idempotency_key="paused-resume-" + str(uuid4()),
            capability="test.inert", request={"kind": "test-only"},
        )
    # Quarantine is global: previous tests may leave other expired leases.
    time.sleep(1.1)
    with pytest.raises(EffectConflict, match="lease is not active"):
        propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential=secret, idempotency_key="expired-" + str(uuid4()),
            capability="test.inert", request={"kind": "test-only"},
        )
    assert quarantine_expired() >= 1
    assert state(eid)["status"] == "UNCERTAIN"
    # Re-running quarantine must not alter this execution again.
    assert state(eid)["attempts"] == 1
    with pytest.raises(ReconciliationDenied):
        reconcile(eid, auditor_credential=auditor_secret, evidence=["operator checked"],
                  disposition="RETRY_CONFIRMED_SAFE")
    with TestClient(app) as client:
        granted = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": auditor_id, "capability": "execution.reconcile",
        })
        assert granted.status_code == 201, granted.text
    from aao.evidence_registry import EvidenceDenied, read_evidence
    inspected = read_evidence(
        project, [evidence_ref], auditor_credential=auditor_secret,
        capability="execution.reconcile",
    )
    assert inspected[0]["content"] == b"AAO inert execution evidence for integration coverage"
    assert inspected[0]["submitted_by"] == worker_id
    with pytest.raises(EvidenceDenied, match="Active auditor credential required"):
        read_evidence(
            project, [evidence_ref], auditor_credential=secret,
            capability="execution.reconcile",
        )
    with pytest.raises(EvidenceDenied, match="Evidence review capability required"):
        read_evidence(
            project, [evidence_ref], auditor_credential=auditor_secret,
            capability="effect.reconcile",
        )
    with pytest.raises(ReconciliationDenied, match="Evidence artifact not found"):
        reconcile(
            eid, auditor_credential=auditor_secret,
            evidence=["sha256:" + "0" * 64], disposition="RETRY_CONFIRMED_SAFE",
        )
    assert state(eid)["status"] == "UNCERTAIN"
    with pytest.raises(ReconciliationDenied):
        reconcile(eid, auditor_credential=secret, evidence=["agent cannot review"],
                  disposition="RETRY_CONFIRMED_SAFE")
    from aao.execution_reconciliation import ReconciliationDenied
    from aao.external_effect_reconciliation import EffectReviewDenied, reject_unexecuted_proposal
    with TestClient(app) as client:
        granted = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": auditor_id, "capability": "effect.reconcile",
        })
        assert granted.status_code == 201, granted.text
    with pytest.raises(EffectConflict, match="lease is not active"):
        propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential=secret, idempotency_key="uncertain-" + str(uuid4()),
            capability="test.inert", request={"kind": "test-only"},
        )
    assert reconcile(
        eid, auditor_credential=auditor_secret, evidence=[evidence_ref],
        disposition="RETRY_CONFIRMED_SAFE",
    ) == "QUEUED"
    lease = claim(worker_id, agent_credential=secret, project_id=project)
    assert lease["execution_id"] == eid
    with pytest.raises(EffectConflict, match="credential required"):
        propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential="wrong", idempotency_key="wrong-auth-" + str(uuid4()),
            capability="test.inert", request={"kind": "test-only"},
        )
    with pytest.raises(EffectConflict, match="does not match"):
        propose(
            execution_id=eid, worker_id="other-worker", lease_token=lease["token"],
            agent_credential=secret, idempotency_key="wrong-worker-" + str(uuid4()),
            capability="test.inert", request={"kind": "test-only"},
        )
    key = "reconcile-" + str(uuid4())
    proposal = propose(
        execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
        agent_credential=secret, idempotency_key=key,
        capability="test.inert", request={"kind": "test-only"},
    )
    again = propose(
        execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
        agent_credential=secret, idempotency_key=key,
        capability="test.inert", request={"kind": "test-only"},
    )
    assert again["id"] == proposal["id"]
    assert again["status"] == "PROPOSED_OR_EXISTING"
    with connect_postgres() as db:
        proposer = db.execute(
            "SELECT details->>'proposed_by' FROM execution_journal "
            "WHERE execution_id=%s AND kind='effect.proposed' ORDER BY id DESC LIMIT 1",
            (eid,),
        ).fetchone()[0]
        assert proposer == worker_id
        db.execute(
            "DELETE FROM project_grants WHERE principal_id=%s AND project_id=%s "
            "AND capability='effect.propose'", (worker_id, project),
        )
    with pytest.raises(EffectConflict, match="proposal grant required"):
        propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential=secret, idempotency_key="not-granted-" + str(uuid4()),
            capability="test.inert", request={"kind": "test-only"},
        )
    with TestClient(app) as client:
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": worker_id, "capability": "effect.propose",
        }).status_code == 201
    with pytest.raises(EffectReviewDenied):
        reject_unexecuted_proposal(
            proposal["id"], auditor_credential=secret, evidence=[evidence_ref]
        )
    for attempt in range(5):
        if attempt == 0:
            replay_key, effect_id = key, proposal["id"]
        else:
            replay_key = "reject-replay-" + str(uuid4())
            candidate = propose(
                execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
                agent_credential=secret, idempotency_key=replay_key,
                capability="test.inert", request={"kind": "test-only"},
            )
            effect_id = candidate["id"]
        def replay_proposal(selected_key):
            try:
                return propose(
                    execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
                    agent_credential=secret, idempotency_key=selected_key,
                    capability="test.inert", request={"kind": "test-only"},
                )
            except EffectConflict as exc:
                return exc

        def reject_proposal(selected_effect_id):
            return reject_unexecuted_proposal(
                selected_effect_id, auditor_credential=auditor_secret,
                evidence=[evidence_ref],
            )

        def wait_until_blocked(query_pattern, blocker_pid, excluded_pid=None):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE query LIKE %s AND wait_event_type='Lock' "
                        "AND %s=ANY(pg_blocking_pids(pid)) "
                        "AND (%s::int IS NULL OR pid != %s::int) LIMIT 1",
                        (query_pattern, blocker_pid, excluded_pid, excluded_pid),
                    ).fetchone()
                    if row:
                        return row[0]
                time.sleep(0.01)
            raise AssertionError(f"query did not wait on expected blocker: {query_pattern}")

        with ThreadPoolExecutor(max_workers=2) as pool:
            with connect_postgres() as blocker:
                blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
                blocker.execute(
                    "SELECT id FROM execution_queue WHERE id=%s FOR UPDATE", (eid,),
                )
                replaying = pool.submit(replay_proposal, replay_key)
                proposal_pid = wait_until_blocked(
                    "SELECT q.status,q.project_id%", blocker_pid,
                )
                rejecting = pool.submit(reject_proposal, effect_id)
                rejection_pid = wait_until_blocked(
                    "%FROM execution_queue%FOR UPDATE OF q,p%", proposal_pid,
                )
                assert proposal_pid != rejection_pid
            # Both real operations were queued on the same execution row. Once
            # released, explicit execution-before-effect lock order serializes them.
            replay_result = replaying.result(timeout=5)
            assert rejecting.result(timeout=5) == "REJECTED"
        if isinstance(replay_result, EffectConflict):
            assert str(replay_result) == "Effect proposal is no longer active"
        else:
            assert replay_result["status"] == "PROPOSED_OR_EXISTING"
        with pytest.raises(EffectConflict, match="no longer active"):
            propose(
                execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
                agent_credential=secret, idempotency_key=replay_key,
                capability="test.inert", request={"kind": "test-only"},
            )

    # Effect rejection uses the same in-transaction grant lock. Exercise both
    # grant-deletion orderings without invoking any external effect.
    def create_effect_proposal(key):
        return propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential=secret, idempotency_key=key,
            capability="test.inert", request={"kind": "grant-race-test"},
        )

    effect = create_effect_proposal("effect-reconcile-first-" + str(uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
        blocker.execute("LOCK TABLE execution_journal IN ACCESS EXCLUSIVE MODE")
        blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
        rejecting = pool.submit(
            reject_unexecuted_proposal, effect["id"],
            auditor_credential=auditor_secret, evidence=[evidence_ref],
        )
        rejecting_pid = wait_until_blocked("INSERT INTO execution_journal%", blocker_pid)
        revoking = pool.submit(
            client.delete,
            f"/v1/projects/{project}/grants/{auditor_id}/effect.reconcile",
            headers=ceo,
        )
        wait_until_blocked("DELETE FROM project_grants%", rejecting_pid)
    assert rejecting.result(timeout=5) == "REJECTED"
    assert revoking.result(timeout=5).status_code == 204

    regrant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
        "principal_id": auditor_id, "capability": "effect.reconcile",
    })
    assert regrant.status_code == 201, regrant.text
    effect = create_effect_proposal("effect-revocation-first-" + str(uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
        blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
        blocker.execute(
            "SELECT project_id FROM project_grants WHERE principal_id=%s "
            "AND project_id=%s AND capability='effect.reconcile' FOR UPDATE",
            (auditor_id, project),
        )
        revoking = pool.submit(
            client.delete,
            f"/v1/projects/{project}/grants/{auditor_id}/effect.reconcile",
            headers=ceo,
        )
        revoker_pid = wait_until_blocked("DELETE FROM project_grants%", blocker_pid)
        rejecting = pool.submit(
            reject_unexecuted_proposal, effect["id"],
            auditor_credential=auditor_secret,
            evidence=[evidence_ref],
        )
        wait_until_blocked("SELECT 1 FROM project_grants%", revoker_pid)
    assert revoking.result(timeout=5).status_code == 204
    with pytest.raises(EffectReviewDenied, match="Independent effect capability missing"):
        rejecting.result(timeout=5)
    with connect_postgres() as db:
        assert db.execute(
            "SELECT status FROM external_effects WHERE id=%s", (effect["id"],),
        ).fetchone()[0] == "PROPOSED"

    def racing_proposal():
        try:
            return propose(
                execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
                agent_credential=secret, idempotency_key="completion-race-" + str(uuid4()),
                capability="test.inert", request={"kind": "completion-race"},
            )
        except EffectConflict as exc:
            return exc

    def racing_completion():
        return complete(
            eid, lease["token"], worker_id, {"inert": True},
            agent_credential=secret,
        )

    with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
        blocker.execute(
            "SELECT id FROM execution_queue WHERE id=%s FOR UPDATE", (eid,),
        )
        proposal_result = pool.submit(racing_proposal)
        deadline = time.monotonic() + 5
        waiting = False
        while time.monotonic() < deadline:
            with connect_postgres() as observer:
                waiting = observer.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE query LIKE 'SELECT q.status,q.project_id%' "
                    "AND wait_event_type='Lock')",
                ).fetchone()[0]
            if waiting:
                break
            time.sleep(0.01)
        assert waiting, "effect proposal did not block on the execution row"
        completion_result = pool.submit(racing_completion)
    raced_proposal = proposal_result.result(timeout=5)
    completion_result.result(timeout=5)
    assert state(eid)["status"] == "SUCCEEDED"
    if isinstance(raced_proposal, EffectConflict):
        assert "lease is not active" in str(raced_proposal)
    else:
        assert raced_proposal["status"] == "PROPOSED"
    with pytest.raises(EffectConflict, match="lease is not active"):
        propose(
            execution_id=eid, worker_id=worker_id, lease_token=lease["token"],
            agent_credential=secret, idempotency_key="after-completion-" + str(uuid4()),
            capability="test.inert", request={"kind": "after-completion"},
        )
    with TestClient(app) as client:
        assert client.post(f"/v1/principals/{worker_id}/revoke", headers=ceo).status_code == 200
    from aao.execution_queue import ExecutionConflict
    with pytest.raises(ExecutionConflict):
        claim(worker_id, agent_credential=secret, project_id=project)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
@pytest.mark.parametrize(
    ("disposition", "expected_state"),
    [("MARK_FAILED", "FAILED"), ("RETRY_CONFIRMED_SAFE", "QUEUED")],
)
def test_reconciliation_serializes_with_auditor_credential_revocation(
    monkeypatch, disposition, expected_state,
):
    from aao.execution_queue import claim, quarantine_expired, state
    from aao.execution_reconciliation import ReconciliationDenied, reconcile
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "reconcile-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "reconcile-revoke-ceo"}
    worker_id = "reconcile-worker-" + str(uuid4())
    auditor_id = "reconcile-auditor-" + str(uuid4())
    with TestClient(app) as client:
        worker_response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        auditor_response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor_id, "kind": "AUDITOR",
        })
        assert worker_response.status_code == auditor_response.status_code == 201
        worker_token = worker_response.json()["token"]
        _register_test_worker(worker_id)
        auditor_token = auditor_response.json()["token"]
        worker = {"X-Agent-Token": worker_token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Reconcile credential revoke " + str(uuid4()),
            "objective": "Serialize reconciliation and auditor revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Reconcile credential revoke", "mandate_id": mandate,
        }).json()["id"]
        for principal, capability in (
            (worker_id, "work.create"), (worker_id, "work.admit"),
            (worker_id, "execution.claim"), (worker_id, "evidence.submit"),
            (auditor_id, "execution.reconcile"),
        ):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": capability,
            })
            assert response.status_code == 201, response.text
        evidence_ref = _registered_evidence(project, worker_id, worker_token)
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Reconcile credential race", "author_id": worker_id,
            "acceptance_criteria": ["inert"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        staged = client.post(f"/v1/work/{work}/stage-inert", headers=worker)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]
        lease = claim(worker_id, agent_credential=worker_token, project_id=project, seconds=1)
        assert lease is not None and lease["execution_id"] == execution_id
        time.sleep(1.05)
        assert quarantine_expired() >= 1
        assert state(execution_id)["status"] == "UNCERTAIN"

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_journal IN ACCESS EXCLUSIVE MODE")
            reconciliation = pool.submit(
                reconcile, execution_id, auditor_credential=auditor_token,
                evidence=[evidence_ref], disposition=disposition,
            )
            deadline = time.monotonic() + 5
            reconciliation_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    reconciliation_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'INSERT INTO execution_journal%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if reconciliation_waiting:
                    break
                time.sleep(0.01)
            assert reconciliation_waiting, "reconciliation did not reach journal write"

            revocation = pool.submit(
                client.post, f"/v1/principals/{auditor_id}/revoke", headers=ceo,
            )
            deadline = time.monotonic() + 5
            revocation_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    revocation_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'UPDATE principal_credentials SET enabled=false%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if revocation_waiting:
                    break
                time.sleep(0.01)
            assert revocation_waiting, "auditor revocation did not wait for reconciliation"

        assert reconciliation.result(timeout=5) == expected_state
        revoked = revocation.result(timeout=5)
        assert revoked.status_code == 200, revoked.text
        assert state(execution_id)["status"] == expected_state
        with pytest.raises(ReconciliationDenied, match="Active auditor credential required"):
            reconcile(
                execution_id, auditor_credential=auditor_token,
                evidence=[evidence_ref], disposition=disposition,
            )


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_execution_reconciliation_serializes_with_grant_revocation(monkeypatch):
    """Whichever transaction locks the grant first determines authorization."""
    from aao.execution_queue import claim, quarantine_expired, state
    from aao.execution_reconciliation import ReconciliationDenied, reconcile
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "reconcile-grant-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "reconcile-grant-revoke-ceo"}
    worker_id = "reconcile-grant-worker-" + str(uuid4())
    auditor_id = "reconcile-grant-auditor-" + str(uuid4())
    with TestClient(app) as client:
        worker_response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        auditor_response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor_id, "kind": "AUDITOR",
        })
        assert worker_response.status_code == auditor_response.status_code == 201
        worker_token = worker_response.json()["token"]
        _register_test_worker(worker_id)
        auditor_token = auditor_response.json()["token"]
        worker = {"X-Agent-Token": worker_token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Reconciliation grant race " + str(uuid4()),
            "objective": "Serialize reconciliation against grant revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Reconciliation grant race", "mandate_id": mandate,
        }).json()["id"]
        for principal, capability in (
            (worker_id, "work.create"), (worker_id, "work.admit"),
            (worker_id, "execution.claim"), (worker_id, "evidence.submit"),
            (auditor_id, "execution.reconcile"),
        ):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": capability,
            })
            assert response.status_code == 201, response.text
        evidence_ref = _registered_evidence(project, worker_id, worker_token)

        def uncertain_execution(label):
            work_id = client.post(f"/v1/projects/{project}/work", headers=worker, json={
                "title": label + " " + str(uuid4()), "author_id": worker_id,
                "acceptance_criteria": ["inert"],
            }).json()["id"]
            assert client.post(f"/v1/work/{work_id}/admit", headers=worker).status_code == 200
            staged = client.post(f"/v1/work/{work_id}/stage-inert", headers=worker)
            assert staged.status_code == 202, staged.text
            execution_id = staged.json()["execution_id"]
            lease = claim(worker_id, agent_credential=worker_token, project_id=project, seconds=1)
            assert lease and lease["execution_id"] == execution_id
            time.sleep(1.05)
            assert quarantine_expired() >= 1
            return execution_id

        def wait_for_blocked_query(pattern, blocker_pid):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity WHERE query LIKE %s "
                        "AND wait_event_type='Lock' "
                        "AND %s=ANY(pg_blocking_pids(pid)) LIMIT 1",
                        (pattern, blocker_pid),
                    ).fetchone()
                    if row:
                        return row[0]
                time.sleep(0.01)
            raise AssertionError(f"query did not wait on expected lock: {pattern}")

        execution_id = uncertain_execution("reconciliation wins grant race")
        # Reconciliation has acquired FOR SHARE on its grant before its journal
        # write. The queued deletion must wait until reconciliation commits.
        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_journal IN ACCESS EXCLUSIVE MODE")
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            reconciliation = pool.submit(
                reconcile, execution_id, auditor_credential=auditor_token,
                evidence=[evidence_ref], disposition="MARK_FAILED",
            )
            reconcile_pid = wait_for_blocked_query("INSERT INTO execution_journal%", blocker_pid)
            revocation = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{auditor_id}/execution.reconcile",
                headers=ceo,
            )
            wait_for_blocked_query("DELETE FROM project_grants%", reconcile_pid)
        assert reconciliation.result(timeout=5) == "FAILED"
        revoked = revocation.result(timeout=5)
        assert revoked.status_code == 204, revoked.text
        assert state(execution_id)["status"] == "FAILED"

        # Reverse the order. Deletion is queued first on the grant row; the
        # reconciliation's FOR SHARE must wait, then deny after deletion wins.
        regrant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": auditor_id, "capability": "execution.reconcile",
        })
        assert regrant.status_code == 201, regrant.text
        execution_id = uncertain_execution("grant revocation wins reconciliation race")
        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            blocker.execute(
                "SELECT project_id FROM project_grants WHERE principal_id=%s "
                "AND project_id=%s AND capability='execution.reconcile' FOR UPDATE",
                (auditor_id, project),
            )
            revocation = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{auditor_id}/execution.reconcile",
                headers=ceo,
            )
            revoker_pid = wait_for_blocked_query("DELETE FROM project_grants%", blocker_pid)
            reconciliation = pool.submit(
                reconcile, execution_id, auditor_credential=auditor_token,
                evidence=[evidence_ref], disposition="MARK_FAILED",
            )
            wait_for_blocked_query("SELECT 1 FROM project_grants%", revoker_pid)
        revoked = revocation.result(timeout=5)
        assert revoked.status_code == 204, revoked.text
        with pytest.raises(ReconciliationDenied, match="Reconciliation capability required"):
            reconciliation.result(timeout=5)
        assert state(execution_id)["status"] == "UNCERTAIN"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_effect_proposal_serializes_with_agent_credential_revocation(monkeypatch):
    """A proposal holding its credential lock commits before revocation."""
    from aao.execution_queue import claim
    from aao.external_effect_registry import EffectConflict, propose
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "proposal-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "proposal-revoke-ceo"}
    worker_id = "proposal-worker-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        credential = issued.json()["token"]
        _register_test_worker(worker_id)
        worker = {"X-Agent-Token": credential}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Proposal revoke " + str(uuid4()),
            "objective": "Serialize effect proposal and credential revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Proposal revoke", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim", "effect.propose"):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": worker_id, "capability": capability,
            })
            assert response.status_code == 201, response.text
        work_id = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Proposal revoke", "author_id": worker_id,
            "acceptance_criteria": ["proposal recorded before revocation"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work_id}/admit", headers=worker).status_code == 200
        execution_id = client.post(
            f"/v1/work/{work_id}/stage-inert", headers=worker,
        ).json()["execution_id"]
        lease = claim(worker_id, agent_credential=credential, project_id=project)
        assert lease and lease["execution_id"] == execution_id

        def make_proposal():
            return propose(
                execution_id=execution_id, worker_id=worker_id,
                lease_token=lease["token"], agent_credential=credential,
                idempotency_key="revoke-race-" + str(uuid4()),
                capability="test.inert", request={"kind": "test-only"},
            )

        def wait_for_blocked_query(pattern, blocker_pid):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity WHERE query LIKE %s "
                        "AND wait_event_type='Lock' "
                        "AND %s=ANY(pg_blocking_pids(pid)) LIMIT 1",
                        (pattern, blocker_pid),
                    ).fetchone()
                    if row:
                        return row[0]
                time.sleep(0.01)
            raise AssertionError(f"query did not wait on expected lock: {pattern}")

        # The proposal reaches its journal write only after it has checked and
        # locked the effect.propose grant. Hold that write so grant revocation
        # must wait for the proposal transaction to commit.
        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_journal IN ACCESS EXCLUSIVE MODE")
            proposal_future = pool.submit(make_proposal)
            proposal_pid = wait_for_blocked_query(
                "INSERT INTO execution_journal%", blocker.execute(
                    "SELECT pg_backend_pid()",
                ).fetchone()[0],
            )
            revoke_grant_future = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{worker_id}/effect.propose",
                headers=ceo,
            )
            wait_for_blocked_query(
                "DELETE FROM project_grants%", proposal_pid,
            )
        proposal = proposal_future.result(timeout=5)
        assert proposal["status"] == "PROPOSED"
        revoked_grant = revoke_grant_future.result(timeout=5)
        assert revoked_grant.status_code == 204, revoked_grant.text
        with pytest.raises(EffectConflict, match="proposal grant required"):
            make_proposal()
        regrant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": worker_id, "capability": "effect.propose",
        })
        assert regrant.status_code == 201, regrant.text

        # Reverse the order: a queued grant deletion obtains the row before a
        # competing proposal's FOR SHARE check, so the proposal must fail.
        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            blocker.execute(
                "SELECT project_id FROM project_grants WHERE principal_id=%s "
                "AND project_id=%s AND capability='effect.propose' FOR UPDATE",
                (worker_id, project),
            )
            revoke_grant_future = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{worker_id}/effect.propose",
                headers=ceo,
            )
            revoker_pid = wait_for_blocked_query(
                "DELETE FROM project_grants%", blocker_pid,
            )
            proposal_future = pool.submit(make_proposal)
            wait_for_blocked_query(
                "SELECT 1 FROM project_grants%", revoker_pid,
            )
        assert revoke_grant_future.result(timeout=5).status_code == 204
        with pytest.raises(EffectConflict, match="proposal grant required"):
            proposal_future.result(timeout=5)
        regrant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": worker_id, "capability": "effect.propose",
        })
        assert regrant.status_code == 201, regrant.text

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            blocker.execute(
                "SELECT id FROM execution_queue WHERE id=%s FOR UPDATE", (execution_id,),
            )
            proposal_future = pool.submit(make_proposal)
            proposal_pid = wait_for_blocked_query(
                "SELECT q.status,q.project_id%", blocker_pid,
            )
            revoke_future = pool.submit(
                client.post, f"/v1/principals/{worker_id}/revoke", headers=ceo,
            )
            wait_for_blocked_query(
                "UPDATE principal_credentials SET enabled=false%", proposal_pid,
            )
        proposal = proposal_future.result(timeout=5)
        assert proposal["status"] == "PROPOSED"
        revoked = revoke_future.result(timeout=5)
        assert revoked.status_code == 200, revoked.text
        with pytest.raises(EffectConflict, match="credential required"):
            make_proposal()

        # Exercise the inverse credential ordering with an independent AGENT:
        # revocation queues first, then proposal waits and is denied.
        second_worker_id = "proposal-worker-" + str(uuid4())
        second_issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": second_worker_id, "kind": "AGENT",
        })
        assert second_issued.status_code == 201, second_issued.text
        second_credential = second_issued.json()["token"]
        _register_test_worker(second_worker_id)
        second_worker = {"X-Agent-Token": second_credential}
        for capability in ("work.create", "work.admit", "execution.claim", "effect.propose"):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": second_worker_id, "capability": capability,
            })
            assert response.status_code == 201, response.text
        second_work = client.post(f"/v1/projects/{project}/work", headers=second_worker, json={
            "title": "Reverse credential race", "author_id": second_worker_id,
            "acceptance_criteria": ["revocation wins before proposal"],
        }).json()["id"]
        assert client.post(
            f"/v1/work/{second_work}/admit", headers=second_worker,
        ).status_code == 200
        second_execution = client.post(
            f"/v1/work/{second_work}/stage-inert", headers=second_worker,
        ).json()["execution_id"]
        second_lease = claim(
            second_worker_id, agent_credential=second_credential, project_id=project,
        )
        assert second_lease and second_lease["execution_id"] == second_execution

        def make_second_proposal():
            return propose(
                execution_id=second_execution, worker_id=second_worker_id,
                lease_token=second_lease["token"],
                agent_credential=second_credential,
                idempotency_key="reverse-credential-" + str(uuid4()),
                capability="test.inert", request={"kind": "test-only"},
            )

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            blocker.execute(
                "SELECT principal_id FROM principal_credentials WHERE principal_id=%s "
                "FOR UPDATE", (second_worker_id,),
            )
            revoke_future = pool.submit(
                client.post, f"/v1/principals/{second_worker_id}/revoke", headers=ceo,
            )
            revoker_pid = wait_for_blocked_query(
                "UPDATE principal_credentials SET enabled=false%", blocker_pid,
            )
            proposal_future = pool.submit(make_second_proposal)
            wait_for_blocked_query(
                "SELECT principal_id FROM principal_credentials%", revoker_pid,
            )
        assert revoke_future.result(timeout=5).status_code == 200
        with pytest.raises(EffectConflict, match="credential required"):
            proposal_future.result(timeout=5)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_evidence_read_denied_when_grant_revocation_wins_race(monkeypatch):
    """An evidence read queued behind grant revocation must observe the revoke."""
    from aao.evidence_registry import EvidenceDenied, read_evidence, register_evidence
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "evidence-read-race-ceo")
    ceo = {"X-CEO-Token": "evidence-read-race-ceo"}

    with TestClient(app) as client:
        agent_id = "evidence-agent-" + str(uuid4())
        auditor_id = "evidence-auditor-" + str(uuid4())
        agent_issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        })
        auditor_issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor_id, "kind": "AUDITOR",
        })
        assert agent_issued.status_code == auditor_issued.status_code == 201
        agent_token = agent_issued.json()["token"]
        auditor_token = auditor_issued.json()["token"]

        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Evidence read race " + str(uuid4()),
            "objective": "Serialize evidence reads with reviewer grant revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Evidence read race", "mandate_id": mandate,
        }).json()["id"]
        for principal_id, capability in (
            (agent_id, "evidence.submit"),
            (auditor_id, "execution.reconcile"),
        ):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal_id, "capability": capability,
            })
            assert response.status_code == 201, response.text

        evidence = register_evidence(
            project, b"sensitive review artifact", agent_id=agent_id,
            agent_credential=agent_token, media_type="text/plain",
        )

        def wait_for_blocked_query(pattern, blocker_pid):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity WHERE query LIKE %s "
                        "AND wait_event_type='Lock' "
                        "AND %s=ANY(pg_blocking_pids(pid)) LIMIT 1",
                        (pattern, blocker_pid),
                    ).fetchone()
                    if row:
                        return row[0]
                time.sleep(0.01)
            raise AssertionError(f"query did not wait on expected lock: {pattern}")

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            blocker.execute(
                "SELECT project_id FROM project_grants WHERE principal_id=%s "
                "AND project_id=%s AND capability='execution.reconcile' FOR UPDATE",
                (auditor_id, project),
            )
            revocation = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{auditor_id}/execution.reconcile",
                headers=ceo,
            )
            revoker_pid = wait_for_blocked_query("DELETE FROM project_grants%", blocker_pid)
            read = pool.submit(
                read_evidence, project, [evidence], auditor_credential=auditor_token,
                capability="execution.reconcile",
            )
            wait_for_blocked_query("SELECT 1 FROM project_grants%", revoker_pid)

        revoked = revocation.result(timeout=5)
        assert revoked.status_code == 204, revoked.text
        with pytest.raises(EvidenceDenied, match="Evidence review capability required"):
            read.result(timeout=5)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_evidence_registration_denied_when_grant_revocation_wins_race(monkeypatch):
    """An evidence write queued behind grant revocation must leave no record."""
    import hashlib

    from aao.evidence_registry import EvidenceDenied, register_evidence
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "evidence-submit-race-ceo")
    ceo = {"X-CEO-Token": "evidence-submit-race-ceo"}
    content = b"evidence submitted after grant revocation"
    digest = hashlib.sha256(content).hexdigest()

    with TestClient(app) as client:
        agent_id = "evidence-submit-agent-" + str(uuid4())
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        agent_token = issued.json()["token"]
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Evidence submit race " + str(uuid4()),
            "objective": "Serialize evidence submission with grant revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Evidence submit race", "mandate_id": mandate,
        }).json()["id"]
        grant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": agent_id, "capability": "evidence.submit",
        })
        assert grant.status_code == 201, grant.text

        def wait_for_blocked_query(pattern, blocker_pid):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity WHERE query LIKE %s "
                        "AND wait_event_type='Lock' "
                        "AND %s=ANY(pg_blocking_pids(pid)) LIMIT 1",
                        (pattern, blocker_pid),
                    ).fetchone()
                    if row:
                        return row[0]
                time.sleep(0.01)
            raise AssertionError(f"query did not wait on expected lock: {pattern}")

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
            blocker.execute(
                "SELECT principal_id FROM project_grants WHERE principal_id=%s "
                "AND project_id=%s AND capability='evidence.submit' FOR UPDATE",
                (agent_id, project),
            )
            revocation = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{agent_id}/evidence.submit",
                headers=ceo,
            )
            revoker_pid = wait_for_blocked_query("DELETE FROM project_grants%", blocker_pid)
            submission = pool.submit(
                register_evidence, project, content,
                agent_id=agent_id, agent_credential=agent_token,
                media_type="text/plain",
            )
            wait_for_blocked_query("SELECT 1 FROM project_grants%", revoker_pid)

        revoked = revocation.result(timeout=5)
        assert revoked.status_code == 204, revoked.text
        with pytest.raises(EvidenceDenied, match="Evidence submission grant required"):
            submission.result(timeout=5)
        with connect_postgres() as db:
            artifact = db.execute(
                "SELECT 1 FROM evidence_artifacts WHERE project_id=%s AND digest=%s",
                (project, digest),
            ).fetchone()
            registration_event = db.execute(
                "SELECT 1 FROM events WHERE subject_id=%s "
                "AND kind='evidence.registered' AND details->>'digest'=%s",
                (project, f"sha256:{digest}"),
            ).fetchone()
        assert artifact is None
        assert registration_event is None
