from datetime import UTC, datetime, timedelta
from contextlib import contextmanager
import json

import pytest
from fastapi.testclient import TestClient

from aao.office_world import Point, position_on_route, validate_route
from aao import work_management_api
from aao.work_management_api import OfficeWorldPlanRequest


def square():
    return [Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)]


def test_route_position_uses_elapsed_server_time_and_wraps():
    started = datetime(2026, 1, 1, tzinfo=UTC)
    route = square()
    first = position_on_route(route, started_at=started, now=started + timedelta(seconds=5), speed=1)
    after_reload = position_on_route(route, started_at=started, now=started + timedelta(seconds=5), speed=1)
    wrapped = position_on_route(route, started_at=started, now=started + timedelta(seconds=45), speed=1)
    assert first == after_reload
    assert (first.x, first.z) == (5, 0)
    assert (wrapped.x, wrapped.z) == (5, 0)


def test_route_is_a_closed_repeatable_polyline_with_bounded_points():
    with pytest.raises(ValueError, match="between 2 and 128"):
        validate_route([Point(0, 0)])
    with pytest.raises(ValueError, match="distinct"):
        validate_route([Point(0, 0), Point(0, 0), Point(10, 10)])
    with pytest.raises(ValueError, match="first waypoint"):
        validate_route([Point(0, 0), Point(10, 0), Point(0, 0)])
    with pytest.raises(ValueError, match="map bounds"):
        validate_route([Point(0, 0), Point(501, 0)])


def test_route_position_clamps_prestart_time_and_rejects_invalid_speed():
    started = datetime(2026, 1, 1, tzinfo=UTC)
    position = position_on_route(square(), started_at=started, now=started - timedelta(seconds=3), speed=0.5)
    assert (position.x, position.z) == (0, 0)
    with pytest.raises(ValueError, match="speed"):
        position_on_route(square(), started_at=started, now=started, speed=5)


def test_published_world_plan_rejects_duplicate_actor_ids_and_unregistered_npcs():
    route = [{"x": 0, "z": 0}, {"x": 1, "z": 0}]
    with pytest.raises(ValueError, match="duplicate actor IDs"):
        OfficeWorldPlanRequest.model_validate({
            "map_revision": "map-v1",
            "actors": [
                {"actor_id": "npc:office-runner", "actor_kind": "NPC", "route": route, "speed": 0.3},
                {"actor_id": "npc:office-runner", "actor_kind": "NPC", "route": route, "speed": 0.3},
            ],
        })


def test_office_world_api_returns_server_clock_positions_and_preserves_route_epoch(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.now = datetime(2026, 1, 1, tzinfo=UTC)
            self.routes = {}

        def execute(self, query, params=()):
            normalized = " ".join(query.split())
            if normalized.startswith("SELECT p.principal_id FROM organization_profiles"):
                return FakeCursor([("agent-1",)])
            if normalized.startswith("SELECT DISTINCT worker_id FROM execution_queue"):
                return FakeCursor([])
            if normalized.startswith("INSERT INTO office_world_routes"):
                actor_id, actor_kind, revision, route_json, speed = params
                previous = self.routes.get(actor_id)
                route = json.loads(route_json)
                started_at = self.now if previous is None or previous[1:3] != (route, speed) else previous[4]
                self.routes[actor_id] = (actor_kind, route, speed, revision, started_at)
                return FakeCursor([])
            if normalized.startswith("DELETE FROM office_world_routes WHERE NOT"):
                keep = set(params[0])
                self.routes = {key: value for key, value in self.routes.items() if key in keep}
                return FakeCursor([])
            if normalized == "DELETE FROM office_world_routes":
                self.routes.clear()
                return FakeCursor([])
            if normalized.startswith("SELECT actor_id,actor_kind,map_revision,route_json,speed,started_at"):
                return FakeCursor([
                    (actor_id, kind, revision, route, speed, started_at)
                    for actor_id, (kind, route, speed, revision, started_at) in self.routes.items()
                ])
            if normalized == "SELECT clock_timestamp()":
                return FakeCursor([(self.now,)])
            raise AssertionError(f"Unexpected SQL: {normalized}")

    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    db = FakeDB()

    @contextmanager
    def fake_tx():
        yield db

    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_CEO_TOKEN", "office-world-test-token")
    monkeypatch.setattr(work_management_api, "tx", fake_tx)
    client = TestClient(work_management_api.app)
    headers = {"X-CEO-Token": "office-world-test-token"}
    route = [{"x": 0, "z": 0}, {"x": 10, "z": 0}, {"x": 10, "z": 10}, {"x": 0, "z": 10}]
    plan = {
        "map_revision": "map-v1",
        "actors": [
            {"actor_id": "agent-1", "actor_kind": "AGENT", "route": route, "speed": 1},
            {"actor_id": "npc:office-runner", "actor_kind": "NPC", "route": route, "speed": 1},
        ],
    }
    published = client.put("/v1/office/world/plan", json=plan, headers=headers)
    assert published.status_code == 200
    assert published.json()["creates_business_evidence"] is False

    db.now += timedelta(seconds=5)
    first = client.get("/v1/office/world", headers=headers).json()
    agent = next(actor for actor in first["actors"] if actor["actor_id"] == "agent-1")
    assert (agent["x"], agent["z"]) == (5, 0)
    original_started_at = db.routes["agent-1"][4]

    db.now += timedelta(seconds=10)
    assert client.put("/v1/office/world/plan", json=plan, headers=headers).status_code == 200
    assert db.routes["agent-1"][4] == original_started_at
    later = client.get("/v1/office/world", headers=headers).json()
    later_agent = next(actor for actor in later["actors"] if actor["actor_id"] == "agent-1")
    assert (later_agent["x"], later_agent["z"]) == (10, 5)
    with pytest.raises(ValueError, match="Unknown ambient NPC"):
        OfficeWorldPlanRequest.model_validate({
            "map_revision": "map-v1",
            "actors": [{"actor_id": "npc:unknown", "actor_kind": "NPC", "route": route, "speed": 0.3}],
        })
