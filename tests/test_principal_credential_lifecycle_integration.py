"""PostgreSQL integration tests, opt-in for explicitly disposable databases."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _register_test_worker(worker_id):
    """Give integration workers an explicit host binding before exercising claims."""
    from aao.backup import register_host_worker
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        register_host_worker(db, "integration-test-host", worker_id)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_legacy_execution_identity_migration_is_applied(monkeypatch):
    from aao.postgresql_connection import connect_postgres

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    with connect_postgres() as db:
        assert db.execute(
            "SELECT to_regclass('public.worker_registrations') IS NULL"
        ).fetchone()[0]
        migrated = db.execute(
            "SELECT kind,token_digest,enabled FROM principal_credentials "
            "WHERE principal_id='legacy-ci-agent'"
        ).fetchone()
        if migrated is not None:
            assert migrated == (
                "AGENT", sha256(b"aao-ci-legacy-migration-token").hexdigest(), True
            )


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_transactional_auditor_authentication_serializes_with_revocation(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import PrincipalDenied, authenticate_in_transaction
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "auditor-race-ceo")
    identity = "auditor-" + str(uuid4())
    ceo = {"X-CEO-Token": "auditor-race-ceo"}
    with TestClient(app) as client:
        response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AUDITOR",
        })
        assert response.status_code == 201, response.text
        token = response.json()["token"]

    with ThreadPoolExecutor(max_workers=1) as pool, connect_postgres() as protected:
        assert authenticate_in_transaction(protected, token, kind="AUDITOR") == identity
        protected_pid = protected.execute("SELECT pg_backend_pid()").fetchone()[0]
        pid_ready = __import__("threading").Event()
        revoke_pid = []

        def revoke():
            with connect_postgres() as revoker:
                revoke_pid.append(revoker.execute("SELECT pg_backend_pid()").fetchone()[0])
                pid_ready.set()
                revoker.execute(
                    "UPDATE principal_credentials SET enabled=false WHERE principal_id=%s",
                    (identity,),
                )

        pending = pool.submit(revoke)
        assert pid_ready.wait(timeout=2)
        deadline = time.monotonic() + 3
        blocked = False
        while time.monotonic() < deadline:
            with connect_postgres() as observer:
                blocked = observer.execute(
                    "SELECT %s = ANY(pg_blocking_pids(%s))",
                    (protected_pid, revoke_pid[0]),
                ).fetchone()[0]
            if blocked:
                break
            time.sleep(0.01)
        assert blocked, "credential revocation was not blocked by the authenticated transaction"
        assert not pending.done()
    pending.result(timeout=2)
    with connect_postgres() as db, pytest.raises(PrincipalDenied):
        authenticate_in_transaction(db, token, kind="AUDITOR")


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_transactional_agent_authentication_serializes_with_rotation(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import (
        PrincipalDenied,
        authenticate,
        authenticate_in_transaction,
        digest_token,
    )
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "agent-rotation-race-ceo")
    identity = "agent-rotation-" + str(uuid4())
    ceo = {"X-CEO-Token": "agent-rotation-race-ceo"}
    with TestClient(app) as client:
        response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert response.status_code == 201, response.text
        old_token = response.json()["token"]

        with ThreadPoolExecutor(max_workers=1) as pool, connect_postgres() as protected:
            assert authenticate_in_transaction(protected, old_token, kind="AGENT") == identity
            protected_pid = protected.execute("SELECT pg_backend_pid()").fetchone()[0]
            pid_ready = __import__("threading").Event()
            rotate_pid = []

            def rotate():
                with connect_postgres() as rotator:
                    rotate_pid.append(rotator.execute("SELECT pg_backend_pid()").fetchone()[0])
                    pid_ready.set()
                    new_secret = "rotated-" + str(uuid4())
                    rotator.execute(
                        "UPDATE principal_credentials SET token_digest=%s "
                        "WHERE principal_id=%s AND enabled=true",
                        (digest_token(new_secret), identity),
                    )
                    return new_secret

            pending = pool.submit(rotate)
            assert pid_ready.wait(timeout=2)
            deadline = time.monotonic() + 3
            blocked = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    blocked = observer.execute(
                        "SELECT %s = ANY(pg_blocking_pids(%s))",
                        (protected_pid, rotate_pid[0]),
                    ).fetchone()[0]
                if blocked:
                    break
                time.sleep(0.01)
            assert blocked, "credential rotation was not blocked by authenticated transaction"
            assert not pending.done()
        new_token = pending.result(timeout=3)
    with pytest.raises(PrincipalDenied):
        authenticate(old_token, kind="AGENT")
    assert authenticate(new_token, kind="AGENT") == identity


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_individual_auditor_credential_is_bound_to_review(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "individual-ceo")
    ceo = {"X-CEO-Token": "individual-ceo"}
    agent_id = "agent-" + str(uuid4())
    auditor_id = "auditor-" + str(uuid4())
    secret = "individual-secret-" + str(uuid4())
    with connect_postgres() as db:
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,'AUDITOR',%s,true)",
            (auditor_id, digest_token(secret)),
        )
    with TestClient(app) as client:
        agent_token = client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": agent_id, "kind": "AGENT"}).json()["token"]
        worker = {"X-Agent-Token": agent_token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Individual reviewer " + str(uuid4()),
            "objective": "Test credentials without external effects",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Audit test", "mandate_id": mandate
        }).json()["id"]
        for identity, capability in (
            (agent_id, "work.create"),
            (agent_id, "work.admit"),
            (agent_id, "work.progress"),
        ):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": capability,
            }).status_code == 201
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO project_grants(principal_id,project_id,capability) "
                "VALUES (%s,%s,'work.review')", (auditor_id, project),
            )
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Individual audited work",
            "author_id": "spoof-attempt",
            "acceptance_criteria": ["independently reviewed"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        assert client.post(f"/v1/work/{work}/progress", headers=worker).status_code == 200
        assert client.post(f"/v1/work/{work}/progress", headers=worker).status_code == 200
        approval_payload = {"decision": "APPROVE", "evidence": ["isolated local proof"]}
        denied = client.post(f"/v1/work/{work}/reviews",
                             headers={"X-Auditor-Token": "incorrect"}, json=approval_payload)
        assert denied.status_code == 403
        approval = client.post(f"/v1/work/{work}/reviews",
                               headers={"X-Auditor-Token": secret}, json=approval_payload)
        assert approval.status_code == 422, approval.text
        sha_bound_payload = {
            "decision": "REJECT", "candidate_sha": "a" * 40,
            "evidence": ["sha256:" + "a" * 64],
        }
        unlinked = client.post(f"/v1/work/{work}/reviews",
                               headers={"X-Auditor-Token": secret}, json=sha_bound_payload)
        assert unlinked.status_code == 409, unlinked.text


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
@pytest.mark.parametrize("revocation", ["credential", "grant"])
def test_review_rejection_serializes_with_auditor_revocation(monkeypatch, revocation):
    """An in-flight rejection commits before its credential or grant is revoked."""
    import aao.work_management_api as work_api
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import AuthenticatedPrincipal, app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "review-revoke-ceo")
    ceo = {"X-CEO-Token": "review-revoke-ceo"}
    agent_id = "review-agent-" + str(uuid4())
    auditor_id = "review-auditor-" + str(uuid4())
    with TestClient(app) as client:
        agent_token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        }).json()["token"]
        auditor_token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor_id, "kind": "AUDITOR",
        }).json()["token"]
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Review revocation race " + str(uuid4()),
            "objective": "Verify review authorization is held through commit",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Review revocation race", "mandate_id": mandate,
        }).json()["id"]
        for principal, capability in (
            (agent_id, "work.create"),
            (agent_id, "work.admit"),
            (agent_id, "work.progress"),
                (agent_id, "evidence.submit"),
            (auditor_id, "work.review"),
        ):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": capability,
            })
            assert response.status_code == 201, response.text
        worker = {"X-Agent-Token": agent_token}
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Review authorization race",
            "author_id": "ignored-client-identity",
            "acceptance_criteria": ["Authorized rejection is auditable"],
        }).json()["id"]
        assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
        assert client.post(f"/v1/work/{work}/progress", headers=worker).status_code == 200
        assert client.post(f"/v1/work/{work}/progress", headers=worker).status_code == 200

        from aao.evidence_registry import register_evidence
        candidate_sha = "b" * 40
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO execution_queue(id,work_id,project_id,status,input_json,"
                "project_state_generation,result_json) "
                "SELECT %s,%s,%s,'SUCCEEDED','{}'::jsonb,state_generation,%s::jsonb "
                "FROM projects WHERE id=%s",
                (str(uuid4()), work, project,
                 json.dumps({"candidate_sha": candidate_sha}), project),
            )
        evidence_ref = register_evidence(
            project, b"review authorization race evidence", agent_id=agent_id,
            agent_credential=agent_token, media_type="text/plain",
        )
        review_payload = {
            "decision": "REJECT", "candidate_sha": candidate_sha,
            "evidence": [evidence_ref],
        }

        authorized = Event()
        release_review = Event()
        protected_pid = []
        real_require_grant = work_api.require_grant

        def pause_after_review_authorization(db, principal, project_id, capability):
            real_require_grant(db, principal, project_id, capability)
            if capability == "work.review":
                protected_pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
                authorized.set()
                if not release_review.wait(timeout=5):
                    raise AssertionError("test did not release the protected review transaction")

        monkeypatch.setattr(work_api, "require_grant", pause_after_review_authorization)
        with ThreadPoolExecutor(max_workers=2) as pool:
            review_future = pool.submit(
                client.post,
                f"/v1/work/{work}/reviews",
                headers={"X-Auditor-Token": auditor_token},
                json=review_payload,
            )
            assert authorized.wait(timeout=5), "review did not reach its in-transaction grant check"
            if revocation == "credential":
                revoke_future = pool.submit(
                    client.post, f"/v1/principals/{auditor_id}/revoke", headers=ceo,
                )
                revoke_query = "UPDATE principal_credentials SET enabled=false%%"
                revoke_status = 200
            else:
                revoke_future = pool.submit(
                    client.delete,
                    f"/v1/projects/{project}/grants/{auditor_id}/work.review",
                    headers=ceo,
                )
                revoke_query = "DELETE FROM project_grants%%"
                revoke_status = 204
            try:
                deadline = time.monotonic() + 5
                blocked = False
                while time.monotonic() < deadline:
                    with connect_postgres() as observer:
                        blocked = observer.execute(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE query LIKE %s "
                            "AND wait_event_type='Lock' "
                            "AND %s=ANY(pg_blocking_pids(pid)))",
                            (revoke_query, protected_pid[0]),
                        ).fetchone()[0]
                    if blocked:
                        break
                    time.sleep(0.01)
                assert blocked, "auditor credential revocation did not wait for the protected review"
                assert not revoke_future.done()
            finally:
                release_review.set()
            review_response = review_future.result(timeout=5)
            revoke_response = revoke_future.result(timeout=5)

        assert review_response.status_code == 201, review_response.text
        assert review_response.json()["status"] == "IN_PROGRESS"
        assert revoke_response.status_code == revoke_status, revoke_response.text
        stale_context = AuthenticatedPrincipal(
            auditor_id, digest_token(auditor_token), "AUDITOR",
        )
        app.dependency_overrides[work_api.require_reviewer] = lambda: stale_context
        try:
            denied = client.post(f"/v1/work/{work}/reviews", json={
                **review_payload,
            })
        finally:
            app.dependency_overrides.pop(work_api.require_reviewer, None)
        assert denied.status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_individual_agent_scoped_creation_and_revocation(monkeypatch):
    """Individual agent cannot write across projects and revocation is immediate."""
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "agent-scope-ceo")
    ceo = {"X-CEO-Token": "agent-scope-ceo"}
    identity = "agent-" + str(uuid4())
    secret = "agent-secret-" + str(uuid4())
    agent = {"X-Agent-Token": secret}
    with connect_postgres() as db:
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,'AGENT',%s,true)", (identity, digest_token(secret))
        )
    with TestClient(app) as client:
        projects = []
        for i in range(2):
            mid = client.post("/v1/mandates", headers=ceo, json={
                "title": f"Individual agent {i} {uuid4()}",
                "objective": "Project isolation",
            }).json()["id"]
            assert client.post(f"/v1/mandates/{mid}/confirm", headers=ceo).status_code == 200
            pid = client.post("/v1/projects", headers=ceo, json={
                "name": f"Agent scope {i}", "mandate_id": mid
            }).json()["id"]
            projects.append(pid)
        allowed, forbidden = projects
        assert client.post(f"/v1/projects/{allowed}/grants", headers=ceo, json={
            "principal_id": identity, "capability": "project.read",
        }).status_code == 201
        scoped = client.get("/v1/projects", headers=agent)
        assert scoped.status_code == 200, scoped.text
        assert [row["id"] for row in scoped.json()] == [allowed]
        assert client.get(f"/v1/projects/{forbidden}/board", headers=agent).status_code == 403
        assert client.get(f"/v1/projects/{allowed}/board", headers=agent).status_code == 200
        assert client.post(f"/v1/projects/{allowed}/grants", headers=ceo, json={
            "principal_id": identity, "capability": "work.create",
        }).status_code == 201
        payload = {"title": "Individual action", "author_id": "spoof-attempt",
                   "acceptance_criteria": ["Persisted"]}
        invalid = client.post(f"/v1/projects/{allowed}/work",
                              headers={"X-Agent-Token": "incorrect"},
                              json=payload)
        assert invalid.status_code == 403
        assert client.post(f"/v1/projects/{forbidden}/work",
                           headers=agent, json=payload).status_code == 403
        accepted = client.post(f"/v1/projects/{allowed}/work",
                               headers=agent, json=payload)
        assert accepted.status_code == 201, accepted.text
        work_id = accepted.json()["id"]
        with connect_postgres() as db:
            author = db.execute("SELECT author_id FROM work_items WHERE id=%s", (work_id,)).fetchone()
            assert author[0] == identity
            db.execute("UPDATE principal_credentials SET enabled=false WHERE principal_id=%s", (identity,))
        assert client.post(f"/v1/projects/{allowed}/work",
                           headers=agent, json=payload).status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_work_creation_serializes_with_project_grant_revocation(monkeypatch):
    """An admitted write holds its grant until its work row commits."""
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "work-grant-race-ceo")
    ceo = {"X-CEO-Token": "work-grant-race-ceo"}
    identity = "agent-grant-race-" + str(uuid4())
    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        worker = {"X-Agent-Token": issued.json()["token"]}
        mid = client.post("/v1/mandates", headers=ceo, json={
            "title": "Grant race " + str(uuid4()), "objective": "Protected write ordering",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mid}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Grant race", "mandate_id": mid,
        }).json()["id"]
        grant_url = f"/v1/projects/{project}/grants/{identity}/work.create"
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": identity, "capability": "work.create",
        }).status_code == 201

        payload = {"title": "Serialized work", "author_id": "ignored",
                   "acceptance_criteria": ["write completes before revocation"]}
        with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
            blocker.execute("LOCK TABLE work_items IN ACCESS EXCLUSIVE MODE")
            creating = pool.submit(
                client.post, f"/v1/projects/{project}/work",
                headers=worker, json=payload,
            )
            deadline = time.monotonic() + 3
            protected_pid = None
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE query LIKE 'INSERT INTO work_items%' "
                        "AND wait_event_type='Lock' LIMIT 1",
                    ).fetchone()
                    protected_pid = row[0] if row else None
                if protected_pid:
                    break
                time.sleep(0.01)
            assert protected_pid, "work insertion did not reach the controlled table-lock wait"

            revoking = pool.submit(client.delete, grant_url, headers=ceo)
            deadline = time.monotonic() + 3
            serialized = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    row = observer.execute(
                        "SELECT pid FROM pg_stat_activity "
                        "WHERE query LIKE 'DELETE FROM project_grants%' "
                        "AND wait_event_type='Lock' LIMIT 1",
                    ).fetchone()
                    if row:
                        serialized = observer.execute(
                            "SELECT %s = ANY(pg_blocking_pids(%s))",
                            (protected_pid, row[0]),
                        ).fetchone()[0]
                if serialized:
                    break
                time.sleep(0.01)
            assert serialized, "grant revocation was not blocked by the protected write"
            assert not creating.done()
            assert not revoking.done()

        created = creating.result(timeout=3)
        revoked = revoking.result(timeout=3)
        assert created.status_code == 201, created.text
        assert revoked.status_code == 204, revoked.text
        with connect_postgres() as db:
            assert db.execute(
                "SELECT 1 FROM work_items WHERE id=%s", (created.json()["id"],)
            ).fetchone()
            assert not db.execute(
                "SELECT 1 FROM project_grants WHERE project_id=%s "
                "AND principal_id=%s AND capability='work.create'",
                (project, identity),
            ).fetchone()


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_individual_agent_claim_and_revocation(monkeypatch):
    from aao.execution_queue import ExecutionConflict, claim, complete, state
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "lease-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "lease-ceo"}
    principal = "agent-" + str(uuid4())
    secret = "secret-" + str(uuid4())
    with connect_postgres() as db:
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,'AGENT',%s,true)", (principal, digest_token(secret)),
        )
    _register_test_worker(principal)
    with TestClient(app) as client:
        worker = {"X-Agent-Token": secret}
        mid = client.post("/v1/mandates", headers=ceo, json={
            "title": "Unified agent lease " + str(uuid4()), "objective": "Isolated test"
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mid}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Unified lease", "mandate_id": mid
        }).json()["id"]
        for who, capability in (
            (principal, "work.create"),
            (principal, "work.admit"),
            (principal, "execution.claim"),
        ):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": who, "capability": capability,
            }).status_code == 201
        wid = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Inert execution", "author_id": "ignored",
            "acceptance_criteria": ["completed"],
        }).json()["id"]
        assert client.post(f"/v1/work/{wid}/admit", headers=worker).status_code == 200
        eid = client.post(f"/v1/work/{wid}/stage-inert", headers=worker).json()["execution_id"]
    with pytest.raises(ExecutionConflict):
        claim(principal, project_id=project, agent_credential="wrong")
    lease = claim(principal, project_id=project, agent_credential=secret)
    assert lease is not None and lease["execution_id"] == eid
    with connect_postgres() as db:
        db.execute("UPDATE principal_credentials SET enabled=false WHERE principal_id=%s", (principal,))
    with pytest.raises(ExecutionConflict):
        complete(eid, lease["token"], principal, {"ok": True}, agent_credential=secret)
    assert state(eid)["status"] == "RUNNING"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_ceo_governed_principal_issue_rotate_revoke(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import PrincipalDenied, authenticate
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "governance-ceo")
    name = "agent-" + str(uuid4())
    ceo = {"X-CEO-Token": "governance-ceo"}
    with TestClient(app) as client:
        payload = {"principal_id": name, "kind": "AGENT"}
        assert client.post("/v1/principals/credentials", json=payload).status_code == 403
        created = client.post("/v1/principals/credentials", headers=ceo, json=payload)
        assert created.status_code == 201, created.text
        initial = created.json()["token"]
        assert authenticate(initial, kind="AGENT") == name
        assert client.post("/v1/principals/credentials", headers=ceo, json=payload).status_code == 409
        changed = client.post(f"/v1/principals/{name}/rotate", headers=ceo)
        assert changed.status_code == 200, changed.text
        rotated = changed.json()["token"]
        assert rotated != initial
        with pytest.raises(PrincipalDenied):
            authenticate(initial, kind="AGENT")
        assert authenticate(rotated, kind="AGENT") == name
        assert client.post(f"/v1/principals/{name}/revoke", headers=ceo).status_code == 200
        with pytest.raises(PrincipalDenied):
            authenticate(rotated, kind="AGENT")
        assert client.post(f"/v1/principals/{name}/revoke", headers=ceo).status_code == 404
        # A revoked identity cannot be silently reactivated by token rotation.
        assert client.post(f"/v1/principals/{name}/rotate", headers=ceo).status_code == 404
        with connect_postgres() as db:
            events = db.execute(
                "SELECT kind FROM events WHERE details->>'principal_id'=%s "
                "AND kind LIKE %s", (name, "principal.credential.%")
            ).fetchall()
            assert {row[0] for row in events} == {
                "principal.credential.issued",
                "principal.credential.rotated",
                "principal.credential.revoked",
            }


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_http_request_context_rejects_token_rotated_before_protected_transaction(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import (
        AuthenticatedPrincipal,
        app,
        read_principal,
    )

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "http-rotation-gap-ceo")
    identity = "agent-rotation-gap-" + str(uuid4())
    ceo = {"X-CEO-Token": "http-rotation-gap-ceo"}

    def wait_for_lock_wait(connect, query_pattern, blocker_pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connect() as observer:
                row = observer.execute(
                    "SELECT pid FROM pg_stat_activity WHERE query LIKE %s "
                    "AND wait_event_type='Lock' "
                    "AND %s=ANY(pg_blocking_pids(pid)) LIMIT 1",
                    (query_pattern, blocker_pid),
                ).fetchone()
                if row:
                    return row[0]
            time.sleep(0.01)
        raise AssertionError(f"query did not wait on expected blocker: {query_pattern}")

    with TestClient(app) as client:
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        old_token = issued.json()["token"]
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Rotation gap " + str(uuid4()),
            "objective": "Reject a request context captured before token rotation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Rotation gap", "mandate_id": mandate,
        }).json()["id"]
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": identity, "capability": "project.read",
        }).status_code == 201

        # This is the dependency-resolution point, before the operation opens
        # its protected DB transaction.
        stale_context = read_principal(x_ceo_token=None, x_agent_token=old_token)
        assert isinstance(stale_context, AuthenticatedPrincipal)
        rotated = client.post(f"/v1/principals/{identity}/rotate", headers=ceo)
        assert rotated.status_code == 200, rotated.text
        new_token = rotated.json()["token"]

        app.dependency_overrides[read_principal] = lambda: stale_context
        try:
            denied = client.get("/v1/projects")
            assert denied.status_code == 403

            fresh_context = read_principal(x_ceo_token=None, x_agent_token=new_token)
            app.dependency_overrides[read_principal] = lambda: fresh_context
            allowed = client.get("/v1/projects")
            assert allowed.status_code == 200, allowed.text
            assert any(row["id"] == project for row in allowed.json())

            # Keep the already-authenticated request context, revoke its
            # project capability, then exercise the protected board route.
            revoked = client.delete(
                f"/v1/projects/{project}/grants/{identity}/project.read",
                headers=ceo,
            )
            assert revoked.status_code == 204, revoked.text
            denied = client.get(f"/v1/projects/{project}/board")
            assert denied.status_code == 403, denied.text

            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": "project.read",
            }).status_code == 201
            with ThreadPoolExecutor(max_workers=2) as pool, connect_postgres() as blocker:
                blocker_pid = blocker.execute("SELECT pg_backend_pid()").fetchone()[0]
                blocker.execute(
                    "SELECT project_id FROM project_grants WHERE principal_id=%s "
                    "AND project_id=%s AND capability='project.read' FOR UPDATE",
                    (identity, project),
                )
                revocation = pool.submit(
                    client.delete,
                    f"/v1/projects/{project}/grants/{identity}/project.read",
                    headers=ceo,
                )
                revoker_pid = wait_for_lock_wait(
                    connect_postgres, "DELETE FROM project_grants%", blocker_pid,
                )
                board_read = pool.submit(client.get, f"/v1/projects/{project}/board")
                wait_for_lock_wait(
                    connect_postgres, "SELECT 1 FROM project_grants%", revoker_pid,
                )
            assert revocation.result(timeout=5).status_code == 204
            assert board_read.result(timeout=5).status_code == 403
        finally:
            app.dependency_overrides.pop(read_principal, None)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_ceo_project_grant_inventory_returns_metadata_only(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "grant-inventory-ceo")
    ceo = {"X-CEO-Token": "grant-inventory-ceo"}
    identity = "inventory-agent-" + str(uuid4())
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Grant inventory " + str(uuid4()),
            "objective": "Inspect grants through the authorized API",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Grant inventory " + str(uuid4()), "mandate_id": mandate,
        }).json()["id"]
        credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert credential.status_code == 201, credential.text
        grant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": identity, "capability": "project.read",
        })
        assert grant.status_code == 201, grant.text

        inventory = client.get(f"/v1/projects/{project}/grants", headers=ceo)
        assert inventory.status_code == 200, inventory.text
        assert inventory.json() == [{
            "principal_id": identity,
            "kind": "AGENT",
            "credential_enabled": True,
            "capability": "project.read",
            "expires_at": None,
        }]
        assert "token" not in inventory.text
        assert "token_digest" not in inventory.text
        assert client.get(
            f"/v1/projects/{project}/grants", headers={"X-CEO-Token": "wrong"},
        ).status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_ceo_mandate_inventory_binds_confirmation_project_and_event_ids(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "mandate-inventory-ceo")
    ceo = {"X-CEO-Token": "mandate-inventory-ceo"}
    title = "Mandate inventory " + str(uuid4())
    project_name = "Mandate inventory " + str(uuid4())
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": title, "objective": "Verify authorized lifecycle evidence",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": project_name, "mandate_id": mandate,
        }).json()["id"]

        response = client.get("/v1/mandates", headers=ceo)
        assert response.status_code == 200, response.text
        result = next(row for row in response.json() if row["id"] == mandate)
        assert result["title"] == title
        assert result["objective"] == "Verify authorized lifecycle evidence"
        assert result["status"] == "CONFIRMED"
        assert result["project"] == {
            "id": project, "name": project_name, "state": "ACTIVE",
        }
        assert {event["kind"] for event in result["events"]} >= {
            "mandate.drafted", "mandate.confirmed", "project.created",
        }
        assert all("id" in event and "subject_id" in event for event in result["events"])
        assert all("details" not in event for event in result["events"])
