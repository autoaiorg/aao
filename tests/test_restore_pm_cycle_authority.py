from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from scripts import restore_pm_cycle_authority as restore_pm

PROJECT_ID = "9d17d6c1-d644-424a-a425-fe7e084c3d91"
PRINCIPAL = "aao-pm-coordinator-existing"
EXPIRY = (datetime.now(UTC) + timedelta(days=5)).isoformat()


def _project_rows():
    return [{"id": PROJECT_ID, "name": restore_pm.PROJECT_NAME, "state": "ACTIVE"}]


def _grant_rows(include_issuer=False):
    caps = set(restore_pm.BASE_GRANTS)
    if include_issuer:
        caps.add(restore_pm.ISSUER_GRANT)
    return [
        {
            "principal_id": PRINCIPAL,
            "kind": "AGENT",
            "credential_enabled": True,
            "capability": capability,
            "expires_at": EXPIRY if capability == restore_pm.ISSUER_GRANT else None,
        }
        for capability in sorted(caps)
    ]


def _setup(monkeypatch, *, install_fails=False, recovery_fails=False):
    api_calls = []
    role_calls = []
    grants = _grant_rows()
    rotate_count = 0

    def request_json(api, path, *, method="GET", ceo_token=None, body=None):
        nonlocal rotate_count
        api_calls.append((path, method, body))
        if path == "/v1/projects":
            return _project_rows()
        if path.endswith("/grants") and method == "GET":
            return list(grants)
        if path.endswith("/grants") and method == "POST":
            grants.append(
                {
                    "principal_id": PRINCIPAL,
                    "kind": "AGENT",
                    "credential_enabled": True,
                    "capability": restore_pm.ISSUER_GRANT,
                    "expires_at": body["expires_at"],
                }
            )
            return {"created": True}
        if path.endswith(
            "/grants/aao-pm-coordinator-existing/credential.issue_selfdev_cycle_roles"
        ):
            return None
        if path.endswith("/rotate"):
            rotate_count += 1
            return {"principal_id": PRINCIPAL, "kind": "AGENT", "token": f"secret-{rotate_count}"}
        raise AssertionError((path, method))

    def run_role_helper(account, *, token, operation):
        role_calls.append((account, token, operation, "pm"))
        if install_fails and operation == "install" and token == "secret-1":
            raise restore_pm.ProvisionError("role token helper failed")
        if recovery_fails and token == "secret-2" and operation in {"install", "verify"}:
            raise restore_pm.ProvisionError("recovery role helper failed")

    monkeypatch.setattr(restore_pm.common, "request_json", request_json)
    monkeypatch.setattr(restore_pm, "_role_helper", run_role_helper)
    original_resolve = restore_pm.Path.resolve
    original_stat = restore_pm.Path.stat

    def resolve(path, strict=False):
        if path in {restore_pm.SUDO, restore_pm.ROLE_PYTHON, restore_pm.ROLE_INSTALLER}:
            return path
        return original_resolve(path, strict=strict)

    checked_paths = {
        parent
        for executable in (restore_pm.SUDO, restore_pm.ROLE_PYTHON, restore_pm.ROLE_INSTALLER)
        for parent in (executable, *executable.parents)
    }

    def stat(path, *args, **kwargs):
        if path in checked_paths:
            return SimpleNamespace(st_mode=0o100755, st_uid=0)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(restore_pm.Path, "resolve", resolve)
    monkeypatch.setattr(restore_pm.Path, "stat", stat)
    monkeypatch.setattr(restore_pm.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=1001))
    monkeypatch.setattr(restore_pm.os, "getuid", lambda: 1000)
    return api_calls, role_calls


def test_restores_existing_pm_with_exact_scoped_expiry(monkeypatch):
    api_calls, role_calls = _setup(monkeypatch)

    principal, expiry = restore_pm.restore(
        PROJECT_ID,
        PRINCIPAL,
        api_url="http://127.0.0.1:8001",
        ceo_token="ceo-secret",
        grant_expiry=EXPIRY,
    )

    assert principal == PRINCIPAL
    assert expiry == datetime.fromisoformat(EXPIRY).astimezone(UTC)
    assert [call[2] for call in role_calls] == ["check", "install", "verify"]
    assert all(call[0] == "aao-pm" and call[3] == "pm" for call in role_calls)
    assert api_calls[2][2]["capability"] == restore_pm.ISSUER_GRANT
    assert api_calls[2][2]["principal_id"] == PRINCIPAL
    assert api_calls[-1][1] == "POST" and api_calls[-1][0].endswith("/rotate")
    assert "secret-1" not in repr(api_calls)


def test_existing_issuer_grant_is_reused_without_post(monkeypatch):
    _, role_calls = _setup(monkeypatch)
    api_calls = []
    grants = _grant_rows(include_issuer=True)

    def request_json(api, path, *, method="GET", ceo_token=None, body=None):
        api_calls.append((path, method, body))
        if path == "/v1/projects":
            return _project_rows()
        if path.endswith("/grants"):
            return list(grants)
        if path.endswith("/rotate"):
            return {"principal_id": PRINCIPAL, "kind": "AGENT", "token": "secret-1"}
        return None

    monkeypatch.setattr(restore_pm.common, "request_json", request_json)
    restore_pm.restore(
        PROJECT_ID,
        PRINCIPAL,
        api_url="http://localhost:8001",
        ceo_token="ceo-secret",
        grant_expiry=EXPIRY,
    )
    assert not any(method == "POST" and path.endswith("/grants") for path, method, _ in api_calls)
    assert [call[2] for call in role_calls] == ["check", "install", "verify"]


def test_failed_install_rotates_again_and_restores_pm_token(monkeypatch):
    api_calls, role_calls = _setup(monkeypatch, install_fails=True)

    with pytest.raises(restore_pm.ProvisionError, match="role token helper failed"):
        restore_pm.restore(
            PROJECT_ID,
            PRINCIPAL,
            api_url="http://127.0.0.1:8001",
            ceo_token="ceo-secret",
            grant_expiry=EXPIRY,
        )

    assert [call[2] for call in role_calls] == ["check", "install", "remove", "install", "verify"]
    assert [call[1] for call in api_calls if call[0].endswith("/rotate")] == ["POST", "POST"]
    assert any(method == "DELETE" for _, method, _ in api_calls)
    assert "secret-1" not in repr(api_calls)
    assert "secret-2" not in repr(api_calls)


def test_recovery_install_failure_is_reported_and_cleanup_attempted(monkeypatch):
    api_calls, role_calls = _setup(monkeypatch, install_fails=True, recovery_fails=True)
    with pytest.raises(restore_pm.ProvisionError, match="CEO must rotate and reinstall"):
        restore_pm.restore(
            PROJECT_ID,
            PRINCIPAL,
            api_url="http://127.0.0.1:8001",
            ceo_token="ceo-secret",
            grant_expiry=EXPIRY,
        )
    assert ("aao-pm", "secret-2", "remove", "pm") in role_calls
    assert any(
        method == "DELETE" and path.endswith(restore_pm.ISSUER_GRANT)
        for path, method, _ in api_calls
    )


def test_sudo_path_is_absolute_and_root_validated(monkeypatch):
    real_helper = restore_pm._role_helper
    _setup(monkeypatch)
    monkeypatch.setattr(restore_pm, "_role_helper", real_helper)
    calls = []
    monkeypatch.setattr(
        restore_pm.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs))
    )
    restore_pm._role_helper("aao-pm", token="sensitive", operation="install")
    assert calls[0][0][0] == "/usr/bin/sudo"
    assert calls[0][1]["input"] == "sensitive\n"


def test_ambiguous_grant_post_is_reconciled_and_revoked(monkeypatch):
    api_calls, role_calls = _setup(monkeypatch)
    original = restore_pm.common.request_json
    failed_once = False

    def request_json(api, path, *, method="GET", ceo_token=None, body=None):
        nonlocal failed_once
        if method == "POST" and path.endswith("/grants") and not failed_once:
            failed_once = True
            original(api, path, method=method, ceo_token=ceo_token, body=body)
            raise TimeoutError("response lost after commit")
        result = original(api, path, method=method, ceo_token=ceo_token, body=body)
        if failed_once and method == "GET" and path.endswith("/grants"):
            for row in result:
                if row.get("capability") == restore_pm.ISSUER_GRANT:
                    row["expires_at"] = row["expires_at"].replace("+00:00", "Z")
        return result

    monkeypatch.setattr(restore_pm.common, "request_json", request_json)
    with pytest.raises(restore_pm.ProvisionError, match="restoration failed"):
        restore_pm.restore(
            PROJECT_ID,
            PRINCIPAL,
            api_url="http://127.0.0.1:8001",
            ceo_token="ceo-secret",
            grant_expiry=EXPIRY,
        )
    assert any(
        method == "DELETE" and path.endswith(restore_pm.ISSUER_GRANT)
        for path, method, _ in api_calls
    )
    assert not any(path.endswith("/rotate") for path, _, _ in api_calls)
    assert [call[2] for call in role_calls] == ["check"]


def test_cli_rejects_arbitrary_python_override():
    with pytest.raises(SystemExit):
        restore_pm.main(
            ["--project-id", PROJECT_ID, "--principal-id", PRINCIPAL, "--python", "/tmp/evil"]
        )


@pytest.mark.parametrize(
    "api_url,principal_id,expiry",
    [
        ("https://example.com", PRINCIPAL, EXPIRY),
        ("http://127.0.0.1:8001", "other-principal", EXPIRY),
        ("http://127.0.0.1:8001", PRINCIPAL, "2030-01-01T00:00:00"),
    ],
)
def test_rejects_unsafe_api_or_identity_before_calls(monkeypatch, api_url, principal_id, expiry):
    api_calls, _ = _setup(monkeypatch)
    with pytest.raises(restore_pm.ProvisionError):
        restore_pm.restore(
            PROJECT_ID,
            principal_id,
            api_url=api_url,
            ceo_token="ceo-secret",
            grant_expiry=expiry,
        )
    assert api_calls == []
