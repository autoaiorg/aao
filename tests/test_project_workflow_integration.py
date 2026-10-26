"""PostgreSQL integration tests, opt-in for explicitly disposable databases."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_work_coordinate_is_an_explicit_project_capability():
    from aao.work_management_api import GrantRequest

    grant = GrantRequest(principal_id="aao-pm", capability="work.coordinate")
    assert grant.capability == "work.coordinate"
    assignment_grant = GrantRequest(principal_id="aao-pm", capability="work.assign")
    assert assignment_grant.capability == "work.assign"
    with pytest.raises(ValueError):
        GrantRequest(principal_id="aao-pm", capability="work.execute")


def test_agent_dispatch_rejects_a_declared_identity_that_disagrees_with_credential():
    from aao.work_management_api import (
        AgentDispatchRequest,
        AuthenticatedPrincipal,
        dispatch_next_agent_work,
    )

    authenticated = AuthenticatedPrincipal("actual-agent", "digest", "AGENT")
    request = AgentDispatchRequest(project_id="project", principal_id="other-agent", base_sha="a" * 40)
    with pytest.raises(HTTPException) as error:
        dispatch_next_agent_work(request, authenticated)

    assert error.value.status_code == 403


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_project_coordinator_consolidates_without_ceo_impersonation(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "coordinator-ceo")
    ceo = {"X-CEO-Token": "coordinator-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "PM coordination " + str(uuid4()), "objective": "Persist PM synthesis",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "PM coordination", "mandate_id": mandate,
        }).json()["id"]
        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "PM result thread",
        }).json()["id"]
        group = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "title": "One outcome",
                "description": "Confirmed group", "acceptance_criteria": ["done"],
                "tasks": [{"key": "one", "title": "Outcome", "acceptance_criteria": ["evidence"],
                           "required_competencies": ["technical-writing"]}],
            },
        ).json()
        assert group["tasks"][0]["required_competencies"] == ["technical-writing"]
        coordinator_id = "aao-pm-test-" + uuid4().hex[:8]
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": coordinator_id, "kind": "AGENT",
        })
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        pm_headers = {"X-Agent-Token": token}
        groups_url = f"/v1/agent/projects/{project}/work-groups"
        assert client.get(groups_url, headers=pm_headers).status_code == 403
        url = f"/v1/agent/projects/{project}/work-groups/{group['id']}/consolidation"
        ungranted_payload = {
            "idempotency_key": str(uuid4()), "expected_source_sha256": "0" * 64,
            "summary": "This coordinator has no project grant.",
        }
        assert client.post(url, headers=pm_headers, json=ungranted_payload).status_code == 403
        assert client.post(f"/v1/projects/{project}/grants", headers=pm_headers, json={
            "principal_id": coordinator_id, "capability": "work.coordinate",
        }).status_code == 403
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": coordinator_id, "capability": "work.coordinate",
        }).status_code == 201
        child_id = group["tasks"][0]["id"]
        target_id = "aao-assignee-test-" + uuid4().hex[:8]
        target = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": target_id, "kind": "AGENT",
        })
        assert target.status_code == 201, target.text
        for capability in ("work.admit", "execution.claim"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": target_id, "capability": capability,
            }).status_code == 201
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO organization_profiles(principal_id,display_name,role_title,competencies) "
                "VALUES (%s,'Test assignee','Implementer','{}')",
                (target_id,),
            )
        assignment_url = f"/v1/agent/work/{child_id}/assignment"
        assignment_body = {"principal_id": target_id}
        assert client.put(assignment_url, headers=pm_headers, json=assignment_body).status_code == 403
        assignable_url = f"/v1/agent/projects/{project}/assignable-agents"
        assert client.get(assignable_url, headers=pm_headers).status_code == 403
        assert client.post(f"/v1/projects/{project}/grants", headers=pm_headers, json={
            "principal_id": coordinator_id, "capability": "work.assign",
        }).status_code == 403
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": coordinator_id, "capability": "work.assign",
        }).status_code == 201
        mismatched = client.put(assignment_url, headers=pm_headers, json=assignment_body)
        assert mismatched.status_code == 409
        assert mismatched.json()["detail"]["code"] == "ASSIGNEE_COMPETENCY_MISMATCH"
        with connect_postgres() as db:
            db.execute(
                "UPDATE organization_profiles SET competencies=ARRAY['technical-writing'] "
                "WHERE principal_id=%s", (target_id,),
            )
        assigned = client.put(assignment_url, headers=pm_headers, json=assignment_body)
        assert assigned.status_code == 200, assigned.text
        assignable = client.get(assignable_url, headers=pm_headers)
        assert assignable.status_code == 200, assignable.text
        assert [agent["principal_id"] for agent in assignable.json()] == [target_id]
        assert assigned.json() == {
            "work_id": child_id, "principal_id": target_id,
            "assigned_by": coordinator_id, "grants_created": False,
        }
        with connect_postgres() as db:
            assignment = db.execute(
                "SELECT principal_id,assigned_by FROM work_item_assignments WHERE work_id=%s",
                (child_id,),
            ).fetchone()
            event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.assigned' "
                "ORDER BY created_at DESC LIMIT 1", (child_id,),
            ).fetchone()[0]
        assert tuple(assignment) == (target_id, coordinator_id)
        assert event["assigned_by"] == coordinator_id and event["grants_created"] is False
        pm_groups = client.get(groups_url, headers=pm_headers)
        assert pm_groups.status_code == 200, pm_groups.text
        assert len(pm_groups.json()) == 1
        assert pm_groups.json()[0]["id"] == group["id"]
        assert pm_groups.json()[0]["parent_status"] == "INBOX"
        assert pm_groups.json()[0]["consolidation_ready"] is False
        assert pm_groups.json()[0]["children"][0]["required_competencies"] == ["technical-writing"]
        with connect_postgres() as db:
            db.execute(
                "UPDATE work_items SET status='DONE',evidence=%s::jsonb WHERE id=%s",
                (json.dumps(["artifact://outcome/result"]), group["tasks"][0]["id"]),
            )
        listed = client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]
        payload = {
            "idempotency_key": str(uuid4()), "expected_source_sha256": listed["source_sha256"],
            "summary": "PM synthesis from persisted evidence.",
        }
        assert client.post(url, headers={"X-Agent-Token": "invalid"}, json=payload).status_code == 403
        saved = client.post(url, headers=pm_headers, json=payload)
        assert saved.status_code == 201, saved.text
        assert saved.json()["created_by"] == coordinator_id
        replay = client.post(url, headers=pm_headers, json=payload)
        assert replay.status_code == 201 and replay.json()["created"] is False
        with connect_postgres() as db:
            event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.group_consolidated'",
                (group["parent_work_id"],),
            ).fetchone()[0]
            message = db.execute(
                "SELECT body FROM project_conversation_messages "
                "WHERE conversation_id=%s AND message_kind='WORK_GROUP_RESULT'", (conversation,),
            ).fetchone()[0]
        assert event["actor"] == coordinator_id
        assert "Consolidación registrada por PM (" + coordinator_id in message
        assert "confirmada por CEO" not in message


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
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
        from aao.postgresql_connection import connect_postgres
        with connect_postgres() as db:
            assert db.execute(
                "SELECT 1 FROM protocol_instances WHERE protocol_id='implementation' AND subject_id=%s",
                (wid,),
            ).fetchone() is None
        admitted = client.post(f"/v1/work/{wid}/admit", headers=worker)
        assert admitted.status_code == 200, admitted.text
        assert admitted.json()["status"] == "READY"
        assert client.post(f"/v1/work/{wid}/admit", headers=worker).status_code == 409
        with connect_postgres() as db:
            implementation = db.execute(
                "SELECT id,protocol_version,subject_type,started_by FROM protocol_instances "
                "WHERE protocol_id='implementation' AND subject_id=%s", (wid,),
            ).fetchone()
            events = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='protocol.started'",
                (wid,),
            ).fetchall()
        assert implementation is not None
        assert implementation[1:] == ("1.0.0", "work_item", agent_id)
        assert len(events) == 1
        assert events[0][0]["protocol_instance_id"] == str(implementation[0])
        board = client.get(f"/v1/projects/{project}/board", headers=ceo)
        assert board.status_code == 200
        assert any(w["id"] == wid and w["status"] == "READY" for w in board.json())


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_work_group_admission_waits_for_prerequisites_and_rejects_parent(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "dependency-ceo")
    ceo = {"X-CEO-Token": "dependency-ceo"}
    with TestClient(app) as client:
        principal = "dependency-agent-" + str(uuid4())
        credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        })
        assert credential.status_code == 201, credential.text
        worker = {"X-Agent-Token": credential.json()["token"]}

        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Dependency admission " + str(uuid4()), "objective": "Test prerequisites",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Dependency admission", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.admit", "execution.claim"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": capability,
            }).status_code == 201
        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Dependency plan",
        }).json()["id"]
        group_response = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo,
            json={
                "idempotency_key": str(uuid4()), "title": "Plan", "description": "Plan summary",
                "acceptance_criteria": ["All results are reviewed"],
                "tasks": [
                    {"key": "prerequisite", "title": "Prerequisite", "acceptance_criteria": ["Done"]},
                    {"key": "parallel", "title": "Independent sibling", "acceptance_criteria": ["Done"]},
                    {"key": "dependent", "title": "Dependent", "acceptance_criteria": ["Done"],
                     "depends_on": ["prerequisite"]},
                ],
            },
        )
        assert group_response.status_code == 201, group_response.text
        group = group_response.json()
        ids = {task["title"]: task["id"] for task in group["tasks"]}
        for task_id in ids.values():
            assigned = client.put(f"/v1/work/{task_id}/assignment", headers=ceo, json={
                "principal_id": principal,
            })
            assert assigned.status_code == 200, assigned.text

        projected = client.get(f"/v1/projects/{project}/work-groups", headers=ceo)
        assert projected.status_code == 200, projected.text
        projected_children = {
            child["work_id"]: child for child in projected.json()[0]["children"]
        }
        assert projected_children[ids["Dependent"]]["dependencies"] == [{
            "work_id": ids["Prerequisite"], "status": "INBOX",
        }]

        # An unresolved prerequisite blocks the dependent child without changing
        # its canonical INBOX state; an independent sibling remains admissible.
        blocked = client.post(f"/v1/work/{ids['Dependent']}/admit", headers=worker)
        assert blocked.status_code == 409
        assert "Dependencies unresolved" in blocked.text
        with connect_postgres() as db:
            assert db.execute(
                "SELECT 1 FROM protocol_instances WHERE protocol_id='implementation' "
                "AND subject_id=%s", (ids["Dependent"],),
            ).fetchone() is None
        assert client.post(f"/v1/work/{ids['Independent sibling']}/admit", headers=worker).status_code == 200
        assert client.post(f"/v1/work/{group['parent_work_id']}/admit", headers=worker).status_code == 409

        with connect_postgres() as db:
            state = db.execute(
                "SELECT status FROM work_items WHERE id=%s", (ids["Dependent"],),
            ).fetchone()[0]
            db.execute("UPDATE work_items SET status='IN_REVIEW' WHERE id=%s", (ids["Prerequisite"],))
        assert state == "INBOX"
        still_blocked = client.post(f"/v1/work/{ids['Dependent']}/admit", headers=worker)
        assert still_blocked.status_code == 409
        projected = client.get(f"/v1/projects/{project}/work-groups", headers=ceo)
        dependency = next(
            child for child in projected.json()[0]["children"]
            if child["work_id"] == ids["Dependent"]
        )["dependencies"][0]
        assert dependency == {"work_id": ids["Prerequisite"], "status": "IN_REVIEW"}
        with connect_postgres() as db:
            db.execute("UPDATE work_items SET status='DONE' WHERE id=%s", (ids["Prerequisite"],))
        projected = client.get(f"/v1/projects/{project}/work-groups", headers=ceo)
        dependency = next(
            child for child in projected.json()[0]["children"]
            if child["work_id"] == ids["Dependent"]
        )["dependencies"][0]
        assert dependency == {"work_id": ids["Prerequisite"], "status": "DONE"}
        admitted = client.post(f"/v1/work/{ids['Dependent']}/admit", headers=worker)
        assert admitted.status_code == 200, admitted.text
        assert admitted.json()["status"] == "READY"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_agent_dispatches_only_its_assigned_and_pre_evaluated_work(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "dispatch-ceo")
    monkeypatch.setenv("AAO_AGENT_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "dispatch-ceo"}
    with TestClient(app) as client:
        agent_ids = ["dispatch-agent-" + str(uuid4()), "unassigned-agent-" + str(uuid4())]
        workers = []
        for principal_id in agent_ids:
            token = client.post("/v1/principals/credentials", headers=ceo, json={
                "principal_id": principal_id, "kind": "AGENT",
            }).json()["token"]
            workers.append({"X-Agent-Token": token})

        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Dispatch " + str(uuid4()), "objective": "Dispatch only existing authorized work",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Dispatch test", "mandate_id": mandate,
        }).json()["id"]
        for principal_id in agent_ids:
            for capability in ("work.create", "work.admit", "execution.claim"):
                assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                    "principal_id": principal_id, "capability": capability,
                }).status_code == 201

        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Dispatch plan",
        }).json()["id"]
        group_response = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo,
            json={
                "idempotency_key": str(uuid4()), "title": "Confirmed plan", "description": "A bounded task",
                "acceptance_criteria": ["The task has an auditable execution"],
                "tasks": [{"key": "task", "title": "Assigned task", "acceptance_criteria": ["Execute once"]}],
            },
        )
        assert group_response.status_code == 201, group_response.text
        work_id = group_response.json()["tasks"][0]["id"]
        assert client.put(f"/v1/work/{work_id}/assignment", headers=ceo, json={
            "principal_id": agent_ids[0],
        }).status_code == 200
        base_sha = "a" * 40

        # The dispatcher neither fabricates a capability evaluation nor stages
        # work in its absence. Another authorized but unassigned identity sees idle.
        blocked = client.post("/v1/agent/dispatch-next", headers=workers[0], json={
            "project_id": project, "principal_id": agent_ids[0], "base_sha": base_sha,
        })
        assert blocked.status_code == 202, blocked.text
        assert blocked.json()["status"] == "BLOCKED"
        assert blocked.json()["work_id"] == work_id
        with connect_postgres() as db:
            blocker_events = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.dispatch_blocked'",
                (work_id,),
            ).fetchall()
        assert len(blocker_events) == 1
        assert blocker_events[0][0]["principal_id"] == agent_ids[0]
        assert blocker_events[0][0]["reason"] == blocked.json()["reason"]
        block_details = blocker_events[0][0]
        assert block_details["blockage_id"]
        assert block_details["next_action"].startswith("Resolve the persisted precondition")
        assert block_details["protocol_instance_id"]
        with connect_postgres() as db:
            pinned = db.execute(
                "SELECT protocol_id,protocol_version,started_by,subject_type,subject_id "
                "FROM protocol_instances WHERE id=%s",
                (block_details["protocol_instance_id"],),
            ).fetchone()
            start_details = db.execute(
                "SELECT details FROM events WHERE kind='protocol.started' "
                "AND details->>'protocol_instance_id'=%s",
                (block_details["protocol_instance_id"],),
            ).fetchone()[0]
        assert pinned[:4] == ("blockage-escalation", "1.0.0", agent_ids[0], "work_item")
        assert str(pinned[4]) == work_id
        assert start_details["protocol_id"] == "blockage-escalation"
        assert start_details["protocol_version"] == "1.0.0"
        assert start_details["actor"] == agent_ids[0]
        projected_group = client.get(
            f"/v1/projects/{project}/work-groups", headers=ceo,
        ).json()[0]
        projected_block = projected_group["children"][0]["dispatch_block"]
        assert projected_block["protocol_instance_id"] == block_details["protocol_instance_id"]
        assert projected_block["next_action"] == block_details["next_action"]
        # Repeated worker polling preserves the canonical event log without spam.
        repeated = client.post("/v1/agent/dispatch-next", headers=workers[0], json={
            "project_id": project, "principal_id": agent_ids[0], "base_sha": base_sha,
        })
        assert repeated.json() == blocked.json()
        with connect_postgres() as db:
            assert db.execute(
                "SELECT count(*) FROM events WHERE subject_id=%s AND kind='work.dispatch_blocked'",
                (work_id,),
            ).fetchone()[0] == 1
        assert client.post("/v1/agent/dispatch-next", headers=workers[1], json={
            "project_id": project, "principal_id": agent_ids[1], "base_sha": base_sha,
        }).json()["status"] == "IDLE"
        mismatch = client.post("/v1/agent/dispatch-next", headers=workers[0], json={
            "project_id": project, "principal_id": agent_ids[1], "base_sha": base_sha,
        })
        assert mismatch.status_code == 403

        capability = {
            "capability_id": "aao.agent-runner", "version": "1.0.0", "capability_type": "agent",
            "provenance": {"kind": "repository"},
            "contract": {
                "purpose": "Turn a task into a patch proposal", "entrypoint": "aao.agent_runner:patch",
                "inputs": ["task", "base_sha"], "outputs": ["patch proposal"], "platform": "Linux",
                "authority_boundary": "edits only a disposable clone; proposes, never applies or merges",
                "compatible_roles": ["implementer"],
                "model_profile": {"backend": "fixture", "provider": "fixture", "model": None,
                                  "seats": ["patch.tests"], "cost_per_attempt_usd": 0.5},
            },
            "required_permissions": ["execution.claim", "code.propose"], "risks": ["agent edits a disposable clone"],
            "dependencies": [], "tests": ["tests/test_agent_runner.py"], "compatibility": {},
            "evidence": ["repository capability contract"],
        }
        registered = client.post(f"/v1/projects/{project}/capabilities", headers=workers[0], json=capability)
        assert registered.status_code == 201, registered.text
        evaluation = client.post(f"/v1/projects/{project}/capability-evaluations", headers=workers[0], json={
            "task_id": work_id,
            "options": [{"choice": choice, "fit": fit, "security": fit, "cost": fit,
                         "time": fit, "tokens": fit, "maintenance": fit}
                        for choice, fit in (("reuse", 5), ("adapt", 3), ("build", 1))],
            "rationale": "Use the registered local runner for this bounded task.",
            "evidence": ["repository capability contract"],
            "capability_id": "aao.agent-runner", "version": "1.0.0",
        })
        assert evaluation.status_code == 201, evaluation.text

        staged = client.post("/v1/agent/dispatch-next", headers=workers[0], json={
            "project_id": project, "principal_id": agent_ids[0], "base_sha": base_sha,
        })
        assert staged.status_code == 202, staged.text
        assert staged.json()["status"] == "QUEUED"
        assert staged.json()["work_id"] == work_id
        assert client.post("/v1/agent/dispatch-next", headers=workers[0], json={
            "project_id": project, "principal_id": agent_ids[0], "base_sha": base_sha,
        }).json()["execution_id"] == staged.json()["execution_id"]

        board = client.get(f"/v1/projects/{project}/board", headers=ceo).json()
        item = next(row for row in board if row["id"] == work_id)
        assert item["status"] == "READY"
        assert len(item["executions"]) == 1


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_dependency_blocked_dispatch_is_persisted_and_resumes_after_prerequisite_clears(monkeypatch):
    """RST-5: dependency gates admission/dispatch and remains retryable."""
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "dependency-dispatch-ceo")
    monkeypatch.setenv("AAO_AGENT_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "dependency-dispatch-ceo"}
    with TestClient(app) as client:
        worker_id = "dependency-dispatch-agent-" + str(uuid4())
        credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        assert credential.status_code == 201, credential.text
        worker = {"X-Agent-Token": credential.json()["token"]}

        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Dependency dispatch " + str(uuid4()),
            "objective": "Verify dependency blocks and later permits dispatch",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Dependency dispatch", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.admit", "execution.claim", "work.create"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": worker_id, "capability": capability,
            }).status_code == 201

        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Dependency dispatch plan",
        }).json()["id"]
        group_response = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "title": "Prerequisite plan",
                "description": "A dependent task must wait for its prerequisite.",
                "acceptance_criteria": ["The prerequisite is complete before dispatch"],
                "tasks": [
                    {"key": "prerequisite", "title": "Prerequisite",
                     "acceptance_criteria": ["Resolve through an authorized operation"]},
                    {"key": "dependent", "title": "Dependent",
                     "acceptance_criteria": ["Dispatch only after prerequisite completion"],
                     "depends_on": ["prerequisite"]},
                ],
            },
        )
        assert group_response.status_code == 201, group_response.text
        tasks = {task["title"].lower(): task["id"]
                 for task in group_response.json()["tasks"]}
        dependent_id = tasks["dependent"]
        assert client.put(f"/v1/work/{dependent_id}/assignment", headers=ceo, json={
            "principal_id": worker_id,
        }).status_code == 200

        capability = {
            "capability_id": "aao.dependency-dispatch-test", "version": "1.0.0",
            "capability_type": "agent", "provenance": {"kind": "repository"},
            "contract": {
                "purpose": "Test dependency-gated dispatch", "entrypoint": "aao.agent_runner:patch",
                "inputs": ["task", "base_sha"], "outputs": ["patch proposal"],
                "platform": "Linux", "authority_boundary": "disposable proposal only",
                "compatible_roles": ["implementer"],
                "model_profile": {"backend": "fixture", "provider": "fixture", "model": None,
                                  "seats": ["patch.tests"], "cost_per_attempt_usd": 0.5},
            },
            "required_permissions": ["execution.claim", "code.propose"],
            "risks": ["agent edits a disposable clone"], "dependencies": [],
            "tests": ["tests/test_agent_runner.py"], "compatibility": {},
            "evidence": ["repository capability contract"],
        }
        registered = client.post(
            f"/v1/projects/{project}/capabilities", headers=worker, json=capability,
        )
        assert registered.status_code == 201, registered.text
        evaluation = client.post(
            f"/v1/projects/{project}/capability-evaluations", headers=worker, json={
                "task_id": dependent_id,
                "options": [{"choice": choice, "fit": fit, "security": fit, "cost": fit,
                             "time": fit, "tokens": fit, "maintenance": fit}
                            for choice, fit in (("reuse", 5), ("adapt", 3), ("build", 1))],
                "rationale": "Use the registered local runner for this bounded test task.",
                "evidence": ["repository capability contract"],
                "capability_id": "aao.dependency-dispatch-test", "version": "1.0.0",
            },
        )
        assert evaluation.status_code == 201, evaluation.text

        rejected_admission = client.post(f"/v1/work/{dependent_id}/admit", headers=worker)
        assert rejected_admission.status_code == 409
        assert "Dependencies unresolved" in rejected_admission.text
        blocked = client.post("/v1/agent/dispatch-next", headers=worker, json={
            "project_id": project, "principal_id": worker_id, "base_sha": "a" * 40,
        })
        assert blocked.status_code == 202, blocked.text
        assert blocked.json()["status"] == "BLOCKED"
        assert blocked.json()["work_id"] == dependent_id
        assert blocked.json()["reason"] == "Dependencies must be DONE before dispatch"
        with connect_postgres() as db:
            assert db.execute(
                "SELECT status FROM work_items WHERE id=%s", (dependent_id,),
            ).fetchone()[0] == "INBOX"
            assert db.execute(
                "SELECT count(*) FROM execution_queue WHERE work_id=%s", (dependent_id,),
            ).fetchone()[0] == 0
            block = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.dispatch_blocked'",
                (dependent_id,),
            ).fetchone()[0]
            assert block["reason"] == blocked.json()["reason"]
            assert block["protocol_instance_id"]
            pin = db.execute(
                "SELECT protocol_id,protocol_version,subject_id FROM protocol_instances WHERE id=%s",
                (block["protocol_instance_id"],),
            ).fetchone()
            assert pin[0:2] == ("blockage-escalation", "1.0.0")
            assert str(pin[2]) == dependent_id

        projected = client.get(f"/v1/projects/{project}/work-groups", headers=ceo)
        assert projected.status_code == 200
        child = next(item for item in projected.json()[0]["children"]
                    if item["work_id"] == dependent_id)
        assert child["dependencies"] == [{"work_id": tasks["prerequisite"], "status": "INBOX"}]
        assert child["dispatch_block"]["reason"] == blocked.json()["reason"]

        # Force the dispatch query to overlap an uncommitted prerequisite
        # completion. Its snapshot may safely see the old state and block; it
        # must never stage while the completion is still uncommitted. This is
        # database-fixture concurrency coverage, not an operational completion.
        prerequisite_updated = Event()
        dispatch_finished = Event()

        def complete_prerequisite_fixture():
            with connect_postgres() as db:
                db.execute("UPDATE work_items SET status='DONE' WHERE id=%s",
                           (tasks["prerequisite"],))
                prerequisite_updated.set()
                assert dispatch_finished.wait(timeout=5)

        with ThreadPoolExecutor(max_workers=1) as executor:
            completion = executor.submit(complete_prerequisite_fixture)
            assert prerequisite_updated.wait(timeout=5)
            raced = client.post("/v1/agent/dispatch-next", headers=worker, json={
                "project_id": project, "principal_id": worker_id, "base_sha": "a" * 40,
            })
            dispatch_finished.set()
            completion.result(timeout=5)
        assert raced.status_code == 202, raced.text
        assert raced.json()["status"] == "BLOCKED"
        assert raced.json()["reason"] == "Dependencies must be DONE before dispatch"
        with connect_postgres() as db:
            assert db.execute(
                "SELECT count(*) FROM execution_queue WHERE work_id=%s", (dependent_id,),
            ).fetchone()[0] == 0

        unblocked = client.post("/v1/agent/dispatch-next", headers=worker, json={
            "project_id": project, "principal_id": worker_id, "base_sha": "a" * 40,
        })
        assert unblocked.status_code == 202, unblocked.text
        assert unblocked.json()["status"] == "QUEUED"
        assert unblocked.json()["work_id"] == dependent_id
        with connect_postgres() as db:
            assert db.execute(
                "SELECT status FROM work_items WHERE id=%s", (dependent_id,),
            ).fetchone()[0] == "READY"
            assert db.execute(
                "SELECT count(*) FROM execution_queue WHERE work_id=%s AND status='QUEUED'",
                (dependent_id,),
            ).fetchone()[0] == 1


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_group_assignment_routes_execution_without_creating_grants(monkeypatch):
    from aao.execution_queue import ExecutionConflict, claim, complete
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "assignment-ceo")
    ceo = {"X-CEO-Token": "assignment-ceo"}
    with TestClient(app) as client:
        worker_ids = ["assigned-" + str(uuid4()), "other-" + str(uuid4())]
        worker_tokens = [
            client.post("/v1/principals/credentials", headers=ceo, json={
                "principal_id": worker_id, "kind": "AGENT",
            }).json()["token"] for worker_id in worker_ids
        ]
        workers = [
            {"X-Agent-Token": token} for token in worker_tokens
        ]
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Assignment " + str(uuid4()), "objective": "Route child work to real identities",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Assignment test", "mandate_id": mandate,
        }).json()["id"]
        for worker_id in worker_ids:
            for capability in ("work.admit", "work.progress", "execution.claim"):
                assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                    "principal_id": worker_id, "capability": capability,
                }).status_code == 201
        assignable = client.get(
            f"/v1/projects/{project}/assignable-agents", headers=ceo,
        )
        assert assignable.status_code == 200, assignable.text
        assert {agent["principal_id"] for agent in assignable.json()} == set(worker_ids)
        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Assignment discussion",
        }).json()["id"]
        group = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "title": "Deliver result",
                "description": "Consolidate children after completion",
                "acceptance_criteria": ["Child evidence is preserved"],
                "tasks": [{"key": "child", "title": "Assigned child",
                           "acceptance_criteria": ["Evidence recorded"],
                           "assigned_principal_id": worker_ids[0]}],
            },
        )
        assert group.status_code == 201, group.text
        work_id = group.json()["tasks"][0]["id"]
        assert group.json()["tasks"][0]["assigned_principal_id"] == worker_ids[0]
        assignment_path = f"/v1/work/{work_id}/assignment"
        assert client.put(assignment_path, headers=workers[0], json={
            "principal_id": worker_ids[0],
        }).status_code == 403
        assignment = client.put(assignment_path, headers=ceo, json={
            "principal_id": worker_ids[0],
        })
        assert assignment.status_code == 200, assignment.text
        assert assignment.json() == {
            "work_id": work_id, "principal_id": worker_ids[0],
            "assigned_by": "ceo", "grants_created": False,
        }
        projected_group = client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]
        assert projected_group["children"][0]["assigned_principal_id"] == worker_ids[0]
        assert projected_group["source_sha256"]
        blocked_dispatch = client.post("/v1/agent/dispatch-next", headers=workers[0], json={
            "project_id": project, "principal_id": worker_ids[0], "base_sha": "a" * 40,
        })
        assert blocked_dispatch.status_code == 202, blocked_dispatch.text
        assert blocked_dispatch.json()["status"] == "BLOCKED"
        projected_group = client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]
        dispatch_block = projected_group["children"][0]["dispatch_block"]
        assert dispatch_block["principal_id"] == worker_ids[0]
        assert "capability evaluation" in dispatch_block["reason"]
        board = client.get(f"/v1/projects/{project}/board", headers=ceo).json()
        child = next(item for item in board if item["id"] == work_id)
        assert child["assigned_principal_id"] == worker_ids[0]
        with connect_postgres() as db:
            grant_count = db.execute(
                "SELECT count(*) FROM project_grants WHERE project_id=%s AND principal_id=%s",
                (project, worker_ids[0]),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO execution_queue(id,work_id,project_id,status,input_json) "
                "VALUES (%s,%s,%s,'QUEUED',%s::jsonb)",
                (str(uuid4()), work_id, project, json.dumps({"type": "aao.inert.v1"})),
            )
        assert grant_count == 3
        assert client.post(f"/v1/work/{work_id}/admit", headers=workers[1]).status_code == 403
        assert client.post(f"/v1/work/{work_id}/admit", headers=workers[0]).status_code == 200
        assert claim(worker_ids[1], agent_credential=worker_tokens[1], project_id=project) is None
        lease = claim(worker_ids[0], agent_credential=worker_tokens[0], project_id=project)
        assert lease and lease["work_id"] == work_id
        reassignment = client.put(assignment_path, headers=ceo, json={
            "principal_id": worker_ids[1],
        })
        assert reassignment.status_code == 409
        with pytest.raises(ExecutionConflict, match="does not own the work assignment"):
            complete(lease["execution_id"], lease["token"], worker_ids[1],
                     {"ok": True}, agent_credential=worker_tokens[1])
        complete(lease["execution_id"], lease["token"], worker_ids[0],
                 {"ok": True}, agent_credential=worker_tokens[0])


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_ceo_work_request_creates_only_audited_inbox_item(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "work-request-ceo")
    ceo = {"X-CEO-Token": "work-request-ceo"}
    payload = {
        "title": "CEO direction " + str(uuid4()),
        "description": "Persist the request without admitting execution.",
        "acceptance_criteria": ["Visible on the canonical project board"],
        "due_date": "2026-11-15",
    }
    with TestClient(app) as client:
        agent_credential = client.post(
            "/v1/principals/credentials", headers=ceo,
            json={"principal_id": "request-agent-" + str(uuid4()), "kind": "AGENT"},
        )
        assert agent_credential.status_code == 201
        worker = {"X-Agent-Token": agent_credential.json()["token"]}
        assert client.post(
            "/v1/projects/not-a-project/work-requests", json=payload,
        ).status_code == 403

        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "CEO request mandate " + str(uuid4()), "objective": "Test request path",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "CEO request project", "mandate_id": mandate,
        }).json()["id"]
        assert client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": payload["title"], "description": payload["description"],
            "author_id": agent_credential.json()["principal_id"],
            "acceptance_criteria": payload["acceptance_criteria"],
        }).status_code == 403
        created = client.post(f"/v1/projects/{project}/work-requests", headers=ceo, json=payload)
        assert created.status_code == 201, created.text
        work_id = created.json()["id"]
        assert created.json()["status"] == "INBOX"

        board = client.get(f"/v1/projects/{project}/board", headers=ceo)
        assert board.status_code == 200
        row = next(item for item in board.json() if item["id"] == work_id)
        assert row["status"] == "INBOX"
        assert row["due_date"] == payload["due_date"]
        with connect_postgres() as db:
            author = db.execute(
                "SELECT author_id,due_date FROM work_items WHERE id=%s", (work_id,),
            ).fetchone()
            event = db.execute(
                "SELECT kind,details FROM events WHERE subject_id=%s AND kind='work.requested'",
                (work_id,),
            ).fetchone()
            protocol_instance = db.execute(
                "SELECT id,protocol_id,protocol_version,subject_type,subject_id,"
                "request_sha256,started_by FROM protocol_instances "
                "WHERE subject_type='work_item' AND subject_id=%s",
                (work_id,),
            ).fetchone()
            protocol_event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='protocol.started'",
                (work_id,),
            ).fetchone()
            execution_count = db.execute(
                "SELECT count(*) FROM execution_queue WHERE work_id=%s", (work_id,),
            ).fetchone()[0]
            grant_count = db.execute(
                "SELECT count(*) FROM project_grants WHERE project_id=%s", (project,),
            ).fetchone()[0]
        assert author[0] == "ceo"
        assert author[1].isoformat() == payload["due_date"]
        assert event[0] == "work.requested"
        assert event[1]["actor"] == "ceo"
        assert event[1]["admitted"] is False
        assert protocol_instance is not None
        assert (
            protocol_instance[1], protocol_instance[2], protocol_instance[3],
            str(protocol_instance[4]),
        ) == ("intake-classification", "1.0.0", "work_item", work_id)
        assert len(protocol_instance[5]) == 64
        assert protocol_instance[6] == "ceo"
        assert protocol_event[0]["protocol_instance_id"] == str(protocol_instance[0])
        assert protocol_event[0]["protocol_version"] == "1.0.0"
        assert execution_count == 0
        assert grant_count == 0

        assert client.post(f"/v1/projects/{project}/state", headers=ceo,
                           json={"action": "pause"}).status_code == 200
        paused = client.post(f"/v1/projects/{project}/work-requests", headers=ceo, json=payload)
        assert paused.status_code == 409


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_ceo_project_conversation_persists_without_fabricating_aao_reply(monkeypatch):
    from aao import conversation_provider
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "conversation-ceo")
    monkeypatch.setenv("AAO_CONVERSATION_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AAO_CONVERSATION_MODEL", "conversation-test-model")
    provider_token = "conversation-test-secret-token"
    monkeypatch.setenv("AAO_CONVERSATION_API_KEY", provider_token)
    monkeypatch.setenv(
        "AAO_CONVERSATION_API_URL",
        "https://user:ignored@gateway.example/v1/chat?api_key=" + provider_token,
    )
    ceo = {"X-CEO-Token": "conversation-ceo"}
    with TestClient(app) as client:
        assert client.post(
            "/v1/projects/not-a-project/conversations", json={"title": "Notes"},
        ).status_code == 403
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Conversation mandate " + str(uuid4()), "objective": "Persistence test",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Conversation project", "mandate_id": mandate,
        }).json()["id"]

        created = client.post(
            f"/v1/projects/{project}/conversations", headers=ceo,
            json={"title": "Pilot discussion"},
        )
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        message = client.post(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages",
            headers=ceo, json={"body": "Please investigate the real execution evidence."},
        )
        assert message.status_code == 201, message.text
        assert message.json()["sender"] == "CEO"
        assert message.json()["related_work_id"] is None

        conversion_url = (
            f"/v1/projects/{project}/conversations/{conversation_id}/messages/"
            f"{message.json()['id']}/work-request"
        )
        conversion = {"title": "Investigate evidence", "description": "Review execution evidence", "acceptance_criteria": ["Evidence linked"]}
        assert client.post(conversion_url, json=conversion).status_code == 403
        other_mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Other conversation mandate " + str(uuid4()), "objective": "Scope test",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{other_mandate}/confirm", headers=ceo).status_code == 200
        other_project = client.post("/v1/projects", headers=ceo, json={
            "name": "Other conversation project", "mandate_id": other_mandate,
        }).json()["id"]
        assert client.post(
            f"/v1/projects/{other_project}/conversations/{conversation_id}/messages/"
            f"{message.json()['id']}/work-request", headers=ceo, json=conversion,
        ).status_code == 404

        # Reopening returns the same persisted objects, without a synthetic
        # AAO reply or implicit work conversion.
        listed = client.get(f"/v1/projects/{project}/conversations", headers=ceo)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [conversation_id]
        reopened = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        )
        assert reopened.status_code == 200
        assert [item["id"] for item in reopened.json()] == [message.json()["id"]]
        assert reopened.json()[0]["body"] == "Please investigate the real execution evidence."
        assert not any(item["sender"] == "AAO" for item in reopened.json())
        assert client.get(
            f"/v1/projects/{uuid4()}/conversations/{conversation_id}/messages", headers=ceo,
        ).status_code == 404
        converted = client.post(conversion_url, headers=ceo, json=conversion)
        assert converted.status_code == 200, converted.text
        work_id = converted.json()["id"]
        assert converted.json()["status"] == "INBOX"
        assert converted.json()["created"] is True
        retry = client.post(conversion_url, headers=ceo, json={
            "title": "Ignored retry payload", "acceptance_criteria": ["Must not duplicate"],
        })
        assert retry.status_code == 200
        assert retry.json() == {"id": work_id, "status": "INBOX", "created": False}

        reopened = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        )
        assert reopened.json()[0]["related_work_id"] == work_id
        assert reopened.json()[0]["work_status"] == "INBOX"
        assert reopened.json()[0]["latest_execution"] is None
        board = client.get(f"/v1/projects/{project}/board", headers=ceo)
        assert any(item["id"] == work_id and item["status"] == "INBOX" for item in board.json())
        with connect_postgres() as db:
            counts = db.execute(
                "SELECT (SELECT count(*) FROM work_items WHERE project_id=%s),"
                "(SELECT count(*) FROM execution_queue e JOIN work_items w ON w.id=e.work_id "
                "WHERE w.project_id=%s),"
                "(SELECT count(*) FROM project_grants WHERE project_id=%s)",
                (project, project, project),
            ).fetchone()
            linked_work = db.execute(
                "SELECT w.project_id,w.author_id,w.description,w.acceptance_criteria "
                "FROM work_items w JOIN project_conversation_messages m ON m.related_work_id=w.id "
                "WHERE m.id=%s", (message.json()["id"],),
            ).fetchone()
            audit_event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s "
                "AND kind='conversation.message.created'", (conversation_id,),
            ).fetchone()
            work_audit = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.requested'",
                (work_id,),
            ).fetchone()
            link_audit = db.execute(
                "SELECT details FROM events WHERE subject_id=%s "
                "AND kind='conversation.message.work_requested'", (message.json()["id"],),
            ).fetchone()
            message_protocols = db.execute(
                "SELECT protocol_id,protocol_version,started_by FROM protocol_instances "
                "WHERE subject_type='work_item' AND subject_id=%s", (work_id,),
            ).fetchall()
        assert counts == (1, 0, 0)

        # The conversation projection exposes only current work/execution
        # status and bounded provenance, never the execution result payload.
        execution_id = str(uuid4())
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO execution_queue(id,work_id,project_id,status,input_json,result_json) "
                "VALUES (%s,%s,%s,'SUCCEEDED','{}'::jsonb,%s::jsonb)",
                (execution_id, work_id, project, '{"provider":"openai","model":"gpt-6-luna","backend":"codex","patch":"private payload"}'),
            )
        projected = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()[0]
        assert projected["work_status"] == "INBOX"
        assert projected["latest_execution"] == {
            "id": execution_id, "status": "SUCCEEDED", "backend": "codex",
            "provider": "openai", "model": "gpt-6-luna",
        }
        assert "patch" not in str(projected)
        assert str(linked_work[0]) == project
        assert linked_work[1] == "ceo"
        assert linked_work[2] == "Please investigate the real execution evidence."
        assert linked_work[3] == ["Evidence linked"]
        assert audit_event and audit_event[0]["actor"] == "ceo"
        assert work_audit[0]["source_message_id"] == message.json()["id"]
        assert work_audit[0]["admitted"] is False
        assert link_audit[0]["work_id"] == work_id
        assert message_protocols == [("intake-classification", "1.0.0", "ceo")]

        # Task structuring references the complete persisted thread, not an
        # individual message; only CEO confirmation creates canonical INBOX work.
        thread_task = client.post(
            f"/v1/projects/{project}/conversations/{conversation_id}/work-requests",
            headers=ceo, json={
                "title": "Synthesize discussion", "description": "CEO-reviewed outcome of the discussion",
                "acceptance_criteria": ["Decision and evidence recorded"],
            },
        )
        assert thread_task.status_code == 201, thread_task.text
        thread_work_id = thread_task.json()["id"]
        assert thread_task.json()["status"] == "INBOX"
        assert client.get(f"/v1/projects/{project}/board", headers=ceo).json()
        with connect_postgres() as db:
            thread_work = db.execute(
                "SELECT project_id,author_id,status,description FROM work_items WHERE id=%s",
                (thread_work_id,),
            ).fetchone()
            thread_audit = db.execute(
                "SELECT kind,details FROM events WHERE subject_id=%s AND kind='work.requested_from_conversation'",
                (thread_work_id,),
            ).fetchone()
            thread_protocol = db.execute(
                "SELECT protocol_id,protocol_version FROM protocol_instances "
                "WHERE subject_type='work_item' AND subject_id=%s", (thread_work_id,),
            ).fetchone()
        assert (str(thread_work[0]), *thread_work[1:]) == (
            project, "ceo", "INBOX", "CEO-reviewed outcome of the discussion",
        )
        assert thread_audit[1]["conversation_id"] == conversation_id
        assert thread_audit[1]["admitted"] is False
        assert thread_protocol == ("intake-classification", "1.0.0")

        # CEO-confirmed thread breakdown persists a parent, parallel children,
        # and a dependency DAG without admitting or queuing any work.
        group_url = f"/v1/projects/{project}/conversations/{conversation_id}/work-groups"
        group_request = {
            "idempotency_key": str(uuid4()),
            "title": "Deliver the reviewed plan",
            "description": "Parent summary from the full discussion",
            "acceptance_criteria": ["All child results consolidated"],
            "tasks": [
                {"key": "research", "title": "Research evidence",
                 "description": "Review primary evidence", "acceptance_criteria": ["Evidence cited"]},
                {"key": "design", "title": "Design implementation",
                 "description": "Draft a viable plan", "acceptance_criteria": ["Plan recorded"]},
                {"key": "consolidate", "title": "Consolidate findings",
                 "description": "Combine approved results", "acceptance_criteria": ["Findings linked"],
                 "depends_on": ["research", "design"]},
            ],
        }
        assert client.post(group_url, json=group_request).status_code == 403
        group = client.post(group_url, headers=ceo, json=group_request)
        assert group.status_code == 201, group.text
        group_body = group.json()
        assert group_body["status"] == "INBOX" and group_body["created"] is True
        assert len(group_body["tasks"]) == 3
        research_id = next(task["id"] for task in group_body["tasks"] if task["title"] == "Research evidence")
        design_id = next(task["id"] for task in group_body["tasks"] if task["title"] == "Design implementation")
        consolidate = next(task for task in group_body["tasks"] if task["title"] == "Consolidate findings")
        assert set(consolidate["depends_on"]) == {research_id, design_id}
        repeated_group = client.post(group_url, headers=ceo, json=group_request)
        assert repeated_group.status_code == 201
        assert repeated_group.json()["created"] is False
        assert repeated_group.json()["id"] == group_body["id"]
        assert repeated_group.json()["parent_work_id"] == group_body["parent_work_id"]
        with connect_postgres() as db:
            planning_instance = db.execute(
                "SELECT id,protocol_id,protocol_version,subject_type,subject_id,started_by "
                "FROM protocol_instances WHERE subject_type='work_group' AND subject_id=%s",
                (group_body["id"],),
            ).fetchone()
            planning_events = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='protocol.started'",
                (group_body["id"],),
            ).fetchall()
        assert planning_instance is not None
        assert (
            planning_instance[1], planning_instance[2], planning_instance[3],
            str(planning_instance[4]), planning_instance[5],
        ) == ("planning-assignment", "1.0.0", "work_group", group_body["id"], "ceo")
        assert len(planning_instance[0].hex) == 32
        assert len(planning_events) == 1
        assert planning_events[0][0]["protocol_instance_id"] == str(planning_instance[0])
        assert client.post(group_url, headers=ceo, json={
            **group_request, "description": "Same key, mutated payload",
        }).status_code == 409
        assert client.post(group_url, headers=ceo, json={
            **group_request, "idempotency_key": str(uuid4()), "tasks": [
                {"key": "x", "title": "X", "acceptance_criteria": ["x"], "depends_on": ["y"]},
                {"key": "y", "title": "Y", "acceptance_criteria": ["y"], "depends_on": ["x"]},
            ],
        }).status_code == 422
        board = client.get(f"/v1/projects/{project}/board", headers=ceo).json()
        parent = next(item for item in board if item["id"] == group_body["parent_work_id"])
        assert parent["work_group_id"] == group_body["id"]
        child = next(item for item in board if item["id"] == consolidate["id"])
        assert child["parent_work_id"] == group_body["parent_work_id"]
        assert set(child["depends_on"]) == {research_id, design_id}
        with connect_postgres() as db:
            group_state = db.execute(
                "SELECT count(*),count(*) FILTER (WHERE status <> 'INBOX') "
                "FROM work_items WHERE id=%s OR parent_work_id=%s",
                (group_body["parent_work_id"], group_body["parent_work_id"]),
            ).fetchone()
            group_executions = db.execute(
                "SELECT count(*) FROM execution_queue WHERE work_id=%s "
                "OR work_id IN (SELECT id FROM work_items WHERE parent_work_id=%s)",
                (group_body["parent_work_id"], group_body["parent_work_id"]),
            ).fetchone()[0]
        assert group_state == (4, 0)
        assert group_executions == 0

        # The assistant context may summarize only relationally persisted
        # validation, independent review, and reconciled publication facts.
        outcome_agent = "conversation-outcome-agent-" + str(uuid4())
        outcome_credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": outcome_agent, "kind": "AGENT",
        })
        assert outcome_credential.status_code == 201, outcome_credential.text
        proposal_id, validation_id, review_id = str(uuid4()), str(uuid4()), str(uuid4())
        candidate_sha = "b" * 40
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO patch_proposals(id,work_id,project_id,proposer_id,base_sha,"
                "patch_sha256,patch_bytes,changed_paths) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (proposal_id, research_id, project, outcome_agent, "a" * 40, "c" * 64,
                 b"test-only patch", "[]"),
            )
            db.execute(
                "INSERT INTO patch_proposal_validations(id,proposal_id,validator_id,base_sha,"
                "patch_sha256,candidate_tree) VALUES (%s,%s,%s,%s,%s,%s)",
                (validation_id, proposal_id, outcome_agent, "a" * 40, "c" * 64, candidate_sha),
            )
            db.execute(
                "INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence,candidate_sha) "
                "VALUES (%s,%s,%s,'APPROVE','[]'::jsonb,%s)",
                (review_id, research_id, outcome_agent, candidate_sha),
            )
            db.execute("UPDATE work_items SET status='DONE' WHERE id=%s", (research_id,))
            db.execute(
                "INSERT INTO events(id,subject_id,kind,details) VALUES (%s,%s,'work.completed',%s::jsonb)",
                (str(uuid4()), research_id,
                 json.dumps({"pr_number": 321, "merge_commit_sha": "d" * 40})),
            )

        provider_calls = 0
        provider_prompts = []
        def successful_provider(messages):
            nonlocal provider_calls
            provider_calls += 1
            provider_prompts.append(messages)
            yield "Conversación persistida."
        monkeypatch.setattr(conversation_provider, "stream_reply", successful_provider)
        turn = {
            "body": "Resume los acuerdos del hilo",
            "idempotency_key": str(uuid4()),
        }
        turn_url = f"/v1/projects/{project}/conversations/{conversation_id}/turns"
        first_turn = client.post(turn_url, headers=ceo, json=turn)
        assert first_turn.status_code == 200
        snapshot_message = next(
            item["content"] for item in provider_prompts[0]
            if item["role"] == "system" and item["content"].startswith("Canonical project work snapshot")
        )
        assert "Deliver the reviewed plan" in snapshot_message
        assert "Research evidence" in snapshot_message
        assert str(research_id) in snapshot_message
        assert "latest_execution" in snapshot_message
        assert '"latest_review"' in snapshot_message and '"decision": "APPROVE"' in snapshot_message
        assert '"validated_in_disposable_clone": true' in snapshot_message
        assert '"state": "MERGED"' in snapshot_message and '"pr_number": 321' in snapshot_message
        assert candidate_sha in snapshot_message and "private payload" not in snapshot_message
        assert "result_json" not in snapshot_message and '"patch"' not in snapshot_message
        # SSE data is JSON-escaped by json.dumps (including non-ASCII text).
        assert '"delta": "Conversaci\\u00f3n persistida."' in first_turn.text
        assert provider_token not in first_turn.text
        with connect_postgres() as db:
            stored_turn = db.execute(
                "SELECT provider,model,endpoint FROM project_conversation_turns "
                "WHERE conversation_id=%s AND idempotency_key=%s",
                (conversation_id, turn["idempotency_key"]),
            ).fetchone()
            provenance = db.execute(
                "SELECT details FROM events WHERE subject_id=%s "
                "AND kind IN ('conversation.turn.started','conversation.turn.completed')",
                (conversation_id,),
            ).fetchall()
        assert tuple(stored_turn) == (
            "openai-compatible", "conversation-test-model", "https://gateway.example/v1/chat",
        )
        assert len(provenance) >= 2
        assert all(
            event[0]["provider"] == "openai-compatible"
            and event[0]["model"] == "conversation-test-model"
            and event[0]["endpoint"] == "https://gateway.example/v1/chat"
            and provider_token not in json.dumps(event[0])
            for event in provenance
        )
        persisted_messages = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()
        assistant = next(item for item in persisted_messages if item["sender"] == "AAO")
        assert assistant["provider"] == "openai-compatible"
        assert assistant["model"] == "conversation-test-model"
        assert assistant["endpoint"] == "https://gateway.example/v1/chat"
        assert provider_token not in json.dumps(persisted_messages)
        assert provider_token not in str(first_turn.headers)
        replayed_turn = client.post(turn_url, headers=ceo, json=turn)
        assert replayed_turn.status_code == 200
        assert replayed_turn.text == first_turn.text
        assert provider_calls == 1
        assert client.post(turn_url, headers=ceo, json={
            **turn, "body": "Different body with the same key",
        }).status_code == 409
        turn_messages = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()
        assert sum(message["body"] == turn["body"] for message in turn_messages) == 1
        assert any(message["body"] == "Conversación persistida." for message in turn_messages)
        assert any(
            message["body"] == turn["body"] and message["sender"] == "CEO"
            and message["turn_status"] == "COMPLETED"
            for message in turn_messages
        )

        # A process crash leaves a durable PENDING row. Only an expired/missing
        # lease can be reclaimed, and retry reuses the same CEO message/key.
        crashed_key = str(uuid4())
        crashed_message_id = str(uuid4())
        crashed_turn_id = str(uuid4())
        crashed_body = "Recover the interrupted answer"
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO project_conversation_messages(id,conversation_id,sender,body) "
                "VALUES (%s,%s,'CEO',%s)", (crashed_message_id, conversation_id, crashed_body),
            )
            db.execute(
                "INSERT INTO project_conversation_turns(id,conversation_id,idempotency_key,"
                "request_sha256,user_message_id,state,provider,model,endpoint,lease_owner,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,'PENDING','openai-compatible','conversation-test-model',%s,%s,clock_timestamp()+interval '10 minutes')",
                (crashed_turn_id, conversation_id, crashed_key, sha256(crashed_body.encode()).hexdigest(),
                 crashed_message_id, "https://gateway.example/v1/chat", str(uuid4())),
            )
        assert client.post(turn_url, headers=ceo, json={
            "body": crashed_body, "idempotency_key": crashed_key,
        }).status_code == 409
        pending_projection = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()
        interrupted = next(item for item in pending_projection if item["id"] == crashed_message_id)
        assert interrupted["turn_status"] == "PENDING"
        assert interrupted["turn_lease_expires_at"] is not None
        with connect_postgres() as db:
            db.execute(
                "UPDATE project_conversation_turns SET lease_expires_at=clock_timestamp()-interval '1 second' "
                "WHERE id=%s", (crashed_turn_id,),
            )
        monkeypatch.setenv("AAO_CONVERSATION_MODEL", "different-model")
        provider_mismatch = client.post(turn_url, headers=ceo, json={
            "body": crashed_body, "idempotency_key": crashed_key,
        })
        assert provider_mismatch.status_code == 409
        assert "provider configuration differs" in provider_mismatch.text
        monkeypatch.setenv("AAO_CONVERSATION_MODEL", "conversation-test-model")
        monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: iter(["Recovered once."]))
        recovered_crash = client.post(turn_url, headers=ceo, json={
            "body": crashed_body, "idempotency_key": crashed_key,
        })
        assert recovered_crash.status_code == 200, recovered_crash.text
        assert "Recovered once." in recovered_crash.text
        with connect_postgres() as db:
            recovered_row = db.execute(
                "SELECT state,user_message_id,lease_owner,lease_expires_at "
                "FROM project_conversation_turns WHERE id=%s", (crashed_turn_id,),
            ).fetchone()
            recovery_events = db.execute(
                "SELECT count(*) FROM events WHERE subject_id=%s "
                "AND kind='conversation.turn.recovered'", (conversation_id,),
            ).fetchone()[0]
        assert recovered_row[0] == "COMPLETED"
        assert str(recovered_row[1]) == crashed_message_id
        assert recovered_row[2] is None and recovered_row[3] is None
        assert recovery_events == 1
        recovered_projection = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()
        recovered_message = next(item for item in recovered_projection if item["id"] == crashed_message_id)
        assert recovered_message["turn_status"] == "COMPLETED"
        assert recovered_message["turn_lease_expires_at"] is None

        # The independent opt-in backend worker must also recover an expired
        # turn without a browser POST, using the same canonical PostgreSQL rows.
        from aao import conversation_provider, conversation_turn_recovery

        worker_key = str(uuid4())
        worker_message_id = str(uuid4())
        worker_turn_id = str(uuid4())
        worker_body = "Recover while the browser is closed"
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO project_conversation_messages(id,conversation_id,sender,body) "
                "VALUES (%s,%s,'CEO',%s)", (worker_message_id, conversation_id, worker_body),
            )
            db.execute(
                "INSERT INTO project_conversation_turns(id,conversation_id,idempotency_key,"
                "request_sha256,user_message_id,state,provider,model,endpoint,lease_owner,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,'PENDING','openai-compatible',"
                "'conversation-test-model','https://provider.invalid/v1/chat/completions',%s,clock_timestamp()-interval '1 second')",
                (worker_turn_id, conversation_id, worker_key,
                 sha256(worker_body.encode()).hexdigest(), worker_message_id, str(uuid4())),
            )
        monkeypatch.setenv("AAO_CONVERSATION_RECOVERY_ENABLED", "true")
        monkeypatch.setenv("AAO_CONVERSATION_API_URL", "https://provider.invalid/v1/chat/completions")
        monkeypatch.setenv("AAO_CONVERSATION_API_KEY", "test-only-not-a-provider-call")
        monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: iter(["Recovered by backend."]))
        worker_result = conversation_turn_recovery.recover_one_turn()
        assert worker_result == {"status": "COMPLETED", "turn_id": worker_turn_id}
        with connect_postgres() as db:
            worker_row = db.execute(
                "SELECT t.state,t.assistant_message_id,m.body,t.lease_owner,t.lease_expires_at "
                "FROM project_conversation_turns t LEFT JOIN project_conversation_messages m "
                "ON m.id=t.assistant_message_id WHERE t.id=%s", (worker_turn_id,),
            ).fetchone()
            worker_events = db.execute(
                "SELECT count(*) FROM events WHERE subject_id=%s "
                "AND kind='conversation.turn.recovered' AND details->>'turn_id'=%s",
                (conversation_id, worker_turn_id),
            ).fetchone()[0]
        assert worker_row[0] == "COMPLETED"
        assert worker_row[2] == "Recovered by backend."
        assert worker_row[3] is None and worker_row[4] is None
        assert worker_events == 1

        concurrent_key = str(uuid4())
        concurrent_message_id = str(uuid4())
        concurrent_turn_id = str(uuid4())
        with connect_postgres() as db:
            db.execute(
                "INSERT INTO project_conversation_messages(id,conversation_id,sender,body) "
                "VALUES (%s,%s,'CEO','Concurrent recovery')",
                (concurrent_message_id, conversation_id),
            )
            db.execute(
                "INSERT INTO project_conversation_turns(id,conversation_id,idempotency_key,"
                "request_sha256,user_message_id,state,provider,model,endpoint,lease_owner,lease_expires_at) "
                "VALUES (%s,%s,%s,%s,%s,'PENDING','openai-compatible',"
                "'conversation-test-model','https://provider.invalid/v1/chat/completions',%s,clock_timestamp()-interval '1 second')",
                (concurrent_turn_id, conversation_id, concurrent_key,
                 sha256(b"Concurrent recovery").hexdigest(), concurrent_message_id, str(uuid4())),
            )
        from threading import Event

        provider_entered = Event()
        release_provider = Event()
        provider_calls = []

        def slow_provider(_messages):
            provider_calls.append(True)
            provider_entered.set()
            assert release_provider.wait(5)
            yield "Single concurrent recovery."

        monkeypatch.setattr(conversation_provider, "stream_reply", slow_provider)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_recovery = executor.submit(conversation_turn_recovery.recover_one_turn)
            assert provider_entered.wait(5)
            second_result = executor.submit(conversation_turn_recovery.recover_one_turn).result(timeout=5)
            release_provider.set()
            first_result = first_recovery.result(timeout=5)
        assert second_result == {"status": "IDLE"}
        assert first_result == {"status": "COMPLETED", "turn_id": concurrent_turn_id}
        assert provider_calls == [True]

        eligible_worker = "conversation-worker-" + str(uuid4())
        assert client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": eligible_worker, "kind": "AGENT",
        }).status_code == 201
        for capability in ("work.admit", "execution.claim"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": eligible_worker, "capability": capability,
            }).status_code == 201
        profile = client.put("/v1/organization/profiles", headers=ceo, json={
            "principal_id": eligible_worker, "display_name": "Declared backend agent",
            "role_title": "Backend engineer", "competencies": ["PostgreSQL", "backend engineering"],
        })
        assert profile.status_code == 200, profile.text
        eligible = client.get(f"/v1/projects/{project}/assignable-agents", headers=ceo)
        assert eligible.status_code == 200
        assert eligible.json() == [{
            "principal_id": eligible_worker, "display_name": "Declared backend agent",
            "competencies": ["PostgreSQL", "backend engineering"],
        }]

        proposal_url = f"/v1/projects/{project}/conversations/{conversation_id}/work-group-proposals"
        proposal_calls = []
        proposal_json = json.dumps({
            "title": "Reviewed outcome", "description": "Deliver the agreed result",
            "acceptance_criteria": ["Results linked to evidence"],
            "tasks": [
                {"key": "inspect", "title": "Inspect evidence", "description": "Review inputs",
                 "acceptance_criteria": ["Evidence recorded"], "depends_on": [],
                 "required_competencies": ["PostgreSQL"],
                 "assigned_principal_id": eligible_worker},
                {"key": "summarize", "title": "Summarize", "description": "Consolidate results",
                 "acceptance_criteria": ["Summary reviewed"], "depends_on": ["inspect"],
                 "required_competencies": [],
                 "assigned_principal_id": None},
            ],
        })
        def proposal_provider(messages):
            proposal_calls.append(messages)
            yield proposal_json
        monkeypatch.setenv("AAO_CONVERSATION_PROVIDER", "openai-compatible")
        monkeypatch.setenv("AAO_CONVERSATION_MODEL", "proposal-test-model")
        monkeypatch.setattr(conversation_provider, "stream_reply", proposal_provider)
        assert client.post(proposal_url).status_code == 403
        with connect_postgres() as db:
            work_count_before_proposal = db.execute(
                "SELECT count(*) FROM work_items WHERE project_id=%s", (project,),
            ).fetchone()[0]
        proposed = client.post(proposal_url, headers=ceo)
        assert proposed.status_code == 200, proposed.text
        proposal_body = proposed.json()
        assert proposal_body["proposal"]["title"] == "Reviewed outcome"
        assert len(proposal_body["proposal"]["tasks"]) == 2
        assert proposal_body["proposal"]["tasks"][0]["required_competencies"] == ["PostgreSQL"]
        assert proposal_body["proposal"]["tasks"][0]["assigned_principal_id"] == eligible_worker
        assert proposal_body["proposal"]["tasks"][1]["assigned_principal_id"] is None
        assert proposal_body["provider"] == "openai-compatible"
        assert proposal_body["model"] == "proposal-test-model"
        assert proposal_body["persisted_as_work"] is False
        current_turn_messages = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()
        assert len(proposal_body["based_on_message_ids"]) == len(current_turn_messages)
        assert any(item["content"] == turn["body"] for item in proposal_calls[0])
        assert any(item["content"] == "Conversación persistida." for item in proposal_calls[0])
        assert any(item["content"] == crashed_body for item in proposal_calls[0])
        assert eligible_worker in proposal_calls[0][0]["content"]
        assert "PostgreSQL" in proposal_calls[0][0]["content"]
        monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: iter([
            json.dumps({
                "title": "Invalid assignment", "description": "test",
                "acceptance_criteria": ["No invalid identities"],
                "tasks": [{"key": "task", "title": "Test", "description": "",
                           "acceptance_criteria": ["Recorded"], "depends_on": [],
                           "assigned_principal_id": "not-an-eligible-worker"}],
            }),
        ]))
        invalid_assignment = client.post(proposal_url, headers=ceo)
        assert invalid_assignment.status_code == 502
        assert any(item["content"] == "Recovered once." for item in proposal_calls[0])
        with connect_postgres() as db:
            work_count_after_proposal = db.execute(
                "SELECT count(*) FROM work_items WHERE project_id=%s", (project,),
            ).fetchone()[0]
            proposal_event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='conversation.work_group.proposed'",
                (conversation_id,),
            ).fetchone()
        assert work_count_after_proposal == work_count_before_proposal
        assert proposal_event[0]["persisted_as_work"] is False
        assert proposal_event[0]["admitted"] is False
        # A generated plan may not be confirmed after the persisted transcript changes.
        late_message = client.post(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages",
            headers=ceo, json={"body": "Añadir una nueva restricción"},
        )
        assert late_message.status_code == 201
        stale_group = {
            "idempotency_key": str(uuid4()),
            "based_on_message_ids": proposal_body["based_on_message_ids"],
            "title": proposal_body["proposal"]["title"],
            "description": proposal_body["proposal"]["description"],
            "acceptance_criteria": proposal_body["proposal"]["acceptance_criteria"],
            "tasks": proposal_body["proposal"]["tasks"],
        }
        stale_confirmation = client.post(
            f"/v1/projects/{project}/conversations/{conversation_id}/work-groups",
            headers=ceo, json=stale_group,
        )
        assert stale_confirmation.status_code == 409
        assert "Conversation changed" in stale_confirmation.text
        with connect_postgres() as db:
            assert db.execute(
                "SELECT count(*) FROM work_items WHERE project_id=%s", (project,),
            ).fetchone()[0] == work_count_before_proposal
        monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: iter(["not json"]))
        assert client.post(proposal_url, headers=ceo).status_code == 502

        failure_key = str(uuid4())
        failure_calls = 0
        def fails_once(_messages):
            nonlocal failure_calls
            failure_calls += 1
            if failure_calls == 1:
                raise conversation_provider.ProviderUnavailable("TEST_PROVIDER_FAILURE", "temporary failure")
            yield "Respuesta recuperada."
        monkeypatch.setattr(conversation_provider, "stream_reply", fails_once)
        retry_turn = {"body": "Otra consulta", "idempotency_key": failure_key}
        failed = client.post(turn_url, headers=ceo, json=retry_turn)
        error_payloads = [
            json.loads(line.removeprefix("data: "))
            for line in failed.text.splitlines() if line.startswith("data: ")
        ]
        assert any(payload.get("code") == "TEST_PROVIDER_FAILURE" for payload in error_payloads)
        failed_message = client.get(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages", headers=ceo,
        ).json()
        assert any(
            message["body"] == retry_turn["body"] and message["turn_status"] == "FAILED"
            and message["turn_error_code"] == "TEST_PROVIDER_FAILURE"
            for message in failed_message
        )
        recovered = client.post(turn_url, headers=ceo, json=retry_turn)
        assert "Respuesta recuperada." in recovered.text
        assert failure_calls == 2

        pending_message = client.post(
            f"/v1/projects/{project}/conversations/{conversation_id}/messages",
            headers=ceo, json={"body": "A second request"},
        ).json()
        assert client.post(f"/v1/projects/{project}/state", headers=ceo,
                           json={"action": "pause"}).status_code == 200
        paused_url = (
            f"/v1/projects/{project}/conversations/{conversation_id}/messages/"
            f"{pending_message['id']}/work-request"
        )
        assert client.post(paused_url, headers=ceo, json=conversion).status_code == 409


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_organization_projection_is_authenticated_and_project_scoped(monkeypatch):
    from aao.work_management_api import app
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "organization-ceo")
    ceo = {"X-CEO-Token": "organization-ceo"}
    with TestClient(app) as client:
        assert client.get("/v1/organization").status_code == 403
        principal = "org-agent-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        }).json()["token"]
        agent = {"X-Agent-Token": token}
        project_ids = []
        for name in ("visible", "hidden"):
            mandate = client.post("/v1/mandates", headers=ceo, json={
                "title": name + str(uuid4()), "objective": "Projection scope test",
            }).json()["id"]
            client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo)
            project_ids.append(client.post("/v1/projects", headers=ceo, json={
                "name": name, "mandate_id": mandate,
            }).json()["id"])
        grant = client.post(f"/v1/projects/{project_ids[0]}/grants", headers=ceo, json={
            "principal_id": principal, "capability": "project.read",
        })
        assert grant.status_code == 201
        visible = client.get("/v1/organization", headers=agent)
        assert visible.status_code == 200
        payload = visible.json()
        assert payload["coverage"]["totalProjects"] == 1
        assert [agent["id"] for agent in payload["agents"]] == [principal]
        assert payload["agents"][0]["status"] == "UNKNOWN"
        assert payload["agents"][0]["currentAssignments"] == []
        assert payload["units"][0]["id"] == "unit-unassigned"
        assert client.get("/v1/organization", headers=ceo).json()["coverage"]["totalProjects"] >= 2


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_organization_profiles_are_persisted_and_do_not_create_grants(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "org-profile-ceo")
    ceo = {"X-CEO-Token": "org-profile-ceo"}
    with TestClient(app) as client:
        principal = "org-profile-" + str(uuid4())
        credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        })
        assert credential.status_code == 201
        agent_headers = {"X-Agent-Token": credential.json()["token"]}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Organization profile " + str(uuid4()), "objective": "Metadata must not grant access",
        }).json()["id"]
        client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo)
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Profile access boundary", "mandate_id": mandate,
        }).json()["id"]
        unit = {
            "id": "unit-" + str(uuid4()), "name": "Research", "code": "R-" + str(uuid4()),
            "parent_id": None, "lead_principal_id": principal, "enabled": True,
        }
        assert client.put("/v1/organization/units", json=unit).status_code == 403
        assert client.put("/v1/organization/units", headers=ceo, json=unit).status_code == 200
        profile = {
            "principal_id": principal, "display_name": "Research Agent", "role_title": "Analyst",
            "unit_id": unit["id"], "manager_principal_id": None, "enabled": True,
        }
        assert client.put("/v1/organization/profiles", headers=ceo, json=profile).status_code == 200
        projection = client.get("/v1/organization", headers=ceo).json()
        agent = next(row for row in projection["agents"] if row["id"] == principal)
        assert agent["name"] == "Research Agent"
        assert agent["roleTitle"] == "Analyst"
        assert agent["unitId"] == unit["id"]
        assert agent["status"] == "UNKNOWN"
        assert any(row["id"] == unit["id"] for row in projection["units"])
        assert client.get(f"/v1/projects/{project}/grants", headers=ceo).json() == []
        scoped = client.get("/v1/organization", headers=agent_headers).json()
        assert [item["id"] for item in scoped["agents"]] == [principal]
        assert {item["id"] for item in scoped["units"]} == {unit["id"], "unit-unassigned"}


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_organization_projection_respects_execution_lease_expiry(monkeypatch):
    from aao.execution_queue import claim
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "org-lease-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "org-lease-ceo"}
    with TestClient(app) as client:
        worker_id = "org-lease-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        }).json()["token"]
        worker = {"X-Agent-Token": token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Org lease " + str(uuid4()), "objective": "Check projection lease state",
        }).json()["id"]
        client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo)
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Org lease", "mandate_id": mandate,
        }).json()["id"]
        for cap in ("work.create", "work.admit", "execution.claim", "project.read"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": worker_id, "capability": cap,
            }).status_code == 201
        execution_ids = []
        for title in ("expired", "active"):
            work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
                "title": title, "author_id": worker_id, "acceptance_criteria": ["projected"],
            }).json()["id"]
            assert client.post(f"/v1/work/{work}/admit", headers=worker).status_code == 200
            staged = client.post(f"/v1/work/{work}/stage-inert", headers=worker)
            assert staged.status_code == 202, staged.text
            lease = claim(worker_id, agent_credential=token, project_id=project)
            assert lease
            execution_ids.append(staged.json()["execution_id"])
        with connect_postgres() as db:
            db.execute(
                "UPDATE execution_queue SET lease_expires_at=CASE WHEN id=%s "
                "THEN clock_timestamp()-interval '1 second' "
                "ELSE clock_timestamp()+interval '10 minutes' END WHERE id=ANY(%s::uuid[])",
                (execution_ids[0], execution_ids),
            )
        projection = client.get("/v1/organization", headers=worker).json()
        agent = next(row for row in projection["agents"] if row["id"] == worker_id)
        by_id = {row["id"]: row for row in agent["currentAssignments"]}
        assert by_id[execution_ids[0]]["status"] == "EXPIRED"
        assert by_id[execution_ids[1]]["status"] == "ACTIVE"
        assert agent["status"] == "BUSY"
        assert agent["operationalState"] == "EJECUTANDO"
        assert projection["activeAssignmentsCount"] == 1


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_organization_projection_never_infers_certification_from_grants_or_reviews(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "org-capability-ceo")
    ceo = {"X-CEO-Token": "org-capability-ceo"}
    with TestClient(app) as client:
        principal = "org-capability-" + str(uuid4())
        issued = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        })
        worker = {"X-Agent-Token": issued.json()["token"]}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Org capability " + str(uuid4()), "objective": "Projection must not certify",
        }).json()["id"]
        client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo)
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Org capabilities", "mandate_id": mandate,
        }).json()["id"]
        for cap in ("project.read", "work.create", "work.admit"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": cap,
            }).status_code == 201
        reviewers = []
        for _ in range(2):
            reviewer = "org-auditor-" + str(uuid4())
            issued_reviewer = client.post("/v1/principals/credentials", headers=ceo, json={
                "principal_id": reviewer, "kind": "AUDITOR",
            })
            assert issued_reviewer.status_code == 201
            reviewers.append(reviewer)
        work = client.post(f"/v1/projects/{project}/work", headers=worker, json={
            "title": "Approval is not a capability", "author_id": principal,
            "acceptance_criteria": ["Projection remains un-certified"],
        }).json()["id"]
        with connect_postgres() as db:
            for reviewer in reviewers:
                db.execute(
                    "INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence,candidate_sha) "
                    "VALUES (%s,%s,%s,'APPROVE','[\"sha256:test\"]'::jsonb,%s)",
                    (str(uuid4()), work, reviewer, "a" * 40),
                )
        projection = client.get("/v1/organization", headers=worker).json()
        agent = next(row for row in projection["agents"] if row["id"] == principal)
        assert agent["capabilities"] == []


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_organization_projection_does_not_infer_unit_from_principal_name(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "org-unit-ceo")
    ceo = {"X-CEO-Token": "org-unit-ceo"}
    with TestClient(app) as client:
        principal = "eng-agent-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        }).json()["token"]
        worker = {"X-Agent-Token": token}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Org unit " + str(uuid4()), "objective": "Unit requires a persisted profile",
        }).json()["id"]
        client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo)
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Org unit", "mandate_id": mandate,
        }).json()["id"]
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": principal, "capability": "project.read",
        }).status_code == 201
        projection = client.get("/v1/organization", headers=worker).json()
        agent = next(row for row in projection["agents"] if row["id"] == principal)
        assert agent["unitId"] == "unit-unassigned"
        assert agent["status"] == "UNKNOWN"


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_organization_projection_counts_every_readable_project(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "org-coverage-ceo")
    ceo = {"X-CEO-Token": "org-coverage-ceo"}
    with TestClient(app) as client:
        principal = "org-coverage-" + str(uuid4())
        token = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal, "kind": "AGENT",
        }).json()["token"]
        agent = {"X-Agent-Token": token}
        for index in range(11):
            mandate = client.post("/v1/mandates", headers=ceo, json={
                "title": f"Org coverage {index} " + str(uuid4()), "objective": "Count all visible projects",
            }).json()["id"]
            client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo)
            project = client.post("/v1/projects", headers=ceo, json={
                "name": f"Org coverage {index}", "mandate_id": mandate,
            }).json()["id"]
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": principal, "capability": "project.read",
            }).status_code == 201
        projection = client.get("/v1/organization", headers=agent)
        assert projection.status_code == 200, projection.text
        assert projection.json()["coverage"] == {
            "totalProjects": 11, "inspectedProjects": 11, "failedProjects": 0, "isPartial": False,
        }


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL test database required",
)
def test_organization_unit_concurrent_reparenting_cannot_create_cycle(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "org-cycle-ceo")
    ceo = {"X-CEO-Token": "org-cycle-ceo"}
    with TestClient(app) as client:
        suffix = str(uuid4())
        first = {
            "id": "unit-cycle-a-" + suffix, "name": "A", "code": "A-" + suffix,
            "parent_id": None, "lead_principal_id": None, "enabled": True,
        }
        second = {
            "id": "unit-cycle-b-" + suffix, "name": "B", "code": "B-" + suffix,
            "parent_id": None, "lead_principal_id": None, "enabled": True,
        }
        assert client.put("/v1/organization/units", headers=ceo, json=first).status_code == 200
        assert client.put("/v1/organization/units", headers=ceo, json=second).status_code == 200

        first["parent_id"] = second["id"]
        second["parent_id"] = first["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda unit: client.put("/v1/organization/units", headers=ceo, json=unit),
                (first, second),
            ))
        assert sorted(result.status_code for result in results) == [200, 409]


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
        from aao.postgresql_connection import connect_postgres
        with connect_postgres() as db:
            review_protocol = db.execute(
                "SELECT id,protocol_version,started_by FROM protocol_instances "
                "WHERE protocol_id='review-acceptance' AND subject_type='work_item' AND subject_id=%s",
                (w,),
            ).fetchone()
            started_events = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='protocol.started' "
                "AND details->>'protocol_id'='review-acceptance'",
                (w,),
            ).fetchall()
        assert review_protocol is not None
        assert review_protocol[1:] == ("1.0.0", agent_id)
        assert len(started_events) == 1
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
        with connect_postgres() as db:
            review_event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.reviewed' "
                "ORDER BY created_at DESC LIMIT 1", (w,),
            ).fetchone()[0]
            escalation_protocol = db.execute(
                "SELECT id,protocol_version,started_by,idempotency_key "
                "FROM protocol_instances WHERE protocol_id='blockage-escalation' "
                "AND subject_type='work_item' AND subject_id=%s",
                (w,),
            ).fetchone()
            escalation_start_event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='protocol.started' "
                "AND details->>'protocol_id'='blockage-escalation'",
                (w,),
            ).fetchone()
        assert review_event["protocol_instance_id"] == str(review_protocol[0])
        assert escalation_protocol is not None
        assert escalation_protocol[1:] == (
            "1.0.0", auditor_id,
            f"blockage-escalation:work_item:{w}:review:{rejected.json()['review_id']}",
        )
        assert review_event["escalation_protocol_instance_id"] == str(escalation_protocol[0])
        assert review_event["next_action"] == (
            "Implement changes under the existing assignment; submit a new candidate "
            "and obtain a separate review."
        )
        assert escalation_start_event[0]["protocol_instance_id"] == str(escalation_protocol[0])
        assert escalation_start_event[0]["actor"] == auditor_id
        assert client.post(f"/v1/work/{w}/progress", headers=worker).json()["status"] == "IN_REVIEW"
        with connect_postgres() as db:
            assert db.execute(
                "SELECT count(*) FROM protocol_instances WHERE protocol_id='review-acceptance' "
                "AND subject_type='work_item' AND subject_id=%s", (w,),
            ).fetchone()[0] == 1
            assert db.execute(
                "SELECT count(*) FROM events WHERE subject_id=%s AND kind='protocol.started' "
                "AND details->>'protocol_id'='review-acceptance'", (w,),
            ).fetchone()[0] == 1
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
def test_self_development_cycle_from_task_to_merged_pr_and_done(monkeypatch, tmp_path):
    """W1-W3 end to end: an agent run turns an admitted task into a proposal and a candidate commit tested in
    the sandbox; failed attempts can be re-run; the auditor approves the tested SHA; a separate publisher pushes
    exactly that SHA and opens the PR; the merged PR makes the task DONE; the activity feed shows each step."""
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
    # The environment says codex (not activated here, so it would fail); the capability's model_profile says
    # fixture and must win.
    monkeypatch.setenv("AAO_AGENT_BACKEND", "codex")
    monkeypatch.delenv("AAO_AGENT_PROVIDER", raising=False)
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
        capability = {
            "capability_id": "aao.agent-runner", "version": "1.0.0", "capability_type": "agent",
            "provenance": {"kind": "repository"},
            "contract": {"purpose": "Turn a task into a patch proposal", "entrypoint": "aao.agent_runner:patch",
                         "inputs": ["task", "base_sha"], "outputs": ["patch proposal"], "platform": "Linux",
                         "authority_boundary": "edits only a disposable clone; proposes, never applies or merges",
                         "compatible_roles": ["implementer"],
                         "model_profile": {"backend": "fixture", "provider": "fixture", "model": None,
                                           "seats": ["patch.tests"], "cost_per_attempt_usd": 0.5}},
            "required_permissions": ["execution.claim", "code.propose"], "risks": ["agent edits a disposable clone"],
            "dependencies": [], "tests": ["tests/test_agent_runner.py"], "compatibility": {}, "evidence": ["repo source"],
        }
        bad = {**capability, "contract": {**capability["contract"], "model_profile": {"backend": "docker"}}}
        rejected = client.post(f"/v1/projects/{project}/capabilities", headers=agent, json=bad)
        assert rejected.status_code == 422 and "model_profile.backend" in rejected.text
        registered = client.post(f"/v1/projects/{project}/capabilities", headers=agent, json=capability)
        assert registered.status_code == 201, registered.text
        # I4: a codex entry ranked higher in the catalog. Routing recommends it only while codex is activated, and
        # staging refuses it once activation is gone, whatever the recorded recommendation said.
        codex = {**capability, "capability_id": "aao.agent-runner.codex", "contract": {
            **capability["contract"], "model_profile": {"backend": "codex", "provider": "openai", "model": "gpt-6-luna",
                                                        "seats": ["patch.tests"], "quality": {"patch.tests": 4}}}}
        assert client.post(f"/v1/projects/{project}/capabilities", headers=agent, json=codex).status_code == 201
        routed = client.post(f"/v1/work/{work}/route-model", headers=agent, json={"seat": "patch.tests"}).json()
        assert routed["capability_id"] == "aao.agent-runner" and routed["execution_authorized"] is False
        assert ["aao.agent-runner.codex@1.0.0", "backend codex not activated"] in routed["rejected"]
        monkeypatch.setenv("AAO_AGENT_PROVIDER", "codex")
        routed = client.post(f"/v1/work/{work}/route-model", headers=agent, json={"seat": "patch.tests"}).json()
        assert routed["capability_id"] == "aao.agent-runner.codex"
        monkeypatch.delenv("AAO_AGENT_PROVIDER")
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
        refused = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json={
            "capability_id": "aao.agent-runner.codex", "version": "1.0.0", "base_sha": base_sha})
        assert refused.status_code == 409 and "not activated" in refused.text
        staged = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert staged.status_code == 202, staged.text
        assert client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run).json()["execution_id"] == staged.json()["execution_id"]
        assert client.post(f"/v1/work/{work}/progress", headers=agent).status_code == 200

        # Attempt 1: the candidate is committed and stored, but its own test fails, so the execution FAILED.
        assert run_one(identity, token, project_id=project, seconds=400)["status"] == "FAILED"
        # Recovery: the task can be re-run after a failed attempt.
        monkeypatch.setenv("AAO_AGENT_FIXTURE_PATCH", str(passing))
        # I5: attempt 1 spent an estimated 0.5 today; with a daily budget of 0.9 another 0.5 does not fit. The
        # router reports what is left and filters the candidate; staging refuses, leaving the excess to the CEO.
        monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "0.9")
        routed = client.post(f"/v1/work/{work}/route-model", headers=agent, json={"seat": "patch.tests"}).json()
        assert routed["budget_left_usd"] == 0.4 and routed["capability_id"] is None
        assert ["aao.agent-runner@1.0.0", "estimated cost 0.5 over budget left 0.4"] in routed["rejected"]
        over = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert over.status_code == 409 and "budget.exceed" in over.text
        monkeypatch.setenv("AAO_AGENT_DAILY_BUDGET_USD", "100")
        restaged = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert restaged.status_code == 202, restaged.text
        assert restaged.json()["execution_id"] != staged.json()["execution_id"]
        # Attempt 2: an infrastructure failure of the checks fails the run after its proposal is stored...
        import aao.sandboxed_repository_checks as checks
        real_check = checks.run_repository_check

        def broken(*_args, **_kwargs):
            raise checks.RepositoryCheckError("sandbox unavailable")
        monkeypatch.setattr(checks, "run_repository_check", broken)
        assert run_one(identity, token, project_id=project, seconds=400)["status"] == "FAILED"
        monkeypatch.setattr(checks, "run_repository_check", real_check)
        # ...and attempt 3 reproduces the same patch: it reuses that proposal instead of failing on it.
        assert client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run).status_code == 202
        outcome = run_one(identity, token, project_id=project, seconds=400)
        board = client.get(f"/v1/projects/{project}/board", headers=agent).json()
        last = next(i for i in board if i["id"] == work)["executions"][-1]["result"]
        print(last.get("check", {}).get("stderr"))  # shown by pytest only on failure
        assert outcome["status"] == "SUCCEEDED", (last.get("error"), last.get("check", {}).get("stderr"),
                                                  last.get("check", {}).get("stdout"))
        board = client.get(f"/v1/projects/{project}/board", headers=agent).json()
        item = next(item for item in board if item["id"] == work)
        failed, infra_failed, succeeded = item["executions"]
        assert failed["status"] == "FAILED" and failed["result"]["check"]["conclusion"] == "failure"
        assert infra_failed["status"] == "FAILED" and infra_failed["result"]["check"]["error"] == "sandbox unavailable"
        result = succeeded["result"]
        assert (result["backend"], result["backend_source"], result["capability_id"]) == (
            "fixture", "capability", "aao.agent-runner")
        assert result["proposal_id"] == infra_failed["result"]["proposal_id"]
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

        # W2b: two publisher principals (implementer identity pushes, PM opens the PR), neither the author.
        from aao.pr_publisher import PublishError, open_pull_request, push_candidate

        def principal(prefix):
            pid = prefix + str(uuid4())
            return pid, client.post("/v1/principals/credentials", headers=ceo,
                                    json={"principal_id": pid, "kind": "AGENT"}).json()["token"]
        pusher_id, pusher = principal("w2b-impl-")
        publisher_id, publisher = principal("w2b-pm-")
        remote = tmp_path / "github.git"  # stands in for GitHub; it already has the base, like the real fork
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        subprocess.run(["git", "--git-dir", str(remote), "config", "receive.shallowUpdate", "true"], check=True)
        subprocess.run(["git", "-C", str(repo), "push", "-q", str(remote), "HEAD:refs/heads/main"], check=True)
        opened = []

        def push(sha, branch):
            subprocess.run(["git", "--git-dir", str(store), "push", "-q", str(remote), f"{sha}:refs/heads/{branch}"], check=True)

        def open_pr(branch, title, body):
            opened.append((branch, title, body))
            head = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
                                  capture_output=True, text=True, check=True).stdout.strip()
            number = 6 + len(opened)
            return {"number": number, "url": f"https://github.invalid/autoaiorg/aao/pull/{number}", "head_sha": head}

        with pytest.raises(PublishError, match="Project grant required"):
            push_candidate(work, pusher, store=store, push=push)
        for pid in (identity, pusher_id, publisher_id):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo,
                               json={"principal_id": pid, "capability": "code.publish"}).status_code == 201
        with pytest.raises(PublishError, match="cannot publish its own work"):
            push_candidate(work, token, store=store, push=push)
        with pytest.raises(PublishError, match="has not been pushed"):
            open_pull_request(work, publisher, open_pr=open_pr)
        pushed = push_candidate(work, pusher, store=store, push=push)
        assert pushed["status"] == "PUSHED" and pushed["candidate_sha"] == candidate_sha
        branch = pushed["branch"]
        assert subprocess.run(["git", "--git-dir", str(remote), "rev-parse", f"refs/heads/{branch}"],
                              capture_output=True, text=True, check=True).stdout.strip() == candidate_sha
        assert push_candidate(work, pusher, store=store, push=push)["status"] == "ALREADY_PUSHED"
        # A fork branch moved after the push is never recorded as the task's PR.
        subprocess.run(["git", "--git-dir", str(remote), "update-ref", f"refs/heads/{branch}", base_sha], check=True)
        with pytest.raises(PublishError, match="head is not the approved candidate"):
            open_pull_request(work, publisher, open_pr=open_pr)
        subprocess.run(["git", "--git-dir", str(remote), "update-ref", f"refs/heads/{branch}", candidate_sha], check=True)
        opened.clear()
        published = open_pull_request(work, publisher, open_pr=open_pr)
        assert published["status"] == "PUBLISHED" and published["pusher"] == pusher_id
        assert opened == [(branch, "aao: Add a notes test", opened[0][2])] and candidate_sha in opened[0][2]
        assert open_pull_request(work, publisher, open_pr=open_pr)["status"] == "ALREADY_PUBLISHED"
        assert len(opened) == 1
        board = client.get(f"/v1/projects/{project}/board", headers=agent).json()
        prs = next(item for item in board if item["id"] == work)["pull_requests"]
        assert [(pr["pr_number"], pr["candidate_sha"], pr["publisher"]) for pr in prs] == [(7, candidate_sha, publisher_id)]

        # W3: the task becomes DONE only once the PR is merged with the approved SHA as its head.
        from aao.pr_publisher import reconcile
        pr_state = {"state": "open", "merged": False, "merge_commit_sha": None, "head_sha": candidate_sha}
        assert reconcile(work, publisher, get_pr=lambda n: pr_state)["status"] == "OPEN"
        with pytest.raises(PublishError, match="head no longer matches"):
            reconcile(work, publisher, get_pr=lambda n: {**pr_state, "head_sha": "f" * 40})
        # A PR closed without merge sends the task back to IN_PROGRESS; a new attempt gets its own PR.
        closed = reconcile(work, publisher, get_pr=lambda n: {**pr_state, "state": "closed"})
        assert closed["status"] == "CLOSED_UNMERGED" and closed["work_status"] == "IN_PROGRESS"
        # Effective retry limit: 3 attempts already ran; with a limit of 3 a fourth is refused at staging.
        monkeypatch.setenv("AAO_AGENT_MAX_ATTEMPTS", "3")
        refused = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert refused.status_code == 409 and "attempt limit" in refused.text
        # Attempts 2 and 3 share a patch but end differently (sandbox unavailable, then tested): that is progress.
        monkeypatch.setenv("AAO_AGENT_MAX_ATTEMPTS", "4")
        assert client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run).status_code == 202
        assert run_one(identity, token, project_id=project, seconds=400)["status"] == "SUCCEEDED"
        # Attempt 4 reproduced attempt 3 exactly (same patch, same tested outcome): no progress, so a fifth is
        # refused even below the attempt limit.
        monkeypatch.setenv("AAO_AGENT_MAX_ATTEMPTS", "10")
        stalled = client.post(f"/v1/work/{work}/stage-agent-run", headers=agent, json=run)
        assert stalled.status_code == 409 and "No progress" in stalled.text
        assert client.post(f"/v1/work/{work}/progress", headers=agent).status_code == 200
        board = client.get(f"/v1/projects/{project}/board", headers=agent).json()
        candidate_sha = next(i for i in board if i["id"] == work)["executions"][-1]["result"]["candidate_sha"]
        assert client.post(f"/v1/work/{work}/reviews", headers=auditor, json={
            "decision": "APPROVE", "candidate_sha": candidate_sha, "evidence": [evidence_ref]}).status_code == 201
        assert push_candidate(work, pusher, store=store, push=push)["status"] == "PUSHED"
        reopened = open_pull_request(work, publisher, open_pr=open_pr)
        assert reopened["status"] == "PUBLISHED" and reopened["pr_number"] == 8
        pr_state = {"state": "closed", "merged": True, "merge_commit_sha": None, "head_sha": candidate_sha}
        merge_sha = "e" * 40
        pr_state.update(merge_commit_sha=merge_sha)
        done = reconcile(work, publisher, get_pr=lambda n: pr_state)
        assert done["status"] == "DONE" and done["merge_commit_sha"] == merge_sha
        assert reconcile(work, publisher, get_pr=lambda n: pr_state) == {"status": "DONE"}
        board = client.get(f"/v1/projects/{project}/board", headers=ceo).json()
        done_item = next(item for item in board if item["id"] == work)
        assert done_item["status"] == "DONE"
        assert [(pr["pr_number"], pr["state"]) for pr in done_item["pull_requests"]] == [(7, "CLOSED_UNMERGED"), (8, "MERGED")]
        assert done_item["pull_requests"][1]["merge_commit_sha"] == merge_sha and done_item["resolution"] is None
        activity = client.get(f"/v1/projects/{project}/activity", headers=agent)
        assert activity.status_code == 200, activity.text
        kinds = [event["kind"] for event in activity.json()]
        assert kinds[0] == "work.completed" and activity.json()[0]["details"]["merge_commit_sha"] == merge_sha
        for kind in ("work.admitted", "execution.staged", "execution.claimed", "execution.completed",
                     "work.patch_proposed", "work.reviewed", "work.pr_opened", "work.pr_closed"):
            assert kind in kinds, kind
        assert client.get(f"/v1/projects/{project}/activity?limit=0", headers=ceo).status_code == 422

        # A task completed outside the agent cycle is closed only by the CEO, with that fact recorded.
        side = client.post(f"/v1/projects/{project}/work", headers=agent, json={
            "title": "Docs change merged by hand", "author_id": identity, "acceptance_criteria": ["merged"]}).json()["id"]
        resolution = {"reason": "Merged by hand in PR #107; agent policy forbids docs/",
                      "pr_number": 107, "merge_commit_sha": merge_sha}
        assert client.post(f"/v1/work/{side}/resolve-outside-cycle", headers=agent, json=resolution).status_code == 403
        resolved = client.post(f"/v1/work/{side}/resolve-outside-cycle", headers=ceo, json=resolution)
        assert resolved.status_code == 200 and resolved.json()["resolved_outside_cycle"] is True
        assert client.post(f"/v1/work/{side}/resolve-outside-cycle", headers=ceo, json=resolution).status_code == 409
        side_item = next(i for i in client.get(f"/v1/projects/{project}/board", headers=ceo).json() if i["id"] == side)
        assert side_item["resolution"]["pr_number"] == 107 and side_item["resolution"]["agent_cycle"] is False
        last = client.get(f"/v1/projects/{project}/activity?limit=1", headers=ceo).json()[0]
        assert last["kind"] == "work.resolved_outside_cycle" and last["details"]["agent_cycle"] is False
    assert subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout == ""


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_group_child_capability_evaluation_is_restricted_to_assignee(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "group-evaluation-ceo")
    ceo = {"X-CEO-Token": "group-evaluation-ceo"}
    with TestClient(app) as client:
        assigned_id = "group-evaluation-assigned-" + str(uuid4())
        other_id = "group-evaluation-other-" + str(uuid4())
        assigned = {"X-Agent-Token": client.post(
            "/v1/principals/credentials", headers=ceo,
            json={"principal_id": assigned_id, "kind": "AGENT"},
        ).json()["token"]}
        other = {"X-Agent-Token": client.post(
            "/v1/principals/credentials", headers=ceo,
            json={"principal_id": other_id, "kind": "AGENT"},
        ).json()["token"]}
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Group evaluation " + str(uuid4()), "objective": "Test task attribution",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Group evaluation", "mandate_id": mandate,
        }).json()["id"]
        for capability in ("work.create", "work.admit", "execution.claim"):
            assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
                "principal_id": assigned_id, "capability": capability,
            }).status_code == 201
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": other_id, "capability": "work.create",
        }).status_code == 201
        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Group evaluation conversation",
        }).json()["id"]
        group = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "title": "Deliver one task",
                "description": "A parent container", "acceptance_criteria": ["Done"],
                "tasks": [{"key": "child", "title": "Assigned task",
                           "acceptance_criteria": ["Evidence exists"],
                           "assigned_principal_id": assigned_id}],
            },
        )
        assert group.status_code == 201, group.text
        task_id = group.json()["tasks"][0]["id"]
        evaluation = {
            "task_id": task_id,
            "options": [{"choice": choice, "fit": score, "security": score,
                         "cost": score, "time": score, "tokens": score,
                         "maintenance": score}
                        for choice, score in (("reuse", 1), ("adapt", 2), ("build", 3))],
            "rationale": "Build is selected for the test case.",
            "evidence": ["work-item acceptance criteria"],
        }
        endpoint = f"/v1/projects/{project}/capability-evaluations"
        denied = client.post(endpoint, headers=other, json=evaluation)
        assert denied.status_code == 403, denied.text
        allowed = client.post(endpoint, headers=assigned, json=evaluation)
        assert allowed.status_code == 201, allowed.text
        assert allowed.json()["recommendation"] == "build"
        with connect_postgres() as db:
            events = db.execute(
                "SELECT details->>'principal_id' FROM events "
                "WHERE subject_id=%s AND kind='capability.evaluated'",
                (task_id,),
            ).fetchall()
        assert events == [(assigned_id,)]


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_work_group_consolidation_is_ceo_confirmed_idempotent_and_evidence_bound(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "consolidation-ceo")
    ceo = {"X-CEO-Token": "consolidation-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Consolidation " + str(uuid4()), "objective": "Test evidenced synthesis",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Work group consolidation", "mandate_id": mandate,
        }).json()["id"]
        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Consolidation discussion",
        }).json()["id"]
        group_response = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "title": "Deliver outcomes",
                "description": "Parent remains a non-executable container",
                "acceptance_criteria": ["All child outcomes are reviewed"],
                "tasks": [
                    {"key": "one", "title": "Outcome one", "acceptance_criteria": ["Evidence one"]},
                    {"key": "two", "title": "Outcome two", "acceptance_criteria": ["Evidence two"]},
                ],
            },
        )
        assert group_response.status_code == 201, group_response.text
        group = group_response.json()
        group_list_url = f"/v1/projects/{project}/work-groups"
        assert client.get(group_list_url).status_code == 403
        initial_group = client.get(group_list_url, headers=ceo).json()[0]
        assert initial_group["consolidation_ready"] is False
        assert initial_group["partial_reports"] == []
        partial_endpoint = f"/v1/projects/{project}/work-groups/{group['id']}/partial-reports"
        partial_payload = {
            "idempotency_key": str(uuid4()),
            "expected_source_sha256": initial_group["source_sha256"],
            "report_kind": "PARTIAL",
            "summary": "One outcome is still in progress; this is not final.",
        }
        assert client.post(partial_endpoint, json=partial_payload).status_code == 403
        partial = client.post(partial_endpoint, headers=ceo, json=partial_payload)
        assert partial.status_code == 201, partial.text
        assert partial.json()["final"] is False
        assert client.post(partial_endpoint, headers=ceo, json=partial_payload).json()["created"] is False
        changed_partial = {**partial_payload, "summary": "Changed after submission"}
        assert client.post(partial_endpoint, headers=ceo, json=changed_partial).status_code == 409
        with connect_postgres() as db:
            statuses = db.execute(
                "SELECT status FROM work_items WHERE id = ANY(%s)",
                ([child["id"] for child in group["tasks"]],),
            ).fetchall()
            report_events = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.group_partial_reported'",
                (group["parent_work_id"],),
            ).fetchall()
        assert [status[0] for status in statuses] == ["INBOX", "INBOX"]
        assert len(report_events) == 1 and report_events[0][0]["final"] is False
        assert len(client.get(group_list_url, headers=ceo).json()[0]["partial_reports"]) == 1

        with connect_postgres() as db:
            for index, child in enumerate(group["tasks"]):
                db.execute(
                    "UPDATE work_items SET status='DONE',evidence=%s::jsonb WHERE id=%s",
                    (json.dumps([f"artifact://{child['id']}/result"]), child["id"]),
                )
                db.execute(
                    "INSERT INTO execution_queue(id,work_id,project_id,status,worker_id,input_json,result_json) "
                    "VALUES (%s,%s,%s,'SUCCEEDED',%s,%s::jsonb,%s::jsonb)",
                    (str(uuid4()), child["id"], project, f"agent-{index}",
                     json.dumps({"type": "aao.inert.v1"}),
                     json.dumps({"patch": "must-not-leak", "completed": True})),
                )
                db.execute(
                    "INSERT INTO reviews(id,work_id,reviewer_id,decision,candidate_sha,evidence) "
                    "VALUES (%s,%s,'auditor-test','APPROVE',%s,%s::jsonb)",
                    (str(uuid4()), child["id"], "a" * 40,
                     json.dumps([f"review://{child['id']}"])),
                )

        listed = client.get(group_list_url, headers=ceo).json()[0]
        assert listed["consolidation_ready"] is True
        endpoint = f"/v1/projects/{project}/work-groups/{group['id']}/consolidation"
        payload = {
            "idempotency_key": str(uuid4()),
            "expected_source_sha256": listed["source_sha256"],
            "summary": "CEO reviewed both completed outcomes and their evidence.",
        }
        assert client.post(endpoint, json=payload).status_code == 403
        stale = dict(payload)
        stale["expected_source_sha256"] = "0" * 64
        assert client.post(endpoint, headers=ceo, json=stale).status_code == 409
        with connect_postgres() as db:
            records = db.execute(
                "SELECT count(*) FROM work_group_consolidations WHERE work_group_id=%s",
                (group["id"],),
            ).fetchone()[0]
        assert records == 0

        changed_report = {
            **partial_payload, "expected_source_sha256": "0" * 64,
            "idempotency_key": str(uuid4()),
        }
        assert client.post(partial_endpoint, headers=ceo, json=changed_report).status_code == 409

        saved = client.post(endpoint, headers=ceo, json=payload)
        assert saved.status_code == 201, saved.text
        consolidation = saved.json()
        assert consolidation["created"] is True
        assert consolidation["source_sha256"] == payload["expected_source_sha256"]
        assert len(consolidation["source_snapshot"]["children"]) == 2
        first_source = consolidation["source_snapshot"]["children"][0]
        assert first_source["status"] == "DONE"
        assert first_source["executions"][0]["worker_id"].startswith("agent-")
        assert first_source["executions"][0]["result_sha256"]
        assert first_source["reviews"][0]["evidence"]
        assert "must-not-leak" not in saved.text
        replay = client.post(endpoint, headers=ceo, json=payload)
        assert replay.status_code == 201 and replay.json()["created"] is False
        messages_url = f"/v1/projects/{project}/conversations/{conversation}/messages"
        messages = client.get(messages_url, headers=ceo)
        assert messages.status_code == 200, messages.text
        results = [message for message in messages.json() if message.get("message_kind") == "WORK_GROUP_RESULT"]
        assert len(results) == 1
        assert results[0]["sender"] == "AAO"
        assert results[0]["related_work_id"] == group["parent_work_id"]
        assert payload["summary"] in results[0]["body"]
        assert payload["expected_source_sha256"] in results[0]["body"]
        assert results[0]["provider"] is None and results[0]["model"] is None
        after_final = {
            "idempotency_key": str(uuid4()),
            "expected_source_sha256": listed["source_sha256"],
            "report_kind": "PARTIAL", "summary": "Cannot append a partial report after final consolidation.",
        }
        assert client.post(partial_endpoint, headers=ceo, json=after_final).status_code == 409
        assert client.post(partial_endpoint, headers=ceo, json=partial_payload).json()["created"] is False

        with connect_postgres() as db:
            parent_status = db.execute(
                "SELECT status FROM work_items WHERE id=%s", (group["parent_work_id"],),
            ).fetchone()[0]
            events = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.group_consolidated'",
                (group["parent_work_id"],),
            ).fetchall()
            result_message_count = db.execute(
                "SELECT count(*) FROM project_conversation_messages "
                "WHERE conversation_id=%s AND message_kind='WORK_GROUP_RESULT'",
                (conversation,),
            ).fetchone()[0]
        assert parent_status == "INBOX"
        assert len(events) == 1 and events[0][0]["work_status_changed"] is False
        assert result_message_count == 1
        assert client.post(endpoint, headers=ceo, json={**payload, "summary": "different"}).status_code == 409


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_ceo_browser_session_cookie_csrf_and_logout(monkeypatch):
    from aao.work_management_api import CEO_SESSION_COOKIE, app, tx

    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "cookie-session-test-token")
    monkeypatch.setenv("AAO_CEO_SESSION_ALLOWED_ORIGINS", "https://testserver")
    origin = {"Origin": "https://testserver"}

    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/v1/auth/ceo/session", headers={**origin, "X-CEO-Token": "bad"}).status_code == 403
        exchanged = client.post("/v1/auth/ceo/session", headers={**origin, "X-CEO-Token": "cookie-session-test-token"})
        assert exchanged.status_code == 200
        assert "cookie-session-test-token" not in exchanged.text
        cookie_header = exchanged.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie_header and "Secure" in cookie_header
        assert "SameSite=strict" in cookie_header and "Path=/" in cookie_header
        assert CEO_SESSION_COOKIE in cookie_header
        assert client.cookies.get(CEO_SESSION_COOKIE)

        mandate = client.post("/v1/mandates", headers=origin | {"X-CEO-Token": "cookie-session-test-token"}, json={
            "title": "Cookie project visibility", "objective": "Cookie CEO sessions can read canonical projects",
        })
        assert mandate.status_code == 201
        assert client.post(
            f"/v1/mandates/{mandate.json()['id']}/confirm",
            headers=origin | {"X-CEO-Token": "cookie-session-test-token"},
        ).status_code == 200
        project = client.post("/v1/projects", headers=origin | {"X-CEO-Token": "cookie-session-test-token"}, json={
            "name": "Cookie-visible project", "mandate_id": mandate.json()["id"],
        })
        assert project.status_code == 201
        project_list = client.get("/v1/projects")
        assert project_list.status_code == 200
        assert project.json()["id"] in {item["id"] for item in project_list.json()}

        with tx() as db:
            cookie_digest = __import__("hashlib").sha256(client.cookies.get(CEO_SESSION_COOKIE).encode()).hexdigest()
            stored = db.execute(
                "SELECT id,session_digest,csrf_digest FROM ceo_browser_sessions WHERE session_digest=%s",
                (cookie_digest,),
            ).fetchone()
        assert stored and stored[1] == cookie_digest
        assert stored[1] != client.cookies.get(CEO_SESSION_COOKIE)
        assert stored[2] == __import__("hashlib").sha256(exchanged.json()["csrf_token"].encode()).hexdigest()

        assert client.get("/v1/mandates").status_code == 200
        with tx() as db:
            db.execute("UPDATE ceo_browser_sessions SET created_at=clock_timestamp() - interval '13 hours', expires_at=clock_timestamp() - interval '1 second' WHERE id=%s", (stored[0],))
        assert client.get("/v1/mandates").status_code == 403
        with tx() as db:
            db.execute("UPDATE ceo_browser_sessions SET expires_at=clock_timestamp() + interval '1 hour' WHERE id=%s", (stored[0],))
        assert client.get("/v1/mandates").status_code == 200
        assert client.post("/v1/mandates", headers=origin, json={"title": "blocked", "objective": "csrf"}).status_code == 403
        assert client.post("/v1/mandates", headers={**origin, "X-AAO-CSRF": "wrong"}, json={"title": "blocked", "objective": "csrf"}).status_code == 403
        csrf = exchanged.json()["csrf_token"]
        created = client.post(
            "/v1/mandates", headers={**origin, "X-AAO-CSRF": csrf},
            json={"title": "Cookie session test", "objective": "Disposable test only"},
        )
        assert created.status_code == 201, created.text

        restored = client.post("/v1/auth/ceo/session/csrf", headers=origin)
        assert restored.status_code == 200
        new_csrf = restored.json()["csrf_token"]
        assert new_csrf != csrf
        assert client.post("/v1/mandates", headers={**origin, "X-AAO-CSRF": csrf}, json={"title": "old csrf", "objective": "rejected"}).status_code == 403
        assert client.post("/v1/auth/ceo/logout", headers={**origin, "X-AAO-CSRF": new_csrf}).status_code == 200
        assert not client.cookies.get(CEO_SESSION_COOKIE)
        assert client.get("/v1/mandates").status_code == 403

        monkeypatch.setenv("AAO_ENV", "production")
        assert client.post("/v1/auth/ceo/session", headers={**origin, "X-CEO-Token": "cookie-session-test-token"}).status_code == 503
        client.cookies.set(CEO_SESSION_COOKIE, "not-a-real-secret", domain="testserver", path="/")
        assert client.get("/v1/mandates").status_code == 503


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or
    os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_ceo_knowledge_index_is_authenticated_and_payload_limited(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "knowledge-index-ceo")
    ceo = {"X-CEO-Token": "knowledge-index-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Knowledge index " + str(uuid4()), "objective": "Index source references",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Knowledge source project", "mandate_id": mandate,
        }).json()["id"]
        created = client.post(f"/v1/projects/{project}/work-requests", headers=ceo, json={
            "title": "Persisted source record", "description": "not indexed as body",
            "acceptance_criteria": ["source metadata only"],
        })
        assert created.status_code == 201, created.text
        work_id = created.json()["id"]
        reviewer_id = "knowledge-index-auditor-" + str(uuid4())
        reviewer_credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": reviewer_id, "kind": "AUDITOR",
        })
        assert reviewer_credential.status_code == 201
        with connect_postgres() as db:
            db.execute(
                "UPDATE work_items SET evidence=%s::jsonb WHERE id=%s",
                (json.dumps(["sha256:source-reference", {"secret": "private evidence body"}]), work_id),
            )
            db.execute(
                "INSERT INTO reviews(id,work_id,reviewer_id,decision,candidate_sha,evidence) "
                "VALUES(%s,%s,%s,'APPROVE',%s,%s::jsonb)",
                (str(uuid4()), work_id, reviewer_id, "a" * 40,
                 json.dumps(["sha256:review-reference", {"secret": "private review body"}])),
            )
            db.execute(
                "INSERT INTO execution_queue(id,work_id,project_id,status,input_json,result_json) "
                "VALUES(%s,%s,%s,'SUCCEEDED','{}'::jsonb,%s::jsonb)",
                (str(uuid4()), work_id, project, json.dumps({"secret": "private execution result"})),
            )
        assert client.get("/v1/knowledge/index").status_code == 403
        agent_id = "knowledge-index-agent-" + str(uuid4())
        agent_credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": agent_id, "kind": "AGENT",
        })
        assert agent_credential.status_code == 201
        agent_headers = {"X-Agent-Token": agent_credential.json()["token"]}
        assert client.get("/v1/knowledge/index", headers=agent_headers).status_code == 403

        response = client.get("/v1/knowledge/index", headers=ceo)
        assert response.status_code == 200, response.text
        indexed = next(record for record in response.json() if record["work_id"] == work_id)
        assert indexed["project_id"] == project
        assert indexed["evidence_references"] == ["sha256:source-reference"]
        assert indexed["reviews"][0]["evidence_references"] == ["sha256:review-reference"]
        assert "private evidence body" not in response.text
        assert "private review body" not in response.text and "private execution result" not in response.text
        assert "result_json" not in response.text and "description" not in indexed
        assert set(indexed) == {"work_id", "project_id", "project_name", "title", "status", "evidence_references", "reviews"}


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_capability_feedback_is_persisted_as_non_applied_ceo_proposal(monkeypatch):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "feedback-proposal-ceo")
    ceo = {"X-CEO-Token": "feedback-proposal-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Feedback " + str(uuid4()), "objective": "Capture reviewed corrections",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Feedback proposal", "mandate_id": mandate,
        }).json()["id"]
        worker_id = "feedback-agent-" + str(uuid4())
        credential = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": worker_id, "kind": "AGENT",
        })
        assert credential.status_code == 201
        worker = {"X-Agent-Token": credential.json()["token"]}
        assert client.post(f"/v1/projects/{project}/grants", headers=ceo, json={
            "principal_id": worker_id, "capability": "work.create",
        }).status_code == 201
        capability = client.post(f"/v1/projects/{project}/capabilities", headers=worker, json={
            "capability_id": "reviewed.skill", "version": "1.0.0",
            "capability_type": "agent_skill", "provenance": {"kind": "test"},
            "contract": {"purpose": "Test capability", "compatible_roles": ["agent"],
                         "inputs": ["request"], "outputs": ["response"],
                         "usage_limits": ["project scope"]},
            "tests": ["test-reference"], "evidence": ["source-reference"],
        })
        assert capability.status_code == 201, capability.text

        payload = {"capability_id": "reviewed.skill", "version": "1.0.0",
                   "correction": "Preserve the source reference in the response.",
                   "evidence": ["sha256:observed-correction"]}
        assert client.post(f"/v1/projects/{project}/capability-feedback", json=payload).status_code == 403
        proposed = client.post(f"/v1/projects/{project}/capability-feedback", headers=ceo, json=payload)
        assert proposed.status_code == 201, proposed.text
        assert proposed.json()["status"] == "proposed"
        assert proposed.json()["applied"] is False
        listing = client.get(f"/v1/projects/{project}/capability-feedback", headers=ceo)
        assert listing.status_code == 200, listing.text
        assert listing.json()[0]["correction"] == payload["correction"]
        assert listing.json()[0]["status"] == "proposed"
        assert listing.json()[0]["applied"] is False
        proposal_id = proposed.json()["id"]
        review_path = f"/v1/projects/{project}/capability-feedback/{proposal_id}/review"
        decision = client.post(review_path, json={"status": "accepted"})
        assert decision.status_code == 403
        decision = client.post(review_path, headers=ceo, json={"status": "accepted"})
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "accepted"
        assert decision.json()["reviewed_by"] == "ceo"
        assert decision.json()["reviewed_at"]
        assert decision.json()["applied"] is False
        assert client.post(review_path, headers=ceo, json={"status": "accepted"}).json() == decision.json()
        assert client.post(review_path, headers=ceo, json={"status": "rejected"}).status_code == 409
        reviewed = client.get(f"/v1/projects/{project}/capability-feedback", headers=ceo).json()[0]
        assert reviewed["status"] == "accepted"
        assert reviewed["reviewed_by"] == "ceo"
        assert reviewed["reviewed_at"] == decision.json()["reviewed_at"]
        assert reviewed["applied"] is False
        version_path = f"/v1/projects/{project}/capability-feedback/{proposal_id}/version"
        version_payload = {
            "version": "1.1.0", "provenance": {"kind": "ceo-reviewed"},
            "contract": {"purpose": "Test capability", "compatible_roles": ["agent"],
                         "inputs": ["request"], "outputs": ["response"],
                         "usage_limits": ["project scope"]},
            "tests": ["test-reference-v2"], "evidence": ["sha256:reviewed-change"],
        }
        assert client.post(version_path, json=version_payload).status_code == 403
        assert client.post(version_path, headers=ceo, json={**version_payload, "version": "1.0.0"}).status_code == 422
        created = client.post(version_path, headers=ceo, json=version_payload)
        assert created.status_code == 201, created.text
        assert created.json() == {
            "id": proposal_id, "capability_id": "reviewed.skill", "source_version": "1.0.0",
            "version": "1.1.0", "status": "registered_local", "applied": True,
            "execution_authorized": False,
        }
        assert client.post(version_path, headers=ceo, json=version_payload).status_code == 409
        versions = client.get(f"/v1/projects/{project}/capabilities", headers=ceo).json()
        assert {item["version"] for item in versions} == {"1.0.0", "1.1.0"}
        new_version = next(item for item in versions if item["version"] == "1.1.0")
        assert new_version["status"] == "registered_local"
        assert new_version["execution_authorized"] is False
        assert new_version["provenance"]["feedback_proposal_id"] == proposal_id
        reviewed = client.get(f"/v1/projects/{project}/capability-feedback", headers=ceo).json()[0]
        assert reviewed["applied"] is True
        assert reviewed["applied_capability_version"] == "1.1.0"
        assert client.post(review_path, headers=ceo, json={"status": "accepted"}).json()["applied"] is True


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="PostgreSQL integration requires an explicitly disposable test database",
)
def test_product_acceptance_closes_group_only_after_current_consolidation(monkeypatch):
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "product-acceptance-ceo")
    ceo = {"X-CEO-Token": "product-acceptance-ceo"}
    with TestClient(app) as client:
        mandate = client.post("/v1/mandates", headers=ceo, json={
            "title": "Product acceptance " + str(uuid4()), "objective": "Accept completed pilot output",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate}/confirm", headers=ceo).status_code == 200
        project = client.post("/v1/projects", headers=ceo, json={
            "name": "Product acceptance", "mandate_id": mandate,
        }).json()["id"]
        conversation = client.post(f"/v1/projects/{project}/conversations", headers=ceo, json={
            "title": "Pilot acceptance",
        }).json()["id"]
        created_group = client.post(
            f"/v1/projects/{project}/conversations/{conversation}/work-groups",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "title": "Pilot objective",
                "description": "Complete and accept pilot output",
                "acceptance_criteria": ["Child result is complete"],
                "tasks": [{"key": "result", "title": "Result", "acceptance_criteria": ["Evidence"]}],
            },
        )
        assert created_group.status_code == 201, created_group.text
        group = created_group.json()
        endpoint = f"/v1/projects/{project}/work-groups/{group['id']}/acceptance"
        assert client.post(endpoint, json={}).status_code == 403

        child_id = group["tasks"][0]["id"]
        before_completion = client.get(
            f"/v1/projects/{project}/work-groups", headers=ceo,
        ).json()[0]
        premature_payload = {
            "idempotency_key": str(uuid4()),
            "expected_source_sha256": before_completion["source_sha256"],
            "accepted_criteria": ["Child result is complete"],
            "acceptance_statement": "The delivered result meets the product acceptance criteria.",
        }
        premature = client.post(endpoint, headers=ceo, json=premature_payload)
        assert premature.status_code == 409
        assert client.get(
            f"/v1/projects/{project}/work-groups", headers=ceo,
        ).json()[0]["parent_status"] == "INBOX"
        candidate_sha = "a" * 40
        with connect_postgres() as db:
            db.execute("UPDATE work_items SET status='DONE',evidence=%s::jsonb WHERE id=%s",
                       (json.dumps(["artifact://pilot/result"]), child_id))
            db.execute(
                "INSERT INTO execution_queue(id,work_id,project_id,status,worker_id,input_json,result_json) "
                "VALUES (%s,%s,%s,'SUCCEEDED','pilot-agent',%s::jsonb,%s::jsonb)",
                (str(uuid4()), child_id, project, json.dumps({"type": "aao.inert.v1"}),
                 json.dumps({"completed": True, "candidate_sha": candidate_sha})),
            )
        listed = client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]
        endpoint = f"/v1/projects/{project}/work-groups/{group['id']}/acceptance"
        acceptance_payload = {
            "idempotency_key": str(uuid4()),
            "expected_source_sha256": listed["source_sha256"],
            "accepted_criteria": ["Child result is complete"],
            "acceptance_statement": "The delivered result meets the product acceptance criteria.",
        }
        unreviewed = client.post(endpoint, headers=ceo, json=acceptance_payload)
        assert unreviewed.status_code == 409
        assert "APPROVE review" in unreviewed.json()["detail"]
        with connect_postgres() as db:
            auditor_id = str(uuid4())
            db.execute(
                "INSERT INTO principals(id,name,kind) VALUES (%s,%s,'AUDITOR')",
                (auditor_id, "quality-pilot"),
            )
            db.execute(
                "INSERT INTO reviews(id,work_id,reviewer_id,decision,evidence,candidate_sha) "
                "VALUES (%s,%s,%s,'APPROVE',%s::jsonb,%s)",
                (str(uuid4()), child_id, auditor_id, json.dumps(["artifact://pilot/review"]), candidate_sha),
            )
        listed = client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]
        acceptance_payload["expected_source_sha256"] = listed["source_sha256"]
        # DONE children are not enough: product acceptance requires an
        # evidence-bound consolidation of the current reviewed source snapshot.
        without_consolidation = client.post(
            endpoint, headers=ceo, json=acceptance_payload,
        )
        assert without_consolidation.status_code == 409
        assert client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]["parent_status"] == "INBOX"
        consolidation = client.post(
            f"/v1/projects/{project}/work-groups/{group['id']}/consolidation",
            headers=ceo, json={
                "idempotency_key": str(uuid4()), "expected_source_sha256": listed["source_sha256"],
                "summary": "The CEO-reviewed product result is ready for acceptance.",
            },
        )
        assert consolidation.status_code == 201, consolidation.text
        payload = acceptance_payload
        rejected_criteria = {**payload, "accepted_criteria": ["Different criteria"]}
        assert client.post(endpoint, headers=ceo, json=rejected_criteria).status_code == 409
        stale_snapshot = {**payload, "expected_source_sha256": "0" * 64}
        assert client.post(endpoint, headers=ceo, json=stale_snapshot).status_code == 409
        accepted = client.post(endpoint, headers=ceo, json=payload)
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["created"] is True
        replay = client.post(endpoint, headers=ceo, json=payload)
        assert replay.status_code == 201 and replay.json()["created"] is False
        changed = {**payload, "acceptance_statement": "Different acceptance statement"}
        assert client.post(endpoint, headers=ceo, json=changed).status_code == 409
        projection = client.get(f"/v1/projects/{project}/work-groups", headers=ceo).json()[0]
        assert projection["parent_status"] == "DONE"
        assert projection["acceptance"]["accepted_criteria"] == payload["accepted_criteria"]
        assert projection["acceptance"]["source_sha256"] == payload["expected_source_sha256"]
        with connect_postgres() as db:
            event = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.group_accepted'",
                (group["parent_work_id"],),
            ).fetchone()
            parent_status = db.execute(
                "SELECT status FROM work_items WHERE id=%s", (group["parent_work_id"],),
            ).fetchone()[0]
        assert parent_status == "DONE"
        assert event[0]["actor"] == "ceo"
        assert event[0]["independent_review"] is False
        assert event[0]["integration_performed"] is False
        with connect_postgres() as db:
            acceptance_protocol = db.execute(
                "SELECT id,protocol_version,started_by FROM protocol_instances "
                "WHERE protocol_id='review-acceptance' AND subject_type='work_group' AND subject_id=%s",
                (group["parent_work_id"],),
            ).fetchone()
        assert acceptance_protocol is not None
        assert acceptance_protocol[1:] == ("1.0.0", "ceo")
        assert event[0]["protocol_instance_id"] == str(acceptance_protocol[0])


@pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
def test_revoked_assignee_is_persistently_blocked_and_pm_can_reassign_unclaimed_queue(monkeypatch):
    from aao.execution_queue import claim
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_CEO_TOKEN", "rst2-ceo")
    monkeypatch.setenv("AAO_SANDBOX_QUEUE_ENABLED", "true")
    ceo = {"X-CEO-Token": "rst2-ceo"}

    def issue(principal_id):
        response = client.post("/v1/principals/credentials", headers=ceo, json={
            "principal_id": principal_id, "kind": "AGENT",
        })
        assert response.status_code == 201, response.text
        return {"X-Agent-Token": response.json()["token"]}

    old_agent_id = "rst2-old-" + str(uuid4())
    new_agent_id = "rst2-new-" + str(uuid4())
    pm_id = "rst2-pm-" + str(uuid4())
    with TestClient(app) as client:
        old_agent = issue(old_agent_id)
        new_agent = issue(new_agent_id)
        pm = issue(pm_id)
        mandate_id = client.post("/v1/mandates", headers=ceo, json={
            "title": "Agent unavailable " + str(uuid4()),
            "objective": "Reassign safely after credential revocation",
        }).json()["id"]
        assert client.post(f"/v1/mandates/{mandate_id}/confirm", headers=ceo).status_code == 200
        project_id = client.post("/v1/projects", headers=ceo, json={
            "name": "RST-2 agent unavailable", "mandate_id": mandate_id,
        }).json()["id"]
        for principal_id in (old_agent_id, new_agent_id):
            for capability in ("work.admit", "execution.claim"):
                grant = client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
                    "principal_id": principal_id, "capability": capability,
                })
                assert grant.status_code == 201, grant.text
            profile = client.put("/v1/organization/profiles", headers=ceo, json={
                "principal_id": principal_id, "display_name": principal_id,
                "role_title": "Engineer", "competencies": ["python"],
            })
            assert profile.status_code == 200, profile.text
        assert client.post(f"/v1/projects/{project_id}/grants", headers=ceo, json={
            "principal_id": pm_id, "capability": "work.assign",
        }).status_code == 201

        conversation_id = client.post(
            f"/v1/projects/{project_id}/conversations", headers=ceo,
            json={"title": "Unavailable assignee"},
        ).json()["id"]
        group_response = client.post(
            f"/v1/projects/{project_id}/conversations/{conversation_id}/work-groups",
            headers=ceo,
            json={
                "idempotency_key": str(uuid4()), "title": "Plan", "description": "A task",
                "acceptance_criteria": ["queue survives reassignment"],
                "tasks": [{
                    "key": "task", "title": "Queued task",
                    "acceptance_criteria": ["claimed by currently assigned agent"],
                    "required_competencies": ["python"],
                    "assigned_principal_id": old_agent_id,
                }],
            },
        )
        assert group_response.status_code == 201, group_response.text
        work_id = group_response.json()["tasks"][0]["id"]
        admitted = client.post(f"/v1/work/{work_id}/admit", headers=old_agent)
        assert admitted.status_code == 200, admitted.text
        staged = client.post(f"/v1/work/{work_id}/stage-inert", headers=old_agent)
        assert staged.status_code == 202, staged.text
        execution_id = staged.json()["execution_id"]

        revoked = client.post(f"/v1/principals/{old_agent_id}/revoke", headers=ceo)
        assert revoked.status_code == 200, revoked.text
        assert client.post("/v1/agent/dispatch-next", headers=old_agent, json={
            "project_id": project_id, "principal_id": old_agent_id, "base_sha": "a" * 40,
        }).status_code == 403

        with connect_postgres() as db:
            row = db.execute(
                "SELECT details FROM events WHERE subject_id=%s AND kind='work.dispatch_blocked'",
                (work_id,),
            ).fetchone()
            protocol = db.execute(
                "SELECT id,protocol_id,protocol_version,started_by FROM protocol_instances "
                "WHERE subject_type='work_item' AND subject_id=%s AND protocol_id='blockage-escalation'",
                (work_id,),
            ).fetchone()
        assert row is not None
        block = row[0]
        assert block["principal_id"] == old_agent_id
        assert block["actor"] == "ceo"
        assert block["reason"] == "Assigned agent credential revoked before execution claim"
        assert block["next_actor_principal_ids"] == [pm_id]
        assert block["protocol_instance_id"] == str(protocol[0])
        assert protocol[1:] == ("blockage-escalation", "1.0.0", "ceo")
        assert "work.assign" in block["next_action"]

        denied = client.put(
            f"/v1/agent/work/{work_id}/assignment", headers=new_agent,
            json={"principal_id": new_agent_id},
        )
        assert denied.status_code == 403
        reassigned = client.put(
            f"/v1/agent/work/{work_id}/assignment", headers=pm,
            json={"principal_id": new_agent_id},
        )
        assert reassigned.status_code == 200, reassigned.text
        assert reassigned.json()["principal_id"] == new_agent_id

    lease = claim(new_agent_id, agent_credential=new_agent["X-Agent-Token"], project_id=project_id)
    assert lease and lease["execution_id"] == execution_id
    assert lease["worker_id"] == new_agent_id
    with connect_postgres() as db:
        queue = db.execute(
            "SELECT status,worker_id,attempts FROM execution_queue WHERE id=%s", (execution_id,),
        ).fetchone()
        assignments = db.execute(
            "SELECT details FROM events WHERE subject_id=%s AND kind='work.assigned' "
            "ORDER BY created_at,id", (work_id,),
        ).fetchall()
        grant_count = db.execute(
            "SELECT count(*) FROM project_grants WHERE principal_id=%s AND project_id=%s",
            (new_agent_id, project_id),
        ).fetchone()[0]
    assert queue == ("RUNNING", new_agent_id, 1)
    assert assignments[-1][0]["principal_id"] == new_agent_id
    assert assignments[-1][0]["previous_principal_id"] == old_agent_id
    assert grant_count == 2
