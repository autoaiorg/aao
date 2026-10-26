"""Tests for Host Fencing, Dual-Host Exclusivity and Anti-Split-Brain Protection.

Validates finding A-07:
1. Demonstrates real exclusivity between two hosts (Host A and Host B).
2. Proves that fencing Host A targets only Host A credentials and leases without blanket revocation.
3. Proves that Host A is strictly prevented from executing external effects post-cutover.
4. Verifies network disconnection / communication recovery scenarios.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from unittest.mock import MagicMock

import psycopg
import pytest

from aao.backup import apply_host_fencing, ensure_host_worker_registry, register_host_worker
from aao.external_effect_registry import propose as propose_external_effect
from aao.postgresql_connection import connect_postgres


def test_apply_host_fencing_targeted_queries():
    """Unit test: verify SQL execution targets only specific workers without blanket updates."""
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [("worker-host-a",)]
    actions = apply_host_fencing(mock_db, host_identifier="host-a", worker_ids=["worker-host-a"])

    assert any("worker-host-a" in a for a in actions)
    # Check that update targeted ANY(%s) with target_workers, not WHERE kind = 'AGENT'
    calls = [str(c) for c in mock_db.execute.mock_calls]
    assert any("principal_id = ANY" in c for c in calls)
    assert not any("WHERE kind = 'AGENT' AND enabled = true" in c for c in calls)
    assert any("worker_id = ANY" in c for c in calls)
    assert any("host.fenced" in c for c in calls)


def test_host_worker_bindings_and_automatic_fencing():
    """Unit test: verify host_worker_bindings registry lookup and targeted fencing without explicit worker_ids."""
    mock_db = MagicMock()
    # Mock finding worker-node-1 bound to node-1
    mock_db.execute.return_value.fetchall.return_value = [("worker-node-1",)]

    register_host_worker(mock_db, "node-1", "worker-node-1")
    # Verify table schema ensured and worker registered
    calls = [str(c) for c in mock_db.execute.mock_calls]
    assert any("host_worker_bindings" in c for c in calls)

    # Now fence node-1 without passing worker_ids
    mock_db.reset_mock()
    mock_db.execute.return_value.fetchall.return_value = [("worker-node-1",)]
    actions = apply_host_fencing(mock_db, host_identifier="node-1")

    assert any("marked host 'node-1' bindings as FENCED" in a for a in actions)
    assert any("worker-node-1" in a for a in actions)
    fencing_calls = [str(c) for c in mock_db.execute.mock_calls]
    assert any("UPDATE host_worker_bindings" in c and "FENCED" in c for c in fencing_calls)
    assert any("principal_id = ANY" in c for c in fencing_calls)


def test_dual_host_isolation_unit():
    """Unit test: verify that Host A and Host B workers are segregated and Host B is never touched."""
    mock_db = MagicMock()
    # node-a only has worker-a
    mock_db.execute.return_value.fetchall.return_value = [("worker-a",)]

    actions = apply_host_fencing(mock_db, host_identifier="node-a")
    calls = [str(c) for c in mock_db.execute.mock_calls]

    # Verify worker-a was revoked
    assert any("revoked credentials for host workers: ['worker-a']" in a for a in actions)
    # Verify no blanket updates were performed
    assert not any("worker-b" in c for c in calls)
    assert not any("WHERE kind = 'AGENT' AND enabled = true" in c for c in calls)


def test_external_effect_propose_rejects_fenced_host_unit():
    """Unit test: verify propose() queries host_worker_bindings and raises EffectConflict if fenced (Finding A-07)."""
    from unittest.mock import patch

    from aao.external_effect_registry import EffectConflict, propose

    mock_db = MagicMock()

    def fake_execute(query, params=None):
        m = MagicMock()
        q = str(query)
        if "FROM host_worker_bindings" in q:
            m.fetchone.return_value = ("host-a", "FENCED")
        elif "FROM principal_credentials" in q:
            m.fetchone.return_value = ("worker-host-a",)
        return m

    mock_db.execute.side_effect = fake_execute

    with patch("aao.external_effect_registry.connect_postgres") as mock_conn, \
         patch("aao.principal_credentials.authenticate_in_transaction", return_value="worker-host-a"):
        mock_conn.return_value.__enter__.return_value = mock_db

        with pytest.raises(EffectConflict, match="bound to fenced host"):
            propose(
                execution_id="exec-1",
                worker_id="worker-host-a",
                lease_token="lease-1",
                agent_credential="cred-1",
                idempotency_key="key-1",
                capability="effect.propose",
                request={"action": "test"},
            )


@pytest.fixture
def clean_postgres(monkeypatch):
    """Ensure clean PostgreSQL tables before and after test."""
    monkeypatch.setenv("AAO_ENV", "test")
    try:
        with connect_postgres() as db:
            db.execute("SELECT 1")
    except (RuntimeError, OSError, psycopg.Error):
        pytest.skip("PostgreSQL not accessible in test environment")

    cleanup_sql = """
        DELETE FROM events WHERE kind IN ('host.fenced', 'external.effect.proposed');
        DELETE FROM external_effects WHERE execution_id IN (
            SELECT id FROM execution_queue WHERE project_id IN (
                '00000000-0000-0000-0000-0000000000a1',
                '00000000-0000-0000-0000-0000000000b1'
            )
        );
        DELETE FROM execution_journal WHERE execution_id IN (
            SELECT id FROM execution_queue WHERE project_id IN (
                '00000000-0000-0000-0000-0000000000a1',
                '00000000-0000-0000-0000-0000000000b1'
            )
        );
        DELETE FROM execution_queue WHERE project_id IN (
            '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000b1'
        );
        DELETE FROM work_items WHERE project_id IN (
            '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000b1'
        );
        DELETE FROM project_grants WHERE project_id IN (
            '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000b1'
        );
        DELETE FROM host_worker_bindings WHERE worker_id IN (
            'worker-host-a',
            'worker-host-b',
            'unrelated-agent'
        );
        DELETE FROM projects WHERE id IN (
            '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000b1'
        );
        DELETE FROM mandates WHERE id IN (
            '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000b1'
        );
        DELETE FROM principal_credentials WHERE principal_id IN (
            'worker-host-a',
            'worker-host-b',
            'unrelated-agent'
        );
    """
    with connect_postgres() as db:
        ensure_host_worker_registry(db)
        db.execute(cleanup_sql)
        db.commit()
    yield
    with connect_postgres() as db:
        ensure_host_worker_registry(db)
        db.execute(cleanup_sql)
        db.commit()


def _setup_dual_host_environment(db):
    """Register distinct credentials and active work claims for Host A and Host B."""
    token_a = "secret-token-host-a"
    token_b = "secret-token-host-b"
    token_unrelated = "secret-token-unrelated"

    hash_a = hashlib.sha256(token_a.encode()).hexdigest()
    hash_b = hashlib.sha256(token_b.encode()).hexdigest()
    hash_unrelated = hashlib.sha256(token_unrelated.encode()).hexdigest()

    # Register principal credentials
    db.execute(
        """
        INSERT INTO principal_credentials (principal_id, kind, token_digest, enabled)
        VALUES
          ('worker-host-a', 'AGENT', %s, true),
          ('worker-host-b', 'AGENT', %s, true),
          ('unrelated-agent', 'AGENT', %s, true)
        ON CONFLICT (principal_id) DO UPDATE SET enabled = true, token_digest = EXCLUDED.token_digest
        """,
        (hash_a, hash_b, hash_unrelated),
    )

    # Register projects
    proj_a = "00000000-0000-0000-0000-0000000000a1"
    proj_b = "00000000-0000-0000-0000-0000000000b1"
    db.execute(
        """
        INSERT INTO mandates (id, title, objective, status)
        VALUES
          (%s, 'Mandate A', 'Objective A', 'CONFIRMED'),
          (%s, 'Mandate B', 'Objective B', 'CONFIRMED')
        ON CONFLICT (id) DO NOTHING;
        """,
        (proj_a, proj_b),
    )
    db.execute(
        """
        INSERT INTO projects (id, mandate_id, name, state)
        VALUES
          (%s, %s, 'Project A', 'ACTIVE'),
          (%s, %s, 'Project B', 'ACTIVE')
        ON CONFLICT (id) DO NOTHING;
        """,
        (proj_a, proj_a, proj_b, proj_b),
    )

    # Register explicit host-worker bindings
    register_host_worker(db, "host-a", "worker-host-a")
    register_host_worker(db, "host-b", "worker-host-b")

    # Register project grants for effect proposal
    db.execute(
        """
        INSERT INTO project_grants (principal_id, project_id, capability)
        VALUES
          ('worker-host-a', %s, 'effect.propose'),
          ('worker-host-b', %s, 'effect.propose')
        ON CONFLICT DO NOTHING;
        """,
        (proj_a, proj_b),
    )

    # Work item and claim for Host A
    work_a = str(uuid.uuid4())
    exec_a = str(uuid.uuid4())
    lease_token_a = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO work_items (id, project_id, title, status, author_id, acceptance_criteria)
        VALUES (%s, %s, 'Work item A', 'IN_PROGRESS', 'worker-host-a', '[]'::jsonb);
        """,
        (work_a, proj_a),
    )
    db.execute(
        """
        INSERT INTO execution_queue (id, work_id, project_id, status, input_json, lease_token, worker_id, lease_expires_at, project_state_generation)
        VALUES (%s, %s, %s, 'RUNNING', '{}'::jsonb, %s, 'worker-host-a', clock_timestamp() + INTERVAL '1 hour', 0);
        """,
        (exec_a, work_a, proj_a, lease_token_a),
    )

    # Work item and claim for Host B
    work_b = str(uuid.uuid4())
    exec_b = str(uuid.uuid4())
    lease_token_b = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO work_items (id, project_id, title, status, author_id, acceptance_criteria)
        VALUES (%s, %s, 'Work item B', 'IN_PROGRESS', 'worker-host-b', '[]'::jsonb);
        """,
        (work_b, proj_b),
    )
    db.execute(
        """
        INSERT INTO execution_queue (id, work_id, project_id, status, input_json, lease_token, worker_id, lease_expires_at, project_state_generation)
        VALUES (%s, %s, %s, 'RUNNING', '{}'::jsonb, %s, 'worker-host-b', clock_timestamp() + INTERVAL '1 hour', 0);
        """,
        (exec_b, work_b, proj_b, lease_token_b),
    )
    db.commit()

    return {
        "token_a": token_a,
        "token_b": token_b,
        "exec_a": exec_a,
        "exec_b": exec_b,
        "lease_token_a": lease_token_a,
        "lease_token_b": lease_token_b,
        "proj_a": proj_a,
        "proj_b": proj_b,
    }


def test_targeted_host_fencing_avoids_blanket_revocation(clean_postgres):
    """Prove that fencing Host A disables only Host A without affecting Host B or unrelated agents."""
    with connect_postgres() as db:
        env = _setup_dual_host_environment(db)

        # Apply targeted fencing for Host A
        actions = apply_host_fencing(db, host_identifier="host-a")
        assert any("marked host 'host-a' bindings as FENCED" in a for a in actions)

        # Verify credentials status
        rows = dict(db.execute("SELECT principal_id, enabled FROM principal_credentials").fetchall())
        assert rows["worker-host-a"] is False, "Host A worker credentials must be disabled"
        assert rows["worker-host-b"] is True, "Host B worker credentials must remain active"
        assert rows["unrelated-agent"] is True, "Unrelated agents must remain completely unaffected"

        # Verify task status
        exec_rows = dict(db.execute("SELECT id::text, status FROM execution_queue").fetchall())
        assert exec_rows[env["exec_a"]] == "FAILED", "Host A task must be failed with lease revoked"
        assert exec_rows[env["exec_b"]] == "RUNNING", "Host B task must remain running without disturbance"


def test_old_host_cannot_execute_external_effects_post_cutover(clean_postgres):
    """Prove that an old fenced host cannot produce external effects after cutover."""
    from aao.external_effect_registry import EffectConflict
    with connect_postgres() as db:
        env = _setup_dual_host_environment(db)

        # Host A is fenced during migration / cutover
        apply_host_fencing(db, host_identifier="host-a")
        db.commit()

        # Old Host A attempts to propose an external effect with its credentials and lease
        with pytest.raises(EffectConflict) as exc_info:
            propose_external_effect(
                execution_id=env["exec_a"],
                worker_id="worker-host-a",
                lease_token=env["lease_token_a"],
                agent_credential=env["token_a"],
                idempotency_key=str(uuid.uuid4()),
                capability="effect.propose",
                request={"branch": "feat/old-host-attempt"},
            )
        assert any(term in str(exc_info.value).lower() for term in ("fenced", "revoked", "credential", "lease", "conflict"))

        # Meanwhile, Host B remains fully authorized and can propose external effects
        res = propose_external_effect(
            execution_id=env["exec_b"],
            worker_id="worker-host-b",
            lease_token=env["lease_token_b"],
            agent_credential=env["token_b"],
            idempotency_key=str(uuid.uuid4()),
            capability="effect.propose",
            request={"branch": "feat/host-b-authorized"},
        )
        assert res is not None
        assert "id" in res


def test_network_partition_and_zero_duplicate_effects(clean_postgres):
    """Prove that after cutover fencing and network reconnection, old host cannot create duplicate effects."""
    from aao.external_effect_registry import EffectConflict
    with connect_postgres() as db:
        env = _setup_dual_host_environment(db)
        # Apply cutover fencing to host-a
        apply_host_fencing(db, host_identifier="host-a")
        db.commit()

        # Old host-a attempts to propose an effect after network recovery
        shared_key = f"idemp-shared-{uuid.uuid4()}"
        with pytest.raises(EffectConflict):
            propose_external_effect(
                execution_id=env["exec_a"],
                worker_id="worker-host-a",
                lease_token=env["lease_token_a"],
                agent_credential=env["token_a"],
                idempotency_key=shared_key,
                capability="effect.propose",
                request={"action": "publish_pr", "candidate": "sha-test"},
            )

        # Host B proposes the effect successfully
        res = propose_external_effect(
            execution_id=env["exec_b"],
            worker_id="worker-host-b",
            lease_token=env["lease_token_b"],
            agent_credential=env["token_b"],
            idempotency_key=shared_key,
            capability="effect.propose",
            request={"action": "publish_pr", "candidate": "sha-test"},
        )
        assert res is not None

        # Verify exact single effect recorded in DB (zero duplicates)
        count = db.execute("SELECT count(*) FROM external_effects WHERE idempotency_key = %s", (shared_key,)).fetchone()[0]
        assert count == 1


def test_fencing_audit_event_recorded(clean_postgres):
    """Verify that an explicit host.fenced audit event is recorded in the events table."""
    with connect_postgres() as db:
        _setup_dual_host_environment(db)
        apply_host_fencing(db, host_identifier="node-01.dc1", worker_ids=["worker-host-a"])

        event = db.execute(
            "SELECT kind, details FROM events WHERE kind = 'host.fenced' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert event is not None
        assert event[0] == "host.fenced"
        details = event[1] if isinstance(event[1], dict) else json.loads(event[1])
        assert details["host"] == "node-01.dc1"
        assert "worker-host-a" in details["fenced_workers"]
