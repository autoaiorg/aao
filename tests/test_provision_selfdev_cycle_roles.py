from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import provision_selfdev_cycle_roles as provisioner


def _expiry():
    return (datetime.now(UTC) + timedelta(hours=2)).isoformat()


def test_provision_separates_roles_and_grants(monkeypatch):
    issued = iter(("agent-secret", "auditor-secret"))
    api_calls = []
    role_calls = []
    grants = []
    uids = {provisioner.IMPLEMENTER: 2001, provisioner.REVIEWER: 2002}
    monkeypatch.setattr(
        provisioner.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=uids[name])
    )

    def request(_api, path, *, method="GET", body=None, **kwargs):
        api_calls.append((method, path, body, kwargs))
        if path == "/v1/projects":
            return [{"id": "selfdev", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"}]
        if path.endswith("/grants") and method == "POST":
            kind = "AGENT" if body["capability"] != "work.review" else "AUDITOR"
            grants.append({**body, "kind": kind, "credential_enabled": True})
            return {"created": True}
        if path.endswith("/grants"):
            return list(grants)
        if path == "/v1/principals/credentials":
            kind = body["kind"]
            return {"principal_id": body["principal_id"], "kind": kind, "token": next(issued)}
        return {"ok": True}

    monkeypatch.setattr(provisioner.common, "request_json", request)
    monkeypatch.setattr(
        provisioner.common,
        "_run_role_helper",
        lambda account, **kw: role_calls.append((account, kw)),
    )
    result = provisioner.provision(
        "selfdev", api_url="http://127.0.0.1:8001", ceo_token="ceo-secret", expiry=_expiry()
    )

    created = [body for method, path, body, _ in api_calls if path == "/v1/principals/credentials"]
    assert [row["kind"] for row in created] == ["AGENT", "AUDITOR"]
    assert len({row["principal_id"] for row in created}) == 2
    grant_posts = [
        body for method, path, body, _ in api_calls if method == "POST" and path.endswith("/grants")
    ]
    assert [r["capability"] for r in grant_posts] == [
        "project.read",
        "work.create",
        "work.admit",
        "work.progress",
        "execution.claim",
        "code.propose",
        "evidence.submit",
        "work.review",
    ]
    assert all(r["expires_at"] == result[0][-1] for r in grant_posts)
    assert [c[0] for c in role_calls] == [
        provisioner.IMPLEMENTER,
        provisioner.REVIEWER,
        provisioner.IMPLEMENTER,
        provisioner.IMPLEMENTER,
        provisioner.REVIEWER,
        provisioner.REVIEWER,
    ]
    assert [row[2] for row in result] == ["AGENT", "AUDITOR"]
    assert "secret" not in repr(result)
    assert all(kwargs["ceo_token"] == "ceo-secret" for *_rest, kwargs in api_calls)


def test_provision_rollback_removes_and_revokes_both_roles(monkeypatch):
    grants = []
    calls = []
    uids = {provisioner.IMPLEMENTER: 2001, provisioner.REVIEWER: 2002}
    monkeypatch.setattr(
        provisioner.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=uids[name])
    )

    def request(_api, path, *, method="GET", body=None, **_kwargs):
        if path == "/v1/projects":
            return [{"id": "p", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"}]
        if path.endswith("/grants") and method == "POST":
            grants.append(
                {
                    **body,
                    "kind": "AGENT" if body["capability"] != "work.review" else "AUDITOR",
                    "credential_enabled": True,
                }
            )
        elif path.endswith("/grants"):
            return list(grants)
        elif path == "/v1/principals/credentials":
            return {
                "principal_id": body["principal_id"],
                "kind": body["kind"],
                "token": f"token-{body['kind']}",
            }
        elif path.endswith("/revoke"):
            calls.append(("revoke", path))
        return {"ok": True}

    def helper(account, *, operation, token_kind, **_kw):
        calls.append((operation, account, token_kind))
        if account == provisioner.REVIEWER and operation == "install":
            raise provisioner.ProvisionError("injected failure")

    monkeypatch.setattr(provisioner.common, "request_json", request)
    monkeypatch.setattr(provisioner.common, "_run_role_helper", helper)
    with pytest.raises(provisioner.ProvisionError, match="issued credentials revoked"):
        provisioner.provision(
            "p", api_url="http://127.0.0.1:8001", ceo_token="ceo", expiry=_expiry()
        )
    assert sum(call[0] == "revoke" for call in calls) == 2
    assert ("remove", provisioner.IMPLEMENTER, "selfdev-implementer") in calls
    assert ("remove", provisioner.REVIEWER, "selfdev-reviewer") in calls


@pytest.mark.parametrize(
    "url", ["https://127.0.0.1:8001", "http://example.com:8001", "http://user@127.0.0.1:8001"]
)
def test_provision_requires_loopback_api(url):
    with pytest.raises(provisioner.ProvisionError):
        provisioner.provision("p", api_url=url, ceo_token="secret", expiry=_expiry())


@pytest.mark.parametrize("offset,valid", [(-1, False), (9, False), (2, True)])
def test_expiry_is_required_future_and_bounded(offset, valid):
    value = (datetime.now(UTC) + timedelta(hours=offset)).isoformat()
    if valid:
        assert provisioner.parse_expiry(value).endswith("+00:00")
    else:
        with pytest.raises(provisioner.ProvisionError):
            provisioner.parse_expiry(value)


def test_grant_readback_rejects_wrong_kind_expiry_or_extra_grant(monkeypatch):
    monkeypatch.setattr(
        provisioner.common,
        "request_json",
        lambda *_a, **_kw: [
            {
                "principal_id": "p",
                "kind": "AGENT",
                "credential_enabled": True,
                "capability": "work.review",
                "expires_at": "2099-01-01T00:00:00+00:00",
            },
        ],
    )
    with pytest.raises(provisioner.ProvisionError, match="exact AUDITOR grants"):
        provisioner._grant_and_verify(
            "http://127.0.0.1:8001", "p", "p", "AUDITOR", ("work.review",), _expiry(), "ceo"
        )


def test_secrets_not_printed_by_main(monkeypatch, capsys):
    monkeypatch.setattr(provisioner.getpass, "getpass", lambda *_: "ceo-never-print")
    monkeypatch.setattr(
        provisioner,
        "provision",
        lambda *a, **_kw: [
            (provisioner.IMPLEMENTER, "principal-1", "AGENT", ("work.create",), _expiry()),
            (provisioner.REVIEWER, "principal-2", "AUDITOR", ("work.review",), _expiry()),
        ],
    )
    assert provisioner.main(["--project-id", "p", "--expires-at", _expiry()]) == 0
    output = capsys.readouterr().out
    assert "ceo-never-print" not in output
    assert "API lifecycle review, not GOV-REV-001" in output


def test_role_helper_sends_token_only_on_stdin(monkeypatch):
    seen = {}
    monkeypatch.setattr(provisioner.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=2020))
    monkeypatch.setattr(
        provisioner.common.subprocess,
        "run",
        lambda args, **kwargs: seen.update(args=args, kwargs=kwargs),
    )
    provisioner.common._run_role_helper(
        provisioner.REVIEWER,
        api_python="/usr/bin/python3",
        token="private-token",
        operation="install",
        token_kind="selfdev-reviewer",
    )
    assert "private-token" not in seen["args"]
    assert seen["kwargs"]["input"] == "private-token\n"
    assert "env" not in seen["kwargs"]


def test_wrong_project_and_same_linux_identity_fail_before_install(monkeypatch):
    monkeypatch.setattr(
        provisioner.common,
        "request_json",
        lambda *_a, **_kw: [
            {"id": "p", "name": "Other", "state": "ACTIVE"},
        ],
    )
    monkeypatch.setattr(
        provisioner.common,
        "_run_role_helper",
        lambda *_a, **_kw: pytest.fail("installer should not run"),
    )
    with pytest.raises(provisioner.ProvisionError, match="active AAO Self Development"):
        provisioner.provision(
            "p", api_url="http://127.0.0.1:8001", ceo_token="ceo", expiry=_expiry()
        )

    monkeypatch.setattr(
        provisioner.common,
        "request_json",
        lambda *_a, **_kw: [
            {"id": "p", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"},
        ],
    )
    monkeypatch.setattr(
        provisioner.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=provisioner.os.getuid())
    )
    with pytest.raises(provisioner.ProvisionError, match="distinct Linux identities"):
        provisioner.provision(
            "p", api_url="http://127.0.0.1:8001", ceo_token="ceo", expiry=_expiry()
        )


@pytest.mark.parametrize(
    "bad_response", [None, {}, {"principal_id": "wrong", "kind": "AGENT", "token": "secret"}]
)
def test_malformed_issue_response_is_revoked_without_install(monkeypatch, bad_response):
    calls = []
    uids = {provisioner.IMPLEMENTER: 2001, provisioner.REVIEWER: 2002}
    monkeypatch.setattr(
        provisioner.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=uids[name])
    )

    def request(_api, path, *, method="GET", body=None, **_kwargs):
        if path == "/v1/projects":
            return [{"id": "p", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"}]
        if path == "/v1/principals/credentials":
            return bad_response
        if path.endswith("/revoke"):
            calls.append(("revoke", path))
        return {"ok": True}

    monkeypatch.setattr(provisioner.common, "request_json", request)
    monkeypatch.setattr(
        provisioner.common,
        "_run_role_helper",
        lambda *a, **kw: calls.append(("helper", kw.get("operation"))),
    )
    with pytest.raises(provisioner.ProvisionError, match="issued credentials revoked"):
        provisioner.provision(
            "p", api_url="http://127.0.0.1:8001", ceo_token="ceo", expiry=_expiry()
        )
    assert len([call for call in calls if call[0] == "revoke"]) == 1
    assert not [call for call in calls if call[0] == "helper" and call[1] == "install"]


def test_issue_request_exception_attempts_principal_revocation(monkeypatch):
    calls = []
    uids = {provisioner.IMPLEMENTER: 2001, provisioner.REVIEWER: 2002}
    monkeypatch.setattr(
        provisioner.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=uids[name])
    )

    def request(_api, path, *, method="GET", body=None, **_kwargs):
        if path == "/v1/projects":
            return [{"id": "p", "name": provisioner.PROJECT_NAME, "state": "ACTIVE"}]
        if path == "/v1/principals/credentials":
            raise OSError("simulated lost response after issue request")
        if path.endswith("/revoke"):
            calls.append(path)
        return {"ok": True}

    monkeypatch.setattr(provisioner.common, "request_json", request)
    monkeypatch.setattr(
        provisioner.common,
        "_run_role_helper",
        lambda *a, **kw: pytest.fail("installer must not run"),
    )
    with pytest.raises(provisioner.ProvisionError, match="issued credentials revoked"):
        provisioner.provision(
            "p", api_url="http://127.0.0.1:8001", ceo_token="ceo", expiry=_expiry()
        )
    assert len(calls) == 1
