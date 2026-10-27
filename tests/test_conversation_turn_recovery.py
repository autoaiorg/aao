from contextlib import contextmanager

from aao.conversation_turn_recovery import (
    RecoveryConfiguration,
    claim_expired_turn,
    configuration_error,
)


def test_recovery_requires_explicit_enable_and_complete_provider_configuration():
    base = {
        "AAO_CONVERSATION_RECOVERY_ENABLED": "true",
        "AAO_CONVERSATION_PROVIDER": "openai-compatible",
        "AAO_CONVERSATION_MODEL": "model-1",
        "AAO_CONVERSATION_API_URL": "https://provider.invalid/v1/chat/completions",
        "AAO_CONVERSATION_API_KEY": "not-a-real-secret",
    }
    assert configuration_error({**base, "AAO_CONVERSATION_RECOVERY_ENABLED": "false"}) == "DISABLED"
    assert configuration_error({key: value for key, value in base.items()
                                if key != "AAO_CONVERSATION_API_KEY"}) == "CONFIGURATION_MISSING"
    assert configuration_error(base) is None


def test_claim_requires_expired_pending_turn_and_matching_provider_model():
    class FakeDB:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params=()):
            self.calls.append((sql, params))
            self.rowcount = 1
            return self

        def fetchone(self):
            return ("turn-1", "conversation-1", "project-1", "key-1", "message-1",
                    "openai-compatible", "model-1", "hello")

    db = FakeDB()
    config = RecoveryConfiguration("openai-compatible", "model-1")
    claim = claim_expired_turn(
        db, config, lease_owner="owner-1", host_id="test-host", fence_epoch=7
    )
    assert claim["turn_id"] == "turn-1"
    select_sql, select_params = db.calls[0]
    update_sql, update_params = db.calls[1]
    normalized = " ".join(select_sql.split())
    assert "t.state='PENDING'" in normalized
    assert "t.lease_expires_at <= clock_timestamp()" in normalized
    assert "FOR UPDATE OF t SKIP LOCKED" in normalized
    assert "t.provider=%s AND t.model=%s" in normalized
    assert select_params == ("openai-compatible", "model-1")
    assert "lease_owner=%s" in update_sql and "lease_host_id=%s" in update_sql
    assert "lease_expires_at <= clock_timestamp()" in update_sql
    assert update_params == ("owner-1", "test-host", 7, 90, "turn-1")


def test_claim_does_not_call_provider_or_touch_database_when_disabled(monkeypatch):
    from aao import conversation_provider
    from aao import conversation_turn_recovery as recovery

    class NoDatabase:
        @contextmanager
        def __call__(self):
            raise AssertionError("database must not be touched when recovery is disabled")
            yield

    monkeypatch.setattr(recovery, "tx", NoDatabase())
    monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: (_ for _ in ()).throw(
        AssertionError("provider must not be called when recovery is disabled")
    ))
    result = recovery.recover_one_turn({"AAO_CONVERSATION_RECOVERY_ENABLED": "false"})
    assert result == {"status": "DISABLED"}


def test_recovery_configuration_requires_recorded_provider_and_model_match():
    config = RecoveryConfiguration("openai-compatible", "model-1")
    assert config.matches("openai-compatible", "model-1")
    assert not config.matches("other-provider", "model-1")
    assert not config.matches("openai-compatible", "model-2")


def test_recovery_no_matching_recorded_provider_model_never_calls_provider(monkeypatch):
    from aao import conversation_provider
    from aao import conversation_turn_recovery as recovery

    class EmptyDB:
        def execute(self, sql, *_args, **_kwargs):
            self.sql = sql
            return self

        def fetchone(self):
            return (False,) if "SELECT EXISTS" in self.sql else None

    @contextmanager
    def empty_tx():
        yield EmptyDB()

    monkeypatch.setattr(recovery, "tx", empty_tx)
    monkeypatch.setattr(recovery, "active_host_fence_epoch", lambda *_args: 1)
    monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: (_ for _ in ()).throw(
        AssertionError("provider must not be called without a matching expired turn")
    ))
    env = {
        "AAO_CONVERSATION_RECOVERY_ENABLED": "true",
        "AAO_CONVERSATION_PROVIDER": "openai-compatible",
        "AAO_CONVERSATION_MODEL": "model-1",
        "AAO_CONVERSATION_API_URL": "https://provider.invalid/v1/chat/completions",
        "AAO_CONVERSATION_API_KEY": "not-a-real-secret",
    }
    assert recovery.recover_one_turn(env) == {"status": "IDLE"}


def test_expired_turn_with_other_recorded_provider_model_is_not_claimed(monkeypatch):
    from aao import conversation_provider
    from aao import conversation_turn_recovery as recovery

    class MismatchDB:
        def execute(self, sql, *_args, **_kwargs):
            self.sql = sql
            return self

        def fetchone(self):
            return (True,) if "SELECT EXISTS" in self.sql else None

    @contextmanager
    def mismatch_tx():
        yield MismatchDB()

    monkeypatch.setattr(recovery, "tx", mismatch_tx)
    monkeypatch.setattr(recovery, "active_host_fence_epoch", lambda *_args: 1)
    monkeypatch.setattr(conversation_provider, "stream_reply", lambda _messages: (_ for _ in ()).throw(
        AssertionError("mismatched provider/model must never be called")
    ))
    env = {
        "AAO_CONVERSATION_RECOVERY_ENABLED": "true",
        "AAO_CONVERSATION_PROVIDER": "openai-compatible",
        "AAO_CONVERSATION_MODEL": "model-1",
        "AAO_CONVERSATION_API_URL": "https://provider.invalid/v1/chat/completions",
        "AAO_CONVERSATION_API_KEY": "not-a-real-secret",
    }
    assert recovery.recover_one_turn(env) == {"status": "CONFIGURATION_MISMATCH"}


def test_response_persistence_is_fenced_and_rolls_back_on_lease_loss(monkeypatch):
    from aao import conversation_turn_recovery as recovery

    calls = []
    turn = {"turn_id": "turn-1", "conversation_id": "conversation-1",
            "user_message_id": "message-1", "lease_owner": "owner-1",
            "lease_host_id": "test-host", "lease_fence_epoch": 1}
    config = recovery.RecoveryConfiguration("openai-compatible", "model-1")

    class SuccessfulDB:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            self.rowcount = 1
            return self

    @contextmanager
    def success_tx():
        yield SuccessfulDB()

    monkeypatch.setattr(recovery, "tx", success_tx)
    monkeypatch.setattr(recovery, "active_host_fence_epoch", lambda *_args: 1)
    assert recovery._finish_turn(turn, "Recovered.", config)
    assert "INSERT INTO project_conversation_messages" in calls[0][0]
    assert "WHERE id=%s AND state='PENDING' AND lease_owner=%s AND lease_host_id=%s" in calls[1][0]
    assert calls[1][1][1:] == ("turn-1", "owner-1", "test-host", 1)
    assert any("INSERT INTO events" in sql for sql, _ in calls)

    class LostLeaseDB:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            self.rowcount = 0
            return self

    @contextmanager
    def lost_tx():
        try:
            yield LostLeaseDB()
        except recovery.TurnLeaseLost:
            calls.append(("ROLLBACK", ()))
            raise

    monkeypatch.setattr(recovery, "tx", lost_tx)
    monkeypatch.setattr(recovery, "active_host_fence_epoch", lambda *_args: 1)
    calls.clear()
    try:
        recovery._finish_turn(turn, "Must not persist.", config)
    except recovery.TurnLeaseLost:
        pass
    else:
        raise AssertionError("lost lease must abort the transaction")
    assert len(calls) == 3
    assert calls[-1][0] == "ROLLBACK"
    assert not any("INSERT INTO events" in sql for sql, _ in calls)


def test_provider_failure_is_persisted_only_by_current_lease_owner(monkeypatch):
    from aao import conversation_turn_recovery as recovery

    calls = []

    class FakeDB:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            self.rowcount = 1
            return self

    @contextmanager
    def fake_tx():
        yield FakeDB()

    monkeypatch.setattr(recovery, "tx", fake_tx)
    monkeypatch.setattr(recovery, "active_host_fence_epoch", lambda *_args: 1)
    turn = {"turn_id": "turn-1", "conversation_id": "conversation-1",
            "user_message_id": "message-1", "lease_owner": "owner-1",
            "lease_host_id": "test-host", "lease_fence_epoch": 1}
    assert recovery._fail_turn(turn, "PROVIDER_UNAVAILABLE")
    update, audit = calls
    assert "state='FAILED'" in update[0]
    assert "WHERE id=%s AND state='PENDING' AND lease_owner=%s AND lease_host_id=%s" in update[0]
    assert update[1] == ("PROVIDER_UNAVAILABLE", "turn-1", "owner-1", "test-host", 1)
    assert "INSERT INTO events" in audit[0]
    assert "PROVIDER_UNAVAILABLE" in audit[1][3]


def test_recover_one_turn_builds_prompt_and_persists_success(monkeypatch):
    from aao import conversation_provider
    from aao import conversation_turn_recovery as recovery

    turn = {
        "turn_id": "turn-1", "conversation_id": "conversation-1", "project_id": "project-1",
        "idempotency_key": "key-1", "user_message_id": "message-1", "body": "Question",
        "lease_owner": "owner-1", "lease_host_id": "integration-test-host",
        "lease_fence_epoch": 1,
    }

    class FakeDB:
        def execute(self, sql, *_args, **_kwargs):
            assert "SELECT sender,body" in sql or "INSERT INTO events" in sql
            return self

        def fetchall(self):
            return [("CEO", "Question")]

    @contextmanager
    def fake_tx():
        yield FakeDB()

    prompt = [{"role": "user", "content": "Question"}]
    provider_prompts = []
    finished = []
    monkeypatch.setattr(recovery, "tx", fake_tx)
    monkeypatch.setattr(recovery, "active_host_fence_epoch", lambda *_args: 1)
    monkeypatch.setattr(recovery, "claim_expired_turn", lambda *_args, **_kwargs: turn)
    monkeypatch.setattr(recovery, "build_conversation_prompt", lambda *_args: prompt)
    monkeypatch.setattr(conversation_provider, "stream_reply", lambda messages: (
        provider_prompts.append(messages) or iter(["Recovered", " answer"])
    ))
    monkeypatch.setattr(recovery, "_finish_turn", lambda claimed, answer, _config: (
        finished.append((claimed, answer)) or True
    ))
    env = {
        "AAO_CONVERSATION_RECOVERY_ENABLED": "true",
        "AAO_CONVERSATION_PROVIDER": "openai-compatible",
        "AAO_CONVERSATION_MODEL": "model-1",
        "AAO_CONVERSATION_API_URL": "https://provider.invalid/v1/chat/completions",
        "AAO_CONVERSATION_API_KEY": "not-a-real-secret",
    }
    assert recovery.recover_one_turn(env) == {"status": "COMPLETED", "turn_id": "turn-1"}
    assert provider_prompts == [prompt]
    assert finished == [(turn, "Recovered answer")]
