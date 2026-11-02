import os
import tempfile

from fastapi.testclient import TestClient

from aao.policy import Verdict, authorize


def test_constitution_blocks_reserved_without_confirmed_ceo():
    assert authorize("project.create", is_ceo=False, confirmed_mandate=False).verdict == Verdict.REQUIRES_CEO
    assert authorize("constitution.change", is_ceo=True, confirmed_mandate=False).verdict == Verdict.REQUIRES_CEO
    assert authorize("ceo.impersonate", is_ceo=True, confirmed_mandate=True).verdict == Verdict.DENY
    assert authorize("repository.read", is_ceo=False, confirmed_mandate=False, permitted=False).verdict == Verdict.DENY
    assert authorize("repository.read", is_ceo=False, confirmed_mandate=False, permitted=True).verdict == Verdict.ALLOW
    assert authorize("repository.read", is_ceo=False, confirmed_mandate=False, permitted=True, residual_risk="high").verdict == Verdict.REQUIRES_CEO


def test_mandate_and_kanban_gates():
    with tempfile.TemporaryDirectory() as tmp:
        import aao.sqlite_api as main
        main.DB_PATH = os.path.join(tmp, "test.db")
        main.CEO_TOKEN = "test-ceo-secret"
        main.WORK_TOKEN = "test-worker-secret"
        main.REVIEW_TOKEN = "test-review-secret"
        with TestClient(main.app) as client:
            headers = {"X-CEO-Token": "test-ceo-secret"}
            worker_headers = {"X-Work-Token": "test-worker-secret"}
            assert client.post("/v1/mandates", json={"title": "Pilot", "objective": "Test core"}).status_code == 403
            mandate = client.post("/v1/mandates", json={"title": "Pilot", "objective": "Test core"}, headers=headers).json()["id"]
            assert client.post("/v1/projects", json={"name": "Pilot", "mandate_id": mandate}).status_code == 403
            assert client.post(f"/v1/mandates/{mandate}/confirm").status_code == 403
            assert client.post(f"/v1/mandates/{mandate}/confirm", headers=headers).status_code == 200
            r = client.post("/v1/projects", json={"name": "Pilot", "mandate_id": mandate}, headers=headers)
            assert r.status_code == 201
            project = r.json()["id"]
            for cap, principal in [("work.create", "development-worker"), ("work.transition", "development-worker"), ("work.review", "development-auditor")]:
                assert client.post(f"/v1/projects/{project}/grants", headers=headers, json={"principal_id": principal, "capability": cap}).status_code == 201
            assert client.post(f"/v1/projects/{project}/work", json={"title":"First task","acceptance_criteria":["Output checked"],"author_id":"engineer-1"}).status_code == 403
            work = client.post(f"/v1/projects/{project}/work", json={"title":"First task","acceptance_criteria":["Output checked"],"author_id":"engineer-1"}, headers=worker_headers).json()["id"]
            assert client.post(f"/v1/work/{work}/transition", json={"status": "DONE"}, headers=worker_headers).status_code == 409
            for status in ("READY", "IN_PROGRESS", "IN_REVIEW"):
                assert client.post(f"/v1/work/{work}/transition", json={"status": status}, headers=worker_headers).status_code == 200
            assert client.post(f"/v1/work/{work}/transition", json={"status": "VERIFIED", "evidence":["example"]}, headers=worker_headers).status_code == 409
            reviewer = {"X-Review-Token": "test-review-secret"}
            assert client.post(f"/v1/work/{work}/reviews", json={"reviewer_id":"engineer-1","decision":"APPROVE","evidence":["proof"]},headers=reviewer).status_code == 409
            approval = client.post(f"/v1/work/{work}/reviews", json={"reviewer_id":"development-auditor","decision":"APPROVE","evidence":["proof"]},headers=reviewer)
            assert approval.status_code == 409
            with main.connection(main.DB_PATH) as db:
                assert db.execute(
                    "SELECT count(*) FROM reviews WHERE work_id=? AND decision='APPROVE'",
                    (work,),
                ).fetchone()[0] == 0
            assert client.post(f"/v1/work/{work}/transition", json={"status":"DONE","evidence":["done"]}, headers=worker_headers).status_code == 409
            assert client.get(f"/v1/projects/{project}/board").json()[0]["status"] == "IN_REVIEW"
            with main.transaction(main.DB_PATH) as db:
                db.execute("UPDATE work_items SET status='VERIFIED' WHERE id=?", (work,))
                db.execute(
                    "INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence) "
                    "VALUES ('legacy-review',?,'legacy-auditor','APPROVE','[\"unverified\"]')",
                    (work,),
                )
            assert client.post(f"/v1/work/{work}/transition", json={"status":"DONE","evidence":["done"]}, headers=worker_headers).status_code == 409
            assert client.get(f"/v1/projects/{project}/board").json()[0]["status"] == "VERIFIED"
            assert client.post(f"/v1/projects/{project}/cancel", headers=worker_headers).status_code == 403
            assert client.post(f"/v1/projects/{project}/pause", headers=worker_headers).json()["state"] == "PAUSED"
            assert client.post(f"/v1/projects/{project}/work", json={"title":"Blocked","author_id":"e2","acceptance_criteria":["x"]}, headers=worker_headers).status_code == 409
            assert client.post(f"/v1/projects/{project}/resume", headers=worker_headers).json()["state"] == "ACTIVE"
            assert client.post(f"/v1/projects/{project}/cancel", headers=headers).json()["state"] == "CANCELLED"
            assert client.post(f"/v1/projects/{project}/resume", headers=worker_headers).status_code == 409
            assert len(client.get("/v1/events").json()) >= 9


def test_postgres_readiness_probe_is_sanitized_and_read_only(monkeypatch):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from aao import work_management_api

    @contextmanager
    def available_database():
        class Database:
            def execute(self, statement):
                assert statement == "SELECT 1"

        yield Database()

    monkeypatch.setattr(work_management_api, "tx", available_database)
    with TestClient(work_management_api.app) as client:
        assert client.get("/ready").json() == {
            "status": "ready", "database": "available",
        }

    @contextmanager
    def unavailable_database():
        raise RuntimeError("must not leak connection details")
        yield  # pragma: no cover

    monkeypatch.setattr(work_management_api, "tx", unavailable_database)
    with TestClient(work_management_api.app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    assert "connection details" not in response.text
