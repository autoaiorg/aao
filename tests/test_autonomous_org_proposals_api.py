"""Integration tests for Autonomous Organization Proposals API & Database Persistence."""
import os

import pytest
from fastapi.testclient import TestClient

from aao.work_management_api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_proposals_api_flow(client, monkeypatch):
    if "AAO_TEST_POSTGRES_URL" in os.environ:
        monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_CEO_TOKEN", "test-ceo-token-123456")
    # Authenticate as CEO via X-CEO-Token
    client.headers["X-CEO-Token"] = "test-ceo-token-123456"

    # 1. Create Proposal with valid criteria
    payload = {
        "title": "Propuesta de Unidad Especializada en Frontend y Experiencia",
        "scope_description": "Constitución de departamento tras 65 días de saturación en desarrollo de interfaces.",
        "target_unit_id": "unit-fe-special",
        "target_unit_code": "FE-EXP",
        "target_unit_name": "Frontend y Experiencia",
        "demand_summary": "Saturación sostenida con 4 proyectos activos y 8 tareas bloqueadas.",
        "criteria": {
            "active_projects_count": 4,
            "future_commitments_count": 3,
            "unassigned_tasks_count": 8,
            "blocked_tasks_count": 4,
            "specialization_gaps": ["frontend", "graphics"],
            "coordination_friction_score": 0.8,
            "budget_utilization_ratio": 0.75,
            "segregation_risk_detected": False,
            "observation_period_days": 65,
        },
        "min_observation_days": 60,
        "max_marginal_cost_usd": 1000.0,
    }

    res = client.post("/v1/organization/proposals", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "id" in data
    assert data["version"] == 1
    assert data["state"] == "REQUIRES_CEO_APPROVAL"
    assert data["impact"] == "CRITICAL"
    proposal_id = data["id"]

    # 2. Get proposal by ID
    get_res = client.get(f"/v1/organization/proposals/{proposal_id}")
    assert get_res.status_code == 200
    prop_data = get_res.json()
    assert prop_data["id"] == proposal_id
    assert prop_data["target_unit_code"] == "FE-EXP"
    assert len(prop_data["alternatives"]) == 5

    # 3. List proposals with pagination
    list_res = client.get("/v1/organization/proposals?limit=10&offset=0")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(p["id"] == proposal_id for p in list_data["items"])

    # 4. Concurrency conflict check on transition (wrong version)
    conflict_res = client.post(
        f"/v1/organization/proposals/{proposal_id}/transitions",
        json={"target_state": "AUTONOMOUS_APPROVED", "expected_version": 999},
    )
    assert conflict_res.status_code == 409
    assert "Concurrency conflict" in conflict_res.json()["detail"]

    # 5. Non-CEO principal cannot approve CRITICAL change
    client.headers.pop("X-CEO-Token", None)
    # Mock read_principal for non-CEO
    from aao.work_management_api import read_principal
    app.dependency_overrides[read_principal] = lambda: "agent-builder-1"
    try:
        forbidden_res = client.post(
            f"/v1/organization/proposals/{proposal_id}/transitions",
            json={"target_state": "AUTONOMOUS_APPROVED", "expected_version": 1},
        )
        assert forbidden_res.status_code == 403
        assert "strictly requires CEO authority" in forbidden_res.json()["detail"]
    finally:
        app.dependency_overrides.pop(read_principal, None)

    # 6. CEO approves the proposal
    client.headers["X-CEO-Token"] = "test-ceo-token-123456"
    trans_res = client.post(
        f"/v1/organization/proposals/{proposal_id}/transitions",
        json={"target_state": "AUTONOMOUS_APPROVED", "expected_version": 1},
    )
    assert trans_res.status_code == 200
    trans_data = trans_res.json()
    assert trans_data["version"] == 2
    assert trans_data["to_state"] == "AUTONOMOUS_APPROVED"

    # 7. Illegal transition fails (cannot transition from APPROVED directly to ANALYZED)
    illegal_res = client.post(
        f"/v1/organization/proposals/{proposal_id}/transitions",
        json={"target_state": "ANALYZED", "expected_version": 2},
    )
    assert illegal_res.status_code == 422
    assert "Invalid transition" in illegal_res.json()["detail"]
