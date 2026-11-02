from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import provision_pm_coordinator_token as pm

API = "http://127.0.0.1:8001"
CEO = "ceo-secret-value"
TOKEN = "pm-coordinator-secret-value"
EXPIRY = (datetime.now(UTC) + timedelta(days=7)).replace(microsecond=0).isoformat()


class FakeApi:
    """In-memory AAO API; ``fail`` maps a (method, path-suffix) to an exception or mutator."""

    def __init__(self, *, credential=None, extra_grant=None, grant_expiry=None, fail=None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.grants: list[dict] = []
        self.credential = credential
        self.extra_grant = extra_grant
        self.grant_expiry = grant_expiry
        self.fail = fail or {}

    def __call__(self, url, path, *, method="GET", ceo_token=None, body=None):
        assert url == API and ceo_token == CEO
        self.calls.append((method, path, body))
        for (fail_method, suffix), exc in self.fail.items():
            if method == fail_method and path.endswith(suffix):
                raise exc
        if path == "/v1/projects":
            return [{"id": "project/1", "name": "Any", "state": "ACTIVE"}]
        if path == "/v1/principals/credentials":
            if self.credential is not None:
                return self.credential
            return {"token": TOKEN, "principal_id": body["principal_id"], "kind": "AGENT"}
        if path.endswith("/grants") and method == "POST":
            expiry = self.grant_expiry if self.grant_expiry is not None else body["expires_at"]
            self.grants.append(
                {**body, "expires_at": expiry, "kind": "AGENT", "credential_enabled": True}
            )
            return {"created": True}
        if path.endswith("/grants") and method == "GET":
            rows = list(self.grants)
            if self.extra_grant and rows:
                rows.append({**rows[0], "capability": self.extra_grant})
            return rows
        return {"ok": True}

    def principal(self):
        return next(b["principal_id"] for m, p, b in self.calls if p.endswith("/credentials"))

    def revoked(self):
        return [p for m, p, _ in self.calls if p.endswith("/revoke")]

    def posted_grants(self):
        return [b["capability"] for m, p, b in self.calls if m == "POST" and p.endswith("/grants")]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(pm.pwd, "getpwnam", lambda _account: SimpleNamespace(pw_uid=1001))
    monkeypatch.setattr(pm.w2.pwd, "getpwnam", lambda _account: SimpleNamespace(pw_uid=1001))
    monkeypatch.setattr(pm.os, "getuid", lambda: 1000)
    role_calls: list[tuple[str, str | None, str, str]] = []
    failing: dict[str, Exception] = {}

    def helper(account, *, api_python, token, operation, token_kind="publisher"):
        role_calls.append((account, token, operation, token_kind))
        if operation in failing:
            raise failing[operation]

    monkeypatch.setattr(pm.w2, "_run_role_helper", helper)

    def install_api(api):
        monkeypatch.setattr(pm.w2, "request_json", api)
        return api

    return SimpleNamespace(role_calls=role_calls, failing=failing, install_api=install_api)


def run(expiry=EXPIRY):
    return pm.provision(
        "project/1", api_url=API, ceo_token=CEO, expiry=expiry, api_python="/usr/bin/python3"
    )


def test_happy_path_issues_distinct_principal_exact_grants_and_installs_pm_token(env):
    api = env.install_api(FakeApi())
    account, principal, expiry = run()

    assert (account, expiry) == ("aao-pm", EXPIRY)
    assert principal.startswith("aao-pm-coordinator-")
    assert not principal.startswith("aao-publisher")
    assert api.posted_grants() == ["project.read", "work.coordinate", "work.assign"]
    assert "work.create" not in api.posted_grants()
    assert all(
        b["expires_at"] == EXPIRY for m, p, b in api.calls if m == "POST" and p.endswith("/grants")
    )
    assert any(p == "/v1/projects/project%2F1/grants" for _, p, _ in api.calls)
    assert env.role_calls == [
        ("aao-pm", None, "check", "pm"),
        ("aao-pm", TOKEN, "install", "pm"),
        ("aao-pm", TOKEN, "verify", "pm"),
    ]
    assert api.revoked() == []
    assert TOKEN not in repr((account, principal, expiry))


def test_no_expiry_is_an_explicit_choice_and_verified_as_null(env):
    api = env.install_api(FakeApi())
    assert run(expiry=None)[2] is None
    assert all(
        b["expires_at"] is None for m, p, b in api.calls if m == "POST" and p.endswith("/grants")
    )


def test_check_failure_issues_nothing(env):
    api = env.install_api(FakeApi())
    env.failing["check"] = pm.ProvisionError("target exists")
    with pytest.raises(pm.ProvisionError, match="target exists"):
        run()
    assert not any(p.endswith("/credentials") for _, p, _ in api.calls)


@pytest.mark.parametrize(
    "api_kwargs, match",
    [
        ({"extra_grant": "code.publish"}, "exact least-privilege"),
        ({"extra_grant": "work.create"}, "exact least-privilege"),
        ({"grant_expiry": (datetime.now(UTC) + timedelta(days=30)).isoformat()}, "expiry"),
        ({"fail": {("POST", "/grants"): pm.BootstrapError("HTTP 500")}}, "revoked where possible"),
        ({"fail": {("GET", "/grants"): pm.BootstrapError("HTTP 500")}}, "revoked where possible"),
    ],
)
def test_failures_after_issuance_remove_token_and_revoke_principal(env, api_kwargs, match):
    api = env.install_api(FakeApi(**api_kwargs))
    with pytest.raises(pm.ProvisionError, match=match):
        run()
    principal = api.principal()
    assert api.revoked() == [f"/v1/principals/{principal}/revoke"]
    assert ("aao-pm", TOKEN, "remove", "pm") in env.role_calls
    assert ("aao-pm", TOKEN, "install", "pm") not in env.role_calls


@pytest.mark.parametrize("operation", ["install", "verify"])
def test_install_or_verify_failure_removes_token_and_revokes(env, operation):
    api = env.install_api(FakeApi())
    env.failing[operation] = pm.ProvisionError(f"simulated {operation} failure")
    with pytest.raises(pm.ProvisionError, match=f"simulated {operation}"):
        run()
    assert env.role_calls[-1] == ("aao-pm", TOKEN, "remove", "pm")
    assert api.revoked() == [f"/v1/principals/{api.principal()}/revoke"]


@pytest.mark.parametrize(
    "credential",
    [
        {"principal_id": "other", "kind": "AGENT", "token": TOKEN},
        {"principal_id": None, "kind": "AUDITOR", "token": TOKEN},
        {"kind": "AGENT"},
    ],
)
def test_invalid_credential_response_revokes_without_touching_files(env, credential):
    api = env.install_api(FakeApi(credential=credential))
    with pytest.raises(pm.ProvisionError, match="invalid publisher credential"):
        run()
    assert api.revoked() == [f"/v1/principals/{api.principal()}/revoke"]
    assert [c[2] for c in env.role_calls] == ["check"]


def test_refuses_inactive_or_unknown_project_and_same_account(env, monkeypatch):
    api = FakeApi()
    env.install_api(lambda *a, **kw: [{"id": "project/1", "state": "ARCHIVED"}])
    with pytest.raises(pm.ProvisionError, match="ACTIVE"):
        run()
    env.install_api(api)
    monkeypatch.setattr(pm.os, "getuid", lambda: 1001)
    with pytest.raises(pm.ProvisionError, match="distinct"):
        run()
    assert env.role_calls == [] and api.calls == [("GET", "/v1/projects", None)]


def test_refuses_non_loopback_before_any_request(env):
    api = env.install_api(FakeApi())
    for url in ("http://example.com:8001", "https://127.0.0.1:8001", "http://u:p@localhost"):
        with pytest.raises(pm.ProvisionError, match="loopback|credentials"):
            pm.provision("project/1", api_url=url, ceo_token=CEO, expiry=EXPIRY)
    assert api.calls == [] and env.role_calls == []


def test_main_requires_explicit_expiry_decision(monkeypatch, capsys):
    monkeypatch.setattr(pm.getpass, "getpass", lambda _p: pytest.fail("must not prompt"))
    with pytest.raises(SystemExit) as exc:
        pm.main(["--project-id", "p"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        pm.main(["--project-id", "p", "--no-expiry", "--expires-at", EXPIRY])
    for bad in ("2020-01-01T00:00:00+00:00", "2999-01-01T00:00:00", "tomorrow"):
        assert pm.main(["--project-id", "p", "--expires-at", bad]) == 1
    assert pm.main(["--project-id", "p", "--no-expiry", "--api", "http://10.0.0.1:8001"]) == 1
    assert "loopback" in capsys.readouterr().err


def test_token_never_in_output_argv_or_env(monkeypatch, capsys):
    """Run the real role helper against a fake subprocess.run and the real main()."""
    monkeypatch.setattr(pm.pwd, "getpwnam", lambda _a: SimpleNamespace(pw_uid=1001))
    monkeypatch.setattr(pm.w2.pwd, "getpwnam", lambda _a: SimpleNamespace(pw_uid=1001))
    monkeypatch.setattr(pm.os, "getuid", lambda: 1000)
    monkeypatch.setattr(pm.getpass, "getpass", lambda _p: CEO)
    api = FakeApi()
    monkeypatch.setattr(pm.w2, "request_json", api)
    runs = []

    def fake_run(args, *, input=None, **kwargs):
        runs.append((args, input, kwargs, dict(os.environ)))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(pm.w2.subprocess, "run", fake_run)
    assert (
        pm.main(
            ["--project-id", "project/1", "--expires-at", EXPIRY, "--python", "/usr/bin/python3"]
        )
        == 0
    )

    out = capsys.readouterr()
    for secret in (TOKEN, CEO):
        assert secret not in out.out + out.err
        for args, _input, kwargs, environ in runs:
            assert all(secret not in arg for arg in args)
            assert "env" not in kwargs
            assert all(secret not in value for value in environ.values())
    assert [r[0][-1] for r in runs] == ["--check", "pm", "--verify"]
    assert all(r[0][r[0].index("--token") + 1] == "pm" for r in runs)
    assert all("--install" not in r[0] for r in runs)
    assert [r[1] for r in runs] == [None, TOKEN + "\n", TOKEN + "\n"]
    assert f"principal={api.principal()}" in out.out
