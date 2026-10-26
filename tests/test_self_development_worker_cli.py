import io
import json
import os
import stat
import threading

import pytest

from scripts import run_self_development_worker as worker


def make_runtime(tmp_path, *, mode=0o700, token_mode=0o600):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=mode)
    runtime.chmod(mode)
    token_path = runtime / worker.AGENT_TOKEN_NAME
    token_path.write_text("agent-token-fixture\n", encoding="utf-8")
    token_path.chmod(token_mode)
    return runtime, token_path


def test_worker_reads_agent_token_only_from_private_runtime_file(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)

    assert worker._read_agent_token() == "agent-token-fixture"


@pytest.mark.parametrize("runtime_mode,token_mode", [(0o750, 0o600), (0o700, 0o640)])
def test_worker_rejects_non_private_runtime_or_token(tmp_path, monkeypatch,
                                                    runtime_mode, token_mode):
    runtime, _ = make_runtime(tmp_path, mode=runtime_mode, token_mode=token_mode)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)

    with pytest.raises(worker.WorkerError, match="private|mode 0600"):
        worker._read_agent_token()


def test_worker_runs_one_authorized_queue_item_without_logging_token(tmp_path, monkeypatch,
                                                                     capsys):
    runtime, _ = make_runtime(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)
    monkeypatch.setattr(
        "aao.inert_execution_worker.run_one",
        lambda principal, token, *, project_id, seconds: (
            {"status": "SUCCEEDED", "execution_id": "exec-1"}
            if (principal, token, project_id, seconds)
            == ("agent-1", "agent-token-fixture", "project-1", worker.MAX_LEASE_SECONDS)
            else pytest.fail("worker arguments did not match the scoped invocation")
        ),
    )
    monkeypatch.setattr(worker.sys, "argv", ["worker", "--project-id", "project-1",
                                             "--principal-id", "agent-1"])

    assert worker.main() == 0
    output = capsys.readouterr().out
    assert "Execution exec-1: SUCCEEDED" in output
    assert "agent-token-fixture" not in output


def test_worker_does_not_downgrade_production_environment(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)
    monkeypatch.setenv("AAO_ENV", "production")
    monkeypatch.setenv("AAO_ENV_FILE", ".env.local")
    monkeypatch.setenv("AAO_TEST_HOST_ID", "attacker-controlled-test-host")
    observed = {}

    def fake_run_one(*_args, **_kwargs):
        observed["environment"] = os.environ["AAO_ENV"]
        observed["env_file"] = os.environ.get("AAO_ENV_FILE")
        return {"status": "SUCCEEDED", "execution_id": "exec-production"}

    monkeypatch.setattr("aao.inert_execution_worker.run_one", fake_run_one)
    result = worker.run("project-1", "agent-1")

    assert result["status"] == "SUCCEEDED"
    assert observed == {"environment": "production", "env_file": None}


def test_worker_token_file_must_be_regular_and_owned(tmp_path, monkeypatch):
    runtime, token_path = make_runtime(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)
    assert stat.S_ISREG(token_path.stat().st_mode)
    token_path.unlink()
    token_path.symlink_to(runtime / "missing")

    with pytest.raises(worker.WorkerError, match="symbolic link"):
        worker._read_agent_token()


def test_worker_error_output_does_not_include_exception_details(tmp_path, monkeypatch, capsys):
    runtime, _ = make_runtime(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)
    monkeypatch.setattr(
        "aao.inert_execution_worker.run_one",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("sensitive detail")),
    )
    monkeypatch.setattr(worker.sys, "argv", ["worker", "--project-id", "p",
                                             "--principal-id", "a"])

    assert worker.main() == 1
    output = capsys.readouterr().err
    assert "RuntimeError" in output
    assert "sensitive detail" not in output


def test_watch_mode_repeats_until_stop_and_suppresses_idle_output(monkeypatch, capsys):
    stop = threading.Event()
    calls = []
    waits = []

    def run_once(project_id, principal_id):
        calls.append((project_id, principal_id))
        if len(calls) == 1:
            return {"status": "IDLE"}
        stop.set()
        return {"status": "SUCCEEDED", "execution_id": "exec-2"}

    monkeypatch.setattr(worker, "run", run_once)
    assert (
        worker.run_watch(
            "project-1",
            "agent-1",
            poll_interval_seconds=3,
            stop_event=stop,
            wait=waits.append,
        )
        == 0
    )

    assert calls == [("project-1", "agent-1"), ("project-1", "agent-1")]
    assert waits == [3]
    assert capsys.readouterr().out == "Execution exec-2: SUCCEEDED\n"


def test_watch_mode_stops_on_non_success_result(monkeypatch):
    calls = []
    waits = []
    monkeypatch.setattr(worker, "run", lambda *_: calls.append(1) or {"status": "FAILED"})

    assert (
        worker.run_watch(
            "p",
            "a",
            poll_interval_seconds=1,
            stop_event=threading.Event(),
            wait=waits.append,
        )
        == 1
    )
    assert calls == [1]
    assert waits == []


def test_watch_dispatches_before_consuming_the_persistent_queue(monkeypatch):
    stop = threading.Event()
    calls = []

    def dispatch(project_id, principal_id, base_sha):
        calls.append(("dispatch", project_id, principal_id, base_sha))
        return {"status": "QUEUED", "work_id": "work-1", "execution_id": "exec-1"}

    def run_once(project_id, principal_id):
        calls.append(("run", project_id, principal_id))
        stop.set()
        return {"status": "SUCCEEDED", "execution_id": "exec-1"}

    monkeypatch.setattr(worker, "dispatch_next", dispatch)
    monkeypatch.setattr(worker, "run", run_once)

    assert worker.run_watch(
        "project-1", "agent-1", poll_interval_seconds=5, stop_event=stop,
        dispatch=True, base_sha="b" * 40,
    ) == 0
    assert calls == [
        ("dispatch", "project-1", "agent-1", "b" * 40),
        ("run", "project-1", "agent-1"),
    ]


def test_watch_poll_interval_is_bounded():
    stop = threading.Event()
    with pytest.raises(worker.WorkerError, match="poll interval"):
        worker.run_watch("p", "a", poll_interval_seconds=0, stop_event=stop)
    with pytest.raises(worker.WorkerError, match="poll interval"):
        worker.run_watch("p", "a", poll_interval_seconds=301, stop_event=stop)


def test_cli_watch_mode_installs_signal_stop_and_restores_handlers(monkeypatch):
    import signal

    old_handlers = {signal.SIGTERM: object(), signal.SIGINT: object()}
    installed = {}
    monkeypatch.setattr(worker.signal, "getsignal", lambda signum: old_handlers[signum])
    monkeypatch.setattr(
        worker.signal, "signal", lambda signum, handler: installed.__setitem__(signum, handler)
    )
    monkeypatch.setattr(
        worker.sys,
        "argv",
        [
            "worker",
            "--project-id",
            "p",
            "--principal-id",
            "a",
            "--watch",
            "--poll-interval-seconds",
            "2.5",
        ],
    )
    observed = {}

    def fake_watch(project_id, principal_id, *, poll_interval_seconds, stop_event,
                   dispatch, base_sha):
        observed.update(
            project_id=project_id,
            principal_id=principal_id,
            interval=poll_interval_seconds,
            event=stop_event,
            dispatch=dispatch,
            base_sha=base_sha,
        )
        installed[signal.SIGTERM](signal.SIGTERM, None)
        assert stop_event.is_set()
        return 0

    monkeypatch.setattr(worker, "run_watch", fake_watch)
    assert worker.main() == 0
    assert observed["project_id"] == "p"
    assert observed["principal_id"] == "a"
    assert observed["interval"] == 2.5
    assert observed["dispatch"] is False
    assert observed["base_sha"] is None
    assert installed == old_handlers


def test_dispatch_sends_agent_token_only_to_local_api(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setattr(worker.os, "getuid", lambda: os.stat(runtime).st_uid)
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    class Opener:
        def open(self, request, timeout):
            captured.update(url=request.full_url, headers=request.headers, body=request.data,
                            timeout=timeout)
            return Response(json.dumps({"status": "QUEUED", "execution_id": "e1",
                                        "work_id": "w1"}).encode())

    def fake_build_opener(handler):
        captured["redirect_handler"] = handler
        return Opener()

    def unused_urlopen(*_args, **_kwargs):
        pytest.fail("dispatch must use the no-redirect opener")

    monkeypatch.setattr(worker.urllib.request, "urlopen", unused_urlopen)
    monkeypatch.setattr(worker.urllib.request, "build_opener", fake_build_opener)

    result = worker.dispatch_next("p1", "a1", "a" * 40)

    assert result["status"] == "QUEUED"
    assert captured["url"] == "http://127.0.0.1:8001/v1/agent/dispatch-next"
    assert captured["headers"]["X-agent-token"] == "agent-token-fixture"
    assert json.loads(captured["body"]) == {
        "project_id": "p1", "principal_id": "a1", "base_sha": "a" * 40,
    }
    assert captured["timeout"] == 10
    assert captured["redirect_handler"] is worker._RejectRedirects
    assert worker._RejectRedirects().redirect_request(None, None, 302, "Found", {},
                                                      "https://elsewhere.test/") is None


def test_dispatch_rejects_plain_http_remote_and_bad_base_sha(monkeypatch):
    monkeypatch.setenv("AAO_API_BASE_URL", "http://api.example.test")
    with pytest.raises(worker.WorkerError, match="HTTPS"):
        worker.dispatch_next("p", "a", "a" * 40)
    monkeypatch.setenv("AAO_API_BASE_URL", "http://127.0.0.1:8001")
    with pytest.raises(worker.WorkerError, match="base SHA"):
        worker.dispatch_next("p", "a", "not-a-sha")
