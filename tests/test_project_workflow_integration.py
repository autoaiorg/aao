"""PostgreSQL integration tests, opt-in for explicitly disposable databases."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_postgres_mandate_project_grant_work_admission(monkeypatch):
    from aao.work_management_api import app
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "test-ceo-key")
    ceo = {"X-CEO-Token": "test-ceo-key"}
    with TestClient(app) as client:
        agent_id = "agent-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": agent_id, "kind": "AGENT"}).json()["token"]
        worker = {"X-Agent-Token": token}
        assert client.get("/health").json()["autonomous_execution"] is False
        mandate = client.post(
            "/v1/mandates", headers=ceo,
            json={"title": "Disposable " + str(uuid4()), "objective": "Test-only mandate"},
        )
        assert mandate.status_code == 201, mandate.text
        mid = mandate.json()["id"]
        assert client.post(
            "/v1/projects", headers=ceo,
            json={"name": "X", "mandate_id": mid},
        ).status_code == 409
        assert client.post(
            f"/v1/mandates/{mid}/confirm", headers=ceo,
        ).status_code == 200
        r = client.post(
            "/v1/projects", headers=ceo,
            json={"name": "Disposable pilot", "mandate_id": mid},
        )
        assert r.status_code == 201, r.text
        project = r.json()["id"]
        work_payload = {
            "title": "Isolated smoke test", "author_id": agent_id,
            "acceptance_criteria": ["State recorded"],
        }
        assert client.post(
            f"/v1/projects/{project}/work", headers=worker,
            json=work_payload,
        ).status_code == 403
        for cap in ("work.create", "work.admit", "work.progress"):
            assert client.post(
                f"/v1/projects/{project}/grants", headers=ceo,
                json={"principal_id": agent_id, "capability": cap},
            ).status_code == 201
        created = client.post(
            f"/v1/projects/{project}/work", headers=worker,
            json=work_payload,
        )
        assert created.status_code == 201, created.text
        wid = created.json()["id"]
        assert client.post(f"/v1/work/{wid}/admit").status_code == 403
        admitted = client.post(f"/v1/work/{wid}/admit", headers=worker)
        assert admitted.status_code == 200, admitted.text
        assert admitted.json()["status"] == "READY"
        assert client.post(f"/v1/work/{wid}/admit", headers=worker).status_code == 409
        board = client.get(f"/v1/projects/{project}/board", headers=ceo)
        assert board.status_code == 200
        assert any(w["id"] == wid and w["status"] == "READY" for w in board.json())


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_capability_catalog_is_project_scoped_and_does_not_grant_execution(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "capability-ceo")
    ceo = {"X-CEO-Token": "capability-ceo"}
    with TestClient(app) as client:
        agent_id = "cap-agent-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        }).json()["token"]
        worker = {"X-Agent-Token": token}
        mandate_id = client.post("/v1/mandates", headers=ceo, json={
            "title": "Capability registry " + str(uuid4()), "objective": "Test local catalog",
        }).json()["id"]
        client.post(f"/v1/mandates/{mandate_id}/confirm", headers=ceo)
        project_id = client.post("/v1/projects", headers=ceo, json={
            "name": "Capability test", "mandate_id": mandate_id,
        }).json()["id"]
        payload = {
            "capability_id": "aao.test.skill", "version": "1.0.0",
            "capability_type": "agent_skill",
            "provenance": {
                "kind": "repository",
                "path": ".agents/skills/aao-postgres-authorization-concurrency/SKILL.md",
            },
            "contract": {
                "purpose": "Design and verify PostgreSQL authorization and concurrency behavior",
                "compatible_roles": ["engineering"],
                "inputs": ["authorization or concurrency change"],
                "outputs": ["verified implementation and test evidence"],
                "usage_limits": ["no production database", "no external effects"],
            },
            "required_permissions": ["execution.claim"],
            "risks": ["instructions are untrusted inputs and cannot grant permissions"],
            "dependencies": [],
            "tests": [
                (
                    "tests/test_project_workflow_integration.py::"
                    "test_capability_catalog_is_project_scoped_and_does_not_grant_execution"
                ),
            ],
            "compatibility": {"agent_roles": ["engineering"]},
            "evidence": [
                "sha256:" + sha256(Path(
                    ".agents/skills/aao-postgres-authorization-concurrency/SKILL.md",
                ).read_bytes()).hexdigest(),
            ],
        }
        path = f"/v1/projects/{project_id}/capabilities"
        assert client.post(path, headers=worker, json=payload).status_code == 403
        assert client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
            "principal_id": agent_id, "capability": "work.create",
        }).status_code == 201
        assert client.post(path, headers=worker, json={
            **payload, "provenance": {},
        }).status_code == 422
        assert client.post(path, headers=worker, json={
            **payload, "evidence": [],
        }).status_code == 422
        assert client.post(path, headers=worker, json={
            **payload, "contract": {"purpose": "incomplete skill"},
        }).status_code == 422
        registered = client.post(path, headers=worker, json=payload)
        assert registered.status_code == 201, registered.text
        assert registered.json()["execution_authorized"] is False
        assert client.post(path, headers=worker, json=payload).status_code == 409

        listed = client.get(path, headers=ceo)
        assert listed.status_code == 200, listed.text
        catalog_entry = listed.json()[0]
        assert catalog_entry["capability_id"] == payload["capability_id"]
        assert catalog_entry["version"] == payload["version"]
        assert catalog_entry["capability_type"] == "agent_skill"
        assert catalog_entry["required_permissions"] == ["execution.claim"]
        assert catalog_entry["created_by"] == agent_id
        assert catalog_entry["status"] == "registered_local"
        assert catalog_entry["execution_authorized"] is False
        assert "project_id" not in catalog_entry
        assert client.get(path, headers=worker).status_code == 403
        task_response = client.post(f"/v1/projects/{project_id}/work", headers=worker, json={
            "title": "Evaluate PostgreSQL authorization skill reuse",
            "author_id": agent_id,
            "acceptance_criteria": ["Compare reuse, adaptation, and new build"],
        })
        assert task_response.status_code == 201, task_response.text
        task_id = task_response.json()["id"]
        evaluation_payload = {
            "task_id": task_id,
            "options": [
                {"choice": "reuse", "fit": 5, "security": 5, "cost": 5,
                 "time": 5, "tokens": 5, "maintenance": 5},
                {"choice": "adapt", "fit": 4, "security": 4, "cost": 3,
                 "time": 3, "tokens": 3, "maintenance": 4},
                {"choice": "build", "fit": 3, "security": 3, "cost": 2,
                 "time": 2, "tokens": 2, "maintenance": 2},
            ],
            "rationale": "The existing PostgreSQL concurrency skill covers this task's test procedure.",
            "evidence": payload["evidence"],
            "capability_id": payload["capability_id"], "version": payload["version"],
        }
        assessment_path = f"/v1/projects/{project_id}/capability-evaluations"
        evaluation = client.post(assessment_path, headers=worker, json=evaluation_payload)
        assert evaluation.status_code == 201, evaluation.text
        assert evaluation.json()["recommendation"] == "reuse"
        assert evaluation.json()["execution_authorized"] is False
        assert client.get(assessment_path, headers=worker).status_code == 403
        from aao.postgresql_connection import connect_postgres
        with connect_postgres() as db:
            assert db.execute(
                "SELECT 1 FROM project_grants WHERE project_id=%s AND principal_id=%s "
                "AND capability='execution.claim'", (project_id, agent_id),
            ).fetchone() is None
        assert client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
            "principal_id": agent_id, "capability": "project.read",
        }).status_code == 201
        assert client.get(path, headers=worker).json()[0]["capability_id"] == "aao.test.skill"
        recorded_evaluation = client.get(assessment_path, headers=worker)
        assert recorded_evaluation.status_code == 200
        assert recorded_evaluation.json()[0]["task_id"] == task_id
        assert recorded_evaluation.json()[0]["details"]["recommendation"] == "reuse"
        assert client.get(path + "?capability_type=agent_skill", headers=ceo).json()[0]["capability_id"] == "aao.test.skill"
        assert client.get(path + "?capability_type=made_up", headers=ceo).status_code == 422
        promotion = {**payload, "capability_id": "forbidden.promotion", "status": "candidate_for_promotion"}
        assert client.post(path, headers=worker, json=promotion).status_code == 422

        isolated_agent = "cap-isolated-reader-" + str(uuid4())
        isolated_token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": isolated_agent, "kind": "AGENT",
        }).json()["token"]
        isolated_reader = {"X-Agent-Token": isolated_token}
        isolated_mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Isolated capability mandate " + str(uuid4()),
            "objective": "Check capability project isolation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{isolated_mandate}/confirm", headers=ceo).status_code == 200
        isolated_project = client.post("/v1/projects", headers=ceo, json={
            "name": "Isolated capability project " + str(uuid4()), "mandate_id": isolated_mandate,
        }).json()["id"]
        assert client.post(f"/v1/projects/{isolated_project}/grants", headers=ceo, json={
            "principal_id": isolated_agent, "capability": "project.read",
        }).status_code == 201
        isolated_capabilities = f"/v1/projects/{isolated_project}/capabilities"
        isolated_evaluations = f"/v1/projects/{isolated_project}/capability-evaluations"
        assert client.get(isolated_capabilities, headers=isolated_reader).json() == []
        assert client.get(isolated_evaluations, headers=isolated_reader).json() == []
        assert client.post(f"/v1/projects/{isolated_project}/grants", headers=ceo, json={
            "principal_id": isolated_agent, "capability": "work.create",
        }).status_code == 201
        assert client.post(isolated_evaluations, headers=isolated_reader,
                           json=evaluation_payload).status_code == 404


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_grant_creation_requires_active_principal_with_matching_kind(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "grant-kind-ceo")
    ceo = {"X-CEO-Token": "grant-kind-ceo"}
    with TestClient(app) as client:
        agent = "grant-agent-" + str(uuid4())
        auditor = "grant-auditor-" + str(uuid4())
        assert client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent, "kind": "AGENT",
        }).status_code == 201
        assert client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor, "kind": "AUDITOR",
        }).status_code == 201
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Grant validation " + str(uuid4()),
            "objective": "Reject grants inconsistent with principal authority",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Grant validation", "mandate_id": mandate,
        }).json()["id"]

        for principal, capability, status in (
            ("absent-principal", "work.create", 404),
            (agent, "work.review", 422),
            (auditor, "work.create", 422),
        ):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": capability,
            })
            assert response.status_code == status, response.text

        valid_agent = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": agent, "capability": "work.create",
        })
        valid_auditor = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": auditor, "capability": "work.review",
        })
        assert valid_agent.status_code == valid_auditor.status_code == 201
        duplicate = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": agent, "capability": "work.create",
        })
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json() == {
            "project_id": project, "capability": "work.create", "created": False,
            "expires_at": None,
        }
        with connect_postgres() as db:
            event_count = db.execute(
                "SELECT count(*) FROM events WHERE subject_id=%s "
                "AND kind='grant.created' AND details->>'principal_id'=%s "
                "AND details->>'capability'='work.create'",
                (project, agent),
            ).fetchone()[0]
        assert event_count == 1
        revoked = "revoked-grantee-" + str(uuid4())
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": revoked, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        assert client.post(f"/v1/principals/{revoked}/revoke", headers=ceo).status_code == 200
        disabled_grant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": revoked, "capability": "work.create",
        })
        assert disabled_grant.status_code == 409, disabled_grant.text


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_postgres_review_is_separate_from_author_and_required_for_done(monkeypatch):
    from aao.work_management_api import app
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "integration-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "integration-ceo"}
    with TestClient(app) as client:
        agent_id = "agent-" + str(uuid4())
        auditor_id = "auditor-" + str(uuid4())
        worker = {"X-Agent-Token": client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": agent_id, "kind": "AGENT"}).json()["token"]}
        auditor = {"X-Auditor-Token": client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": auditor_id, "kind": "AUDITOR"}).json()["token"]}
        m = client.post("/v1/mandates", headers=ceo, json={"title": str(uuid4()), "objective": "Review gate test"}).json()["id"]
        client.post(f"/v1/mandates/{m}/confirm", headers=ceo)
        p = client.post("/v1/projects", headers=ceo, json={"name": "Audit smoke", "mandate_id": m}).json()["id"]
        for who, cap in ((agent_id, "work.create"), (agent_id, "work.admit"),
                         (agent_id, "work.progress"), (agent_id, "execution.claim"),
                         (agent_id, "evidence.submit"),
                         (auditor_id, "work.review")):
            assert client.post(f"/v1/projects/{p}/grants", headers=ceo, json={"principal_id": who, "capability": cap}).status_code == 201
        w = client.post(f"/v1/projects/{p}/work", headers=worker, json={"title": "Review", "author_id": "spoofed", "acceptance_criteria": ["Reviewed"]}).json()["id"]
        assert client.post(f"/v1/work/{w}/progress", headers=worker).status_code == 409
        assert client.post(f"/v1/work/{w}/admit", headers=worker).status_code == 200
        execution_id = client.post(f"/v1/work/{w}/stage-inert", headers=worker).json()["execution_id"]
        from aao.execution_queue import claim, complete
        lease = claim(agent_id, agent_credential=worker["X-Agent-Token"],
                      project_id=p)
        assert lease and lease["execution_id"] == execution_id
        assert client.post(f"/v1/work/{w}/progress", headers=worker).json()["status"] == "IN_PROGRESS"
        assert client.post(f"/v1/work/{w}/progress", headers=worker).json()["status"] == "IN_REVIEW"
        assert client.post(f"/v1/work/{w}/reviews", headers=auditor, json={
            "decision": "APPROVE", "candidate_sha": "a" * 40,
            "evidence": ["sha256:" + "a" * 64],
        }).status_code == 409
        rejected_while_running = client.post(f"/v1/work/{w}/reviews", headers=auditor, json={
            "decision": "REJECT", "candidate_sha": "a" * 40,
            "evidence": ["sha256:" + "a" * 64],
        })
        assert rejected_while_running.status_code == 409
        candidate_sha = "a" * 40
        complete(execution_id, lease["token"], agent_id,
                 {"ok": True, "candidate_sha": candidate_sha},
                 agent_credential=worker["X-Agent-Token"])
        from aao.evidence_registry import register_evidence
        evidence_ref = register_evidence(
            p, b"independent review fixture", agent_id=agent_id,
            agent_credential=worker["X-Agent-Token"], media_type="text/plain",
        )
        assert client.post(f"/v1/work/{w}/progress", headers=worker).status_code == 409
        assert client.post(f"/v1/work/{w}/reviews", headers=worker, json={"decision": "APPROVE", "candidate_sha": candidate_sha, "evidence": [evidence_ref]}).status_code == 403
        assert client.post(f"/v1/work/{w}/reviews", headers=auditor, json={"decision": "APPROVE", "candidate_sha": candidate_sha, "evidence": [""]}).status_code == 409
        # A verified approval is covered by the W2a test; here: REJECT, then a veto blocks approval.
        from aao.postgresql_connection import connect_postgres
        with connect_postgres() as db:
            approval_rows = db.execute(
                "SELECT count(*) FROM reviews WHERE work_id=%s AND decision='APPROVE'",
                (w,),
            ).fetchone()[0]
        assert approval_rows == 0
        board = client.get(f"/v1/projects/{p}/board", headers=ceo)
        assert board.status_code == 200, board.text
        assert any(item["id"] == w and item["status"] == "IN_REVIEW"
                   for item in board.json())
        rejected = client.post(f"/v1/work/{w}/reviews", headers=auditor, json={
            "decision": "REJECT", "candidate_sha": candidate_sha,
            "evidence": [evidence_ref],
        })
        assert rejected.status_code == 201, rejected.text
        assert rejected.json()["status"] == "IN_PROGRESS"
        assert client.post(f"/v1/work/{w}/progress", headers=worker).json()["status"] == "IN_REVIEW"
        veto = client.post(f"/v1/work/{w}/reviews", headers=auditor, json={
            "decision": "VETO", "candidate_sha": candidate_sha,
            "evidence": [evidence_ref],
        })
        assert veto.status_code == 201, veto.text
        assert veto.json()["status"] == "IN_REVIEW"
        assert client.post(f"/v1/work/{w}/reviews", headers=auditor, json={
            "decision": "APPROVE", "candidate_sha": candidate_sha,
            "evidence": [evidence_ref],
        }).status_code == 409
        veto_board = client.get(f"/v1/projects/{p}/board", headers=ceo)
        veto_task = next(item for item in veto_board.json() if item["id"] == w)
        assert veto_task["status"] == "IN_REVIEW"
        assert any(item["decision"] == "VETO" and item["candidate_sha"] == candidate_sha
                   for item in veto_task["reviews"])
        from psycopg.errors import RaiseException
        with pytest.raises(RaiseException, match="review records are append-only"), connect_postgres() as db:
            db.execute("DELETE FROM reviews WHERE id=%s", (veto.json()["review_id"],))
        with connect_postgres() as db:
            db.execute(
                "UPDATE work_items SET status='VERIFIED' WHERE id=%s", (w,),
            )
            db.execute(
                "INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence) "
                "VALUES (%s,%s,%s,'APPROVE',%s::jsonb)",
                (str(uuid4()), w, auditor_id, '["legacy unverified approval"]'),
            )
        legacy_completion = client.post(f"/v1/work/{w}/progress", headers=worker)
        assert legacy_completion.status_code == 409, legacy_completion.text
        legacy_board = client.get(f"/v1/projects/{p}/board", headers=ceo)
        assert any(item["id"] == w and item["status"] == "VERIFIED"
                   for item in legacy_board.json())


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_postgres_workboard_requires_ceo_read_credentials(monkeypatch):
    """The browser and API share an origin, but project reads stay protected."""
    from aao.work_management_api import app
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "read-only-test-ceo")
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "AAO" in page.text
        assert client.get("/v1/projects").status_code == 403
        assert client.get("/v1/projects", headers={"X-CEO-Token": "wrong"}).status_code == 403
        allowed = client.get(
            "/v1/projects", headers={"X-CEO-Token": "read-only-test-ceo"}
        )
        assert allowed.status_code == 200
        assert isinstance(allowed.json(), list)


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_project_reads_are_scoped_to_granted_worker(monkeypatch):
    from aao.work_management_api import app
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "scoped-read-ceo")
    ceo = {"X-CEO-Token": "scoped-read-ceo"}
    with TestClient(app) as client:
        agent_id = "agent-" + str(uuid4())
        worker = {"X-Agent-Token": client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": agent_id, "kind": "AGENT"}).json()["token"]}
        project_ids = []
        for i in range(2):
            mid = client.post("/v1/mandates", headers=ceo, json={
                "title": f"Read scope {i} {uuid4()}", "objective": "Disposable read test"
            }).json()["id"]
            assert client.post(f"/v1/mandates/{mid}/confirm", headers=ceo).status_code == 200
            pid = client.post("/v1/projects", headers=ceo, json={
                "name": f"Scope {i}", "mandate_id": mid,
            }).json()["id"]
            project_ids.append(pid)
        allow, deny = project_ids
        before = client.get("/v1/projects", headers=worker)
        assert before.status_code == 200
        assert allow not in [p["id"] for p in before.json()]
        assert deny not in [p["id"] for p in before.json()]
        assert client.get(f"/v1/projects/{deny}/board", headers=worker).status_code == 403
        granted = client.post(f"/v1/projects/{allow}/grants", headers=ceo, json={
            "principal_id": agent_id, "capability": "project.read",
        })
        assert granted.status_code == 201, granted.text
        visible = client.get("/v1/projects", headers=worker)
        assert visible.status_code == 200
        ids = [p["id"] for p in visible.json()]
        assert allow in ids and deny not in ids
        assert client.get(f"/v1/projects/{allow}/board", headers=worker).status_code == 200
        assert client.get(f"/v1/projects/{deny}/board", headers=worker).status_code == 403
        assert client.get(f"/v1/projects/{deny}/board", headers=ceo).status_code == 200


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_agent_can_inspect_only_its_own_project_grants(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "grant-inventory-ceo")
    ceo = {"X-CEO-Token": "grant-inventory-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Grant inventory " + str(uuid4()),
            "objective": "Test self-scoped grant discovery",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Grant inventory", "mandate_id": mandate,
        }).json()["id"]
        agent_id = "grant-agent-" + str(uuid4())
        agent_token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        }).json()["token"]
        other_id = "other-agent-" + str(uuid4())
        client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": other_id, "kind": "AGENT",
        })
        expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        for principal_id, capability in (
            (agent_id, "project.read"), (agent_id, "code.propose"),
            (other_id, "work.create"),
        ):
            grant = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal_id, "capability": capability,
                "expires_at": expiry,
            })
            assert grant.status_code == 201, grant.text

        assert client.get("/v1/principals/me/grants").status_code == 403
        response = client.get(
            "/v1/principals/me/grants", headers={"X-Agent-Token": agent_token},
        )
        assert response.status_code == 200, response.text
        grants = response.json()
        assert {row["capability"] for row in grants} == {"project.read", "code.propose"}
        assert {row["project_id"] for row in grants} == {project}
        assert {row["principal_id"] for row in grants} == {agent_id}
        assert all(row["active"] for row in grants)
        assert all(row["expires_at"] for row in grants)
        assert client.post(f"/v1/principals/{agent_id}/revoke", headers=ceo).status_code == 200
        assert client.get(
            "/v1/principals/me/grants", headers={"X-Agent-Token": agent_token},
        ).status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_auditor_can_inspect_only_its_own_review_grants(monkeypatch):
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "auditor-grant-inventory-ceo")
    from aao.work_management_api import app

    ceo = {"X-CEO-Token": "auditor-grant-inventory-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Auditor grant inventory " + str(uuid4()),
            "objective": "Test self-scoped auditor grant discovery",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Auditor grant inventory", "mandate_id": mandate,
        }).json()["id"]

        auditor_id = "grant-auditor-" + str(uuid4())
        auditor_token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": auditor_id, "kind": "AUDITOR",
        }).json()["token"]
        other_id = "other-auditor-" + str(uuid4())
        client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": other_id, "kind": "AUDITOR",
        })
        agent_id = "grant-agent-" + str(uuid4())
        client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        })
        for principal_id, capability in (
            (auditor_id, "work.review"), (auditor_id, "execution.reconcile"),
            (other_id, "work.review"), (agent_id, "project.read"),
        ):
            response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal_id, "capability": capability,
            })
            assert response.status_code == 201, response.text

        assert client.get("/v1/auditors/me/grants").status_code == 403
        assert client.get(
            "/v1/auditors/me/grants", headers={"X-Agent-Token": auditor_token},
        ).status_code == 403
        response = client.get(
            "/v1/auditors/me/grants", headers={"X-Auditor-Token": auditor_token},
        )
        assert response.status_code == 200, response.text
        grants = response.json()
        assert {row["capability"] for row in grants} == {"work.review", "execution.reconcile"}
        assert {row["project_id"] for row in grants} == {project}
        assert {row["principal_id"] for row in grants} == {auditor_id}
        assert all(row["active"] for row in grants)
        assert client.post(f"/v1/principals/{auditor_id}/revoke", headers=ceo).status_code == 200
        assert client.get(
            "/v1/auditors/me/grants", headers={"X-Auditor-Token": auditor_token},
        ).status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_grant_revocation_serializes_after_authorized_transaction(monkeypatch):
    """An in-flight grant-checked transaction completes before CEO revocation."""
    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import AuthenticatedPrincipal, app, require_grant

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "grant-race-ceo")
    ceo = {"X-CEO-Token": "grant-race-ceo"}
    with TestClient(app) as client:
        agent_id = "agent-" + str(uuid4())
        worker = {"X-Agent-Token": client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": agent_id, "kind": "AGENT"}).json()["token"]}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": f"Grant race {uuid4()}", "objective": "Test grant serialization",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": f"Grant race {uuid4()}", "mandate_id": mandate,
        }).json()["id"]
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": agent_id, "capability": "work.create",
        }).status_code == 201

        with ThreadPoolExecutor(max_workers=1) as pool, connect_postgres() as protected_db:
            require_grant(
                protected_db,
                AuthenticatedPrincipal(agent_id, digest_token(worker["X-Agent-Token"]), "AGENT"),
                project,
                "work.create",
            )
            revoke = pool.submit(client.delete,
                f"/v1/projects/{project}/grants/{agent_id}/work.create",
                headers=ceo,
            )
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'DELETE FROM project_grants%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if waiting:
                    break
                time.sleep(0.01)
            assert waiting, "grant revocation did not wait for the protected transaction"

        response = revoke.result(timeout=5)
        assert response.status_code == 204, response.text
        assert client.post(f"/v1/projects/{project}/work", headers={
            "X-Agent-Token": worker["X-Agent-Token"],
        }, json={"title": "Must be denied", "author_id": "ignored",
                "acceptance_criteria": ["denial"]}).status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_grant_expiring_while_lock_waiting_is_denied(monkeypatch):
    """A grant is checked against wall-clock time after waiting for its row lock."""
    from datetime import UTC, datetime, timedelta

    from fastapi import HTTPException

    from aao.postgresql_connection import connect_postgres
    from aao.principal_credentials import digest_token
    from aao.work_management_api import AuthenticatedPrincipal, app, require_grant

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "grant-expiry-ceo")
    ceo = {"X-CEO-Token": "grant-expiry-ceo"}
    with TestClient(app) as client:
        agent_id = "agent-" + str(uuid4())
        agent_token = client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": agent_id, "kind": "AGENT"}).json()["token"]
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": f"Grant expiry {uuid4()}", "objective": "Test expiry after lock wait",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": f"Grant expiry {uuid4()}", "mandate_id": mandate,
        }).json()["id"]
        expiry = datetime.now(UTC) + timedelta(seconds=1)
        grant_response = client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": agent_id,
            "capability": "work.create",
            "expires_at": expiry.isoformat(),
        })
        assert grant_response.status_code == 201
        assert grant_response.json()["expires_at"] == expiry.isoformat()

        def check_grant():
            try:
                with connect_postgres() as db:
                    require_grant(
                        db,
                        AuthenticatedPrincipal(agent_id, digest_token(agent_token), "AGENT"),
                        project,
                        "work.create",
                    )
                return "allowed"
            except HTTPException:
                return "denied"

        with ThreadPoolExecutor(max_workers=1) as pool, connect_postgres() as blocker:
            blocker.execute(
                "UPDATE project_grants SET expires_at=expires_at WHERE project_id=%s "
                "AND principal_id=%s AND capability='work.create'",
                (project, agent_id),
            )
            check = pool.submit(check_grant)
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with connect_postgres() as observer:
                    waiting = observer.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE query LIKE 'SELECT 1 FROM project_grants%' "
                        "AND wait_event_type='Lock')"
                    ).fetchone()[0]
                if waiting:
                    break
                time.sleep(0.01)
            assert waiting, "grant check did not wait for the held row lock"
            time.sleep(1.1)
        assert check.result(timeout=5) == "denied"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_registered_repository_check_requires_task_selection_before_queue_claim(monkeypatch):
    from aao.execution_queue import claim
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "capability-check-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "capability-check-ceo"}
    with TestClient(app) as client:
        identity = "check-agent-" + str(uuid4())
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": identity, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        agent = {"X-Agent-Token": issued.json()["token"]}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Repository check " + str(uuid4()), "objective": "Test bounded repo check",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Repository check", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim", "project.read"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": identity, "capability": capability,
            }).status_code == 201
        work = client.post(f"/v1/projects/{project}/work", headers=agent, json={
            "title": "Run registered core checks", "author_id": identity,
            "acceptance_criteria": ["Exact fixed check is executed in sandbox"],
        }).json()["id"]
        registered = client.post(f"/v1/projects/{project}/capabilities", headers=agent, json={
            "capability_id": "aao.repository-check", "version": "1.0.0",
            "capability_type": "cli_script", "provenance": {"kind": "repository"},
            "contract": {
                "purpose": "Run fixed allow-listed core tests",
                "entrypoint": "aao.sandboxed_repository_checks:core-unit",
                "inputs": ["fixed core-unit check id"],
                "outputs": ["test result and exact candidate SHA"],
                "platform": "Linux with bubblewrap",
            },
            "required_permissions": ["execution.claim"], "risks": ["local test code runs"],
            "dependencies": [], "tests": ["tests/test_sandboxed_repository_checks.py"],
            "compatibility": {}, "evidence": ["repo source"],
        })
        assert registered.status_code == 201, registered.text
        evaluation = client.post(
            f"/v1/projects/{project}/capability-evaluations", headers=agent,
            json={
                "task_id": work,
                "options": [
                    {"choice": choice, "fit": fit, "security": fit, "cost": fit,
                     "time": fit, "tokens": fit, "maintenance": fit}
                    for choice, fit in (("reuse", 5), ("adapt", 3), ("build", 1))
                ],
                "rationale": "Reuse the checked-in fixed sandbox instead of building a new tool.",
                "evidence": ["tests/test_sandboxed_repository_checks.py"],
                "capability_id": "aao.repository-check", "version": "1.0.0",
            },
        )
        assert evaluation.status_code == 201, evaluation.text
        assert evaluation.json()["recommendation"] == "reuse"
        assert client.post(f"/v1/work/{work}/admit", headers=agent).status_code == 200
        request = {"capability_id": "aao.repository-check", "version": "1.0.0",
                   "check_id": "core-unit"}
        not_selected = client.post(
            f"/v1/work/{work}/stage-repository-check", headers=agent,
            json={**request, "capability_id": "other"},
        )
        assert not_selected.status_code == 409
        staged = client.post(
            f"/v1/work/{work}/stage-repository-check", headers=agent, json=request,
        )
        assert staged.status_code == 202, staged.text
        lease = claim(identity, agent_credential=issued.json()["token"], project_id=project)
        assert lease["input"] == {
            "type": "aao.repository-check.v1", "check_id": "core-unit",
            "capability_id": "aao.repository-check", "version": "1.0.0",
        }
        board = client.get(f"/v1/projects/{project}/board", headers=agent)
        execution = board.json()[0]["executions"][0]
        assert execution["id"] == staged.json()["execution_id"]
        assert execution["status"] == "RUNNING"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_w2a_agent_run_produces_a_tested_candidate_retries_after_failure_and_is_reviewable(monkeypatch, tmp_path):
    """W1+W2a end to end: an agent run turns an admitted task into a patch proposal and a candidate commit,
    tests it in the sandbox, a failed attempt can be re-run, and the auditor approves the tested candidate SHA."""
    import subprocess

    from aao.inert_execution_worker import run_one
    from aao.work_management_api import app

    # The fixture repository is this checkout's HEAD, so the sandboxed core-unit check has real tests to run.
    root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "self-dev"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{root}", str(repo)], check=True)  # shallow, like CI
    base_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    store = tmp_path / "candidates.git"

    def fixture(name: str, body: str) -> Path:
        lines = body.splitlines()
        path = tmp_path / f"{name}.patch"
        path.write_text("diff --git a/tests/test_notes.py b/tests/test_notes.py\nnew file mode 100644\n--- /dev/null\n"
                        f"+++ b/tests/test_notes.py\n@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{line}\n" for line in lines))
        return path

    failing = fixture("failing", "def test_note():\n    assert 'hello' == 'bye'")
    passing = fixture("passing", "def test_note():\n    assert 'hello from the agent'")

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "agent-run-ceo")
    monkeypatch.setenv("AAO_AGENT_QUEUE_ENABLED", "true")
    monkeypatch.setenv("AAO_SELF_DEV_REPOSITORY", str(repo))
    monkeypatch.setenv("AAO_CANDIDATE_REPOSITORY", str(store))
    monkeypatch.setenv("AAO_AGENT_BACKEND", "fixture")
    monkeypatch.setenv("AAO_AGENT_FIXTURE_PATCH", str(failing))
    ceo = {"X-CEO-Token": "agent-run-ceo"}
    with TestClient(app) as client:
        identity = "w1-agent-" + str(uuid4())
        auditor_id = "w2-auditor-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={"principal_id": identity, "kind": "AGENT"}).json()["token"]
        agent = {"X-Agent-Token": token}
        auditor = {"X-Auditor-Token": client.post("/v1/principals/credentials", headers=ceo,
                                                  json={"principal_id": auditor_id, "kind": "AUDITOR"}).json()["token"]}
        mandate = client.post("/v1/mandates", headers=ceo, json={"title": "W2 " + str(uuid4()), "objective": "Agent patch"}).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={"name": "W2", "mandate_id": mandate}).json()["id"]
        from datetime import UTC, datetime, timedelta
        expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        for capability in ("work.create", "work.admit", "work.progress", "execution.claim", "project.read",
                           "code.propose", "evidence.submit"):
            grant = {"principal_id": identity, "capability": capability}
            if capability == "code.propose":
                grant["expires_at"] = expiry  # code.propose grants must expire within 24h
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json=grant).status_code == 201
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo,
                           json={"principal_id": auditor_id, "capability": "work.review"}).status_code == 201
        work = client.post(f"/v1/projects/{project}/work", headers=agent, json={
            "title": "Add a notes test", "author_id": identity, "description": "Create tests/test_notes.py",
            "acceptance_criteria": ["tests/test_notes.py exists and passes"],
        })
        assert work.status_code == 201, work.text
        work = work.json()["id"]
        registered = client.post(f"/v1/projects/{project}/capabilities", headers=agent, json={
            "capability_id": "aao.agent-runner", "version": "1.0.0", "capability_type": "agent",
            "provenance": {"kind": "repository"},
            "contract": {"purpose": "Turn a task into a patch proposal", "entrypoint": "aao.agent_runner:patch",
                         "inputs": ["task", "base_sha"], "outputs": ["patch proposal"], "platform": "Linux",
                         "authority_boundary": "edits only a disposable clone; proposes, never applies or merges",
                         "compatible_roles": ["implementer"]},
            "required_permissions": ["execution.claim", "code.propose"], "risks": ["agent edits a disposable clone"],
            "dependencies": [], "tests": ["tests/test_agent_runner.py"], "compatibility": {}, "evidence": ["repo source"],
        })
        assert registered.status_code == 201, registered.text
        evaluation = client.post(f"/v1/projects/{project}/capability-evaluations", headers=agent, json={
            "task_id": work,
            "options": [{"choice": c, "fit": f, "security": f, "cost": f, "time": f, "tokens": f, "maintenance": f}
                        for c, f in (("reuse", 5), ("adapt", 3), ("build", 1))],
            "rationale": "Reuse the agent runner.", "evidence": ["tests/test_agent_runner.py"],
            "capability_id": "aao.agent-runner", "version": "1.0.0",
        })
        assert evaluation.status_code == 201, evaluation.text
        assert client.post(f"/v1/work/{work}/admit", headers=agent).status_code == 200
        run = {"capability_id": "aao.agent-runner", "version": "1.0.0", "base_sha": base_sha}
        staged = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert staged.status_code == 202, staged.text
        assert client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run).json()["execution_id"] == staged.json()["execution_id"]
        assert client.post(f"/v1/work/{work}/progress", headers=agent).status_code == 200

        # Attempt 1: the candidate is committed and stored, but its own test fails, so the execution FAILED.
        assert run_one(identity, token, project_id=project, seconds=400)["status"] == "FAILED"
        # Recovery: the task can be re-run after a failed attempt.
        monkeypatch.setenv("AAO_AGENT_FIXTURE_PATCH", str(passing))
        restaged = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert restaged.status_code == 202, restaged.text
        assert restaged.json()["execution_id"] != staged.json()["execution_id"]
        outcome = run_one(identity, token, project_id=project, seconds=400)
        board = client.get(f"/v1/projects/{project}/board", headers=agent).json()
        last = next(i for i in board if i["id"] == work)["executions"][-1]["result"]
        assert outcome["status"] == "SUCCEEDED", (last.get("error"), last.get("check", {}).get("stderr"),
                                                  last.get("check", {}).get("stdout"))
        board = client.get(f"/v1/projects/{project}/board", headers=agent).json()
        item = next(item for item in board if item["id"] == work)
        failed, succeeded = item["executions"]
        assert failed["status"] == "FAILED" and failed["result"]["check"]["conclusion"] == "failure"
        result = succeeded["result"]
        assert succeeded["status"] == "SUCCEEDED" and result["check"]["conclusion"] == "success", result
        assert result["check"]["extra_tests"] == ["tests/test_notes.py"]
        candidate_sha = result["candidate_sha"]
        assert len(item["patch_proposals"]) == 2
        assert {p["changed_paths"][0] for p in item["patch_proposals"]} == {"tests/test_notes.py"}

        # The tested candidate is kept under a durable ref, authored by the fixed agent identity, on top of base.
        git = ["git", "--git-dir", str(store)]
        assert subprocess.run([*git, "rev-parse", result["candidate_ref"]], capture_output=True, text=True, check=True).stdout.strip() == candidate_sha
        meta = subprocess.run([*git, "log", "-1", "--format=%P|%an|%ae|%ce|%B", candidate_sha], capture_output=True, text=True, check=True).stdout
        assert meta.startswith(f"{base_sha}|AAO agent|{identity}@agents.aao.invalid|{identity}@agents.aao.invalid|Add a notes test")
        assert f"AAO-Work: {work}" in meta

        # Review: the auditor approves exactly the tested candidate; the earlier failed attempt does not block it.
        assert client.post(f"/v1/work/{work}/progress", headers=agent).status_code == 200
        from aao.evidence_registry import register_evidence
        evidence_ref = register_evidence(project, b"candidate check output", agent_id=identity,
                                         agent_credential=token, media_type="text/plain")
        failed_sha = failed["result"]["candidate_sha"]
        assert client.post(f"/v1/work/{work}/reviews", headers=auditor, json={
            "decision": "APPROVE", "candidate_sha": failed_sha, "evidence": [evidence_ref]}).status_code == 409
        approval = client.post(f"/v1/work/{work}/reviews", headers=auditor, json={
            "decision": "APPROVE", "candidate_sha": candidate_sha, "evidence": [evidence_ref]})
        assert approval.status_code == 201, approval.text
        assert approval.json()["status"] == "VERIFIED"
    assert subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout == ""
