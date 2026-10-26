from urllib.error import HTTPError

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


def test_bootstrap_requires_preexisting_confirmed_mandate_without_writes(monkeypatch):
    calls = []

    def no_mandates(_base_url, path, *, method="GET", ceo_token=None, **_):
        calls.append((method, path))
        assert ceo_token == "local-ceo-secret"
        assert method == "GET"
        assert path == "/v1/mandates"
        return []

    monkeypatch.setattr(bootstrap, "request_json", no_mandates)
    try:
        bootstrap.ensure_mandated_project(
            "http://127.0.0.1:8001", "local-ceo-secret",
        )
    except bootstrap.BootstrapError as exc:
        assert "will not create or confirm" in str(exc)
    else:
        raise AssertionError("bootstrap must not create or confirm a mandate")
    assert calls == [("GET", "/v1/mandates")]


def test_bootstrap_refuses_draft_mandate_without_confirmation_write(monkeypatch):
    draft = mandate_record()
    draft["status"] = "DRAFT"
    calls = []

    def draft_inventory(_base_url, path, *, method="GET", ceo_token=None, **_):
        calls.append((method, path))
        assert method == "GET"
        assert path == "/v1/mandates"
        return [draft]

    monkeypatch.setattr(bootstrap, "request_json", draft_inventory)
    try:
        bootstrap.ensure_mandated_project(
            "http://127.0.0.1:8001", "local-ceo-secret",
        )
    except bootstrap.BootstrapError as exc:
        assert "will not confirm it" in str(exc)
    else:
        raise AssertionError("bootstrap must not confirm a draft mandate")
    assert calls == [("GET", "/v1/mandates")]


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
