"""Real API + PostgreSQL tests for the narrowly scoped Self Development issuer."""

from __future__ import annotations

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


def _seed(monkeypatch, *, pm_caps=None):
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import SELFDEV_CYCLE_ISSUER_CAPABILITY, SELFDEV_PROJECT_NAME

    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
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
