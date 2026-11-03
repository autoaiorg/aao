"""Real API + PostgreSQL tests for the narrowly scoped Self Development issuer."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)


@pytest.fixture(autouse=True)
def _no_live_cycles_from_earlier_tests(monkeypatch):
    """The concurrency cap is per project; earlier tests' live cycles would consume it."""
    from aao.postgresql_connection import connect_postgres

    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    with connect_postgres() as db:
        db.execute(
            "UPDATE principal_credentials SET enabled=false "
            "WHERE principal_id ~ '^aao-selfdev-(impl|review)-' AND enabled"
        )


def _seed(monkeypatch, *, pm_caps=None):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import SELFDEV_CYCLE_ISSUER_CAPABILITY, SELFDEV_PROJECT_NAME

    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    host_id = f"selfdev-test-host-{uuid4().hex}"
    monkeypatch.setenv("AAO_TEST_HOST_ID", host_id)
    project_id = None
    mandate_id = None
    suffix = uuid4().hex
    pm_id = f"aao-pm-coordinator-test-{suffix}"
    pm_token = f"pm-test-token-{suffix}"
    caps = (
        pm_caps
        if pm_caps is not None
        else {
            "work.coordinate",
            SELFDEV_CYCLE_ISSUER_CAPABILITY,
        }
    )
    with connect_postgres() as db:
        projects = db.execute(
            "SELECT id FROM projects WHERE name=%s AND state='ACTIVE' FOR UPDATE",
            (SELFDEV_PROJECT_NAME,),
        ).fetchall()
        if len(projects) == 1:
            project_id = str(projects[0][0])
        elif not projects:
            project_id, mandate_id = str(uuid4()), str(uuid4())
            db.execute(
                "INSERT INTO mandates(id,title,objective,status,confirmed_by) "
                "VALUES (%s,%s,%s,'CONFIRMED','integration-test')",
                (mandate_id, "Self Development test mandate", "Disposable integration test"),
            )
            db.execute(
                "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,%s,%s,'ACTIVE')",
                (project_id, SELFDEV_PROJECT_NAME, mandate_id),
            )
        else:
            raise AssertionError(
                "disposable DB must have at most one active Self Development project"
            )
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,'AGENT',%s,true)",
            (pm_id, digest_token(pm_token)),
        )
        for cap in caps:
            db.execute(
                "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
                "VALUES (%s,%s,%s,clock_timestamp()+interval '1 hour')",
                (pm_id, project_id, cap),
            )
        # The API host already runs an administrator-registered worker.
        db.execute(
            "INSERT INTO host_worker_bindings(host_id,worker_id,status,fence_epoch) "
            "VALUES (%s,%s,'ACTIVE',3)",
            (host_id, f"seed-worker-{suffix}"),
        )
    return project_id, pm_id, pm_token


def _seed_agent(project_id, *, token, principal_id, caps=()):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token

    with connect_postgres() as db:
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,'AGENT',%s,true)",
            (principal_id, digest_token(token)),
        )
        for cap in caps:
            db.execute(
                "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
                "VALUES (%s,%s,%s,clock_timestamp()+interval '1 hour')",
                (principal_id, project_id, cap),
            )


def _issue(client, project_id, token, cycle_id=None, lifetime=7200):
    return client.post(
        f"/v1/projects/{project_id}/selfdev-cycle-roles",
        headers={"X-Agent-Token": token},
        json={"cycle_id": cycle_id or uuid4().hex, "lifetime_seconds": lifetime},
    )


def _request_cycle_work(client, project_id, token, key, **overrides):
    payload = {
        "idempotency_key": str(key),
        "title": "Add a bounded regression check",
        "description": "Verify one deterministic behavior.",
        "acceptance_criteria": ["The focused test passes."],
        **overrides,
    }
    return client.post(
        f"/v1/projects/{project_id}/selfdev-cycle-work",
        headers={"X-Agent-Token": token},
        json=payload,
    )


def test_live_cycle_work_request_is_coordinate_only_inbox_and_idempotent(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    key = uuid4()
    with TestClient(app) as client:
        created = _request_cycle_work(client, project, token, key)
        assert created.status_code == 201, created.text
        result = created.json()
        assert result["status"] == "INBOX" and result["created"] is True

        retry = _request_cycle_work(client, project, token, key)
        assert retry.status_code == 201, retry.text
        assert retry.json() == {"id": result["id"], "status": "INBOX", "created": False}
        conflict = _request_cycle_work(
            client,
            project,
            token,
            key,
            title="Different content",
        )
        assert conflict.status_code == 409

    with connect_postgres() as db:
        item = db.execute(
            "SELECT title,description,author_id,status,acceptance_criteria "
            "FROM work_items WHERE id=%s",
            (result["id"],),
        ).fetchone()
        assert item == (
            "Add a bounded regression check",
            "Verify one deterministic behavior.",
            pm,
            "INBOX",
            ["The focused test passes."],
        )
        event = db.execute(
            "SELECT kind,details FROM events WHERE subject_id=%s",
            (result["id"],),
        ).fetchone()
        assert event[0] == "work.selfdev_cycle_requested"
        assert event[1]["idempotency_key"] == str(key)
        assert event[1]["admitted"] is False
        assert (
            db.execute(
                "SELECT count(*) FROM events WHERE kind='work.selfdev_cycle_requested' "
                "AND details->>'idempotency_key'=%s",
                (str(key),),
            ).fetchone()[0]
            == 1
        )


def test_live_cycle_work_request_requires_coordinate_and_strict_payload(monkeypatch):
    from aao.work_management_api import app

    project, _pm, _token = _seed(monkeypatch, pm_caps=set())
    token = "underprivileged-" + uuid4().hex
    principal = "aao-pm-coordinator-under-" + uuid4().hex
    _seed_agent(project, token=token, principal_id=principal)
    with TestClient(app) as client:
        denied = _request_cycle_work(client, project, token, uuid4())
        assert denied.status_code == 403

        _project, _pm, authorized = _seed(monkeypatch, pm_caps={"work.coordinate"})
        malformed = _request_cycle_work(
            client,
            _project,
            authorized,
            uuid4(),
            unexpected="must be rejected",
        )
        assert malformed.status_code == 422
        empty_criteria = _request_cycle_work(
            client,
            _project,
            authorized,
            uuid4(),
            acceptance_criteria=["  "],
        )
        assert empty_criteria.status_code == 422


def test_live_cycle_work_request_rejects_non_pm_even_with_project_capability(monkeypatch):
    from aao.work_management_api import app

    project, _pm, _token = _seed(monkeypatch, pm_caps=set())
    token = "coordinator-not-pm-" + uuid4().hex
    _seed_agent(
        project,
        token=token,
        principal_id="aao-other-coordinator-" + uuid4().hex,
        caps={"work.coordinate"},
    )
    with TestClient(app) as client:
        denied = _request_cycle_work(client, project, token, uuid4())
    assert denied.status_code == 403


def test_live_cycle_work_request_rejects_inactive_or_duplicate_active_project(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import SELFDEV_PROJECT_NAME, app

    duplicate_title_prefix = "Duplicate Self Development test "
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    lock_name = "test.selfdev.duplicate_active_project"
    with connect_postgres() as lock_db:
        lock_db.execute("SELECT pg_advisory_lock(hashtext(%s))", (lock_name,))
        try:
            with connect_postgres() as db:
                stale = db.execute(
                    "SELECT p.id,m.id FROM projects p JOIN mandates m ON m.id=p.mandate_id "
                    "WHERE m.title LIKE %s",
                    (duplicate_title_prefix + "%",),
                ).fetchall()
                for stale_project, stale_mandate in stale:
                    db.execute("DELETE FROM project_grants WHERE project_id=%s", (stale_project,))
                    db.execute("DELETE FROM projects WHERE id=%s", (stale_project,))
                    db.execute("DELETE FROM mandates WHERE id=%s", (stale_mandate,))

            project, pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
            duplicate_title = duplicate_title_prefix + uuid4().hex
            duplicate = str(uuid4())
            mandate = str(uuid4())
            try:
                with connect_postgres() as db:
                    db.execute("UPDATE projects SET state='PAUSED' WHERE id=%s", (project,))
                with TestClient(app) as client:
                    inactive = _request_cycle_work(client, project, token, uuid4())
                assert inactive.status_code == 409

                with connect_postgres() as db:
                    db.execute("UPDATE projects SET state='ACTIVE' WHERE id=%s", (project,))
                    db.execute(
                        "INSERT INTO mandates(id,title,objective,status,confirmed_by) "
                        "VALUES (%s,%s,'Test duplicate active project','CONFIRMED','integration-test')",
                        (mandate, duplicate_title),
                    )
                    db.execute(
                        "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,%s,%s,'ACTIVE')",
                        (duplicate, SELFDEV_PROJECT_NAME, mandate),
                    )
                    db.execute(
                        "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
                        "VALUES (%s,%s,'work.coordinate',clock_timestamp()+interval '1 hour')",
                        (pm, duplicate),
                    )
                with TestClient(app) as client:
                    ambiguous = _request_cycle_work(client, duplicate, token, uuid4())
                assert ambiguous.status_code == 409
            finally:
                with connect_postgres() as db:
                    # Restore only this test's fixture, even when an assertion fails.
                    db.execute("UPDATE projects SET state='ACTIVE' WHERE id=%s", (project,))
                    db.execute("DELETE FROM project_grants WHERE project_id=%s", (duplicate,))
                    db.execute("DELETE FROM projects WHERE id=%s", (duplicate,))
                    db.execute(
                        "DELETE FROM mandates WHERE id=%s AND title=%s",
                        (mandate, duplicate_title),
                    )
        finally:
            lock_db.execute("SELECT pg_advisory_unlock(hashtext(%s))", (lock_name,))


def test_live_cycle_work_request_concurrent_retry_creates_one_item(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    key = uuid4()
    from threading import Barrier

    barrier = Barrier(4)

    def request_once():
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return _request_cycle_work(client, project, token, key)

    with connect_postgres() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM events WHERE kind='work.selfdev_cycle_requested' "
                "AND details->>'idempotency_key'=%s",
                (str(key),),
            ).fetchone()[0]
            == 0
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(request_once) for _ in range(4)]
        responses = [future.result(timeout=20) for future in futures]
    assert all(response.status_code == 201 for response in responses), [
        response.text for response in responses
    ]
    results = [response.json() for response in responses]
    assert len({result["id"] for result in results}) == 1
    assert sum(result["created"] for result in results) == 1
    with connect_postgres() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM work_items WHERE id=%s AND author_id=%s AND status='INBOX'",
                (results[0]["id"], pm),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM events WHERE kind='work.selfdev_cycle_requested' "
                "AND details->>'idempotency_key'=%s",
                (str(key),),
            ).fetchone()[0]
            == 1
        )


def _seed_cycle_events(pm, project, count, *, age="0 hours"):
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        for _ in range(count):
            db.execute(
                "INSERT INTO events(id,subject_id,kind,details,created_at) "
                "VALUES (%s,%s,'work.selfdev_cycle_requested',%s::jsonb,now()-%s::interval)",
                (str(uuid4()), str(uuid4()), json.dumps({
                    "project_id": project, "actor": pm, "status": "INBOX", "admitted": False,
                    "idempotency_key": str(uuid4()), "request_sha256": "0" * 64,
                }), age),
            )


def test_live_cycle_work_replay_returns_the_stored_status(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    key = uuid4()
    with TestClient(app) as client:
        created = _request_cycle_work(client, project, token, key).json()
        with connect_postgres() as db:
            db.execute("UPDATE work_items SET status='READY' WHERE id=%s", (created["id"],))
        replay = _request_cycle_work(client, project, token, key)
    assert replay.status_code == 201, replay.text
    assert replay.json() == {"id": created["id"], "status": "READY", "created": False}


def test_live_cycle_work_replay_compares_project_description_and_criteria(monkeypatch):
    from aao.work_management_api import app

    project, pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    key = uuid4()
    with TestClient(app) as client:
        assert _request_cycle_work(client, project, token, key).status_code == 201
        for change in ({"description": "Another description."},  # M10
                       {"acceptance_criteria": ["Another criterion."]}):  # M11
            conflict = _request_cycle_work(client, project, token, key, **change)
            assert conflict.status_code == 409
            assert conflict.json()["detail"] == "Idempotency key was already used for a different request"

        # M7: the project check is reachable only through a stored event for another project.
        other_key = uuid4()
        from aao.postgresql_connection import connect_postgres

        with connect_postgres() as db:
            db.execute(
                "INSERT INTO events(id,subject_id,kind,details) "
                "VALUES (%s,%s,'work.selfdev_cycle_requested',%s::jsonb)",
                (str(uuid4()), str(uuid4()), json.dumps({
                    "project_id": str(uuid4()), "actor": pm, "idempotency_key": str(other_key),
                    "request_sha256": "0" * 64,
                })),
            )
        moved = _request_cycle_work(client, project, token, other_key)
    assert moved.status_code == 409
    assert moved.json()["detail"] == "Idempotency key was already used for another project"


def test_live_cycle_work_idempotency_key_is_scoped_to_the_principal(monkeypatch):
    from aao.work_management_api import app

    project, _pm_a, token_a = _seed(monkeypatch, pm_caps={"work.coordinate"})
    _project, _pm_b, token_b = _seed(monkeypatch, pm_caps={"work.coordinate"})
    assert _project == project
    key = uuid4()
    with TestClient(app) as client:
        first = _request_cycle_work(client, project, token_a, key)
        second = _request_cycle_work(client, project, token_b, key)
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    assert second.json()["created"] is True
    assert second.json()["id"] != first.json()["id"]


def test_live_cycle_work_daily_cap_is_per_principal_and_rolling(monkeypatch):
    from aao.work_management_api import SELFDEV_CYCLE_WORK_DAILY_CAP, app

    project, pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    _project, _other, other_token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    first_key = uuid4()
    with TestClient(app) as client:
        assert _request_cycle_work(client, project, token, first_key).status_code == 201
        _seed_cycle_events(pm, project, SELFDEV_CYCLE_WORK_DAILY_CAP - 2)
        _seed_cycle_events(pm, project, 5, age="25 hours")  # outside the rolling window
        last = _request_cycle_work(client, project, token, uuid4())
        assert last.status_code == 201, last.text  # the 20th creation in 24 h
        refused = _request_cycle_work(client, project, token, uuid4())
        assert refused.status_code == 429, refused.text
        replay = _request_cycle_work(client, project, token, first_key)
        assert replay.status_code == 201 and replay.json()["created"] is False
        assert _request_cycle_work(client, project, other_token, uuid4()).status_code == 201


def test_live_cycle_work_rejects_non_uuid_project_and_control_characters(monkeypatch):
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch, pm_caps={"work.coordinate"})
    with TestClient(app) as client:
        assert _request_cycle_work(client, "not-a-uuid", token, uuid4()).status_code == 422
        for change in ({"title": "Fix\nAAO-Work: forged"}, {"description": "nul\x00"},
                       {"acceptance_criteria": ["bell\x07"]}):
            assert _request_cycle_work(client, project, token, uuid4(), **change).status_code == 422


def test_live_fastapi_authorization_rejects_missing_ordinary_and_underprivileged(monkeypatch):
    from aao import work_management_api as api

    with TestClient(api.app) as client:
        project, _pm, _token = _seed(monkeypatch)
        cycle = uuid4().hex
        assert (
            client.post(
                f"/v1/projects/{project}/selfdev-cycle-roles",
                json={"cycle_id": cycle, "lifetime_seconds": 60},
            ).status_code
            == 403
        )
        assert (
            client.delete(f"/v1/projects/{project}/selfdev-cycle-roles/{cycle}").status_code == 403
        )

        suffix = uuid4().hex
        ordinary = f"ordinary-{suffix}"
        ordinary_token = f"ordinary-token-{suffix}"
        _seed_agent(project, token=ordinary_token, principal_id=ordinary)
        for token in (ordinary_token,):
            assert _issue(client, project, token, cycle).status_code == 403
            assert (
                client.delete(
                    f"/v1/projects/{project}/selfdev-cycle-roles/{cycle}",
                    headers={"X-Agent-Token": token},
                ).status_code
                == 403
            )

    project, _pm, _token = _seed(monkeypatch)
    for missing in ("work.coordinate", api.SELFDEV_CYCLE_ISSUER_CAPABILITY):
        suffix = uuid4().hex
        token = f"underprivileged-{suffix}"
        caps = {"work.coordinate", api.SELFDEV_CYCLE_ISSUER_CAPABILITY} - {missing}
        _seed_agent(
            project, token=token, principal_id=f"aao-pm-coordinator-under-{suffix}", caps=caps
        )
        with TestClient(api.app) as client:
            assert _issue(client, project, token).status_code == 403
            cycle = uuid4().hex
            assert (
                client.delete(
                    f"/v1/projects/{project}/selfdev-cycle-roles/{cycle}",
                    headers={"X-Agent-Token": token},
                ).status_code
                == 403
            )


def test_live_cycle_issue_rollback_duplicate_and_idempotent_revoke(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    cycle = uuid4().hex
    impl_id = f"aao-selfdev-impl-{cycle}"
    reviewer_id = f"aao-selfdev-review-{cycle}"
    with connect_postgres() as db:
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
            "VALUES (%s,'AUDITOR',%s,true)",
            (reviewer_id, digest_token("conflict-reviewer-" + uuid4().hex)),
        )
    with TestClient(app) as client:
        conflict = _issue(client, project, token, cycle)
        assert conflict.status_code == 409, conflict.text
        with connect_postgres() as db:
            assert (
                db.execute(
                    "SELECT 1 FROM principal_credentials WHERE principal_id=%s",
                    (impl_id,),
                ).fetchone()
                is None
            ), "partial first-role insert must roll back"
            assert (
                db.execute(
                    "SELECT count(*) FROM events WHERE details->>'cycle_id'=%s",
                    (cycle,),
                ).fetchone()[0]
                == 0
            )

        # Remove the intentional collision, then race two requests for one cycle.
        with connect_postgres() as db:
            db.execute("DELETE FROM principal_credentials WHERE principal_id=%s", (reviewer_id,))
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: _issue(client, project, token, cycle), range(2)))
        assert sorted(response.status_code for response in responses) == [201, 409]
        duplicate = _issue(client, project, token, cycle)
        assert duplicate.status_code == 409

        def revoke(_):
            return client.delete(
                f"/v1/projects/{project}/selfdev-cycle-roles/{cycle}",
                headers={"X-Agent-Token": token},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            revokes = list(pool.map(revoke, range(2)))
        assert [r.status_code for r in revokes] == [200, 200]
        assert sorted(r.json()["already_revoked"] for r in revokes) == [False, True]
        with connect_postgres() as db:
            rows = db.execute(
                "SELECT enabled FROM principal_credentials WHERE principal_id=ANY(%s)",
                ([impl_id, reviewer_id],),
            ).fetchall()
            assert rows == [(False,), (False,)]
            assert (
                db.execute(
                    "SELECT count(*) FROM events WHERE kind='principal.selfdev_cycle_role.revoked' "
                    "AND details->>'cycle_id'=%s",
                    (cycle,),
                ).fetchone()[0]
                == 2
            )


def test_production_cycle_issue_creates_only_pending_mtls_intents_and_revoke_is_atomic(monkeypatch):
    """Production route integration stays inert pending an independently reviewed verifier."""
    from fastapi import HTTPException

    # This integration test exercises repository wiring only; the production
    # signer/verifier availability gate remains false by default.
    import aao.work_management_api as api_module
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.selfdev_cycle_mtls import CycleMtlError
    from aao.selfdev_cycle_mtls_repository import PostgresCycleIntentRepository
    from aao.work_management_api import (
        AuthenticatedPrincipal,
        SelfDevCycleIssueRequest,
        issue_selfdev_cycle_roles,
        revoke_selfdev_cycle_roles,
    )
    monkeypatch.setattr(api_module, "_production_selfdev_cycle_mtls_ready", lambda: True)
    project, pm, token = _seed(monkeypatch)
    monkeypatch.setenv("AAO_ENV", "production")
    cycle = uuid4().hex
    # Models only the principal object produced after require_worker completed
    # server-verified mTLS. Bearer-only production rejection is tested separately.
    fingerprint = uuid4().hex + uuid4().hex
    principal = AuthenticatedPrincipal(
        pm, digest_token(token), "AGENT", workload_fingerprint=fingerprint
    )
    with connect_postgres() as db:
        db.execute(
            "INSERT INTO workload_identity_bindings"
            "(certificate_sha256,principal_id,enabled,expires_at) "
            "VALUES (%s,%s,true,clock_timestamp()+interval '1 hour')",
            (fingerprint, pm),
        )

    failed_cycle = uuid4().hex
    create_intent = PostgresCycleIntentRepository.create_intent_in_transaction

    def fail_intent(_db, _intent):
        raise CycleMtlError("test failure")

    monkeypatch.setattr(
        PostgresCycleIntentRepository, "create_intent_in_transaction", fail_intent,
    )
    with pytest.raises(HTTPException) as failure:
        issue_selfdev_cycle_roles(
            project,
            SelfDevCycleIssueRequest(cycle_id=failed_cycle, lifetime_seconds=600),
            principal,
        )
    assert failure.value.status_code == 503
    with connect_postgres() as db:
        assert db.execute(
            "SELECT count(*) FROM principal_credentials WHERE principal_id=ANY(%s)",
            ([f"aao-selfdev-impl-{failed_cycle}", f"aao-selfdev-review-{failed_cycle}"],),
        ).fetchone()[0] == 0

    monkeypatch.setattr(
        PostgresCycleIntentRepository, "create_intent_in_transaction", create_intent,
    )
    monkeypatch.setenv("AAO_ENV", "production")
    result = issue_selfdev_cycle_roles(
        project, SelfDevCycleIssueRequest(cycle_id=cycle, lifetime_seconds=600), principal,
    )
    assert result["cycle_id"] == cycle
    assert len(result["roles"]) == 2
    assert all(role["certificate_status"] == "pending_verifier" for role in result["roles"])
    assert all("token" not in role for role in result["roles"])
    assert {role["kind"] for role in result["roles"]} == {"AGENT", "AUDITOR"}
    replay = issue_selfdev_cycle_roles(
        project, SelfDevCycleIssueRequest(cycle_id=cycle, lifetime_seconds=600), principal,
    )
    assert replay["replayed"] is True
    assert {role["intent_id"] for role in replay["roles"]} == {
        role["intent_id"] for role in result["roles"]
    }

    # Pending intents reserve the H1b overlap slot despite disabled credentials.
    second_cycle = uuid4().hex
    issue_selfdev_cycle_roles(
        project,
        SelfDevCycleIssueRequest(cycle_id=second_cycle, lifetime_seconds=600),
        principal,
    )
    with pytest.raises(HTTPException) as cap_error:
        issue_selfdev_cycle_roles(
            project,
            SelfDevCycleIssueRequest(cycle_id=uuid4().hex, lifetime_seconds=600),
            principal,
        )
    assert cap_error.value.status_code == 409
    with connect_postgres() as db:
        db.execute(
            "UPDATE selfdev_cycle_mtls_intents "
            "SET not_before=clock_timestamp()-interval '2 seconds', "
            "not_after=clock_timestamp()-interval '1 second' "
            "WHERE project_id=%s AND cycle_id=%s",
            (project, cycle),
        )
    with pytest.raises(HTTPException) as expired_replay:
        issue_selfdev_cycle_roles(
            project, SelfDevCycleIssueRequest(cycle_id=cycle, lifetime_seconds=600), principal,
        )
    assert expired_replay.value.status_code == 409
    with connect_postgres() as db:
        rows = db.execute(
            "SELECT i.kind,i.state,c.enabled,i.principal_id "
            "FROM selfdev_cycle_mtls_intents i JOIN principal_credentials c USING(principal_id) "
            "WHERE i.project_id=%s AND i.cycle_id=%s ORDER BY i.kind",
            (project, cycle),
        ).fetchall()
        assert len(rows) == 2
        assert all(state == "PENDING" and enabled is False for _kind, state, enabled, _pid in rows)
        assert all(any(row[3] == role["principal_id"] for row in rows) for role in result["roles"])
        assert db.execute(
            "SELECT count(*) FROM host_worker_bindings WHERE worker_id=%s AND status='ACTIVE'",
            (f"aao-selfdev-impl-{cycle}",),
        ).fetchone()[0] == 0

    revoked = revoke_selfdev_cycle_roles(project, cycle, principal)
    assert revoked == {"cycle_id": cycle, "revoked": True, "already_revoked": False}
    with connect_postgres() as db:
        assert db.execute(
            "SELECT count(*) FROM selfdev_cycle_mtls_intents "
            "WHERE project_id=%s AND cycle_id=%s AND state='REVOKED'",
            (project, cycle),
        ).fetchone()[0] == 2
        assert db.execute(
            "SELECT count(*) FROM principal_credentials WHERE principal_id=ANY(%s) AND enabled",
            ([f"aao-selfdev-impl-{cycle}", f"aao-selfdev-review-{cycle}"],),
        ).fetchone()[0] == 0


def test_live_cycle_credential_expiry_rejects_authentication(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    with TestClient(app) as client:
        response = _issue(client, project, token, lifetime=1)
        assert response.status_code == 201, response.text
        impl = response.json()["roles"][0]
        time.sleep(1.1)
        denied = client.get("/v1/principals/me", headers={"X-Agent-Token": impl["token"]})
        assert denied.status_code == 403
        with connect_postgres() as db:
            expires = db.execute(
                "SELECT expires_at FROM principal_credentials WHERE principal_id=%s",
                (impl["principal_id"],),
            ).fetchone()[0]
            assert expires is not None
            assert (
                db.execute(
                    "SELECT enabled FROM principal_credentials WHERE principal_id=%s",
                    (impl["principal_id"],),
                ).fetchone()[0]
                is True
            )



def _counts(db, cycle):
    impl, reviewer = f"aao-selfdev-impl-{cycle}", f"aao-selfdev-review-{cycle}"
    ids = [impl, reviewer]
    return {
        "credentials": db.execute(
            "SELECT count(*) FROM principal_credentials WHERE principal_id=ANY(%s)", (ids,),
        ).fetchone()[0],
        "grants": db.execute(
            "SELECT count(*) FROM project_grants WHERE principal_id=ANY(%s)", (ids,),
        ).fetchone()[0],
        "bindings": db.execute(
            "SELECT count(*) FROM host_worker_bindings WHERE worker_id=ANY(%s)", (ids,),
        ).fetchone()[0],
        "profiles": db.execute(
            "SELECT count(*) FROM organization_profiles WHERE principal_id=ANY(%s)", (ids,),
        ).fetchone()[0],
        "events": db.execute(
            "SELECT count(*) FROM events WHERE details->>'cycle_id'=%s", (cycle,),
        ).fetchone()[0],
    }


def _seed_profile(principal_id, competencies=("python", "postgres")):
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        db.execute(
            "INSERT INTO organization_profiles(principal_id,display_name,role_title,competencies) "
            "VALUES (%s,'Self Development implementer','Implementer',%s)",
            (principal_id, list(competencies)),
        )


def _revoke(client, project, token, cycle):
    return client.delete(
        f"/v1/projects/{project}/selfdev-cycle-roles/{cycle}",
        headers={"X-Agent-Token": token},
    )


def test_live_issue_binds_host_and_inherits_project_profile_atomically(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    host_id = os.environ["AAO_TEST_HOST_ID"]
    with TestClient(app) as client:
        first = _issue(client, project, token)
        assert first.status_code == 201, first.text
        first_impl = first.json()["roles"][0]["principal_id"]
        first_reviewer = first.json()["roles"][1]["principal_id"]
        with connect_postgres() as db:
            assert db.execute(
                "SELECT host_id,status,fence_epoch FROM host_worker_bindings WHERE worker_id=%s",
                (first_impl,),
            ).fetchall() == [(host_id, "ACTIVE", 3)]
            assert db.execute(
                "SELECT 1 FROM host_worker_bindings WHERE worker_id=%s", (first_reviewer,),
            ).fetchone() is None
            issued = db.execute(
                "SELECT details FROM events WHERE kind='principal.selfdev_cycle_role.issued' "
                "AND details->>'principal_id'=%s", (first_impl,),
            ).fetchone()[0]
            assert issued["host_id"] == host_id

        # The CEO declares a profile for the current implementer; the next cycle inherits it.
        with connect_postgres() as db:
            db.execute("DELETE FROM organization_profiles WHERE principal_id=%s", (first_impl,))
        _seed_profile(first_impl, ("python", f"marker-{first_impl[-8:]}"))
        second = _issue(client, project, token)
        assert second.status_code == 201, second.text
        second_impl = second.json()["roles"][0]["principal_id"]
        with connect_postgres() as db:
            assert db.execute(
                "SELECT competencies,enabled FROM organization_profiles WHERE principal_id=%s",
                (second_impl,),
            ).fetchone() == (["python", f"marker-{first_impl[-8:]}"], True)
            assert db.execute(
                "SELECT details->>'profile_inherited_from' FROM events "
                "WHERE kind='principal.selfdev_cycle_role.issued' AND details->>'principal_id'=%s",
                (second_impl,),
            ).fetchone()[0] == first_impl
            assert db.execute(
                "SELECT 1 FROM organization_profiles WHERE principal_id=%s",
                (second.json()["roles"][1]["principal_id"],),
            ).fetchone() is None

        # Same cycle id again: 409 and nothing new anywhere.
        cycle = second.json()["cycle_id"]
        with connect_postgres() as db:
            before = _counts(db, cycle)
        assert _issue(client, project, token, cycle).status_code == 409
        with connect_postgres() as db:
            assert _counts(db, cycle) == before


@pytest.mark.parametrize(
    ("decoy", "is_source"),
    [
        ("expired-credential", True),
        ("disabled-credential", True),
        ("expired-grant", True),
        ("foreign-project", False),
        ("disabled-profile", False),
        ("no-project-read", False),
        ("prefixed-name", False),
        ("suffixed-name", False),
    ],
)
def test_live_issue_profile_source_ignores_credential_liveness(monkeypatch, decoy, is_source):
    """M3/A10: lineage survives expiry or revocation of the source's credential."""
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    principal_id = {
        "prefixed-name": f"x-aao-selfdev-impl-{uuid4().hex}",
        "suffixed-name": f"aao-selfdev-impl-{uuid4().hex}x",
    }.get(decoy, f"aao-selfdev-impl-{uuid4().hex}")
    grant_project = project
    with connect_postgres() as db:
        if decoy == "foreign-project":
            grant_project, mandate = str(uuid4()), str(uuid4())
            db.execute(
                "INSERT INTO mandates(id,title,objective,status,confirmed_by) "
                "VALUES (%s,'Other','Other','CONFIRMED','integration-test')", (mandate,),
            )
            db.execute(
                "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,%s,%s,'ACTIVE')",
                (grant_project, f"Other {uuid4().hex}", mandate),
            )
        # Future-dated created_at makes the decoy the newest candidate.
        db.execute(
            "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled,"
            "expires_at,created_at) VALUES (%s,'AGENT',%s,%s,clock_timestamp()+%s::interval,"
            "clock_timestamp()+interval '1 day')",
            (principal_id, digest_token(uuid4().hex), decoy != "disabled-credential",
             "-1 day" if decoy == "expired-credential" else "2 days"),
        )
        db.execute(
            "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
            "VALUES (%s,%s,%s,clock_timestamp()+%s::interval)",
            (principal_id, grant_project,
             "execution.claim" if decoy == "no-project-read" else "project.read",
             "-1 day" if decoy == "expired-grant" else "2 days"),
        )
    _seed_profile(principal_id, (f"marker-{decoy}",))
    if decoy == "disabled-profile":
        with connect_postgres() as db:
            db.execute("UPDATE organization_profiles SET enabled=false WHERE principal_id=%s",
                       (principal_id,))
    try:
        with TestClient(app) as client:
            response = _issue(client, project, token)
            assert response.status_code == 201, response.text
            impl = response.json()["roles"][0]["principal_id"]
        with connect_postgres() as db:
            inherited = db.execute(
                "SELECT details->>'profile_inherited_from' FROM events "
                "WHERE kind='principal.selfdev_cycle_role.issued' "
                "AND details->>'principal_id'=%s", (impl,),
            ).fetchone()[0]
            competencies = db.execute(
                "SELECT competencies FROM organization_profiles WHERE principal_id=%s", (impl,),
            ).fetchone()
        if is_source:
            assert inherited == principal_id
            assert competencies == ([f"marker-{decoy}"],)
        else:
            assert inherited != principal_id
            assert competencies is None or f"marker-{decoy}" not in competencies[0]
    finally:
        # Do not leave a future-dated decoy that would shadow later tests' sources.
        with connect_postgres() as db:
            db.execute("UPDATE organization_profiles SET enabled=false WHERE principal_id=%s",
                       (principal_id,))
            db.execute("UPDATE principal_credentials SET created_at=clock_timestamp(),"
                       "enabled=false WHERE principal_id=%s", (principal_id,))


def _disable_all_cycle_profiles():
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        db.execute("UPDATE organization_profiles SET enabled=false "
                   "WHERE principal_id ~ 'selfdev-impl-' AND enabled")


def test_live_issue_never_copies_the_pm_coordinator_profile(monkeypatch):
    """A4: with no implementer source, the PM's own profile is never inherited."""
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, pm, token = _seed(monkeypatch)
    _disable_all_cycle_profiles()
    with connect_postgres() as db:
        # The PM passes every other predicate: AGENT, enabled, project.read, newest.
        db.execute(
            "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
            "VALUES (%s,%s,'project.read',clock_timestamp()+interval '1 hour')", (pm, project),
        )
        db.execute("UPDATE principal_credentials SET created_at=clock_timestamp()+interval "
                   "'1 day' WHERE principal_id=%s", (pm,))
    _seed_profile(pm, ("pm-only-competency",))
    try:
        with TestClient(app) as client:
            response = _issue(client, project, token)
            assert response.status_code == 201, response.text
            impl = response.json()["roles"][0]["principal_id"]
        with connect_postgres() as db:
            assert db.execute(
                "SELECT 1 FROM organization_profiles WHERE principal_id=%s", (impl,),
            ).fetchone() is None
            assert db.execute(
                "SELECT details->>'profile_inherited_from' FROM events "
                "WHERE kind='principal.selfdev_cycle_role.issued' "
                "AND details->>'principal_id'=%s", (impl,),
            ).fetchone()[0] is None
    finally:
        with connect_postgres() as db:
            db.execute("UPDATE organization_profiles SET enabled=false WHERE principal_id=%s",
                       (pm,))
            db.execute("UPDATE principal_credentials SET created_at=clock_timestamp() "
                       "WHERE principal_id=%s", (pm,))


def test_live_concurrency_cap_allows_renewal_and_frees_on_revoke_and_expiry(monkeypatch):
    """H1b: N+1 while N is valid succeeds; a third live cycle is refused."""
    from aao.work_management_api import SELFDEV_CYCLE_CONCURRENT_CAP, app

    assert SELFDEV_CYCLE_CONCURRENT_CAP == 2
    project, _pm, token = _seed(monkeypatch)
    with TestClient(app) as client:
        first = _issue(client, project, token)
        assert first.status_code == 201, first.text
        renewal = _issue(client, project, token)
        assert renewal.status_code == 201, renewal.text
        refused = _issue(client, project, token)
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"]["code"] == "SELFDEV_CYCLE_CONCURRENCY_CAP"

        # Revoking N frees its slot.
        assert _revoke(client, project, token, first.json()["cycle_id"]).status_code == 200
        short = _issue(client, project, token, lifetime=1)
        assert short.status_code == 201, short.text
        assert _issue(client, project, token).json()["detail"]["code"] == (
            "SELFDEV_CYCLE_CONCURRENCY_CAP"
        )
        # Expiry frees it as well.
        time.sleep(1.1)
        after_expiry = _issue(client, project, token)
        assert after_expiry.status_code == 201, after_expiry.text


def _seed_issued_events(pm, count, *, kind="AGENT", age="0 hours"):
    from aao.postgresql_connection import connect_postgres

    with connect_postgres() as db:
        for _ in range(count):
            db.execute(
                "INSERT INTO events(id,subject_id,kind,details,created_at) "
                "VALUES (%s,%s,'principal.selfdev_cycle_role.issued',%s::jsonb,"
                "now()-%s::interval)",
                (str(uuid4()), str(uuid4()), json.dumps({
                    "cycle_id": uuid4().hex, "kind": kind, "issuer_principal_id": pm,
                }), age),
            )


def test_live_issuance_daily_cap_is_per_pm_principal_and_rolling(monkeypatch):
    from aao.work_management_api import SELFDEV_CYCLE_ISSUANCE_DAILY_CAP, app

    assert SELFDEV_CYCLE_ISSUANCE_DAILY_CAP == 24
    project, pm, token = _seed(monkeypatch)
    _project, _other, other_token = _seed(monkeypatch)
    _seed_issued_events(pm, SELFDEV_CYCLE_ISSUANCE_DAILY_CAP - 2, age="23 hours")
    _seed_issued_events(pm, SELFDEV_CYCLE_ISSUANCE_DAILY_CAP, kind="AUDITOR")  # one per cycle
    _seed_issued_events(pm, 5, age="25 hours")  # outside the rolling window
    with TestClient(app) as client:
        for _ in range(2):  # the 23rd and 24th issuance in 24 h
            response = _issue(client, project, token)
            assert response.status_code == 201, response.text
            assert _revoke(client, project, token, response.json()["cycle_id"]).status_code == 200
        refused = _issue(client, project, token)
        assert refused.status_code == 429, refused.text
        assert refused.json()["detail"]["code"] == "SELFDEV_CYCLE_ISSUANCE_DAILY_CAP"
        assert _issue(client, project, other_token).status_code == 201


def test_live_issue_retires_expired_unrevoked_cycle_after_copying_profile(monkeypatch):
    """M3: an expired, never-revoked cycle keeps lineage and loses its host binding."""
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    _disable_all_cycle_profiles()
    with TestClient(app) as client:
        old = _issue(client, project, token, lifetime=1)
        assert old.status_code == 201, old.text
        old_impl, old_reviewer = (role["principal_id"] for role in old.json()["roles"])
        _seed_profile(old_impl, ("python", "lineage-after-gap"))
        time.sleep(1.1)  # gap: N expired with no successor and no revoke
        new = _issue(client, project, token)
        assert new.status_code == 201, new.text
        new_impl = new.json()["roles"][0]["principal_id"]
    with connect_postgres() as db:
        assert db.execute(
            "SELECT competencies,enabled FROM organization_profiles WHERE principal_id=%s",
            (new_impl,),
        ).fetchone() == (["python", "lineage-after-gap"], True)
        assert db.execute(
            "SELECT status FROM host_worker_bindings WHERE worker_id=%s", (old_impl,),
        ).fetchone()[0] == "FENCED"
        assert db.execute(
            "SELECT status FROM host_worker_bindings WHERE worker_id=%s", (new_impl,),
        ).fetchone()[0] == "ACTIVE"
        assert db.execute(
            "SELECT bool_or(enabled) FROM principal_credentials WHERE principal_id=ANY(%s)",
            ([old_impl, old_reviewer],),
        ).fetchone()[0] is False
        details = db.execute(
            "SELECT details FROM events WHERE kind='principal.selfdev_cycle_role.expired_retired' "
            "AND details->>'principal_id'=%s", (old_impl,),
        ).fetchone()[0]
        assert details["host_bindings_retired"] == 1 and details["profile_disabled"] is True


def test_live_revoke_fails_closed_when_binding_stays_active(monkeypatch):
    """A2: if 041 refuses to retire the binding, revoke is 503 and rolls back."""
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    with TestClient(app) as client:
        response = _issue(client, project, token)
        assert response.status_code == 201, response.text
        cycle = response.json()["cycle_id"]
        impl = response.json()["roles"][0]["principal_id"]
        with connect_postgres() as db:
            # Same capability set (revoke's own check passes), but 041's exact
            # grant/credential expiry match now fails, so it retires nothing.
            db.execute(
                "UPDATE project_grants SET expires_at=expires_at-interval '1 second' "
                "WHERE principal_id=%s AND capability='work.create'", (impl,),
            )
        denied = _revoke(client, project, token, cycle)
        assert denied.status_code == 503, denied.text
    with connect_postgres() as db:
        assert db.execute(
            "SELECT status FROM host_worker_bindings WHERE worker_id=%s", (impl,),
        ).fetchone()[0] == "ACTIVE"
        assert db.execute(
            "SELECT bool_and(enabled) FROM principal_credentials WHERE principal_id=ANY(%s)",
            ([impl, f"aao-selfdev-review-{cycle}"],),
        ).fetchone()[0] is True
        assert db.execute(
            "SELECT count(*) FROM events WHERE kind='principal.selfdev_cycle_role.revoked' "
            "AND details->>'cycle_id'=%s", (cycle,),
        ).fetchone()[0] == 0
        db.execute("UPDATE principal_credentials SET enabled=false WHERE principal_id=ANY(%s)",
                   ([impl, f"aao-selfdev-review-{cycle}"],))


@pytest.mark.parametrize("failure", ["fenced-host", "stray-binding"])
def test_live_issue_failure_after_credentials_leaves_nothing(monkeypatch, failure):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    host_id = os.environ["AAO_TEST_HOST_ID"]
    cycle = uuid4().hex
    with connect_postgres() as db:
        if failure == "fenced-host":
            db.execute("UPDATE host_worker_bindings SET status='FENCED' WHERE host_id=%s",
                       (host_id,))
        else:
            db.execute(
                "INSERT INTO host_worker_bindings(host_id,worker_id,status,fence_epoch) "
                "VALUES (%s,%s,'ACTIVE',1)",
                (f"other-{uuid4().hex}", f"aao-selfdev-impl-{cycle}"),
            )
    with TestClient(app) as client:
        response = _issue(client, project, token, cycle)
        assert response.status_code == 409, response.text
    with connect_postgres() as db:
        expected_bindings = 0 if failure == "fenced-host" else 1
        assert _counts(db, cycle) == {"credentials": 0, "grants": 0,
                                      "bindings": expected_bindings,
                                      "profiles": 0, "events": 0}


def test_live_issue_refuses_cross_project_and_inactive_project(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import SELFDEV_CYCLE_ISSUER_CAPABILITY, SELFDEV_PROJECT_NAME, app

    _project, pm, token = _seed(monkeypatch)
    targets = []
    with connect_postgres() as db:
        for name, state in ((f"Other {uuid4().hex}", "ACTIVE"), (SELFDEV_PROJECT_NAME, "PAUSED")):
            target, mandate = str(uuid4()), str(uuid4())
            db.execute(
                "INSERT INTO mandates(id,title,objective,status,confirmed_by) "
                "VALUES (%s,'T','T','CONFIRMED','integration-test')", (mandate,),
            )
            db.execute(
                "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,%s,%s,%s)",
                (target, name, mandate, state),
            )
            for cap in ("work.coordinate", SELFDEV_CYCLE_ISSUER_CAPABILITY):
                db.execute(
                    "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
                    "VALUES (%s,%s,%s,clock_timestamp()+interval '1 hour')", (pm, target, cap),
                )
            targets.append(target)
    with TestClient(app) as client:
        for target in targets:
            cycle = uuid4().hex
            response = _issue(client, target, token, cycle)
            assert response.status_code == 409, response.text
            with connect_postgres() as db:
                assert set(_counts(db, cycle).values()) == {0}


def test_live_revoke_cleans_up_and_escalates_assigned_work(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    project, pm, token = _seed(monkeypatch)
    with TestClient(app) as client:
        response = _issue(client, project, token)
        assert response.status_code == 201, response.text
        cycle = response.json()["cycle_id"]
        impl = response.json()["roles"][0]["principal_id"]
        with connect_postgres() as db:
            db.execute("DELETE FROM organization_profiles WHERE principal_id=%s", (impl,))
        _seed_profile(impl)
        work_id = str(uuid4())
        valid_coordinator = f"aao-coordinator-valid-{uuid4().hex}"
        expired_coordinator = f"aao-coordinator-expired-{uuid4().hex}"
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO work_items(id,project_id,title,status,author_id,acceptance_criteria) "
                "VALUES (%s,%s,'Assigned child','READY',%s,'[]'::jsonb)", (work_id, project, pm),
            )
            db.execute(
                "INSERT INTO work_item_assignments(project_id,work_id,principal_id,assigned_by) "
                "VALUES (%s,%s,%s,%s)", (project, work_id, impl, pm),
            )
            for coordinator, credential_expired in (
                (valid_coordinator, False), (expired_coordinator, True),
            ):
                db.execute(
                    "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled,expires_at) "
                    "VALUES (%s,'AGENT',%s,true,CASE WHEN %s THEN "
                    "clock_timestamp()-interval '1 second' ELSE "
                    "clock_timestamp()+interval '1 hour' END)",
                    (coordinator, digest_token(uuid4().hex), credential_expired),
                )
                db.execute(
                    "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
                    "VALUES (%s,%s,'work.assign',clock_timestamp()+interval '1 hour')",
                    (coordinator, project),
                )
        revoked = _revoke(client, project, token, cycle)
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["already_revoked"] is False
        with connect_postgres() as db:
            assert db.execute(
                "SELECT status,fenced_at IS NOT NULL,fence_epoch FROM host_worker_bindings "
                "WHERE worker_id=%s", (impl,),
            ).fetchone() == ("FENCED", True, 3)
            # The host itself and its administrator-registered worker stay untouched.
            assert db.execute(
                "SELECT count(*) FROM host_worker_bindings WHERE host_id=%s AND status='ACTIVE'",
                (os.environ["AAO_TEST_HOST_ID"],),
            ).fetchone()[0] == 1
            assert db.execute(
                "SELECT enabled FROM organization_profiles WHERE principal_id=%s", (impl,),
            ).fetchone()[0] is False
            blocked = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.dispatch_blocked'",
                (work_id,),
            ).fetchall()
            assert len(blocked) == 1
            assert blocked[0][0]["principal_id"] == impl
            assert blocked[0][0]["actor"] == pm
            assert valid_coordinator in blocked[0][0]["next_actor_principal_ids"]
            assert expired_coordinator not in blocked[0][0]["next_actor_principal_ids"]
            assert db.execute(
                "SELECT started_by FROM protocol_instances WHERE subject_id=%s "
                "AND protocol_id='blockage-escalation'", (work_id,),
            ).fetchone()[0] == pm
            details = db.execute(
                "SELECT details FROM events WHERE kind='principal.selfdev_cycle_role.revoked' "
                "AND details->>'principal_id'=%s", (impl,),
            ).fetchone()[0]
            assert details["host_bindings_retired"] == 1
            assert details["profile_disabled"] is True
            # Simulate legacy/interrupted cleanup: credentials remain revoked,
            # but an ACTIVE binding and enabled profile need repair.
            db.execute(
                "UPDATE host_worker_bindings SET status='ACTIVE',fenced_at=NULL WHERE worker_id=%s",
                (impl,),
            )
            db.execute(
                "UPDATE organization_profiles SET enabled=true WHERE principal_id=%s", (impl,),
            )
        again = _revoke(client, project, token, cycle)
        assert again.status_code == 200 and again.json()["already_revoked"] is True
        with connect_postgres() as db:
            assert db.execute(
                "SELECT status,fenced_at IS NOT NULL FROM host_worker_bindings WHERE worker_id=%s",
                (impl,),
            ).fetchone() == ("FENCED", True)
            assert db.execute(
                "SELECT enabled FROM organization_profiles WHERE principal_id=%s", (impl,),
            ).fetchone()[0] is False
            assert db.execute(
                "SELECT count(*) FROM events WHERE subject_id=%s AND kind='work.dispatch_blocked'",
                (work_id,),
            ).fetchone()[0] == 1
            assert db.execute(
                "SELECT count(*) FROM events WHERE kind='principal.selfdev_cycle_role.retirement_repaired' "
                "AND details->>'principal_id'=%s", (impl,),
            ).fetchone()[0] == 1


def test_live_revoke_never_issued_is_404_and_partial_set_is_409(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import app

    project, _pm, token = _seed(monkeypatch)
    with TestClient(app) as client:
        missing = _revoke(client, project, token, uuid4().hex)
        assert missing.status_code == 404, missing.text
        assert missing.json()["detail"]["code"] == "CYCLE_NOT_FOUND"
        # A credential with no grants is not "never issued": still a 409 conflict.
        cycle = uuid4().hex
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled) "
                "VALUES (%s,'AGENT',%s,true)",
                (f"aao-selfdev-impl-{cycle}", digest_token(uuid4().hex)),
            )
        assert _revoke(client, project, token, cycle).status_code == 409


def test_insert_only_binding_needs_no_update_privilege(monkeypatch):
    """The API role holds SELECT, INSERT only; ON CONFLICT DO UPDATE would need UPDATE."""
    import psycopg

    from aao.backup import register_host_worker
    from aao.postgresql_connection import connect_postgres

    _seed(monkeypatch)
    host_id = os.environ["AAO_TEST_HOST_ID"]
    role = f"aao_runtime_probe_{uuid4().hex[:12]}"
    with connect_postgres() as db:
        db.execute(f"CREATE ROLE {role} NOLOGIN")
        db.execute(f"GRANT SELECT, INSERT ON host_worker_bindings TO {role}")
        # As in apply_api_grants.sql; information_schema only lists visible columns.
        db.execute(f"GRANT SELECT ON execution_queue, project_conversation_turns TO {role}")
    try:
        with connect_postgres() as db:
            db.execute(f"SET LOCAL ROLE {role}")
            register_host_worker(db, host_id, f"aao-selfdev-impl-{uuid4().hex}",
                                 new_worker_only=True)
            db.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connect_postgres() as db:
            db.execute(f"SET LOCAL ROLE {role}")
            register_host_worker(db, host_id, f"aao-selfdev-impl-{uuid4().hex}")
    finally:
        with connect_postgres() as db:
            db.execute(f"REVOKE ALL ON host_worker_bindings, execution_queue, "
                       f"project_conversation_turns FROM {role}")
            db.execute(f"DROP ROLE {role}")


def test_retire_function_only_retires_disabled_cycle_implementers(monkeypatch):
    """Migration 041 scopes retirement to a disabled, valid Self Development cycle."""
    import psycopg

    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import SELFDEV_IMPLEMENTER_GRANTS

    project_id, _pm_id, _pm_token = _seed(monkeypatch)
    host_id = os.environ["AAO_TEST_HOST_ID"]
    enabled_impl = f"aao-selfdev-impl-{uuid4().hex}"
    disabled_impl = f"aao-selfdev-impl-{uuid4().hex}"
    unscoped_impl = f"aao-selfdev-impl-{uuid4().hex}"
    long_ttl_impl = f"aao-selfdev-impl-{uuid4().hex}"
    wrong_project_impl = f"aao-selfdev-impl-{uuid4().hex}"
    other = f"other-worker-{uuid4().hex}"
    role = f"aao_runtime_probe_{uuid4().hex[:12]}"
    with connect_postgres() as db:
        other_project, other_mandate = str(uuid4()), str(uuid4())
        db.execute(
            "INSERT INTO mandates(id,title,objective,status,confirmed_by) "
            "VALUES (%s,'Other','Other','CONFIRMED','integration-test')", (other_mandate,),
        )
        db.execute(
            "INSERT INTO projects(id,name,mandate_id,state) VALUES (%s,%s,%s,'ACTIVE')",
            (other_project, f"Other {uuid4().hex}", other_mandate),
        )
        workers = (enabled_impl, disabled_impl, unscoped_impl, long_ttl_impl,
                   wrong_project_impl, other)
        for worker in workers:
            enabled = worker == enabled_impl
            db.execute(
                "INSERT INTO principal_credentials(principal_id,kind,token_digest,enabled,expires_at) "
                "VALUES (%s,'AGENT',%s,%s,clock_timestamp()+CASE WHEN %s THEN "
                "interval '3 hours' ELSE interval '1 hour' END)",
                (worker, digest_token(uuid4().hex), enabled, worker == long_ttl_impl),
            )
            db.execute(
                "INSERT INTO host_worker_bindings(host_id,worker_id,status,fence_epoch) "
                "VALUES (%s,%s,'ACTIVE',3)", (host_id, worker),
            )
        for worker, grant_project in (
            (disabled_impl, project_id),
            (long_ttl_impl, project_id),
            (wrong_project_impl, other_project),
        ):
            db.execute(
                "INSERT INTO project_grants(principal_id,project_id,capability,expires_at) "
                "SELECT %s,%s,capability,(SELECT expires_at FROM principal_credentials "
                "WHERE principal_id=%s) FROM unnest(%s::text[]) AS capability",
                (worker, grant_project, worker, list(SELFDEV_IMPLEMENTER_GRANTS)),
            )
        db.execute(f"CREATE ROLE {role} NOLOGIN")
        db.execute(f"GRANT EXECUTE ON FUNCTION retire_selfdev_cycle_host_binding(text, uuid) TO {role}")
    try:
        with connect_postgres() as db:
            db.execute(f"SET LOCAL ROLE {role}")
            results = [
                db.execute("SELECT retire_selfdev_cycle_host_binding(%s,%s)",
                           (worker, project_id)).fetchone()[0]
                for worker in (enabled_impl, other, unscoped_impl, long_ttl_impl,
                               wrong_project_impl, disabled_impl, disabled_impl)
            ]
            assert results == [0, 0, 0, 0, 0, 1, 0]
        with pytest.raises(psycopg.errors.InsufficientPrivilege), connect_postgres() as db:
            db.execute(f"SET LOCAL ROLE {role}")
            db.execute("UPDATE host_worker_bindings SET status='ACTIVE' WHERE worker_id=%s",
                       (disabled_impl,))
        with connect_postgres() as db:
            rows = dict(db.execute(
                "SELECT worker_id,status||':'||fence_epoch FROM host_worker_bindings "
                "WHERE worker_id=ANY(%s)", ([*workers],),
            ).fetchall())
            assert rows == {worker: ("FENCED:3" if worker == disabled_impl else "ACTIVE:3")
                            for worker in workers}
    finally:
        with connect_postgres() as db:
            db.execute(
                f"REVOKE ALL ON FUNCTION retire_selfdev_cycle_host_binding(text, uuid) FROM {role}"
            )
            db.execute(f"DROP ROLE {role}")
