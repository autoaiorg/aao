import pytest

from scripts import run_execution_lease_recovery_worker as worker


def test_one_shot_quarantines_expired_leases(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr("aao.execution_queue.quarantine_expired", lambda: calls.append(1) or 2)

    assert worker.run() == 0
    assert calls == [1]
    assert capsys.readouterr().out == "Quarantined 2 expired execution lease(s)\n"


def test_idle_one_shot_is_silent(monkeypatch, capsys):
    monkeypatch.setattr("aao.execution_queue.quarantine_expired", lambda: 0)

    assert worker.run() == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("poll_seconds", [0, -1, worker.MAX_POLL_SECONDS + 1])
def test_rejects_invalid_poll_interval(poll_seconds):
    with pytest.raises(ValueError, match="poll interval"):
        worker.run(watch=True, poll_seconds=poll_seconds)


def test_watch_reports_failure_without_database_details_and_stops(monkeypatch, capsys):
    calls = []

    def fail_with_sensitive_details():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("postgresql://secret@db/private")
        return 0

    class StopAfterPoll:
        def wait(self, _seconds):
            return len(calls) >= 2

        def set(self):
            pass

    monkeypatch.setattr("aao.execution_queue.quarantine_expired", fail_with_sensitive_details)
    monkeypatch.setattr(worker.threading, "Event", StopAfterPoll)

    assert worker.run(watch=True) == 0
    captured = capsys.readouterr()
    assert "Execution lease recovery failed (RuntimeError)" in captured.err
    assert "postgresql://secret" not in captured.err
    assert len(calls) == 2


def test_watch_uses_interruptible_poll(monkeypatch):
    waits = []

    class StopAfterPoll:
        def wait(self, seconds):
            waits.append(seconds)
            return True

    monkeypatch.setattr("aao.execution_queue.quarantine_expired", lambda: 0)
    monkeypatch.setattr(worker.threading, "Event", StopAfterPoll)
    assert worker.run(watch=True, poll_seconds=2.5) == 0
    assert waits == [2.5]


def test_one_shot_failure_returns_nonzero_without_database_details(monkeypatch, capsys):
    monkeypatch.setattr("aao.execution_queue.quarantine_expired", lambda: (_ for _ in ()).throw(
        RuntimeError("postgresql://secret@db/private")
    ))
    monkeypatch.setattr(worker.sys, "argv", ["worker", "--once"])

    assert worker.main() == 1
    captured = capsys.readouterr()
    assert "Execution lease recovery failed (RuntimeError)" in captured.err
    assert "postgresql://secret" not in captured.err
