"""Durable routines use canonical work and an explicitly disposable PostgreSQL DB."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)


@pytest.fixture
def context(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "routine-test-ceo")
    ceo = {"X-CEO-Token": "routine-test-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Routines " + uuid4().hex, "objective": "Authorized recurring work",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Routines", "mandate_id": mandate,
        }).json()["id"]
        principal = "routine-worker-" + uuid4().hex[:12]
        token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        }).json()["token"]
        worker = {"X-Agent-Token": token}
        yield client, ceo, project, principal, worker, connect_postgres


def template():
    return {
        "idempotency_key": str(uuid4()), "title": "Review project status",
        "description": "Produce a factual report", "acceptance_criteria": ["Cite real work"],
        "interval_seconds": 3600,
        "first_run_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
    }


def grant(client, ceo, project, principal, capability):
    assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
        "principal_id": principal, "capability": capability,
    }).status_code == 201


def test_routine_is_ceo_authorized_persistent_and_idempotent(context):
    client, ceo, project, principal, worker, connect = context
    url = f"/v1/projects/{project}/routines"
    body = template()
    assert client.post(url, headers=worker, json=body).status_code == 403
    made = client.post(url, headers=ceo, json=body)
    assert made.status_code == 201, made.text
    routine = made.json()
    assert routine["created"] is True
    assert client.post(url, headers=ceo, json=body).json() == {**routine, "created": False}
    assert client.post(url, headers=ceo, json={**body, "title": "Changed"}).status_code == 409
    assert client.get(url, headers=worker).status_code == 403
    grant(client, ceo, project, principal, "project.read")
    rows = client.get(url, headers=worker).json()
    assert rows[0]["id"] == routine["id"]
    assert rows[0]["template"]["title"] == body["title"]
    with connect() as db:
        assert db.execute("SELECT count(*) FROM work_items WHERE project_id=%s", (project,)).fetchone()[0] == 0


def test_tick_rechecks_grants_coalesces_missed_periods_and_survives_restart(context):
    client, ceo, project, principal, worker, connect = context
    body = template()
    made = client.post(f"/v1/projects/{project}/routines", headers=ceo, json=body)
    assert made.status_code == 201, made.text
    url = f"/v1/agent/projects/{project}/routines/materialize"
    assert client.post(url, headers=worker).status_code == 403
    grant(client, ceo, project, principal, "work.create")
    tick = client.post(url, headers=worker)
    assert tick.status_code == 200, tick.text
    rows = tick.json()["materialized"]
    assert len(rows) == 1
    work_id = rows[0]["work_id"]
    # A fresh API client reads persisted next_run_at; this is not an OS process restart test.
    with TestClient(client.app) as restarted:
        assert restarted.post(url, headers=worker).json() == {"materialized": []}
    with connect() as db:
        work = db.execute("SELECT status,author_id,title,due_date FROM work_items WHERE id=%s", (work_id,)).fetchone()
        assert work[:3] == ("INBOX", principal, body["title"])
        assert work[3] == datetime.fromisoformat(body["first_run_at"]).date()
        assert db.execute("SELECT count(*) FROM execution_queue WHERE work_id=%s", (work_id,)).fetchone()[0] == 0
        details = db.execute("SELECT details FROM events WHERE subject_id=%s AND kind='routine.materialized'", (work_id,)).fetchone()[0]
        assert details["principal_id"] == principal
        assert details["authorized_by"] == "ceo"
        assert details["missed_periods_coalesced"] == 3
        assert details["execution_authorized"] is False
        assert db.execute("SELECT count(*) FROM protocol_instances WHERE subject_id=%s", (work_id,)).fetchone()[0] == 1
        db.execute("UPDATE project_routines SET next_run_at=clock_timestamp()-interval '1 minute' WHERE project_id=%s", (project,))
        db.commit()
    assert client.delete(f"/v1/projects/{project}/grants/{principal}/work.create", headers=ceo).status_code == 204
    assert client.post(url, headers=worker).status_code == 403
    grant(client, ceo, project, principal, "work.create")
    assert client.post(url, headers={"X-Agent-Token": "invalid"}).status_code == 403
    assert len(client.post(url, headers=worker).json()["materialized"]) == 1


def test_disable_future_and_inactive_project_do_not_materialize(context):
    client, ceo, project, principal, worker, connect = context
    grant(client, ceo, project, principal, "work.create")
    body = template()
    body["first_run_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    routine = client.post(f"/v1/projects/{project}/routines", headers=ceo, json=body).json()["id"]
    url = f"/v1/agent/projects/{project}/routines/materialize"
    assert client.post(url, headers=worker).json() == {"materialized": []}
    update = f"/v1/projects/{project}/routines/{routine}"
    assert client.patch(update, headers=worker, json={"enabled": False}).status_code == 403
    assert client.patch(update, headers=ceo, json={"enabled": False}).status_code == 200
    with connect() as db:
        db.execute("UPDATE project_routines SET next_run_at=clock_timestamp()-interval '1 minute' WHERE id=%s", (routine,))
        db.commit()
    assert client.post(url, headers=worker).json() == {"materialized": []}
    assert client.patch(update, headers=ceo, json={"enabled": True}).status_code == 200
    # Actual lifecycle API, not a synthetic project state.
    assert client.post(f"/v1/projects/{project}/state", headers=ceo, json={"action": "pause"}).status_code == 200
    assert client.post(url, headers=worker).status_code == 409
    assert client.post(f"/v1/projects/{project}/routines", headers=ceo, json=template()).status_code == 409


def test_materialization_atomic_rollback_and_concurrent_ticks(context, monkeypatch):
    from aao import work_management_api as api

    client, ceo, project, principal, worker, connect = context
    grant(client, ceo, project, principal, "work.create")
    routine = client.post(f"/v1/projects/{project}/routines", headers=ceo, json=template())
    assert routine.status_code == 201, routine.text
    original_audit = api.audit

    def fail(db, subject, kind, details):
        if kind == "routine.materialized":
            raise RuntimeError("injected interruption before commit")
        return original_audit(db, subject, kind, details)

    url = f"/v1/agent/projects/{project}/routines/materialize"
    monkeypatch.setattr(api, "audit", fail)
    with pytest.raises(RuntimeError, match="injected interruption"):
        client.post(url, headers=worker)
    with connect() as db:
        assert db.execute("SELECT count(*) FROM work_items WHERE project_id=%s", (project,)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM routine_occurrences WHERE routine_id=%s", (routine.json()["id"],)).fetchone()[0] == 0
    monkeypatch.setattr(api, "audit", original_audit)

    def tick(_):
        with TestClient(api.app) as other:
            response = other.post(url, headers=worker)
            assert response.status_code == 200, response.text
            return len(response.json()["materialized"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(tick, range(2))) == [0, 1]
    with connect() as db:
        assert db.execute("SELECT count(*) FROM work_items WHERE project_id=%s", (project,)).fetchone()[0] == 1


def test_routine_rejects_ambiguous_time_and_empty_template(context):
    client, ceo, project, *_ = context
    body = template()
    url = f"/v1/projects/{project}/routines"
    for change in ({"first_run_at": "2026-10-26T12:00:00"}, {"title": " "},
                   {"acceptance_criteria": [" "]}, {"interval_seconds": 0}):
        assert client.post(url, headers=ceo, json={**body, **change}).status_code == 422


def test_project_pause_serializes_after_the_materialization_transaction(context, monkeypatch):
    import time
    from threading import Event

    from aao import work_management_api as api

    client, ceo, project, principal, worker, connect = context
    grant(client, ceo, project, principal, "work.create")
    assert client.post(f"/v1/projects/{project}/routines", headers=ceo, json=template()).status_code == 201
    entered, release = Event(), Event()
    held_pid = []
    original_audit = api.audit

    def hold_tick(db, subject, kind, details):
        if kind == "routine.materialized":
            held_pid.append(db.execute("SELECT pg_backend_pid()").fetchone()[0])
            entered.set()
            assert release.wait(10), "test did not release held tick"
        return original_audit(db, subject, kind, details)

    monkeypatch.setattr(api, "audit", hold_tick)

    def tick():
        with TestClient(api.app) as other:
            return other.post(f"/v1/agent/projects/{project}/routines/materialize", headers=worker)

    def pause():
        with TestClient(api.app) as other:
            return other.post(f"/v1/projects/{project}/state", headers=ceo, json={"action": "pause"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(tick)
        try:
            assert entered.wait(5)
            # SKIP LOCKED must skip the still-uncommitted due routine, not duplicate it.
            assert client.post(f"/v1/agent/projects/{project}/routines/materialize", headers=worker).json() == {"materialized": []}
            suspended = pool.submit(pause)
            deadline = time.monotonic() + 5
            blocked = False
            while time.monotonic() < deadline:
                with connect() as db:
                    blocked = db.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE %s=ANY(pg_blocking_pids(pid)))",
                        (held_pid[0],),
                    ).fetchone()[0]
                if blocked:
                    break
                time.sleep(0.01)
            assert blocked, "no PostgreSQL lock wait observed for project pause"
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
        assert suspended.result(timeout=10).status_code == 200
    assert client.post(f"/v1/agent/projects/{project}/routines/materialize", headers=worker).status_code == 409
