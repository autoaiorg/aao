"""PostgreSQL integration tests, opt-in for explicitly disposable databases."""
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_ceo_project_suspension_transitions_are_audited_and_fence_generation(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "test-ceo")
    ceo = {"X-CEO-Token": "test-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Suspension " + str(uuid4()), "objective": "Test control",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Suspension project", "mandate_id": mandate,
        }).json()["id"]
        endpoint = f"/v1/projects/{project}/state"
        assert client.post(endpoint, json={"action": "pause"}).status_code == 403
        paused = client.post(endpoint, headers=ceo, json={"action": "pause"})
        assert paused.status_code == 200, paused.text
        assert paused.json()["state"] == "PAUSED"
        resumed = client.post(endpoint, headers=ceo, json={"action": "resume"})
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["state"] == "ACTIVE"
        cancelled = client.post(endpoint, headers=ceo, json={"action": "cancel"})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "CANCELLED"
        assert client.post(endpoint, headers=ceo, json={"action": "resume"}).status_code == 409

    with connect_postgres() as db:
        generation = db.execute(
            "SELECT state_generation FROM projects WHERE id=%s", (project,),
        ).fetchone()[0]
        events = db.execute(
            "SELECT count(*) FROM events WHERE subject_id=%s AND kind='project.state_changed'",
            (project,),
        ).fetchone()[0]
    assert generation == 3
    assert events == 3


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_postgres_inert_staging_is_default_off_and_idempotent(monkeypatch):
    from aao.execution_queue import claim, state
    from aao.work_management_api import app
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "test-ceo")
    monkeypatch.delenv("AAO_SANDBOX_QUEUE_ENABLED", raising=False)
    ceo = {"X-CEO-Token": "test-ceo"}
    with TestClient(app) as client:
        worker_id = "agent-" + str(uuid4())
        issued = client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": worker_id, "kind": "AGENT"})
        assert issued.status_code == 201, issued.text
        worker = {"X-Agent-Token": issued.json()["token"]}
        mid = client.post("/v1/mandates", headers=ceo, json={
            "title": "Queue " + str(uuid4()), "objective": "Inert test"
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mid}/confirm", headers=ceo).status_code == 200
        pid = client.post("/v1/projects", headers=ceo, json={
            "name": "Queue project", "mandate_id": mid
        }).json()["id"]
        for capability in ("work.create", "work.admit"):
            assert client.post(f"/v1/projects/{pid}/grants", headers=ceo, json={
                "principal_id": worker_id, "capability": capability
            }).status_code == 201
        wid = client.post(f"/v1/projects/{pid}/work", headers=worker, json={
            "title": "Inert", "author_id": worker_id,
            "acceptance_criteria": ["queued"]
        }).json()["id"]
        assert client.post(f"/v1/work/{wid}/stage-inert", headers=worker).status_code == 503
        assert client.post(f"/v1/work/{wid}/admit", headers=worker).status_code == 200
        monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
        denied = client.post(f"/v1/work/{wid}/stage-inert", headers=worker)
        assert denied.status_code == 403, denied.text
        assert client.post(f"/v1/projects/{pid}/grants", headers=ceo, json={
            "principal_id": worker_id, "capability": "execution.claim",
        }).status_code == 201
        first = client.post(f"/v1/work/{wid}/stage-inert", headers=worker)
        assert first.status_code == 202, first.text
        again = client.post(f"/v1/work/{wid}/stage-inert", headers=worker)
        assert again.status_code == 202, again.text
        assert first.json()["execution_id"] == again.json()["execution_id"]

        execution_id = first.json()["execution_id"]
        token = worker["X-Agent-Token"]

    lease = claim(worker_id, agent_credential=token, project_id=pid)
    assert lease["execution_id"] == execution_id
    before_replay = state(execution_id)
    assert before_replay["status"] == "RUNNING"
    assert before_replay["attempts"] == 1
    with TestClient(app) as reconnected_client:
        replay = reconnected_client.post(f"/v1/work/{wid}/stage-inert", headers=worker)
    assert replay.status_code == 202, replay.text
    assert replay.json() == {"execution_id": execution_id, "status": "RUNNING"}
    after_replay = state(execution_id)
    assert after_replay["attempts"] == before_replay["attempts"]
    assert after_replay["status"] == "RUNNING"
    from aao.postgresql_connection import connect_postgres
    with connect_postgres() as db:
        rows = db.execute(
            "SELECT count(*) FROM execution_queue WHERE work_id=%s", (wid,),
        ).fetchone()[0]
        journal_entries = db.execute(
            "SELECT count(*) FROM execution_journal WHERE execution_id=%s "
            "AND kind='claimed'", (execution_id,),
        ).fetchone()[0]
    assert rows == 1
    assert journal_entries == 1


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_worker_claim_complete_respects_identity_and_project_state(monkeypatch):
    from aao.execution_queue import (
        ExecutionConflict,
        claim,
        complete,
        quarantine_expired,
        state,
    )
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "integration-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "integration-ceo"}
    worker_id = "worker-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        worker = {"X-Agent-Token": token}
        mid = client.post("/v1/mandates", headers=ceo, json={
            "title": "Lease " + str(uuid4()), "objective": "Isolated worker tests"
        }).json()["id"]
        client.post(f"/v1/mandates/{mid}/confirm", headers=ceo)
        project_id = client.post("/v1/projects", headers=ceo, json={
            "name": "Lease project", "mandate_id": mid
        }).json()["id"]
        for cap in ("work.create", "work.admit"):
            client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
                "principal_id": worker_id, "capability": cap
            })
        assert client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
            "principal_id": worker_id, "capability": "execution.claim",
        }).status_code == 201
        wid = client.post(f"/v1/projects/{project_id}/work", headers=worker, json={
            "title": "Lease test", "author_id": worker_id,
            "acceptance_criteria": ["inert completion"]
        }).json()["id"]
        client.post(f"/v1/work/{wid}/admit", headers=worker)
        eid = client.post(f"/v1/work/{wid}/stage-inert", headers=worker).json()["execution_id"]
        with pytest.raises(ExecutionConflict):
            claim(worker_id, agent_credential="wrong", project_id=project_id)
        lease = claim(worker_id, agent_credential=token, project_id=project_id)
        assert lease is not None and lease["execution_id"] == eid
        with pytest.raises(ExecutionConflict):
            complete(eid, lease["token"], worker_id, {"ok": True}, agent_credential="wrong")
        assert state(eid)["status"] == "RUNNING"

    # Exercise the CEO API transition against this exact live lease, not only
    # the state-generation trigger through direct SQL in the race below.
    with TestClient(app) as client:
        paused = client.post(
            f"/v1/projects/{project_id}/state", headers=ceo,
            json={"action": "pause"},
        )
        assert paused.status_code == 200, paused.text
        with pytest.raises(ExecutionConflict, match="Project is not active"):
            complete(eid, lease["token"], worker_id, {"ok": True}, agent_credential=token)
        resumed = client.post(
            f"/v1/projects/{project_id}/state", headers=ceo,
            json={"action": "resume"},
        )
        assert resumed.status_code == 200, resumed.text
        with pytest.raises(ExecutionConflict):
            complete(eid, lease["token"], worker_id, {"ok": True}, agent_credential=token)

        with ThreadPoolExecutor(max_workers=1) as pool, connect_postgres() as blocker:
            blocker.execute("SELECT id FROM projects WHERE id=%s FOR UPDATE", (project_id,))
            paused_completion = pool.submit(
                complete, eid, lease["token"], worker_id, {"ok": True},
                agent_credential=token,
            )
            deadline = time.monotonic() + 5
            waiting_for_project = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    waiting_for_project = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'SELECT state,state_generation FROM projects%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if waiting_for_project:
                    break
                time.sleep(0.01)
            assert waiting_for_project, "completion did not wait on project-state lock"
            blocker.execute("UPDATE projects SET state='PAUSED' WHERE id=%s", (project_id,))
        with pytest.raises(ExecutionConflict, match="Project is not active"):
            paused_completion.result(timeout=5)
        with connect_postgres() as db:
            paused_generation = db.execute(
                "SELECT state_generation FROM projects WHERE id=%s", (project_id,),
            ).fetchone()[0]
            assert paused_generation == 3
            db.execute(
                "UPDATE projects SET state_generation=999 WHERE id=%s", (project_id,),
            )
            assert db.execute(
                "SELECT state_generation FROM projects WHERE id=%s", (project_id,),
            ).fetchone()[0] == paused_generation
        assert state(eid)["status"] == "RUNNING"
        with connect_postgres() as db:
            db.execute("UPDATE projects SET state='ACTIVE' WHERE id=%s", (project_id,))
            assert db.execute(
                "SELECT state_generation FROM projects WHERE id=%s", (project_id,),
            ).fetchone()[0] == 4
        with pytest.raises(ExecutionConflict, match="Project state changed"):
            complete(eid, lease["token"], worker_id, {"ok": True}, agent_credential=token)
        assert state(eid)["status"] == "RUNNING"
        with connect_postgres() as db:
            db.execute(
                "UPDATE execution_queue SET lease_expires_at=clock_timestamp()-interval '1 second' "
                "WHERE id=%s", (eid,),
            )
        assert quarantine_expired() >= 1
        assert state(eid)["status"] == "UNCERTAIN"

        # A completion blocked beyond its lease deadline must use the database
        # clock at the guarded update, not a timestamp captured before waiting.
        delayed_work = client.post(f"/v1/projects/{project_id}/work", headers=worker, json={
            "title": "Delayed completion", "author_id": worker_id,
            "acceptance_criteria": ["expired lease is denied"],
        }).json()["id"]
        client.post(f"/v1/work/{delayed_work}/admit", headers=worker)
        delayed_execution = client.post(
            f"/v1/work/{delayed_work}/stage-inert", headers=worker,
        ).json()["execution_id"]
        delayed_lease = claim(
            worker_id, agent_credential=token, project_id=project_id, seconds=1,
        )
        assert delayed_lease and delayed_lease["execution_id"] == delayed_execution
        with ThreadPoolExecutor(max_workers=1) as pool, connect_postgres() as blocker:
            blocker.execute(
                "SELECT id FROM execution_queue WHERE id=%s FOR UPDATE",
                (delayed_execution,),
            )
            delayed_completion = pool.submit(
                complete, delayed_execution, delayed_lease["token"], worker_id,
                {"ok": True}, agent_credential=token,
            )
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'SELECT project_id,project_state_generation FROM execution_queue%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if waiting:
                    break
                time.sleep(0.01)
            assert waiting, "completion did not block on the execution row"
            time.sleep(1.1)
        with pytest.raises(ExecutionConflict, match="Lease stale"):
            delayed_completion.result(timeout=5)
        assert state(delayed_execution)["status"] == "RUNNING"

        # Completion and quarantine contend on the same queue row. Once expiry
        # has passed, all schedules must end UNCERTAIN, never SUCCEEDED.
        for attempt in range(3):
            racing_work = client.post(f"/v1/projects/{project_id}/work", headers=worker, json={
                "title": f"Quarantine race {attempt}", "author_id": worker_id,
                "acceptance_criteria": ["expiry wins"],
            }).json()["id"]
            client.post(f"/v1/work/{racing_work}/admit", headers=worker)
            racing_execution = client.post(
                f"/v1/work/{racing_work}/stage-inert", headers=worker,
            ).json()["execution_id"]
            racing_lease = claim(
                worker_id, agent_credential=token, project_id=project_id, seconds=1,
            )
            assert racing_lease and racing_lease["execution_id"] == racing_execution
            time.sleep(1.05)
            start = threading.Barrier(2)

            def finish_expired(
                barrier=start, execution_id=racing_execution,
                lease_token=racing_lease["token"], selected_worker=worker_id,
                credential=token,
            ):
                barrier.wait(timeout=3)
                complete(
                    execution_id, lease_token, selected_worker,
                    {"ok": True}, agent_credential=credential,
                )

            def quarantine_work(barrier=start):
                barrier.wait(timeout=3)
                return quarantine_expired()

            with ThreadPoolExecutor(max_workers=2) as pool:
                completion = pool.submit(finish_expired)
                quarantining = pool.submit(quarantine_work)
                with pytest.raises(ExecutionConflict, match="Lease stale"):
                    completion.result(timeout=5)
                assert quarantining.result(timeout=5) >= 1
            assert state(racing_execution)["status"] == "UNCERTAIN"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_inert_worker_concurrent_claims_never_duplicate(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from aao.execution_queue import claim, state
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "concurrent-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "concurrent-ceo"}
    identity = "concurrent-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        secret = issued.json()["token"]
        worker = {"X-Agent-Token": secret}
        mid = client.post("/v1/mandates", headers=ceo, json={"title": str(uuid4()), "objective": "Concurrency"}).json()["id"]
        client.post(f"/v1/mandates/{mid}/confirm", headers=ceo)
        pid = client.post("/v1/projects", headers=ceo, json={"name": "Concurrency", "mandate_id": mid}).json()["id"]
        for cap in ("work.create", "work.admit"):
            client.post(f"/v1/projects/{pid}/grants", headers=ceo, json={"principal_id": identity, "capability": cap})
        assert client.post(f"/v1/projects/{pid}/grants", headers=ceo, json={
            "principal_id": identity, "capability": "execution.claim",
        }).status_code == 201
        ids = []
        for i in range(4):
            wid = client.post(f"/v1/projects/{pid}/work", headers=worker, json={"title": f"Batch {i}", "author_id": identity, "acceptance_criteria": ["inert"]}).json()["id"]
            client.post(f"/v1/work/{wid}/admit", headers=worker)
            ids.append(client.post(f"/v1/work/{wid}/stage-inert", headers=worker).json()["execution_id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        leases = list(pool.map(lambda _: claim(identity, agent_credential=secret, project_id=pid), range(4)))
    claimed = [lease["execution_id"] for lease in leases if lease is not None]
    assert set(claimed) == set(ids)
    assert len(claimed) == len(set(claimed)) == 4
    assert all(state(eid)["status"] == "RUNNING" for eid in ids)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_recovery_worker_process_quarantines_expired_lease_once(monkeypatch):
    """Exercise restart recovery through the standalone service entry point."""
    from aao.execution_queue import claim
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    db_url = os.environ["AAO_TEST_POSTGRES_URL"]
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", db_url)
    monkeypatch.setenv("AAO_CEO_TOKEN", "recovery-process-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "recovery-process-ceo"}
    worker_id = "recovery-worker-" + str(uuid4())

    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        worker = {"X-Agent-Token": token}
        mandate_id = client.post("/v1/mandates", headers=ceo, json={
            "title": "Recovery " + str(uuid4()), "objective": "Restart recovery",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate_id}/confirm", headers=ceo).status_code == 200
        project_id = client.post("/v1/projects", headers=ceo, json={
            "name": "Recovery process", "mandate_id": mandate_id,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim"):
            grant = client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
                "principal_id": worker_id, "capability": capability,
            })
            assert grant.status_code == 201, grant.text
        work_id = client.post(f"/v1/projects/{project_id}/work", headers=worker, json={
            "title": "Recover expired execution", "author_id": worker_id,
            "acceptance_criteria": ["uncertain after expired lease"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work_id}/admit", headers=worker).status_code == 200
        staged = client.post(f"/v1/work/{work_id}/stage-inert", headers=worker)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]

    lease = claim(worker_id, agent_credential=token, project_id=project_id, seconds=3600)
    assert lease and lease["execution_id"] == execution_id
    with connect_postgres() as db:
        db.execute(
            "UPDATE execution_queue SET lease_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE id=%s", (execution_id,),
        )

    env = os.environ.copy()
    env["AAO_ENV"] = "test"
    env["AAO_POSTGRES_URL"] = db_url
    repo_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable, str(repo_root / "scripts/run_execution_lease_recovery_worker.py"), "--once",
    ]
    first = subprocess.run(command, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert first.stdout.startswith("Quarantined ")
    assert int(first.stdout.split()[1]) >= 1

    with connect_postgres() as db:
        status = db.execute(
            "SELECT status FROM execution_queue WHERE id=%s", (execution_id,),
        ).fetchone()[0]
        journal_count = db.execute(
            "SELECT count(*) FROM execution_journal WHERE execution_id=%s AND kind='quarantined'",
            (execution_id,),
        ).fetchone()[0]
        event_count = db.execute(
            "SELECT count(*) FROM events WHERE subject_id=%s AND kind='work.execution_quarantined'",
            (work_id,),
        ).fetchone()[0]
        protocol_count = db.execute(
            "SELECT count(*) FROM protocol_instances WHERE subject_id=%s AND subject_type='work_item' "
            "AND protocol_id='blockage-escalation'",
            (work_id,),
        ).fetchone()[0]
    assert status == "UNCERTAIN"
    assert (journal_count, event_count, protocol_count) == (1, 1, 1)

    second = subprocess.run(command, cwd=repo_root, env=env, capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stderr
    assert second.stdout == ""
    with connect_postgres() as db:
        assert db.execute(
            "SELECT count(*) FROM execution_journal WHERE execution_id=%s AND kind='quarantined'",
            (execution_id,),
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT count(*) FROM events WHERE subject_id=%s AND kind='work.execution_quarantined'",
            (work_id,),
        ).fetchone()[0] == 1


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_execution_claim_serializes_with_grant_revocation(monkeypatch):
    from aao.execution_queue import ExecutionConflict, claim, state
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "claim-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "claim-revoke-ceo"}
    identity = "claim-revoke-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        worker = {"X-Agent-Token": token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Claim revoke " + str(uuid4()), "objective": "Serialize claim and revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Claim revoke", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim"):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": capability,
            })
            assert response.status_code == 201, response.text
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Claim race", "author_id": identity, "acceptance_criteria": ["inert"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        staged = client.post(f"/v1/work/{work}/stage-inert", headers=worker)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_queue IN ACCESS EXCLUSIVE MODE")
            claim_future = pool.submit(
                claim, identity, agent_credential=token, project_id=project,
            )
            deadline = time.monotonic() + 5
            claim_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    claim_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'SELECT q.id,q.work_id,q.input_json FROM execution_queue q JOIN projects p%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if claim_waiting:
                    break
                time.sleep(0.01)
            assert claim_waiting, "claim did not reach the queue while holding its grant lock"

            revoke_future = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{identity}/execution.claim",
                headers=ceo,
            )
            deadline = time.monotonic() + 5
            revoke_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    revoke_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'DELETE FROM project_grants%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if revoke_waiting:
                    break
                time.sleep(0.01)
            assert revoke_waiting, "grant revocation did not wait for the in-flight claim"

        lease = claim_future.result(timeout=5)
        revoked = revoke_future.result(timeout=5)
        assert lease is not None and lease["execution_id"] == execution_id
        assert revoked.status_code == 204, revoked.text
        assert state(execution_id)["status"] == "RUNNING"
        with pytest.raises(ExecutionConflict, match="execution claim grant required"):
            claim(identity, agent_credential=token, project_id=project)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_execution_completion_serializes_with_grant_revocation(monkeypatch):
    from aao.execution_queue import ExecutionConflict, claim, complete, state
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "complete-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "complete-revoke-ceo"}
    identity = "complete-revoke-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        worker = {"X-Agent-Token": token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Complete revoke " + str(uuid4()), "objective": "Serialize completion and revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Complete revoke", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim"):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": capability,
            })
            assert response.status_code == 201, response.text
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Completion race", "author_id": identity, "acceptance_criteria": ["inert"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        staged = client.post(f"/v1/work/{work}/stage-inert", headers=worker)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]
        lease = claim(identity, agent_credential=token, project_id=project)
        assert lease is not None and lease["execution_id"] == execution_id

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_journal IN ACCESS EXCLUSIVE MODE")
            completion_future = pool.submit(
                complete, execution_id, lease["token"], identity,
                {"ok": True}, agent_credential=token,
            )
            deadline = time.monotonic() + 5
            completion_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    completion_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'INSERT INTO execution_journal%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if completion_waiting:
                    break
                time.sleep(0.01)
            assert completion_waiting, "completion did not reach its journal write after authorization"

            revoke_future = pool.submit(
                client.delete,
                f"/v1/projects/{project}/grants/{identity}/execution.claim",
                headers=ceo,
            )
            deadline = time.monotonic() + 5
            revoke_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    revoke_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'DELETE FROM project_grants%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if revoke_waiting:
                    break
                time.sleep(0.01)
            assert revoke_waiting, "grant revocation did not wait for in-flight completion"

        assert completion_future.result(timeout=5) is None
        revoked = revoke_future.result(timeout=5)
        assert revoked.status_code == 204, revoked.text
        assert state(execution_id)["status"] == "SUCCEEDED"
        with pytest.raises(ExecutionConflict, match="Project execution claim grant revoked"):
            complete(execution_id, lease["token"], identity, {"ok": True}, agent_credential=token)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_execution_completion_serializes_with_credential_revocation(monkeypatch):
    from aao.execution_queue import ExecutionConflict, claim, complete, state
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "complete-credential-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "complete-credential-revoke-ceo"}
    identity = "complete-credential-revoke-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        worker = {"X-Agent-Token": token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Credential revoke " + str(uuid4()),
            "objective": "Serialize completion and credential revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Credential revoke", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim"):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": capability,
            })
            assert response.status_code == 201, response.text
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Credential completion race", "author_id": identity,
            "acceptance_criteria": ["inert"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        staged = client.post(f"/v1/work/{work}/stage-inert", headers=worker)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]
        lease = claim(identity, agent_credential=token, project_id=project)
        assert lease is not None and lease["execution_id"] == execution_id

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_journal IN ACCESS EXCLUSIVE MODE")
            completion_future = pool.submit(
                complete, execution_id, lease["token"], identity,
                {"ok": True}, agent_credential=token,
            )
            deadline = time.monotonic() + 5
            completion_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    completion_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'INSERT INTO execution_journal%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if completion_waiting:
                    break
                time.sleep(0.01)
            assert completion_waiting, "completion did not reach its journal write after credential auth"

            revoke_future = pool.submit(
                client.post, f"/v1/principals/{identity}/revoke", headers=ceo,
            )
            deadline = time.monotonic() + 5
            revoke_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    revoke_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'UPDATE principal_credentials SET enabled=false%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if revoke_waiting:
                    break
                time.sleep(0.01)
            assert revoke_waiting, "credential revocation did not wait for in-flight completion"

        assert completion_future.result(timeout=5) is None
        revoked = revoke_future.result(timeout=5)
        assert revoked.status_code == 200, revoked.text
        assert state(execution_id)["status"] == "SUCCEEDED"
        with pytest.raises(ExecutionConflict, match="credential invalid or revoked"):
            complete(execution_id, lease["token"], identity, {"ok": True}, agent_credential=token)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_execution_claim_serializes_with_credential_revocation(monkeypatch):
    from aao.execution_queue import ExecutionConflict, claim, state
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "claim-credential-revoke-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "claim-credential-revoke-ceo"}
    identity = "claim-credential-revoke-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        worker = {"X-Agent-Token": token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Claim credential revoke " + str(uuid4()),
            "objective": "Serialize claim and credential revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Claim credential revoke", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim"):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": capability,
            })
            assert response.status_code == 201, response.text
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Claim credential race", "author_id": identity,
            "acceptance_criteria": ["inert"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        staged = client.post(f"/v1/work/{work}/stage-inert", headers=worker)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]

        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE execution_queue IN ACCESS EXCLUSIVE MODE")
            claim_future = pool.submit(
                claim, identity, agent_credential=token, project_id=project,
            )
            deadline = time.monotonic() + 5
            claim_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    claim_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'SELECT q.id,q.work_id,q.input_json FROM execution_queue q JOIN projects p%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if claim_waiting:
                    break
                time.sleep(0.01)
            assert claim_waiting, "claim did not reach queue after credential authentication"

            revoke_future = pool.submit(
                client.post, f"/v1/principals/{identity}/revoke", headers=ceo,
            )
            deadline = time.monotonic() + 5
            revoke_waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    revoke_waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'UPDATE principal_credentials SET enabled=false%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if revoke_waiting:
                    break
                time.sleep(0.01)
            assert revoke_waiting, "credential revocation did not wait for in-flight claim"

        lease = claim_future.result(timeout=5)
        revoked = revoke_future.result(timeout=5)
        assert lease is not None and lease["execution_id"] == execution_id
        assert revoked.status_code == 200, revoked.text
        assert state(execution_id)["status"] == "RUNNING"
        with pytest.raises(ExecutionConflict, match="credential invalid or revoked"):
            claim(identity, agent_credential=token, project_id=project)
