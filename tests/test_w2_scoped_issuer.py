from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

needs_pg = pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
CEO = {"X-CEO-Token": "w2-self-rotation-test-ceo"}


@pytest.mark.parametrize(
    "identity,grants",
    [
        (
            {
                "principal_id": "aao-publisher-pm-20261102123456-deadbeef",
                "kind": "AGENT",
                "enabled": True,
            },
            [],
        ),
        (
            {
                "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                "kind": "AGENT",
                "enabled": True,
            },
            [
                {
                    "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                    "project_id": "p1",
                    "capability": "project.read",
                    "active": True,
                    "expires_at": "future",
                },
                {
                    "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                    "project_id": "p1",
                    "capability": "code.publish",
                    "active": True,
                    "expires_at": "future",
                },
                {
                    "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                    "project_id": "p1",
                    "capability": "work.assign",
                    "active": True,
                    "expires_at": "future",
                },
            ],
        ),
        (
            {
                "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                "kind": "AGENT",
                "enabled": True,
            },
            [
                {
                    "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                    "project_id": "p1",
                    "capability": "project.read",
                    "active": True,
                    "expires_at": "future",
                },
                {
                    "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
                    "project_id": "p2",
                    "capability": "code.publish",
                    "active": True,
                    "expires_at": "future",
                },
            ],
        ),
    ],
)
def test_pending_recovery_identity_requires_exact_role_and_grant_scope(
    monkeypatch, identity, grants
):
    from scripts import rotate_w2_publisher_token as rotation

    monkeypatch.setattr(rotation, "_request", lambda *_args, **_kwargs: identity)
    monkeypatch.setattr(rotation, "_request_grants", lambda *_args, **_kwargs: grants)
    monkeypatch.setattr(
        rotation,
        "_request_projects",
        lambda *_args, **_kwargs: [
            {"id": "p1", "name": "AAO — Self Development", "state": "ACTIVE"}
        ],
    )
    with pytest.raises(rotation.RotationError):
        rotation._validate_w2_identity("http://127.0.0.1:8001", "opaque", "aao-impl-codex")


def test_pending_recovery_identity_requires_active_self_development_project(monkeypatch):
    from scripts import rotate_w2_publisher_token as rotation

    principal_id = "aao-publisher-impl-20261102123456-deadbeef"
    monkeypatch.setattr(
        rotation,
        "_request",
        lambda *_args, **_kwargs: {"principal_id": principal_id, "kind": "AGENT", "enabled": True},
    )
    monkeypatch.setattr(
        rotation,
        "_request_grants",
        lambda *_args, **_kwargs: [
            {
                "principal_id": principal_id,
                "project_id": "p1",
                "capability": cap,
                "active": True,
                "expires_at": "future",
            }
            for cap in ("project.read", "code.publish")
        ],
    )
    monkeypatch.setattr(
        rotation,
        "_request_projects",
        lambda *_args, **_kwargs: [{"id": "p1", "name": "Other", "state": "ACTIVE"}],
    )
    with pytest.raises(rotation.RotationError, match="Self Development"):
        rotation._validate_w2_identity("http://127.0.0.1:8001", "opaque", "aao-impl-codex")


def test_w2_publisher_rejects_unknown_and_malformed_id_before_database(monkeypatch):
    from aao.work_management_api import AuthenticatedPrincipal, app

    for principal_id in ("ordinary-agent", "aao-publisher-impl-not-valid"):
        principal = AuthenticatedPrincipal(principal_id, "digest", "AGENT")
        monkeypatch.setattr(
            "aao.work_management_api._authenticate_request_principal",
            lambda *_, principal=principal: principal,
        )

        def forbidden_tx():
            raise AssertionError("invalid W2 identity must be rejected before database access")

        monkeypatch.setattr("aao.work_management_api.tx", forbidden_tx)
        with TestClient(app) as client:
            response = client.post(
                "/v1/principals/me/w2-publisher/rotate",
                headers={"X-Agent-Token": "not-a-real-token"},
            )
        assert response.status_code == 403


def test_w2_publisher_grant_validation_rejects_non_exact_set():
    from aao.work_management_api import _lock_w2_publisher_grant_set

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class DB:
        def execute(self, sql, _params=()):
            if "SELECT id FROM projects" in sql:
                return Result([("project-1",)])
            return Result([("project-1", "project.read", None, False)])

    with pytest.raises(HTTPException):
        _lock_w2_publisher_grant_set(DB(), "aao-publisher-pm-20261102123456-1234abcd")


def _pg_fixture(monkeypatch):
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_CEO_TOKEN", CEO["X-CEO-Token"])
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    client = TestClient(app)
    return client, connect_postgres


def _project(client):
    response = client.get("/v1/projects", headers=CEO)
    assert response.status_code == 200, response.text
    projects = [
        p
        for p in response.json()
        if p.get("name") == "AAO — Self Development" and p.get("state") == "ACTIVE"
    ]
    assert len(projects) <= 1, "disposable DB has ambiguous active Self Development projects"
    if projects:
        return projects[0]["id"]
    mandate = client.post(
        "/v1/mandates",
        headers=CEO,
        json={
            "title": "W2 rotation " + uuid4().hex,
            "objective": "Exercise role-owned publisher self-rotation",
        },
    )
    assert mandate.status_code == 201, mandate.text
    mandate_id = mandate.json()["id"]
    assert client.post(f"/v1/mandates/{mandate_id}/confirm", headers=CEO).status_code == 200
    project = client.post(
        "/v1/projects",
        headers=CEO,
        json={"name": "AAO — Self Development", "mandate_id": mandate_id},
    )
    assert project.status_code == 201, project.text
    return project.json()["id"]


def _publisher(client, project_id):
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    principal_id = f"aao-publisher-impl-{stamp}-{uuid4().hex[:8]}"
    issued = client.post(
        "/v1/principals/credentials",
        headers=CEO,
        json={"principal_id": principal_id, "kind": "AGENT"},
    )
    assert issued.status_code == 201, issued.text
    token = issued.json()["token"]
    expiry = (datetime.now(UTC) + timedelta(hours=7)).isoformat()
    for capability in ("project.read", "code.publish"):
        grant = client.post(
            f"/v1/projects/{project_id}/grants",
            headers=CEO,
            json={"principal_id": principal_id, "capability": capability, "expires_at": expiry},
        )
        assert grant.status_code == 201, grant.text
    return principal_id, token


def _me(client, token):
    return client.get("/v1/principals/me", headers={"X-Agent-Token": token})


@needs_pg
def test_role_owned_helper_rotates_end_to_end_without_pm_or_process_disclosure(
    monkeypatch, capsys, tmp_path
):
    from aao.principal_credentials import digest_token
    from scripts import rotate_w2_publisher_token as rotation

    client, connect = _pg_fixture(monkeypatch)
    project_id = _project(client)
    principal_id, old_token = _publisher(client, project_id)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    live = runtime / "aao-publisher.token"
    pending = runtime / ".aao-publisher.token.pending"
    live.write_text(old_token + "\n", encoding="utf-8")
    live.chmod(0o600)
    monkeypatch.setattr(rotation, "_paths", lambda _account: (live, pending))

    calls = []

    def api_request(base_url, path, *, method="GET", ceo_token=None, agent_token=None, body=None):
        assert ceo_token is None
        calls.append((path, method, agent_token is not None, body))
        response = client.request(
            method, path, headers={"X-Agent-Token": agent_token} if agent_token else {}, json=body
        )
        if response.status_code >= 400:
            from scripts.bootstrap_self_dev_agent import BootstrapError

            raise BootstrapError(
                f"AAO API rejected the bootstrap request (HTTP {response.status_code})"
            )
        return response.json()

    monkeypatch.setattr(rotation, "request_json", api_request)
    monkeypatch.setattr("sys.argv", ["rotate_w2_publisher_token.py", "--account", "aao-impl-codex"])
    assert rotation.main() == 0
    captured = capsys.readouterr()
    new_token = live.read_text(encoding="utf-8").strip()

    assert new_token != old_token
    assert stat.S_IMODE(live.stat().st_mode) == 0o600
    assert not pending.exists()
    assert _me(client, new_token).status_code == 200
    assert _me(client, old_token).status_code == 403
    # The old PM issuance route is absent; PM cannot obtain/relay this bearer.
    pm_response = client.post(
        f"/v1/projects/{project_id}/w2-publishers/aao-impl-codex/issue",
        headers={"X-Agent-Token": "not-a-real-pm-token"},
    )
    assert pm_response.status_code == 405  # no POST issuance route exists
    assert new_token not in pm_response.text
    assert new_token not in captured.out + captured.err + repr(calls)
    assert new_token not in " ".join(__import__("sys").argv)
    assert new_token not in repr(dict(os.environ))
    assert digest_token(new_token) not in repr(calls)
    assert calls[0][0] == "/v1/principals/me"
    assert calls[1][0] == "/v1/principals/me/w2-publisher/rotate"
    assert calls[2][0] == "/v1/principals/me/w2-publisher/rotate/confirm"
    assert all("credential.issue_publisher" not in path for path, *_ in calls)

    with connect() as db:
        expiry_rows = db.execute(
            "SELECT capability,expires_at FROM project_grants WHERE principal_id=%s",
            (principal_id,),
        ).fetchall()
        audit_rows = db.execute(
            "SELECT kind,details::text FROM events WHERE details->>'principal_id'=%s "
            "AND kind LIKE 'principal.w2_publisher.%%' ORDER BY created_at",
            (principal_id,),
        ).fetchall()
    assert {row[0] for row in expiry_rows} == {"project.read", "code.publish"}
    assert all(
        datetime.now(UTC) < row[1] <= datetime.now(UTC) + timedelta(hours=8) for row in expiry_rows
    )
    assert [row[0] for row in audit_rows] == [
        "principal.w2_publisher.rotation_pending",
        "principal.w2_publisher.rotated",
    ]
    assert all(
        new_token not in row[1] and digest_token(new_token) not in row[1] for row in audit_rows
    )


@needs_pg
def test_role_owned_helper_recovers_after_confirmation_before_atomic_install(monkeypatch, tmp_path):
    from scripts import rotate_w2_publisher_token as rotation

    client, _connect = _pg_fixture(monkeypatch)
    project_id = _project(client)
    principal_id, old_token = _publisher(client, project_id)
    staged = client.post(
        "/v1/principals/me/w2-publisher/rotate", headers={"X-Agent-Token": old_token}
    )
    assert staged.status_code == 200, staged.text
    new_token = staged.json()["token"]
    confirmed = client.post(
        "/v1/principals/me/w2-publisher/rotate/confirm",
        headers={"X-Agent-Token": new_token},
        json={"expected_principal_id": principal_id},
    )
    assert confirmed.status_code == 200, confirmed.text

    runtime = tmp_path / "runtime-recovery"
    runtime.mkdir(mode=0o700)
    live = runtime / "aao-publisher.token"
    pending = runtime / ".aao-publisher.token.pending"
    live.write_text(old_token + "\n", encoding="utf-8")
    live.chmod(0o600)
    pending.write_text(new_token + "\n", encoding="utf-8")
    pending.chmod(0o600)
    identity = pending.with_name(pending.name + ".identity")
    identity.write_text(
        json.dumps({"account": "aao-impl-codex", "principal_id": principal_id}) + "\n",
        encoding="utf-8",
    )
    identity.chmod(0o600)
    monkeypatch.setattr(rotation, "_paths", lambda _account: (live, pending))

    def api_request(_base_url, path, *, method="GET", agent_token=None, body=None, **_kwargs):
        response = client.request(
            method,
            path,
            headers={"X-Agent-Token": agent_token} if agent_token else {},
            json=body,
        )
        if response.status_code >= 400:
            from scripts.bootstrap_self_dev_agent import BootstrapError

            raise BootstrapError("AAO API request failed")
        return response.json()

    monkeypatch.setattr(rotation, "request_json", api_request)
    rotation.rotate("aao-impl-codex")
    assert live.read_text(encoding="utf-8") == new_token + "\n"
    assert not pending.exists()
    assert not identity.exists()
    assert _me(client, new_token).status_code == 200
    assert _me(client, old_token).status_code == 403
    assert principal_id.startswith("aao-publisher-impl-")


@needs_pg
def test_role_owned_helper_refuses_pending_token_bound_to_another_principal(monkeypatch, tmp_path):
    from scripts import rotate_w2_publisher_token as rotation

    client, _connect = _pg_fixture(monkeypatch)
    project_id = _project(client)
    principal_id, old_token = _publisher(client, project_id)
    staged = client.post(
        "/v1/principals/me/w2-publisher/rotate", headers={"X-Agent-Token": old_token}
    )
    assert staged.status_code == 200, staged.text
    new_token = staged.json()["token"]

    runtime = tmp_path / "runtime-mismatched-recovery"
    runtime.mkdir(mode=0o700)
    live = runtime / "aao-publisher.token"
    pending = runtime / ".aao-publisher.token.pending"
    live.write_text(old_token + "\n", encoding="utf-8")
    live.chmod(0o600)
    pending.write_text(new_token + "\n", encoding="utf-8")
    pending.chmod(0o600)
    identity = pending.with_name(pending.name + ".identity")
    identity.write_text(
        json.dumps(
            {
                "account": "aao-impl-codex",
                "principal_id": "aao-publisher-impl-20261102123456-deadbeef",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    identity.chmod(0o600)
    monkeypatch.setattr(rotation, "_paths", lambda _account: (live, pending))

    def api_request(_base_url, path, *, method="GET", agent_token=None, body=None, **_kwargs):
        response = client.request(
            method,
            path,
            headers={"X-Agent-Token": agent_token} if agent_token else {},
            json=body,
        )
        if response.status_code >= 400:
            from scripts.bootstrap_self_dev_agent import BootstrapError

            raise BootstrapError("AAO API request failed")
        return response.json()

    monkeypatch.setattr(rotation, "request_json", api_request)
    with pytest.raises(rotation.RotationError, match="another W2 principal"):
        rotation.rotate("aao-impl-codex")
    assert live.read_text(encoding="utf-8") == old_token + "\n"
    assert pending.read_text(encoding="utf-8") == new_token + "\n"
    assert principal_id != "aao-publisher-impl-20261102123456-deadbeef"


@needs_pg
def test_w2_confirmation_rejects_wrong_expected_principal_without_promoting(monkeypatch):
    from aao.principal_credentials import digest_token

    client, connect = _pg_fixture(monkeypatch)
    project_id = _project(client)
    principal_id, old_token = _publisher(client, project_id)
    staged = client.post(
        "/v1/principals/me/w2-publisher/rotate", headers={"X-Agent-Token": old_token}
    )
    assert staged.status_code == 200, staged.text
    new_token = staged.json()["token"]

    refused = client.post(
        "/v1/principals/me/w2-publisher/rotate/confirm",
        headers={"X-Agent-Token": new_token},
        json={"expected_principal_id": "aao-publisher-impl-other"},
    )
    assert refused.status_code == 403
    assert _me(client, old_token).status_code == 200
    assert _me(client, new_token).status_code == 403
    with connect() as db:
        row = db.execute(
            "SELECT token_digest,pending_token_digest FROM principal_credentials "
            "WHERE principal_id=%s",
            (principal_id,),
        ).fetchone()
    assert row == (digest_token(old_token), digest_token(new_token))


@needs_pg
def test_w2_confirmation_failure_rolls_back_promotion_and_preserves_old_bearer(monkeypatch):
    from aao.principal_credentials import digest_token

    client, connect = _pg_fixture(monkeypatch)
    project_id = _project(client)
    principal_id, old_token = _publisher(client, project_id)
    staged = client.post(
        "/v1/principals/me/w2-publisher/rotate", headers={"X-Agent-Token": old_token}
    )
    assert staged.status_code == 200, staged.text
    new_token = staged.json()["token"]
    with connect() as db:
        db.execute(
            "DELETE FROM project_grants WHERE principal_id=%s AND capability='code.publish'",
            (principal_id,),
        )
        db.commit()
    refused = client.post(
        "/v1/principals/me/w2-publisher/rotate/confirm",
        headers={"X-Agent-Token": new_token},
        json={"expected_principal_id": principal_id},
    )
    assert refused.status_code == 403
    assert _me(client, old_token).status_code == 200
    assert _me(client, new_token).status_code == 403
    with connect() as db:
        row = db.execute(
            "SELECT token_digest,pending_token_digest FROM principal_credentials "
            "WHERE principal_id=%s",
            (principal_id,),
        ).fetchone()
    assert row[0] == digest_token(old_token)
    assert row[1] == digest_token(new_token)


@needs_pg
def test_w2_pending_expiry_refuses_confirmation_without_revoking_old_token(monkeypatch):

    client, connect = _pg_fixture(monkeypatch)
    project_id = _project(client)
    principal_id, old_token = _publisher(client, project_id)
    staged = client.post(
        "/v1/principals/me/w2-publisher/rotate", headers={"X-Agent-Token": old_token}
    )
    assert staged.status_code == 200, staged.text
    new_token = staged.json()["token"]
    with connect() as db:
        db.execute(
            "UPDATE principal_credentials SET pending_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE principal_id=%s",
            (principal_id,),
        )
        db.commit()
    refused = client.post(
        "/v1/principals/me/w2-publisher/rotate/confirm",
        headers={"X-Agent-Token": new_token},
        json={"expected_principal_id": principal_id},
    )
    assert refused.status_code == 403
    assert _me(client, old_token).status_code == 200
    assert _me(client, new_token).status_code == 403
