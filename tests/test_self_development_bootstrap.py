import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError

import pytest

from scripts import bootstrap_self_dev_agent as bootstrap


def mandate_record(*, project=None, include_project_event=False):
    mandate_id = "mandate-1"
    events = [
        {"id": "event-draft", "subject_id": mandate_id, "kind": "mandate.drafted"},
        {"id": "event-confirmed", "subject_id": mandate_id, "kind": "mandate.confirmed"},
    ]
    if include_project_event:
        events.append({"id": "event-project", "subject_id": "project-1",
                       "kind": "project.created"})
    return {
        "id": mandate_id,
        "title": bootstrap.MANDATE_TITLE,
        "objective": bootstrap.MANDATE_OBJECTIVE,
        "status": "CONFIRMED",
        "project": project,
        "events": events,
    }


def test_bootstrap_registers_and_confirms_mandate_and_project_idempotently(monkeypatch):
    project = {"id": "project-1", "name": bootstrap.PROJECT_NAME, "state": "ACTIVE"}
    record = mandate_record(project=project, include_project_event=True)
    calls = []
    inventories = iter(([], [mandate_record()], [record]))

    def fake_request(_base_url, path, *, method="GET", ceo_token=None, body=None, **_):
        calls.append((method, path, body))
        assert ceo_token == "local-ceo-secret"
        if method == "GET":
            return next(inventories)
        if path == "/v1/mandates":
            return {"id": "mandate-1", "status": "DRAFT"}
        if path == "/v1/mandates/mandate-1/confirm":
            return {"id": "mandate-1", "status": "CONFIRMED"}
        if path == "/v1/projects":
            return {"id": "project-1", "state": "ACTIVE"}
        raise AssertionError(f"Unexpected bootstrap request: {method} {path}")

    monkeypatch.setattr(bootstrap, "request_json", fake_request)
    mandate, actual_project = bootstrap.ensure_mandated_project(
        "http://127.0.0.1:8001", "local-ceo-secret",
    )
    assert mandate["id"] == "mandate-1"
    assert actual_project == project
    assert [call[1] for call in calls if call[0] == "POST"] == [
        "/v1/mandates", "/v1/mandates/mandate-1/confirm", "/v1/projects",
    ]


def test_bootstrap_reuses_verified_existing_project_without_writes(monkeypatch):
    project = {"id": "project-1", "name": bootstrap.PROJECT_NAME, "state": "ACTIVE"}
    record = mandate_record(project=project, include_project_event=True)
    calls = []

    def fake_request(_base_url, path, *, method="GET", ceo_token=None, **_):
        calls.append((method, path))
        assert path == "/v1/mandates"
        return [record]

    monkeypatch.setattr(bootstrap, "request_json", fake_request)
    mandate, actual_project = bootstrap.ensure_mandated_project(
        "http://127.0.0.1:8001", "local-ceo-secret",
    )
    assert mandate["id"] == "mandate-1"
    assert actual_project == project
    assert calls == [("GET", "/v1/mandates"), ("GET", "/v1/mandates")]


def test_bootstrap_matches_confirmed_runtime_mandate_wording_without_mutation(monkeypatch):
    """The bootstrap contract must match the CEO-confirmed persisted record."""
    mandate = mandate_record(
        project={
            "id": "project-1",
            "name": "AAO — Self Development",
            "state": "ACTIVE",
        },
        include_project_event=True,
    )
    mandate["objective"] = (
        "Build the minimum functional AAO core that can manage, develop, test, "
        "audit, and improve AAO software as its first project, observable from "
        "AAO Control Center using authentic shared backend state."
    )
    calls = []

    def authorized_read(_base_url, path, *, method="GET", **_kwargs):
        calls.append((method, path))
        return [mandate]

    monkeypatch.setattr(bootstrap, "request_json", authorized_read)
    result, project = bootstrap.ensure_mandated_project(
        "http://127.0.0.1:8001", "non-displayed-test-token",
    )

    assert result["id"] == "mandate-1"
    assert project["name"] == "AAO — Self Development"
    assert calls == [("GET", "/v1/mandates"), ("GET", "/v1/mandates")]


def test_request_json_explains_stale_api_method_mismatch(monkeypatch):
    def stale_api(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:8001/v1/mandates", 405,
                        "Method Not Allowed", {}, None)

    monkeypatch.setattr(bootstrap, "urlopen", stale_api)
    try:
        bootstrap.request_json("http://127.0.0.1:8001", "/v1/mandates")
    except bootstrap.BootstrapError as exc:
        assert "restart it from the current checkout" in str(exc)
    else:
        raise AssertionError("expected stale API method mismatch to fail closed")


def test_request_json_ignores_proxy_env_and_refuses_redirects(monkeypatch):
    hits = {"api": [], "proxy": []}

    class Proxy(BaseHTTPRequestHandler):
        def do_GET(self):
            hits["proxy"].append(self.path)
            self.send_response(502)
            self.end_headers()

        def log_message(self, *_args):
            pass

    class Api(Proxy):
        def do_GET(self):
            hits["api"].append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{proxy.server_port}/stolen")
                self.end_headers()
                return
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    servers = [HTTPServer(("127.0.0.1", 0), cls) for cls in (Api, Proxy)]
    api, proxy = servers
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for name in ("no_proxy", "NO_PROXY"):
            monkeypatch.delenv(name, raising=False)
        for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
            monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.server_port}")
        base = f"http://127.0.0.1:{api.server_port}"
        assert bootstrap.request_json(base, "/ok", ceo_token="ceo-secret") == {"ok": True}
        with pytest.raises(bootstrap.BootstrapError, match="HTTP 302"):
            bootstrap.request_json(base, "/redirect", ceo_token="ceo-secret")
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    assert hits == {"api": ["/ok", "/redirect"], "proxy": []}


def test_configured_ceo_token_refuses_inherited_override(monkeypatch):
    monkeypatch.setenv("AAO_ENV", "development")
    monkeypatch.setenv("AAO_CEO_TOKEN", "inherited-secret")
    try:
        bootstrap.configured_local_ceo_token()
    except bootstrap.BootstrapError as exc:
        assert "already inherited" in str(exc)
        assert "inherited-secret" not in str(exc)
    else:
        raise AssertionError("expected ambiguous credential source to fail closed")


def test_bootstrap_reuses_supplied_ceo_credential_without_prompt(monkeypatch, tmp_path):
    token_path = tmp_path / "agent.token"
    project = {"id": "project-1", "name": bootstrap.PROJECT_NAME, "state": "ACTIVE"}
    mandate = {"id": "mandate-1"}
    monkeypatch.setattr(bootstrap, "private_runtime_file", lambda: token_path)
    monkeypatch.setattr(bootstrap, "ensure_mandated_project", lambda *_: (mandate, project))
    monkeypatch.setattr(
        bootstrap.getpass, "getpass",
        lambda *_: (_ for _ in ()).throw(AssertionError("credential prompted twice")),
    )
    calls = []

    def fake_request(_base_url, path, *, method="GET", ceo_token=None,
                     agent_token=None, body=None):
        calls.append((method, path))
        if agent_token:
            assert ceo_token is None
        else:
            assert ceo_token == "hidden-ceo-token"
        if path.endswith("/grants") and method == "GET":
            return []
        if path == "/v1/principals/credentials":
            return {"principal_id": body["principal_id"], "token": "hidden-agent-token"}
        if path.endswith("/grants") and method == "POST":
            return {"created": True}
        if path == "/v1/projects" and agent_token:
            return [project]
        raise AssertionError(f"unexpected API call: {method} {path}")

    monkeypatch.setattr(bootstrap, "request_json", fake_request)
    monkeypatch.setattr(bootstrap, "write_private_token", lambda path, _token: path.touch())

    principal, mandate_id, project_id, expiry, result_path = bootstrap.bootstrap(
        "http://127.0.0.1:8001", ceo_token="hidden-ceo-token",
    )

    assert principal.startswith("aao-selfdev-")
    assert (mandate_id, project_id, result_path) == ("mandate-1", "project-1", token_path)
    assert expiry.tzinfo is not None
    assert [path for method, path in calls if method == "POST" and path.endswith("/grants")] == [
        "/v1/projects/project-1/grants"
    ] * len(bootstrap.GRANTS)
