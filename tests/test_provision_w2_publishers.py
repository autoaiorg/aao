from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import provision_w2_publishers as provisioner


def test_local_api_url_is_loopback_only():
    assert provisioner.local_api_url("http://127.0.0.1:8001/") == "http://127.0.0.1:8001"
    for url in ("https://127.0.0.1:8001", "http://example.com", "http://user@localhost:8001"):
        with pytest.raises(provisioner.ProvisionError):
            provisioner.local_api_url(url)


def test_provision_issues_separate_principals_and_delivers_tokens(monkeypatch):
    api_calls = []
    role_calls = []
    tokens = iter(("secret-for-impl", "secret-for-pm"))
    grants = []
    uids = {"aao-impl-codex": 2001, "aao-pm": 2002}
    monkeypatch.setattr(provisioner.pwd, "getpwnam",
                        lambda account: SimpleNamespace(pw_uid=uids[account]))

    def fake_request(url, path, *, method="GET", ceo_token=None, body=None):
        assert url == "http://127.0.0.1:8001"
        assert ceo_token == "ceo-secret"
        api_calls.append((method, path, body))
        if path == "/v1/projects":
            return [{"id": "project/id", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"}]
        if path.endswith("/grants") and method == "GET":
            return list(grants)
        if path.endswith("/grants") and method == "POST":
            grants.append({**body, "kind": "AGENT", "credential_enabled": True})
            return {"ok": True}
        if path == "/v1/principals/credentials":
            return {"token": next(tokens), "principal_id": body["principal_id"], "kind": "AGENT"}
        return {"ok": True}

    def fake_helper(account, *, api_python, token, operation):
        assert api_python == "/usr/bin/python3"
        role_calls.append((account, token, operation))

    monkeypatch.setattr(provisioner, "request_json", fake_request)
    monkeypatch.setattr(provisioner, "_run_role_helper", fake_helper)
    result = provisioner.provision("project/id", api_url="http://127.0.0.1:8001",
                                   ceo_token="ceo-secret", api_python="/usr/bin/python3")

    principals = [call[2]["principal_id"] for call in api_calls if call[1] == "/v1/principals/credentials"]
    assert len(set(principals)) == 2
    assert [call[2]["capability"] for call in api_calls
            if call[0] == "POST" and call[1].endswith("/grants")] == [
        "project.read", "code.publish", "project.read", "code.publish",
    ]
    assert [(account, token, operation) for account, token, operation in role_calls] == [
        ("aao-impl-codex", None, "check"),
        ("aao-pm", None, "check"),
        ("aao-impl-codex", "secret-for-impl", "install"),
        ("aao-impl-codex", "secret-for-impl", "verify"),
        ("aao-pm", "secret-for-pm", "install"),
        ("aao-pm", "secret-for-pm", "verify"),
    ]
    assert [entry[0] for entry in result] == ["aao-impl-codex", "aao-pm"]
    assert "secret-" not in repr(result)


def test_provision_failure_removes_token_files_and_revokes_issued_credentials(monkeypatch):
    api_calls = []
    tokens = iter(("secret-for-impl", "secret-for-pm"))
    role_calls = []
    grants = []
    uids = {"aao-impl-codex": 2001, "aao-pm": 2002}
    monkeypatch.setattr(provisioner.pwd, "getpwnam",
                        lambda account: SimpleNamespace(pw_uid=uids[account]))

    def fake_request(_url, path, *, method="GET", body=None, **_kwargs):
        api_calls.append((method, path, body))
        if path == "/v1/projects":
            return [{"id": "project-1", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"}]
        if path.endswith("/grants") and method == "GET":
            return list(grants)
        if path.endswith("/grants") and method == "POST":
            grants.append({**body, "kind": "AGENT", "credential_enabled": True})
            return {"ok": True}
        if path == "/v1/principals/credentials":
            return {"token": next(tokens), "principal_id": body["principal_id"], "kind": "AGENT"}
        return {"ok": True}

    def fake_helper(account, *, token, operation, **_kwargs):
        role_calls.append((account, token, operation))
        if account == "aao-pm" and operation == "install":
            raise provisioner.ProvisionError("simulated installer failure")

    monkeypatch.setattr(provisioner, "request_json", fake_request)
    monkeypatch.setattr(provisioner, "_run_role_helper", fake_helper)

    with pytest.raises(provisioner.ProvisionError, match="simulated installer failure"):
        provisioner.provision("project-1", api_url="http://127.0.0.1:8001", ceo_token="ceo-secret")

    assert len([call for call in api_calls if call[1].endswith("/revoke")]) == 2
    assert ("aao-impl-codex", "secret-for-impl", "remove") in role_calls
    assert ("aao-pm", "secret-for-pm", "remove") in role_calls


def test_provision_refuses_non_self_development_project_before_sudo(monkeypatch):
    monkeypatch.setattr(provisioner, "_run_role_helper",
                        lambda *_args, **_kwargs: pytest.fail("must not run sudo helper"))
    monkeypatch.setattr(provisioner, "request_json", lambda *_a, **_kw: [
        {"id": "project-1", "name": "Another Project", "state": "ACTIVE"},
    ])

    with pytest.raises(provisioner.ProvisionError, match="active AAO Self Development"):
        provisioner.provision("project-1", api_url="http://127.0.0.1:8001", ceo_token="ceo-secret")
