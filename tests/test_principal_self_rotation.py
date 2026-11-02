"""AGENT self-rotation (two-phase, pending token with TTL)."""

import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aao.principal_credentials import digest_token

needs_pg = pytest.mark.skipif(
    not os.getenv("AAO_TEST_POSTGRES_URL") or os.getenv("AAO_TEST_DB_DISPOSABLE") != "yes",
    reason="Explicit disposable PostgreSQL database required",
)
CEO = {"X-CEO-Token": "self-rotation-ceo"}


def _forbid_db(monkeypatch):
    from aao import principal_credentials, work_management_api

    def forbidden(*_a, **_k):
        raise AssertionError("must be denied before database access")

    monkeypatch.setattr(principal_credentials, "connect_postgres", forbidden)
    monkeypatch.setattr(work_management_api, "tx", forbidden)


@pytest.mark.parametrize("path", ["/v1/principals/me/rotate", "/v1/principals/me/rotate/confirm"])
@pytest.mark.parametrize(
    "env,headers",
    [
        ("development", {}),
        ("production", {"X-Agent-Token": "not-a-real-token"}),
    ],
)
def test_self_rotation_fails_closed_before_database(monkeypatch, path, env, headers):
    from aao.work_management_api import app

    monkeypatch.setenv("AAO_ENV", env)
    _forbid_db(monkeypatch)
    with TestClient(app) as client:
        assert client.post(path, headers=headers).status_code == 403


@pytest.fixture
def pg(monkeypatch):
    monkeypatch.setenv("AAO_POSTGRES_URL", os.environ["AAO_TEST_POSTGRES_URL"])
    monkeypatch.setenv("AAO_ENV", "test")
    monkeypatch.setenv("AAO_CEO_TOKEN", CEO["X-CEO-Token"])
    from aao.postgresql_connection import connect_postgres
    from aao.work_management_api import app

    with TestClient(app) as client:
        yield client, connect_postgres


def _issue(client, kind="AGENT"):
    principal = f"aao-pm-coordinator-test-{uuid4()}"
    response = client.post(
        "/v1/principals/credentials", headers=CEO, json={"principal_id": principal, "kind": kind}
    )
    assert response.status_code == 201, response.text
    return principal, response.json()["token"]


def _me(client, token):
    return client.get("/v1/principals/me", headers={"X-Agent-Token": token}).status_code


def _rotate(client, token):
    return client.post("/v1/principals/me/rotate", headers={"X-Agent-Token": token})


def _confirm(client, token):
    return client.post("/v1/principals/me/rotate/confirm", headers={"X-Agent-Token": token})


@needs_pg
def test_rotate_then_confirm_promotes_new_token_and_kills_old(pg):
    client, connect = pg
    principal, old = _issue(client)
    response = _rotate(client, old)
    assert response.status_code == 200, response.text
    new = response.json()["token"]
    assert new != old and response.json()["principal_id"] == principal
    for digest in (digest_token(old), digest_token(new)):
        assert digest not in response.text
    # Old token still valid; pending token authenticates nothing but confirm.
    assert _me(client, old) == 200
    assert _me(client, new) == 403
    # Confirm with the old token is refused.
    assert _confirm(client, old).status_code == 403

    confirmed = _confirm(client, new)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"principal_id": principal, "kind": "AGENT", "rotated": True}
    for digest in (digest_token(old), digest_token(new)):
        assert digest not in confirmed.text
    assert _me(client, new) == 200
    assert _me(client, old) == 403
    assert _rotate(client, old).status_code == 403
    assert _confirm(client, new).status_code == 403  # pending already consumed

    with connect() as db:
        row = db.execute(
            "SELECT kind,enabled,pending_token_digest,pending_expires_at "
            "FROM principal_credentials WHERE principal_id=%s",
            (principal,),
        ).fetchone()
        events = db.execute(
            "SELECT kind,details FROM events WHERE details->>'principal_id'=%s "
            "AND kind LIKE 'principal.credential.%%' ORDER BY created_at",
            (principal,),
        ).fetchall()
    assert row == ("AGENT", True, None, None)
    kinds = [kind for kind, _ in events]
    assert kinds == [
        "principal.credential.issued",
        "principal.credential.rotation_pending",
        "principal.credential.rotated",
    ]
    blob = json.dumps([details for _, details in events])
    for secret in (old, new, digest_token(old), digest_token(new)):
        assert secret not in blob


@needs_pg
def test_confirm_after_ttl_fails_and_old_token_survives(pg):
    client, connect = pg
    _, old = _issue(client)
    new = _rotate(client, old).json()["token"]
    with connect() as db:
        db.execute(
            "UPDATE principal_credentials SET pending_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE pending_token_digest=%s",
            (digest_token(new),),
        )
    assert _confirm(client, new).status_code == 403
    assert _me(client, old) == 200
    assert _me(client, new) == 403


@needs_pg
def test_second_rotate_replaces_pending(pg):
    client, _ = pg
    _, old = _issue(client)
    first = _rotate(client, old).json()["token"]
    second = _rotate(client, old).json()["token"]
    assert _confirm(client, first).status_code == 403
    assert _confirm(client, second).status_code == 200
    assert _me(client, second) == 200


@needs_pg
def test_rotate_rejects_wrong_disabled_and_auditor(pg):
    client, _ = pg
    assert _rotate(client, "not-a-real-token").status_code == 403
    principal, token = _issue(client)
    pending = _rotate(client, token).json()["token"]
    assert client.post(f"/v1/principals/{principal}/revoke", headers=CEO).status_code == 200
    assert _rotate(client, token).status_code == 403
    assert _confirm(client, pending).status_code == 403
    _, auditor = _issue(client, kind="AUDITOR")
    assert _rotate(client, auditor).status_code == 403


@needs_pg
def test_ceo_rotation_discards_pending_self_rotation(pg):
    client, _ = pg
    principal, token = _issue(client)
    pending = _rotate(client, token).json()["token"]
    response = client.post(f"/v1/principals/{principal}/rotate", headers=CEO)
    assert response.status_code == 200
    assert _confirm(client, pending).status_code == 403
    assert _me(client, response.json()["token"]) == 200
