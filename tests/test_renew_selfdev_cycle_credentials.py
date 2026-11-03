"""Unattended Self Development cycle renewal runner: state machine with fakes."""

import io
import json
import os
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

import pytest

from scripts import renew_selfdev_cycle_credentials as renew

PROJECT = "3f0d7b52-1111-4222-8333-944455556666"
T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
IMPL_GRANTS = sorted(renew.ROLE_GRANTS[0])


class Crash(BaseException):
    """Simulated process death: not caught by the runner."""


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


class FakeServer:
    """In-memory model of the scoped issue/revoke API plus identity endpoints."""

    def __init__(self, clock):
        self.clock = clock
        self.cycles = {}  # id -> {"expires": dt, "revoked": bool}
        self.calls = []
        self.busy_worker = None
        self.fail = {}  # method -> callable returning (status, body) or raising
        self.crash_after = None  # method name: perform the action, then crash

    def _maybe(self, name, *args):
        self.calls.append((name, *args))
        if name in self.fail:
            return self.fail[name](*args)
        return None

    def live(self):
        return [c for c, v in self.cycles.items()
                if not v["revoked"] and v["expires"] > self.clock()]

    def issue(self, cycle_id):
        override = self._maybe("issue", cycle_id)
        if override is not None:
            return override
        if cycle_id in self.cycles:
            return 409, {"detail": "Self Development cycle roles already exist"}
        expires = self.clock() + renew.CYCLE_TTL
        self.cycles[cycle_id] = {"expires": expires, "revoked": False,
                                 "issued": self.clock()}
        body = {
            "cycle_id": cycle_id, "project_id": PROJECT, "expires_at": expires.isoformat(),
            "roles": [
                {"principal_id": f"aao-selfdev-impl-{cycle_id}", "kind": "AGENT",
                 "grants": IMPL_GRANTS, "token": f"SECRET-impl-{cycle_id}"},
                {"principal_id": f"aao-selfdev-review-{cycle_id}", "kind": "AUDITOR",
                 "grants": ["work.review"], "token": f"SECRET-review-{cycle_id}"},
            ],
        }
        if self.crash_after == "issue":
            raise Crash
        return 201, body

    def revoke(self, cycle_id):
        override = self._maybe("revoke", cycle_id)
        if override is not None:
            return override
        if cycle_id not in self.cycles:
            return 404, {"detail": {"code": "CYCLE_NOT_FOUND", "message": "never issued"}}
        already = self.cycles[cycle_id]["revoked"]
        self.cycles[cycle_id]["revoked"] = True
        self.cycles[cycle_id]["revoked_at"] = self.clock()
        if self.crash_after == "revoke":
            raise Crash
        return 200, {"cycle_id": cycle_id, "revoked": True, "already_revoked": already}

    def board(self):
        override = self._maybe("board")
        if override is not None:
            return override
        if self.crash_after == "board":
            raise Crash
        executions = []
        if self.busy_worker:
            executions.append({"id": "e1", "status": "RUNNING", "worker_id": self.busy_worker,
                               "attempts": 1})
        return 200, [{"id": "w1", "executions": executions}]

    def agent_me(self, token):
        override = self._maybe("agent_me")
        if override is not None:
            return override
        if self.crash_after == "agent_me":
            raise Crash
        cycle = token.removeprefix("SECRET-impl-")
        return 200, {"principal_id": f"aao-selfdev-impl-{cycle}", "kind": "AGENT",
                     "enabled": True}

    def auditor_grants(self, token):
        override = self._maybe("auditor_grants")
        if override is not None:
            return override
        cycle = token.removeprefix("SECRET-review-")
        return 200, [{"principal_id": f"aao-selfdev-review-{cycle}", "project_id": PROJECT,
                      "capability": "work.review", "expires_at": None, "active": True}]


class FakeInstaller:
    def __init__(self, server):
        self.server = server
        self.files = {}
        self.rc = {}  # (account, op) -> rc
        self.crash_at = None  # (account, op)

    def run(self, account, kind, operation, token):
        assert operation in {"replace", "verify"}, operation
        self.server.calls.append((operation, account))
        rc = self.rc.get((account, operation), 0)
        if operation == "replace" and rc in {0, renew.REPLACE_COMMITTED}:
            self.files[account] = token
        if self.crash_at == (account, operation):
            raise Crash
        if operation == "verify" and rc == 0 and self.files.get(account) != token:
            return 1
        return rc


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    server = FakeServer(clock)
    installer = FakeInstaller(server)
    store = renew.StateStore(tmp_path / "state.json", PROJECT)
    logs = []

    def make():
        return renew.Runner(project_id=PROJECT, api=server, installer=installer, store=store,
                            clock=clock, log=logs.append)

    return clock, server, installer, store, logs, make


def _bootstrap(env):
    _clock, _server, _installer, store, _logs, make = env
    assert make().tick(bootstrap=True) == 0
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"]
    return state["current_cycle_id"]


def _to_renewal(env):
    clock = env[0]
    clock.advance(minutes=60)  # exactly 50 % of TTL left


def _no_secret_anywhere(env, capsys=None):
    _clock, _server, _installer, store, logs, _make = env
    blobs = [json.dumps(logs)]
    if store.path.exists():
        blobs.append(store.path.read_text())
    if capsys is not None:
        out = capsys.readouterr()
        blobs += [out.out, out.err]
    for blob in blobs:
        assert "SECRET" not in blob


def test_happy_path_renews_verifies_then_revokes_old_after_drain(env, capsys):
    clock, server, installer, store, logs, make = env
    c1 = _bootstrap(env)
    assert installer.files["aao-impl-codex"] == f"SECRET-impl-{c1}"
    clock.advance(minutes=59)
    server.calls.clear()
    assert make().tick() == 0 and server.calls == []  # not yet due

    clock.advance(minutes=1)
    server.busy_worker = f"aao-selfdev-impl-{c1}"
    assert make().tick() == 0
    state = store.load()
    c2 = state["next_cycle_id"]
    assert state["phase"] == "VERIFIED" and state["current_cycle_id"] == c1
    assert installer.files == {"aao-impl-codex": f"SECRET-impl-{c2}",
                               "aao-auditor": f"SECRET-review-{c2}"}
    assert not server.cycles[c1]["revoked"]

    server.busy_worker = None
    clock.advance(minutes=5)
    assert make().tick() == 0
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] == c2
    assert state["next_cycle_id"] is None and server.cycles[c1]["revoked"]
    names = [c[0] for c in server.calls]
    # Reviewer file first, implementer last; verify both before the old cycle is revoked.
    replaces = [c for c in server.calls if c[0] == "replace"]
    assert replaces == [("replace", "aao-auditor"), ("replace", "aao-impl-codex")]
    assert names.index("agent_me") < names.index("replace")
    assert max(i for i, n in enumerate(names) if n == "verify") < names.index("revoke")
    events = [e["event"] for e in logs]
    for name in ("renewal_started", "installed", "verified", "drain_waited", "old_revoked"):
        assert f"selfdev_cycle.{name}" in events
    assert len(server.live()) == 1
    _no_secret_anywhere(env, capsys)
    assert os.stat(store.path).st_mode & 0o777 == 0o600


def test_missing_state_requires_bootstrap_and_bootstrap_refuses_existing(env):
    *_rest, make = env
    with pytest.raises(renew.RenewError, match="bootstrap"):
        make().tick()
    _bootstrap(env)
    with pytest.raises(renew.RenewError, match="already exists"):
        make().tick(bootstrap=True)


CRASH_POINTS = [
    ("server", "issue"),  # issued server-side, response lost
    ("server", "agent_me"),
    ("installer", ("aao-auditor", "replace")),
    ("installer", ("aao-impl-codex", "replace")),
    ("installer", ("aao-impl-codex", "verify")),
    ("installer", ("aao-auditor", "verify")),
]


@pytest.mark.parametrize(("where", "point"), CRASH_POINTS)
def test_crash_during_issuance_revokes_next_and_keeps_current(env, where, point):
    _clock, server, installer, store, _logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    if where == "server":
        server.crash_after = point
    else:
        installer.crash_at = point
    with pytest.raises(Crash):
        make().tick()
    crashed = store.load()
    assert crashed["phase"] in {"ISSUING", "INSTALLED_PENDING"}
    c2 = crashed["next_cycle_id"]
    server.crash_after = installer.crash_at = None

    server.calls.clear()
    # Recovery closes c2 first, then (same tick) renews with a fresh cycle ID.
    assert make().tick() == 0
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] not in {c1, c2}
    names = [c[0] for c in server.calls]
    assert names[0] == "revoke" and server.calls[0][1] == c2
    assert names.index("issue") > 0
    assert server.cycles[c1]["revoked"]
    if c2 in server.cycles:
        assert server.cycles[c2]["revoked"]
    assert len(server.live()) == 1


@pytest.mark.parametrize("point", ["board", "revoke"])
def test_crash_after_verification_resumes_idempotently(env, point):
    _clock, server, _installer, store, _logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    server.crash_after = point
    with pytest.raises(Crash):
        make().tick()
    c2 = store.load()["next_cycle_id"]
    server.crash_after = None
    assert make().tick() == 0
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] == c2
    assert server.cycles[c1]["revoked"] and not server.cycles[c2]["revoked"]


@pytest.mark.parametrize("response", [
    (409, {"detail": "exists"}),
    (500, {"detail": "boom"}),
    (503, None),
    "timeout",
])
def test_issue_errors_fail_issue_then_close_and_retry_with_new_id(env, response):
    clock, server, installer, store, _logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)

    def fail(cycle_id):
        if response == "timeout":
            raise renew.ApiUnavailable("timeout")
        return response

    server.fail["issue"] = fail
    assert make().tick() == 1
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] == c1
    assert installer.files["aao-impl-codex"] == f"SECRET-impl-{c1}"
    revoked = [c[1] for c in server.calls if c[0] == "revoke"]
    assert len(revoked) == 1 and revoked[0] != c1
    del server.fail["issue"]
    clock.advance(minutes=5)
    assert make().tick() == 0
    assert store.load()["current_cycle_id"] not in {c1, revoked[0]}


def test_lost_issue_response_with_delete_unavailable_never_issues_third_cycle(env):
    clock, server, _installer, store, logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    server.crash_after = "issue"
    with pytest.raises(Crash):
        make().tick()
    server.crash_after = None
    server.fail["revoke"] = lambda _c: (_ for _ in ()).throw(renew.ApiUnavailable("down"))
    issued_before = len(server.cycles)
    for _ in range(5):
        clock.advance(minutes=5)
        assert make().tick() == 1
        assert store.load()["phase"] == "FAILED_ISSUE"
    assert len(server.cycles) == issued_before == 2
    # After the unconfirmed cycle's own TTL it is closed even without a DELETE.
    clock.now = server.cycles[store.load()["next_cycle_id"]]["issued"] + renew.CYCLE_TTL \
        + renew.CLOCK_SKEW
    c2 = store.load()["next_cycle_id"]
    # c2 is past its TTL: closed with an alert; c1 has expired too, so a fresh
    # cycle is issued directly and the unrevokable expired c1 is left behind.
    assert make().tick() == 0
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] not in {c1, c2}
    assert server.live() == [state["current_cycle_id"]]
    assert "selfdev_cycle.expired_without_successor" in [e["event"] for e in logs]


@pytest.mark.parametrize("account", ["aao-auditor", "aao-impl-codex"])
def test_install_failure_keeps_old_credentials_valid(env, account):
    _clock, server, installer, store, _logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    installer.rc[(account, "replace")] = 1
    assert make().tick() == 1
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] == c1
    assert not server.cycles[c1]["revoked"]
    assert installer.files["aao-impl-codex"] == f"SECRET-impl-{c1}"
    assert all(v["revoked"] for k, v in server.cycles.items() if k != c1)


def test_post_install_verify_failure_revokes_new_and_keeps_old_cycle(env):
    _clock, server, installer, _store, logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    installer.rc[("aao-impl-codex", "verify")] = 1
    assert make().tick() == 1
    assert not server.cycles[c1]["revoked"]
    assert all(v["revoked"] for k, v in server.cycles.items() if k != c1)
    assert any(e.get("phase") == "INSTALLED_PENDING" for e in logs)


def test_replace_exit_3_is_decided_by_verify(env):
    _clock, _server, installer, store, _logs, make = env
    _bootstrap(env)
    _to_renewal(env)
    installer.rc[("aao-impl-codex", "replace")] = renew.REPLACE_COMMITTED
    assert make().tick() == 0
    assert store.load()["phase"] == "ACTIVE"


@pytest.mark.parametrize(("endpoint", "response"), [
    ("agent_me", (200, {"principal_id": "aao-selfdev-impl-" + "0" * 32, "kind": "AGENT",
                        "enabled": True})),
    ("agent_me", (403, {"detail": "rejected"})),
    ("auditor_grants", (200, [])),
    ("auditor_grants", (200, [
        {"principal_id": "x", "project_id": PROJECT, "capability": "work.review",
         "active": True}])),
    ("auditor_grants", (200, [
        {"principal_id": "R", "project_id": PROJECT, "capability": "work.review",
         "active": True},
        {"principal_id": "R", "project_id": PROJECT, "capability": "work.create",
         "active": True}])),
])
def test_verification_mismatch_revokes_new_and_keeps_old_untouched(env, endpoint, response):
    _clock, server, installer, store, _logs, make = env
    c1 = _bootstrap(env)
    files_before = dict(installer.files)
    _to_renewal(env)
    server.fail[endpoint] = lambda *_a: response
    server.calls.clear()
    assert make().tick() == 1
    assert installer.files == files_before
    assert not any(c[0] == "replace" for c in server.calls)
    revoked = [c[1] for c in server.calls if c[0] == "revoke"]
    assert revoked and c1 not in revoked
    assert not server.cycles[c1]["revoked"]
    assert store.load()["current_cycle_id"] == c1


def test_issue_response_with_wrong_grants_is_rejected_before_install(env):
    _clock, server, installer, _store, _logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    real_issue = FakeServer.issue

    def widened(cycle_id):
        server.fail.pop("issue")
        status, body = real_issue(server, cycle_id)
        body["roles"][0]["grants"] = [*IMPL_GRANTS, "work.assign"]
        return status, body

    server.fail["issue"] = widened
    assert make().tick() == 1
    assert installer.files["aao-impl-codex"] == f"SECRET-impl-{c1}"
    assert not server.cycles[c1]["revoked"]


def test_overlap_bound_drain_cap_and_renewal_threshold(env):
    clock, server, _installer, store, _logs, make = env
    c1 = _bootstrap(env)
    exp1 = server.cycles[c1]["expires"]
    server.busy_worker = f"aao-selfdev-impl-{c1}"  # never drains
    while not server.cycles[c1]["revoked"]:
        clock.advance(minutes=5)
        make().tick()
        assert len(server.live()) <= 2
        assert clock.now < exp1 + timedelta(minutes=5)
    c2 = store.load()["current_cycle_id"]
    issued2 = server.cycles[c2]["issued"]
    assert exp1 - issued2 <= timedelta(minutes=60)
    assert server.cycles[c1]["revoked_at"] - issued2 <= renew.DRAIN_CAP + timedelta(minutes=5)
    assert server.cycles[c1]["revoked_at"] - issued2 >= renew.DRAIN_CAP


def test_old_revoke_error_retries_until_old_cycle_expires(env):
    clock, server, _installer, store, logs, make = env
    c1 = _bootstrap(env)
    exp1 = server.cycles[c1]["expires"]
    _to_renewal(env)
    server.fail["revoke"] = lambda _c: (500, None)
    assert make().tick() == 1
    assert store.load()["phase"] == "REVOKING_OLD"
    clock.now = exp1 - timedelta(minutes=1)
    assert make().tick() == 1  # old cycle still valid: keep retrying, do not advance
    assert store.load()["current_cycle_id"] == c1
    clock.now = exp1
    make().tick()
    state = store.load()
    assert state["current_cycle_id"] != c1
    assert any("already expired" in e.get("reason", "") for e in logs)


def test_expired_current_issues_directly_without_drain(env):
    clock, server, _installer, store, logs, make = env
    c1 = _bootstrap(env)
    server.busy_worker = f"aao-selfdev-impl-{c1}"
    clock.now = server.cycles[c1]["expires"] + timedelta(minutes=1)
    assert make().tick() == 0
    state = store.load()
    assert state["phase"] == "ACTIVE" and state["current_cycle_id"] != c1
    assert server.cycles[c1]["revoked"]
    assert "selfdev_cycle.expired_without_successor" in [e["event"] for e in logs]


@pytest.mark.parametrize("content", [
    b"not json",
    b"{}",
    b'{"phase": "ACTIVE"}',
    json.dumps({**dict.fromkeys(renew.STATE_KEYS), "phase": "BOGUS",
                "project_id": PROJECT}).encode(),
    json.dumps({**dict.fromkeys(renew.STATE_KEYS), "phase": "ACTIVE",
                "project_id": "other"}).encode(),
    json.dumps({**dict.fromkeys(renew.STATE_KEYS), "phase": "VERIFIED",
                "project_id": PROJECT}).encode(),
    json.dumps({**dict.fromkeys(renew.STATE_KEYS), "phase": "ACTIVE", "project_id": PROJECT,
                "current_cycle_id": "../../x", "current_expires_at": T0.isoformat()}).encode(),
])
def test_corrupt_state_fails_closed_without_api_calls(env, content):
    _clock, server, _installer, store, _logs, make = env
    fd = os.open(store.path, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, content)
    os.close(fd)
    with pytest.raises(renew.RenewError):
        make().tick()
    assert server.calls == []


def test_state_file_mode_and_symlink_fail_closed(env, tmp_path):
    _clock, _server, _installer, store, _logs, make = env
    _bootstrap(env)
    os.chmod(store.path, 0o644)
    with pytest.raises(renew.RenewError, match="private"):
        make().tick()
    os.chmod(store.path, 0o600)
    target = tmp_path / "real.json"
    store.path.rename(target)
    store.path.symlink_to(target)
    with pytest.raises(renew.RenewError, match="symlink"):
        make().tick()


def test_lock_contention_returns_without_acting(tmp_path, monkeypatch):
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(renew, "runtime_dir", lambda: runtime)

    def forbidden():
        raise AssertionError("PM token must not be read while another run holds the lock")

    monkeypatch.setattr(renew, "read_pm_token", forbidden)
    with renew.exclusive_lock(runtime / "aao-selfdev-cycle.lock") as held:
        assert held
        assert renew.main(["--project-id", PROJECT]) == renew.EXIT_LOCKED
    with renew.exclusive_lock(runtime / "aao-selfdev-cycle.lock") as held:
        assert held


def test_main_without_state_fails_closed_and_never_prints_token(tmp_path, monkeypatch, capsys):
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setattr(renew, "runtime_dir", lambda: runtime)
    monkeypatch.setattr(renew, "read_pm_token", lambda: "SECRET-pm")
    assert renew.main(["--project-id", PROJECT]) == 1
    out = capsys.readouterr()
    assert "bootstrap" in out.out and "SECRET" not in out.out + out.err


def test_wrapper_installer_uses_atomic_replace_with_token_only_on_stdin(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"], seen["kwargs"] = command, kwargs
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(renew.subprocess, "run", fake_run)
    monkeypatch.setenv("AAO_LEAK_CHECK", "x")
    assert renew.WrapperInstaller().run(
        "aao-impl-codex", "selfdev-implementer", "replace", "SECRET-tok") == 0
    command = seen["command"]
    assert command[:3] == ["/usr/bin/sudo", "-n", renew.ROOT_WRAPPER]
    assert command[command.index("--operation") + 1] == "replace"
    assert not any("SECRET" in part for part in command)
    assert seen["kwargs"]["input"] == "SECRET-tok\n"
    env_values = seen["kwargs"]["env"]
    assert "AAO_LEAK_CHECK" not in env_values
    assert not any("SECRET" in v for v in env_values.values())
    with pytest.raises(renew.RenewError):
        renew.WrapperInstaller().run("aao-impl-codex", "selfdev-implementer", "install", "t")
    with pytest.raises(renew.RenewError):
        renew.WrapperInstaller().run("aao-pm", "pm", "replace", "t")


class _Response:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return json.dumps(self._body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_api_client_headers_status_codes_and_loopback(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.get_method() == "DELETE":
            raise HTTPError(request.full_url, 404, "nf", {}, io.BytesIO(
                b'{"detail": {"code": "CYCLE_NOT_FOUND"}}'))
        return _Response(200, [])

    monkeypatch.setattr(renew, "urlopen", fake_urlopen)
    client = renew.ApiClient("http://127.0.0.1:8001", PROJECT, "SECRET-pm")
    assert client.auditor_grants("SECRET-rev") == (200, [])
    assert requests[-1].get_header("X-auditor-token") == "SECRET-rev"
    assert requests[-1].get_header("X-agent-token") is None
    client.agent_me("SECRET-impl")
    assert requests[-1].get_header("X-agent-token") == "SECRET-impl"
    assert client.revoke("a" * 32) == (404, {"detail": {"code": "CYCLE_NOT_FOUND"}})
    client.issue("b" * 32)
    body = json.loads(requests[-1].data)
    assert body == {"cycle_id": "b" * 32, "lifetime_seconds": 7200}
    assert requests[-1].get_header("X-agent-token") == "SECRET-pm"

    def unavailable(request, timeout):
        raise TimeoutError

    monkeypatch.setattr(renew, "urlopen", unavailable)
    with pytest.raises(renew.ApiUnavailable):
        client.board()
    with pytest.raises(renew.ProvisionError):
        renew.ApiClient("http://example.com", PROJECT, "t")


def test_404_without_cycle_not_found_code_is_not_never_issued(env):
    _clock, server, _installer, store, _logs, make = env
    c1 = _bootstrap(env)
    _to_renewal(env)
    server.fail["issue"] = lambda _c: (500, None)
    server.fail["revoke"] = lambda _c: (404, {"detail": "Self Development project not found"})
    assert make().tick() == 1
    assert store.load()["phase"] == "FAILED_ISSUE"
    assert c1 in server.cycles


def test_user_units_are_oneshot_without_no_new_privileges():
    from pathlib import Path

    unit_dir = Path(__file__).resolve().parents[1] / "deploy/systemd/user"
    service = (unit_dir / "aao-selfdev-cycle-renew.service").read_text()
    timer = (unit_dir / "aao-selfdev-cycle-renew.timer").read_text()
    directives = [line for line in service.splitlines() if not line.startswith("#")]
    assert "Type=oneshot" in directives and "SuccessExitStatus=75" in directives
    assert "from scripts.renew_selfdev_cycle_credentials import main" in service
    # sudo (setuid) must work: no NNP and no directive that implies it in user mode.
    for forbidden in ("NoNewPrivileges", "PrivateDevices", "PrivateTmp", "ProtectSystem",
                      "ProtectHome", "RestrictSUIDSGID", "LockPersonality",
                      "RestrictAddressFamilies", "SystemCallFilter"):
        assert not any(line.startswith(forbidden) for line in directives)
    assert "OnUnitActiveSec=5min" in timer and "Unit=aao-selfdev-cycle-renew.service" in timer
