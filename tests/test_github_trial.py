from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

import pytest

from aao import github_app_auth as auth
from aao import github_trial as trial


@pytest.fixture(autouse=True)
def trial_env(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_REPOS", "org/trial")
    monkeypatch.setenv("AAO_GITHUB_API_ALLOW_TEST", "1")


class FakeGitHub(BaseHTTPRequestHandler):
    calls: ClassVar[list] = []
    responses: ClassVar[dict] = {}

    def log_message(self, *_args):
        return

    def do_GET(self):
        self._reply("GET", self.path)

    def do_POST(self):
        self._reply("POST", self.path)

    def do_PUT(self):
        self._reply("PUT", self.path)

    def do_PATCH(self):
        self._reply("PATCH", self.path)

    def do_DELETE(self):
        self._reply("DELETE", self.path)

    def _reply(self, method, path):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))) if self.headers.get("Content-Length") else b""
        FakeGitHub.calls.append((method, path, bool(self.headers.get("Authorization")), body))
        status, payload = FakeGitHub.responses.get((method, path), (404, {"message": "not found"}))
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def api_server(monkeypatch):
    FakeGitHub.calls = []
    FakeGitHub.responses = {
        ("GET", "/repos/org/trial/installation"): (200, {"id": 901}),
        ("POST", "/app/installations/901/access_tokens"): (201, {"token": "never-store-this-token", "expires_at": "2030-01-01T00:00:00Z"}),
        ("GET", "/installation"): (200, {"id": 901}),
        ("DELETE", "/installation/token"): (204, {}),
    }
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
    except PermissionError:
        # Keep the auth flow testable in network-restricted sandboxes that deny bind().
        class FakeResponse:
            def __init__(self, status, payload):
                self.status, self.headers = status, {}
                self._body = json.dumps(payload).encode()

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(request, timeout=None):
            method, path = request.get_method(), urlparse(request.full_url).path
            FakeGitHub.calls.append((method, path, bool(request.get_header("Authorization")), request.data or b""))
            status, payload = FakeGitHub.responses[(method, path)]
            return FakeResponse(status, payload)

        monkeypatch.setattr(auth.urllib.request, "urlopen", fake_urlopen)
        class FakeOpener:
            def open(self, request, timeout=None):
                return fake_urlopen(request, timeout)
        monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *_handlers: FakeOpener())
        yield "http://mock.invalid"
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_jwt_well_formed_and_signature_verifies(tmp_path):
    key = tmp_path / "private.pem"
    pub = tmp_path / "public.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(pub)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    jwt = auth.create_jwt(12345, key, now=1_800_000_000)
    header, payload, signature = jwt.split(".")
    pad = lambda x: x + "=" * (-len(x) % 4)
    assert json.loads(base64.urlsafe_b64decode(pad(header))) == {"alg": "RS256", "typ": "JWT"}
    claims = json.loads(base64.urlsafe_b64decode(pad(payload)))
    assert claims == {"iat": 1_799_999_940, "exp": 1_800_000_540, "iss": "12345"}
    signed, sig = tmp_path / "signed", tmp_path / "sig"
    signed.write_text(f"{header}.{payload}", encoding="ascii")
    sig.write_bytes(base64.urlsafe_b64decode(pad(signature)))
    subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig), str(signed)], check=True, capture_output=True)


def test_token_is_memory_only_and_not_printed(tmp_path, monkeypatch, api_server, capsys):
    key = tmp_path / "app.pem"
    key.write_text("not used for this API token test")
    client = object.__new__(auth.GitHubAppClient)
    client.app_id, client._key_path, client.api_base, client.timeout = 77, key, api_server, 5
    client._installation_token = None
    monkeypatch.setattr(auth, "create_jwt", lambda *_: "jwt-for-test")
    token = client.installation_token("org", "trial")
    assert token == "never-store-this-token"
    assert client.request("GET", "/installation").status == 200
    client.close()
    assert capsys.readouterr().out == ""
    assert not list(tmp_path.glob("*token*"))
    assert all("never-store-this-token" not in str(call) for call in FakeGitHub.calls)
    assert all(call[2] for call in FakeGitHub.calls)
    assert json.loads(FakeGitHub.calls[1][3]) == {"repository_names": ["trial"]}
    assert FakeGitHub.calls[-1][1] == "/installation/token"


def test_installation_token_can_be_unrestricted_for_scope_audit(tmp_path, monkeypatch, api_server):
    key = tmp_path / "app.pem"
    key.write_text("not used for this API token test")
    client = object.__new__(auth.GitHubAppClient)
    client.app_id, client._key_path, client.api_base, client.timeout = 77, key, api_server, 5
    client._installation_token = None
    monkeypatch.setattr(auth, "create_jwt", lambda *_: "jwt-for-test")
    assert client.installation_token("org", "trial", repository_names=False) == "never-store-this-token"
    assert json.loads(FakeGitHub.calls[1][3]) == {}


def test_rejects_wrong_uid(monkeypatch):
    monkeypatch.setattr(trial, "ROLE_NAMES", {"aao-impl-codex"})
    monkeypatch.setattr(trial.pwd, "getpwnam", lambda _role: type("Entry", (), {"pw_uid": os.getuid() + 1000})())
    with pytest.raises(auth.GitHubAuthError, match="does not match role"):
        trial.validate_role_uid("aao-impl-codex")


class DummyClient:
    _installation_token = "test"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        response = next(self.replies)
        return auth.APIResponse(response[0], response[1], {})

    def app_request(self, method, path, body=None):
        self.calls.append(("app " + method, path, body))
        response = next(self.replies)
        return auth.APIResponse(response[0], response[1], {})


def _promotion_replies(*, audit_app_id=77):
    base, head, tree, merge = "a" * 40, "b" * 40, "c" * 40, "d" * 40
    return [
        (200, [{"number": 8, "head": {"sha": head}}]),
        (200, {"number": 8, "head": {"sha": head}, "base": {"ref": "main"}}),
        (200, {"object": {"sha": base}}),
        (200, {"id": 77, "owner": {"login": "autoaiorg"}}),
        (200, {"check_runs": [
            {"name": "aao-audit", "app": {"id": audit_app_id}, "status": "completed", "conclusion": "success"},
            {"name": "test", "app": {"id": 1}, "status": "completed", "conclusion": "success"},
        ]}),
        (200, {"data": {"updateRefs": {"refs": [{"name": "refs/heads/main"}]}}}),
        (200, {"object": {"sha": merge}}),
        (200, {"sha": merge, "tree": {"sha": tree}, "parents": [{"sha": base}, {"sha": head}]}),
        (200, {"merged": True}),
    ]


def _fake_git(monkeypatch):
    tree, merge = "c" * 40, "d" * 40

    def run(args, **_kwargs):
        return type("Result", (), {"stdout": tree + "\n" if "merge-tree" in args else merge + "\n"})()

    monkeypatch.setattr(trial.subprocess, "run", run)
    monkeypatch.setattr(trial, "_git_push", lambda *_args, **_kwargs: {"status": 0, "response": "push accepted"})


@pytest.mark.parametrize("test_id", ["A-05", "P3-06"])
def test_authorized_promotion_uses_update_refs_never_merge_endpoint(monkeypatch, test_id):
    _fake_git(monkeypatch)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PR", "8")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PR_HEAD", "b" * 40)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PHASE", "stage")
    monkeypatch.setattr(trial, "CHECK_WAIT_SECONDS", 1)
    client = DummyClient(_promotion_replies())
    status, _, evidence = trial.run_test(test_id, "org", "trial", "aao-integrator", client)
    assert status == "STAGED"
    assert not any(method == "PUT" and path.endswith("/merge") for method, path, _ in client.calls)
    assert not any(method == "POST" and path == "/graphql" for method, path, _ in client.calls)
    assert any(item.get("method", "").startswith("git merge-tree") for item in evidence)
    assert any(item.get("method") == "staged merge commit" and item.get("sha") == "d" * 40 for item in evidence)


@pytest.mark.nt("NT-02-5")
def test_authorized_promotion_fails_for_wrong_audit_app(monkeypatch):
    monkeypatch.setattr(trial, "CHECK_WAIT_SECONDS", 1)
    client = DummyClient([(200, {"id": 77, "owner": {"login": "autoaiorg"}}),
                          (200, {"check_runs": [{"name": "aao-audit", "app": {"id": 999}, "status": "completed", "conclusion": "success"}]})])
    ok, reason = trial._wait_required_checks(client, "/repos/org/trial", "d" * 40, [])
    assert not ok and "app_id 999" in reason


def test_push_client_failure_is_not_misreported_as_permission_rejection(monkeypatch):
    client = DummyClient([(200, {"object": {"sha": "a" * 40}}), (200, {"object": {"sha": "a" * 40}})])
    monkeypatch.setattr(trial, "_git_push", lambda *_args, **_kwargs: {"status": 1, "exit_code": 128, "server_rejected": False, "response": "Could not resolve host"})
    status, _, _ = trial.run_test("A-01", "org", "trial", "aao-impl-codex", client)
    assert status == "FAIL"


def test_a03_rejects_unrelated_graphql_error(monkeypatch):
    monkeypatch.setattr(trial.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {"stdout": "b" * 40})())
    monkeypatch.setattr(trial, "_git_push", lambda *_args, **_kwargs: {"exit_code": 0, "status": 0})
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (True, "green"))
    client = DummyClient([
        (200, {"object": {"sha": "a" * 40}}),
        (200, {"data": {"updateRefs": {"refs": [{"name": "main"}]}}}),
        (200, {"object": {"sha": "b" * 40}}),
        (200, {"errors": [{"message": "internal server error"}]}),
        (200, {"object": {"sha": "b" * 40}}),
    ])
    status, _, _ = trial.run_test("A-03", "org", "trial", "aao-integrator", client)
    assert status == "FAIL"


def test_p3_03_wrong_http_reason_is_fail(monkeypatch):
    monkeypatch.setattr(trial.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {"stdout": "b" * 40})())
    monkeypatch.setattr(trial, "_git_push", lambda *_args, **_kwargs: {"exit_code": 0, "status": 0})
    client = DummyClient([(200, {"object": {"sha": "a" * 40}}), (403, {"message": "Resource not accessible"}), (200, {"object": {"sha": "a" * 40}})])
    status, _, _ = trial.run_test("P3-03", "org", "trial", "aao-integrator", client)
    assert status == "FAIL"


def test_a10_wrong_installation_permissions_is_fail():
    client = DummyClient([(200, {"fork": False}),
                          (200, {"permissions": {"contents": "write", "metadata": "read", "administration": "write"}})])
    status, _, _ = trial.run_test("A-10", "org", "trial", "aao-impl-codex", client)
    assert status == "FAIL"


def test_a10_installation_lookup_uses_app_jwt_and_404_is_inconclusive():
    client = DummyClient([(200, {"fork": False}), (404, {"message": "Not Found"})])
    status, _, evidence = trial.run_test("A-10", "org", "trial", "aao-auditor", client)
    assert status == "INCONCLUSIVE"
    assert client.calls == [("GET", "/repos/org/trial", None),
                            ("app GET", "/repos/org/trial/installation", None)]
    assert evidence[-1] == {"method": "GET", "path": "/repos/org/trial/installation",
                            "status": 404, "response": {"message": "Not Found"}}


def test_permission_tables_match_p2_manifest_values():
    """Pin corrected P2 manifest defaults and the narrower implementer fork scope offline."""
    assert trial.EXPECTED_PERMISSIONS["aao-auditor"] == {
        "contents": "read", "pull_requests": "read", "checks": "write",
        "statuses": "write", "metadata": "read",
    }
    assert trial.EXPECTED_PERMISSIONS["aao-auditor-alt"] == trial.EXPECTED_PERMISSIONS["aao-auditor"]
    assert trial.EXPECTED_PERMISSIONS["aao-pm"] == {
        "issues": "write", "pull_requests": "write", "contents": "read", "metadata": "read",
    }
    expected_fork = {"contents": "write", "workflows": "write", "metadata": "read"}
    for role in ("aao-impl-codex", "aao-impl-claude", "aao-impl-agy"):
        assert trial.EXPECTED_PERMISSIONS[role] == {
            "contents": "write", "pull_requests": "write", "workflows": "write", "metadata": "read",
        }
        assert trial.FORK_PERMISSIONS[role] == expected_fork
        assert "pull_requests" not in trial.FORK_PERMISSIONS[role]


def test_a10_implementer_on_trial_canonical_fails_even_with_read_only_permissions():
    """P2 §4 makes the trial repo canonical: implementers must be absent, not merely read-only."""
    client = DummyClient([(200, {"fork": False})])
    status, _, _ = trial.run_test("A-10", "org", "trial", "aao-impl-codex", client)
    assert status == "FAIL"
    assert [call[1] for call in client.calls] == ["/repos/org/trial"]


def test_default_branch_delete_is_not_run():
    status, reason, evidence = trial.run_test("P3-08", "org", "trial", "aao-integrator", DummyClient([]))
    assert status == "NOT RUN"
    assert "Default-branch" in reason
    assert not evidence


def test_a14_requires_implementer_on_fork():
    status, reason, _ = trial.run_test("A-14", "org", "trial", "aao-notifier", DummyClient([]))
    assert status == "NOT RUN"
    assert "implementer App" in reason


def test_disallowed_repo_has_no_api_or_git_side_effects(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_REPOS", "org/another")
    client = DummyClient([])
    status, _, evidence = trial.run_test("A-01", "org", "trial", "aao-impl-codex", client)
    assert status == "NOT RUN"
    assert client.calls == []
    assert evidence == []


def test_push_classifier_requires_server_reason_and_unchanged_state():
    assert trial._push_rejection_pass({"exit_code": 1, "server_rejected": True,
                                      "response": "remote: protected branch hook declined"}, True)
    assert not trial._push_rejection_pass({"exit_code": 1, "server_rejected": False,
                                           "response": "fatal: could not resolve host"}, True)
    assert not trial._push_rejection_pass({"exit_code": 1, "server_rejected": True,
                                           "response": "remote: protected branch hook declined"}, False)


@pytest.mark.parametrize(("stderr", "expected"), [
    (" ! [rejected]        HEAD -> main (non-fast-forward)\nerror: failed to push some refs", False),
    (" ! [rejected]        main -> main (stale info)\nerror: failed to push some refs", False),
    (" ! [remote rejected] HEAD -> main (protected branch hook declined)\nerror: failed to push some refs", True),
    ("remote: error: GH013: repository rule violations found for refs/heads/main.\n! [remote rejected] HEAD -> main (push declined)", True),
])
def test_git_push_classifies_real_client_and_server_transcripts(monkeypatch, stderr, expected):
    monkeypatch.setattr(trial.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {"returncode": 1, "stderr": stderr.encode()})())
    result = trial._git_push(type("Client", (), {"_installation_token": "unique-test-token"})(), "org/trial", "HEAD:refs/heads/main")
    assert result["server_rejected"] is expected


@pytest.mark.parametrize(("stderr", "expected"), [
    (" ! [rejected] main -> main (stale info)\nerror: failed to push some refs", False),
    (" ! [rejected] main -> main (non-fast-forward)\nerror: failed to push some refs", False),
    (" ! [remote rejected] main -> main (protected branch hook declined)\nerror: failed to push some refs", True),
    ("remote: error: GH013: Repository rule violations found for refs/heads/main", True),
])
def test_push_rejection_regex_distinguishes_client_and_server(stderr, expected):
    assert trial._is_server_rejection(stderr) is expected


def _push_record(refspec, response, *, code=1, server=True):
    return {"method": "git push", "refspec": refspec, "exit_code": code,
            "status": 0 if code == 0 else 1, "server_rejected": server, "response": response}


class RefClient(DummyClient):
    def __init__(self, refs):
        super().__init__([])
        self.refs = refs

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        status, payload = self.refs[path].pop(0)
        return auth.APIResponse(status, payload, {})


def _ref_reply(sha):
    return (200, {"object": {"sha": sha}})


def test_a01_implementer_passes_only_server_push_denial_and_unchanged_main(monkeypatch):
    before = "a" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [_ref_reply(before), _ref_reply(before)]})
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "HEAD:refs/heads/main", "! [remote rejected] HEAD -> main (protected branch hook declined)"))
    status, reason, _evidence = trial.run_test("A-01", "org", "trial", "aao-impl-codex", client)
    assert status == "FAIL"
    assert "explicit equivalence mode" in reason
    assert not client.calls


@pytest.mark.parametrize("test_id", ["A-01", "A-02", "P3-02"])
def test_equivalence_sensitive_tests_never_pass_without_equivalence_mode(test_id):
    status, _, _ = trial.run_test(test_id, "org", "trial", "aao-impl-codex", DummyClient([]))
    assert status == "FAIL"


def test_a04_never_claims_server_rejection_from_stale_lease_client_result(monkeypatch):
    old, moved = "a" * 40, "b" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [
        _ref_reply(old), _ref_reply(moved), _ref_reply(moved),
    ]})
    pushes = iter([
        _push_record("local:refs/heads/aao-trial/stale-lease", "To github\n * [new branch]", code=0, server=False),
        _push_record("old:refs/heads/main", "! [remote rejected] old -> main (non-fast-forward)")])
    monkeypatch.setattr(trial.subprocess, "run", lambda args, **_kw: type(
        "Result", (), {"stdout": moved + "\n" if args[1:3] == ["rev-parse", "HEAD"] else ""})())
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: next(pushes))
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (True, "green"))
    original_api = trial._api
    def fake_api(c, method, path, body=None):
        if method == "GET" and path == "/repos/org/trial":
            return {"method": method, "path": path, "status": 200, "response": {"node_id": "R_kgDOtrial"}}
        return original_api(c, method, path, body) if method == "GET" else {"method": method, "path": path, "status": 200,
            "response": {"data": {"updateRefs": {"refs": [{"name": "main"}]}}}}
    monkeypatch.setattr(trial, "_api", fake_api)
    status, _, evidence = trial.run_test("A-04", "org", "trial", "aao-integrator", client)
    assert status == "NOT RUN"
    assert evidence[-1]["server_side_demonstrated"] is False


def test_p3_01_ceo_pass_requires_restrict_updates_attribution(monkeypatch):
    """Direct protected-ref text remains attributable with co-occurring rules."""
    before = "a" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [_ref_reply(before), _ref_reply(before)]})
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "HEAD:refs/heads/main", "remote: error: GH013: Repository rule violations found for refs/heads/main.\n"
        "- Cannot update this protected ref.\n- Changes must be made through a pull request.\n"
        "- 2 of 2 required status checks are expected."))
    assert trial.run_test("P3-01", "org", "trial", "ceo", client)[0] == "PASS"


def test_p3_01_generic_gh013_is_inconclusive(monkeypatch):
    before = "a" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [_ref_reply(before), _ref_reply(before)]})
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "HEAD:refs/heads/main", "remote: error: GH013: Repository rule violations"))
    assert trial.run_test("P3-01", "org", "trial", "ceo", client)[0] == "INCONCLUSIVE"


def test_p3_01_permission_denied_is_not_ruleset_evidence(monkeypatch):
    before = "a" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [_ref_reply(before), _ref_reply(before)]})
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "HEAD:refs/heads/main", "remote: Permission to org/trial.git denied to app"))
    assert trial.run_test("P3-01", "org", "trial", "ceo", client)[0] == "INCONCLUSIVE"


def test_p3_01_ruleset_name_does_not_override_failed_required_checks(monkeypatch):
    before = "a" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [_ref_reply(before), _ref_reply(before)]})
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "HEAD:refs/heads/main", "remote: GH013: Restrict updates and required status checks aao-audit failed"))
    assert trial.run_test("P3-01", "org", "trial", "ceo", client)[0] == "INCONCLUSIVE"


def test_required_status_check_text_is_attributable_even_with_http_422():
    response = "Repository rule violations found\n\n2 of 2 required status checks are expected.\n\n"
    assert trial._rejection_attributable({"response": response}, "required status check")


def test_non_fast_forward_with_required_checks_is_not_attributable():
    response = "Cannot force-push this ref.\n2 of 2 required status checks are expected."
    assert not trial._rejection_attributable({"response": response}, "non-fast-forward")


def test_generic_gh013_without_rule_message_is_not_attributable():
    assert not trial._rejection_attributable(
        {"response": "GH013: Repository rule violations found for refs/heads/main."}, "restrict updates")
    assert not trial._rejection_attributable(
        {"response": "other rule blocked by required checks"}, "some other rule")


def test_p3_03_live_required_status_check_422_is_pass(monkeypatch):
    candidate, main = "b" * 40, "a" * 40
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n"})())
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        f"{candidate}:refs/heads/aao-trial/no-audit-{candidate[:8]}", "staged", code=0, server=False))
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [
        _ref_reply(main), _ref_reply(main),
    ], "/repos/org/trial/git/refs/heads/main": [(422, {"message": "Repository rule violations found\n\n"
                                                        "2 of 2 required status checks are expected.\n\n"})]})
    status, reason, evidence = trial.run_test("P3-03", "org", "trial", "aao-integrator", client)
    assert status == "PASS" and "HTTP 422" in reason
    assert any(record.get("status") == 422 for record in evidence)


def test_p3_07_integrator_requires_non_fast_forward_rule_for_both_refs(monkeypatch):
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (True, "passed"))
    """P3-07 is PASS only when both server denials name non_fast_forward, not required checks."""
    main, candidate = "a" * 40, "b" * 40
    base = "/repos/org/trial/git/ref/heads/"
    client = RefClient({base + "main": [_ref_reply(main), _ref_reply(main)],
                        base + "aao-staging/" + candidate[:12]: [(404, {"message": "Not Found"}),
                                                                (404, {"message": "Not Found"})]})
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n", "returncode": 1})())
    pushes = []
    def fake_push(_client, _repo, refspec, **_kwargs):
        pushes.append(refspec)
        return _push_record(refspec, "remote: GH013: non_fast_forward rule violation")
    monkeypatch.setattr(trial, "_git_push", fake_push)
    status, _, _ = trial.run_test("P3-07", "org", "trial", "aao-integrator", client)
    assert status == "PASS"
    assert pushes == [f"+{candidate}:refs/heads/main",
                      f"+{candidate}:refs/heads/aao-staging/{candidate[:12]}"]



def test_p3_07_waits_for_required_checks_before_forced_push(monkeypatch):
    main, candidate = "a" * 40, "b" * 40
    base = "/repos/org/trial/git/ref/heads/"
    client = RefClient({base + "main": [_ref_reply(main)],
                        base + "aao-staging/" + candidate[:12]: [(404, {"message": "Not Found"})]})
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n", "returncode": 1})())
    pushes = []
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (False, "checks pending"))
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: pushes.append(True))
    status, reason, _ = trial.run_test("P3-07", "org", "trial", "aao-integrator", client)
    assert (status, reason) == ("INCONCLUSIVE", "checks pending")
    assert pushes == []


def test_p3_12_waits_for_required_checks_before_push(monkeypatch):
    main, candidate = "a" * 40, "b" * 40
    base = "/repos/org/trial/git/ref/heads/main"
    client = RefClient({base: [_ref_reply(main)]})
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n", "returncode": 0})())
    monkeypatch.setattr(trial, "_is_ancestor", lambda *_a: False)
    pushes = []
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (False, "checks pending"))
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: pushes.append(True))
    status, reason, _ = trial.run_test("P3-12", "org", "trial", "aao-integrator", client)
    assert (status, reason) == ("INCONCLUSIVE", "checks pending")
    assert pushes == []

def test_p3_07_generic_ruleset_denial_is_inconclusive(monkeypatch):
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (True, "passed"))
    main, candidate = "a" * 40, "b" * 40
    base = "/repos/org/trial/git/ref/heads/"
    client = RefClient({base + "main": [_ref_reply(main), _ref_reply(main)],
                        base + "aao-staging/" + candidate[:12]: [(404, {"message": "Not Found"}),
                                                                (404, {"message": "Not Found"})]})
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n", "returncode": 1})())
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "forced", "remote: GH013: Repository rule violations"))
    assert trial.run_test("P3-07", "org", "trial", "aao-integrator", client)[0] == "INCONCLUSIVE"


def test_p3_07_non_fast_forward_name_does_not_override_failed_checks(monkeypatch):
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (True, "passed"))
    main, candidate = "a" * 40, "b" * 40
    base = "/repos/org/trial/git/ref/heads/"
    client = RefClient({base + "main": [_ref_reply(main), _ref_reply(main)],
                        base + "aao-staging/" + candidate[:12]: [(404, {"message": "Not Found"}),
                                                                (404, {"message": "Not Found"})]})
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n", "returncode": 1})())
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: _push_record(
        "forced", "remote: GH013: non_fast_forward; 2 of 2 required status checks are expected"))
    assert trial.run_test("P3-07", "org", "trial", "aao-integrator", client)[0] == "INCONCLUSIVE"


def test_p3_07_implementer_uses_a01_not_p3_07():
    client = DummyClient([])
    status, _, evidence = trial.run_test("P3-07", "org", "trial", "aao-impl-codex", client)
    assert status == "NOT RUN"
    assert not client.calls and not evidence


def test_p3_12_forced_non_fast_forward_must_be_server_rejected(monkeypatch):
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (True, "passed"))
    main, candidate = "a" * 40, "b" * 40
    client = RefClient({"/repos/org/trial/git/ref/heads/main": [_ref_reply(main), _ref_reply(main)]})
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type(
        "Result", (), {"stdout": candidate + "\n", "returncode": 1})())
    calls = []
    monkeypatch.setattr(trial, "_git_push", lambda _c, _r, spec, **kw: (
        calls.append((spec, kw)) or _push_record(spec,
        "! [remote rejected] HEAD -> main (non-fast-forward update rejected by ruleset)")))
    status, _, _ = trial.run_test("P3-12", "org", "trial", "aao-integrator", client)
    assert status == "PASS"
    assert calls == [("+HEAD:refs/heads/main", {"no_verify": True})]


def test_a14_requires_workflows_permission_denial_and_accepted_control(monkeypatch):
    main, parent = "a" * 40, "b" * 40
    base = "/repos/org/trial"
    client = RefClient({base: [(200, {"fork": True, "parent": {"full_name": "org/parent"}})],
                        base + "/git/ref/heads/main": [_ref_reply(main), _ref_reply(main)]})
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORK_PARENT", "org/parent")
    monkeypatch.setattr(trial.subprocess, "run", lambda args, **_kw: type(
        "Result", (), {"stdout": ".github/workflows/ci.yml\n" if "diff-tree" in args else parent + "\n"})())
    pushes = []
    def fake_push(_client, _repo, spec, **_kw):
        pushes.append(spec)
        if spec.endswith("main"):
            return _push_record(spec, "remote: refusing to allow an OAuth App to create or update workflow without 'workflows' permission")
        return _push_record(spec, "To github\n * [new branch]", code=0, server=False)
    monkeypatch.setattr(trial, "_git_push", fake_push)
    status, _, _ = trial.run_test("A-14", "org", "trial", "aao-probe-noworkflows", client)
    assert status == "PASS"
    assert pushes == ["HEAD:refs/heads/main", f"{parent}:refs/heads/aao-trial/no-workflows-{parent[:12]}"]


def test_p3_09_ceo_pass_requires_restrict_updates_attribution():
    """A still-open PR plus generic denial is insufficient; the API message must name Restrict updates."""
    client = DummyClient([
        (200, [{"number": 9}]),
        (403, {"message": "Cannot update this protected ref."}),
        (200, {"merged": False, "state": "open"}),
    ])
    status, _, _ = trial.run_test("P3-09", "org", "trial", "ceo", client)
    assert status == "PASS"


def test_p3_09_generic_rule_violation_is_inconclusive():
    client = DummyClient([
        (200, [{"number": 9}]),
        (403, {"message": "Protected branch update failed: rule violations"}),
        (200, {"merged": False, "state": "open"}),
    ])
    assert trial.run_test("P3-09", "org", "trial", "ceo", client)[0] == "INCONCLUSIVE"


def test_p3_09_rule_name_does_not_override_failed_required_checks():
    client = DummyClient([
        (200, [{"number": 9}]),
        (403, {"message": "Restrict updates and required status checks are failing"}),
        (200, {"merged": False, "state": "open"}),
    ])
    assert trial.run_test("P3-09", "org", "trial", "ceo", client)[0] == "INCONCLUSIVE"


@pytest.mark.parametrize("error", [AttributeError("unexpected API shape"), KeyError("head")])
def test_b6_07_attribute_or_key_error_is_recorded_as_failure(monkeypatch, error):
    monkeypatch.setattr(trial, "_run_test", lambda *_a, **_k: (_ for _ in ()).throw(error))
    status, reason, evidence = trial.run_test("A-01", "org", "trial", "aao-impl-codex", DummyClient([]))
    assert status == "FAIL"
    assert type(error).__name__ in reason
    assert evidence[0]["exception"] == type(error).__name__


def test_a10_auditor_permissions_pass_on_fork_installation(monkeypatch):
    """Fork permissions apply only after API parent identity matches the configured canonical repo."""
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORK_PARENT", "org/parent")
    permissions = trial.FORK_PERMISSIONS["aao-auditor"]
    client = DummyClient([(200, {"fork": True, "parent": {"full_name": "org/parent"}}),
                          (200, {"permissions": permissions})])
    status, _, _ = trial.run_test("A-10", "org", "trial", "aao-auditor", client)
    assert status == "PASS"


@pytest.mark.parametrize("role", [
    "aao-integrator", "aao-auditor", "aao-auditor-alt", "aao-supervisor",
    "aao-notifier", "aao-pm",
])
def test_a10_non_implementer_roles_are_checked_against_canonical_column(role):
    """Every non-implementer role is evaluated against its explicit P2 permissions."""
    permissions = trial.EXPECTED_PERMISSIONS[role]
    client = DummyClient([(200, {"fork": False}), (200, {"permissions": permissions})])
    status, _, _ = trial.run_test("A-10", "org", "trial", role, client)
    assert status == "PASS"


def test_git_push_discards_trace_settings_and_redacts_stderr(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "2")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_KEY_1", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_1", "false")
    monkeypatch.setenv("GIT_TRACE_CURL", "/tmp/curl-trace.log")
    monkeypatch.setenv("GIT_TRACE_REDACT", "0")
    seen = {}
    def fake_run(args, *, env, **_kwargs):
        seen["args"], seen["env"] = args, env
        return type("Result", (), {"returncode": 1, "stderr": b"remote: permission denied secret-token"})()
    monkeypatch.setattr(trial.subprocess, "run", fake_run)
    client = type("Client", (), {"_installation_token": "secret-token"})()
    result = trial._git_push(client, "org/trial", "HEAD:refs/heads/main")
    assert "secret-token" not in " ".join(seen["args"])
    assert "GIT_TRACE_CURL" not in seen["env"]
    assert seen["env"]["GIT_TRACE_REDACT"] == "1"
    assert seen["env"]["GIT_CONFIG_COUNT"] == "3"
    assert seen["env"]["GIT_CONFIG_VALUE_0"] == "/dev/null"
    assert seen["env"]["GIT_CONFIG_VALUE_1"] == "false"
    assert seen["env"]["GIT_CONFIG_KEY_2"] == "http.extraheader"
    assert "secret-token" not in result["response"]


def test_a02_405_non_permission_rejection_fails():
    client = DummyClient([
        (200, [{"number": 4}]),
        (405, {"message": "Pull request is not mergeable"}),
        (200, {"state": "open", "merged": False}),
    ])
    status, _, _ = trial.run_test("A-02", "org", "trial", "aao-impl-codex", client)
    assert status == "FAIL"


def test_ceo_cli_identity_must_be_exact_user_and_admin(monkeypatch):
    replies = iter(["another-user\n"])
    monkeypatch.setattr(trial.subprocess, "run", lambda *_args, **_kwargs: type("Result", (), {"stdout": next(replies)})())
    with pytest.raises(auth.GitHubAuthError, match="not alessbarb"):
        trial.validate_ceo_gh_identity("org/trial")


def test_custom_api_host_requires_explicit_test_flag(monkeypatch):
    monkeypatch.setattr(auth, "load_app", lambda _role: (7, Path("/unused")))
    monkeypatch.delenv("AAO_GITHUB_API_ALLOW_TEST", raising=False)
    with pytest.raises(auth.GitHubAuthError, match="requires AAO_GITHUB_API_ALLOW_TEST"):
        auth.GitHubAppClient("aao-impl-codex", api_base="https://attacker.invalid")


def test_redirect_handler_never_forwards_credentials():
    handler = auth._NoRedirect()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://attacker.invalid") is None


def test_evidence_mode_and_redaction(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("AAO_TRIAL_RUN_ID", "trial-1")
    monkeypatch.setenv("AAO_TRIAL_HARNESS_REV", "a" * 40)
    monkeypatch.setenv("AAO_TRIAL_CANDIDATE_SHA", "b" * 40)
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    dest = trial.write_evidence("A-01", "PASS", "ok", "org/trial", "aao-impl-codex", 17,
                                [{"request": {"token": "hide"}, "response": {"ok": True}}])
    assert dest.stat().st_mode & 0o777 == 0o600
    payload = json.loads(dest.read_text())
    assert "hide" not in dest.read_text()
    assert payload["run_id"] == "trial-1"
    assert payload["harness_revision"] == "a" * 40
    assert payload["candidate_sha"] == "b" * 40
    assert "c" * 40 not in payload["shas"]


def test_explicit_audit_publication_is_auditor_only_and_trial_only(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_SHA", "a" * 40)
    denied = DummyClient([])
    status, _, _ = trial.run_test("PUBLISH-AUDIT", "autoaiorg", "aao-governance-trial", "aao-integrator", denied)
    assert status == "NOT RUN" and not denied.calls
    monkeypatch.setenv("AAO_GITHUB_TRIAL_REPOS", "")
    status, _, _ = trial.run_test("PUBLISH-AUDIT", "autoaiorg", "aao-governance-trial", "aao-auditor", DummyClient([]))
    assert status == "NOT RUN"
    monkeypatch.setenv("AAO_GITHUB_TRIAL_REPOS", "autoaiorg/aao")
    status, _, _ = trial.run_test("PUBLISH-AUDIT", "autoaiorg", "aao", "aao-auditor", DummyClient([]))
    assert status == "NOT RUN"


def test_explicit_audit_publication_records_exact_sha_and_app_id(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_SHA", "a" * 40)
    client = DummyClient([(201, {"app": {"id": 42}})])
    client.app_id = 42
    status, _, evidence = trial.run_test("PUBLISH-AUDIT", "org", "trial", "aao-auditor", client)
    assert status == "PASS"
    assert client.calls[0][2]["head_sha"] == "a" * 40
    assert client.calls[0][2]["status"] == "completed"
    assert evidence[0]["response"]["app"]["id"] == 42


def test_explicit_stage_commit_is_integrator_only_and_named_trial_branch(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_BRANCH", "aao-trial/explicit-candidate")
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type("Result", (), {"stdout": "c" * 40})())
    pushes = []
    monkeypatch.setattr(trial, "_git_push", lambda _client, repo, ref: pushes.append((repo, ref)) or {"status": 0})
    status, _, evidence = trial.run_test("STAGE-COMMIT", "org", "trial", "aao-integrator", DummyClient([]))
    assert status == "PASS" and pushes == [("org/trial", "cccccccccccccccccccccccccccccccccccccccc:refs/heads/aao-trial/explicit-candidate")]
    assert any(x.get("sha") == "c" * 40 for x in evidence)
    status, _, _ = trial.run_test("STAGE-COMMIT", "org", "trial", "aao-auditor", DummyClient([]))
    assert status == "NOT RUN"


def test_explicit_stage_commit_rejects_candidate_mismatch_before_push(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_BRANCH", "aao-trial/explicit-candidate")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_EXPECTED_SHA", "d" * 40)
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type("Result", (), {"stdout": "c" * 40})())
    pushes = []
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: pushes.append(True) or {"status": 0})
    status, reason, _ = trial.run_test("STAGE-COMMIT", "org", "trial", "aao-integrator", DummyClient([]))
    assert status == "FAIL" and "does not match runner candidate" in reason
    assert not pushes


def test_explicit_stage_commit_rejects_unsafe_branch(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_BRANCH", "refs/heads/main")
    status, reason, evidence = trial.run_test("STAGE-COMMIT", "org", "trial", "aao-integrator", DummyClient([]))
    assert status == "FAIL" and "safe named" in reason and not evidence


def test_check_wait_timeout_is_fail_closed(monkeypatch):
    monkeypatch.setattr(trial, "CHECK_WAIT_SECONDS", 0)
    client = DummyClient([(200, {"id": 42, "owner": {"login": "autoaiorg"}})])
    ok, reason = trial._wait_required_checks(client, "/repos/org/trial", "a" * 40, [])
    assert not ok and "did not become green" in reason


def test_main_moving_test_fails_without_green_candidate_checks(monkeypatch):
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type("Result", (), {"stdout": "b" * 40})())
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: {"status": 0, "exit_code": 0})
    monkeypatch.setattr(trial, "_wait_required_checks", lambda *_a: (False, "required checks did not become green"))
    client = DummyClient([(200, {"object": {"sha": "a" * 40}})])
    status, reason, _evidence = trial.run_test("A-03", "org", "trial", "aao-integrator", client)
    assert status == "FAIL" and "cannot move main" in reason
    assert not any(method == "POST" and path == "/graphql" for method, path, _ in client.calls)


def test_equivalence_is_pending_never_pass_and_rejects_wrong_role(monkeypatch):
    class EquivalenceClient(DummyClient):
        app_id = 77
        _installation_id = 901
        selection = "selected"
        def app_request(self, method, path):
            if path == "/repos/autoaiorg/aao-governance-trial/installation":
                return auth.APIResponse(404, {"message": "Not Found"}, {})
            assert method == "GET" and path == "/app/installations/901"
            return auth.APIResponse(200, {"repository_selection": self.selection}, {})
        def installation_token(self, *args, **kwargs):
            self.token_options = getattr(self, "token_options", []) + [kwargs]
            return "test"
        def revoke(self):
            return auth.APIResponse(204, {}, {})
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORKS", "autoaiorg/aao-codex,autoaiorg/aao-trial-codex")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORK", "autoaiorg/aao-trial-codex")
    monkeypatch.setenv("AAO_TRIAL_EXPECTED_REPO_ID", "123")
    monkeypatch.setenv("AAO_TRIAL_P0_EVIDENCE", json.dumps({"status": 200, "full_name": "autoaiorg/aao-governance-trial", "id": 123}))
    monkeypatch.setenv("AAO_TRIAL_P4_EVIDENCE", json.dumps({"gh_hosts_yml_absent": True, "git_credentials_absent": True, "token_environment_absent": True, "runner_environment_token_absent": True, "aao_config_exact": True, "deploy_keys_empty": True, "outside_collaborators_clear": True, "org_members_clear": True}))
    monkeypatch.setenv("AAO_TRIAL_P4B_EVIDENCE", json.dumps({"ceo_login": "alessbarb", "org_owners": ["alessbarb"], "repo_admins": ["alessbarb"]}))
    monkeypatch.setattr(trial.subprocess, "run", lambda *_a, **_k: type("Result", (), {"stdout": "b" * 40})())
    monkeypatch.setattr(trial, "_git_push", lambda *_a, **_k: {"status": 0, "exit_code": 0})
    client = EquivalenceClient([
        (200, {"total_count": 2, "repositories": [{"full_name": "autoaiorg/aao-codex"}]}),
        (200, {"total_count": 2, "repositories": [{"full_name": "autoaiorg/aao-trial-codex"}]}),
    ])
    status, _, _ = trial.run_test("EQUIVALENCE", "autoaiorg", "aao-governance-trial", "aao-impl-codex", client)
    assert status == "EQUIVALENCE-PENDING" and status != "PASS"
    assert client.token_options == [{"repository_names": False}, {}]
    assert [call[1] for call in client.calls] == ["/installation/repositories?per_page=100&page=1", "/installation/repositories?per_page=100&page=2"]
    unselected = EquivalenceClient([])
    unselected.selection = "all"
    status, _, _ = trial.run_test("EQUIVALENCE", "autoaiorg", "aao-governance-trial", "aao-impl-codex", unselected)
    assert status == "FAIL" and not unselected.calls
    status, _, _ = trial.run_test("EQUIVALENCE", "autoaiorg", "aao-governance-trial", "aao-integrator", DummyClient([]))
    assert status == "NOT RUN"


@pytest.mark.parametrize("premise, facts", [
    ("P0", {"status": 404, "full_name": "autoaiorg/aao-governance-trial", "id": 123}),
    ("P4", {"gh_hosts_yml_absent": False, "git_credentials_absent": True, "token_environment_absent": True, "runner_environment_token_absent": True,
             "aao_config_exact": True, "deploy_keys_empty": True,
             "outside_collaborators_clear": True, "org_members_clear": True}),
    ("P4b", {"org_owners": ["alessbarb", "unexpected"], "repo_admins": ["alessbarb"]}),
])
def test_equivalence_failed_premise_is_fail_and_never_pass(premise, facts):
    checks = trial.evaluate_equivalence_premises(
        {"status": 200, "full_name": "autoaiorg/aao-governance-trial", "id": 123},
        {"gh_hosts_yml_absent": True, "git_credentials_absent": True, "token_environment_absent": True, "runner_environment_token_absent": True,
         "aao_config_exact": True, "deploy_keys_empty": True,
         "outside_collaborators_clear": True, "org_members_clear": True},
        {"ceo_login": "alessbarb", "org_owners": ["alessbarb"], "repo_admins": ["alessbarb"]},
        expected_repo_id=123,
    )
    assert all(item["result"] == "PASS" for item in checks)
    if premise == "P0":
        checks = trial.evaluate_equivalence_premises(facts, {}, {}, expected_repo_id=123)
    elif premise == "P4":
        checks = trial.evaluate_equivalence_premises(
            {"status": 200, "full_name": "autoaiorg/aao-governance-trial", "id": 123}, facts,
            {"ceo_login": "alessbarb", "org_owners": ["alessbarb"], "repo_admins": ["alessbarb"]}, expected_repo_id=123)
    else:
        checks = trial.evaluate_equivalence_premises(
            {"status": 200, "full_name": "autoaiorg/aao-governance-trial", "id": 123},
            {"gh_hosts_yml_absent": True, "git_credentials_absent": True, "token_environment_absent": True, "runner_environment_token_absent": True,
             "aao_config_exact": True, "deploy_keys_empty": True,
             "outside_collaborators_clear": True, "org_members_clear": True}, facts,
            expected_repo_id=123)
    assert next(item for item in checks if item["id"] == premise)["result"] == "FAIL"
    assert not any(item["result"] == "PASS" and item["id"] == premise for item in checks)


def test_equivalence_premises_all_pass_only_while_pending():
    checks = trial.evaluate_equivalence_premises(
        {"status": 200, "full_name": "autoaiorg/aao-governance-trial", "id": 123},
        {"gh_hosts_yml_absent": True, "git_credentials_absent": True, "token_environment_absent": True, "runner_environment_token_absent": True,
         "aao_config_exact": True, "deploy_keys_empty": True,
         "outside_collaborators_clear": True, "org_members_clear": True},
        {"ceo_login": "alessbarb", "org_owners": ["alessbarb"], "repo_admins": ["alessbarb"]}, expected_repo_id=123)
    assert [item["id"] for item in checks] == ["P0", "P4", "P4b"]
    assert all(item["result"] == "PASS" for item in checks)
    assert "return \"PASS\"" not in __import__("inspect").getsource(trial._run_equivalence)


def test_equivalence_missing_premise_forces_fail_before_scope_claim(monkeypatch):
    for key in ("AAO_TRIAL_P0_EVIDENCE", "AAO_TRIAL_P4_EVIDENCE", "AAO_TRIAL_P4B_EVIDENCE", "AAO_TRIAL_EXPECTED_REPO_ID"):
        monkeypatch.delenv(key, raising=False)
    status, reason, evidence = trial.run_test(
        "EQUIVALENCE", "autoaiorg", "aao-governance-trial", "aao-impl-codex", DummyClient([]))
    assert status == "FAIL" and "P0" in reason and "P4" in reason and "P4b" in reason
    assert not any(item.get("result") == "PASS" and item.get("id") in {"P0", "P4", "P4b"}
                   for record in evidence if record.get("method") == "equivalence premises"
                   for item in record["premises"])


def test_promotion_phase_requires_staged_sha_green_checks_and_cas(monkeypatch):
    _fake_git(monkeypatch)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PR", "8")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PR_HEAD", "b" * 40)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PHASE", "promote")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PROMOTE_SHA", "d" * 40)
    client = DummyClient([
        (200, [{"number": 8, "head": {"sha": "b" * 40}}]),
        (200, {"number": 8, "head": {"sha": "b" * 40}, "base": {"ref": "main"}}),
        (200, {"object": {"sha": "a" * 40}}),
        (200, {"id": 77, "owner": {"login": "autoaiorg"}}),
        (200, {"tree": {"sha": "c" * 40}, "parents": [{"sha": "a" * 40}, {"sha": "b" * 40}]}),
        (200, {"object": {"sha": "d" * 40}}),
        (200, {"check_runs": [{"name": "aao-audit", "status": "completed", "conclusion": "success", "app": {"id": 77}}, {"name": "test", "status": "completed", "conclusion": "success", "app": {"id": 1}}]}),
        (200, {"object": {"sha": "d" * 40}}),
        (200, {"node_id": "R_kgDOtrial"}),
        (200, {"data": {"updateRefs": {"refs": [{"name": "refs/heads/main"}]}}}),
        (200, {"object": {"sha": "d" * 40}}),
        (200, {"sha": "d" * 40, "tree": {"sha": "c" * 40}, "parents": [{"sha": "a" * 40}, {"sha": "b" * 40}]}),
        (200, {"merged": True}),
    ])
    status, _, evidence = trial.run_test("A-05", "org", "trial", "aao-integrator", client)
    assert status == "PASS"
    assert any(method == "POST" and path == "/graphql" for method, path, _ in client.calls)
    mutation = next(body for method, path, body in client.calls if method == "POST" and path == "/graphql")
    assert mutation["variables"]["input"]["repositoryId"] == "R_kgDOtrial"
    assert "refs {" not in mutation["query"]
    assert any(item.get("sha") == "d" * 40 and item.get("status") == "green" for item in evidence)


def test_all_update_refs_inputs_include_repository_id():
    source = (Path(__file__).parents[1] / "src/aao/github_trial.py").read_text()
    assert source.count('"refUpdates": [{"name": "refs/heads/main"') == source.count('"repositoryId": repository_id, "refUpdates": [{"name": "refs/heads/main"')
    assert "refs {" not in source


def test_restrict_updates_attribution_lists_co_occurring_rules_and_checks_need_expected_phrase():
    from aao.github_trial import _denial_outcome, _rejection_attributable
    live = ("remote: error: GH013: Repository rule violations found for refs/heads/main.\nremote: \n"
            "remote: - Cannot update this protected ref.\nremote: \nremote: - Changes must be made through a pull request.\n"
            "remote: \nremote: - 2 of 2 required status checks are expected.\n")
    item = {"exit_code": 1, "server_rejected": True, "response": live}
    status, reason = _denial_outcome(item, True, "restrict updates", "CEO push")
    assert status == "PASS" and "Cannot update this protected ref." in reason and "2 of 2 required status checks are expected." in reason
    only_checks = {"exit_code": 1, "server_rejected": True, "response": "remote: - 2 of 2 required status checks are expected."}
    assert _denial_outcome(only_checks, True, "restrict updates", "CEO push")[0] == "INCONCLUSIVE"
    assert not _rejection_attributable({"response": "Validation failed: required status check context is invalid"}, "required status check")
    assert not _rejection_attributable({"response": "deletion of this branch is not supported here"}, "deletion")
    assert _rejection_attributable({"response": "Cannot delete this protected ref."}, "deletion")


def test_stage_merge_commit_message_is_given_on_stdin_never_inherited():
    # Without a message, git commit-tree reads the caller's stdin (the CEO terminal) and times out (live run e09a18a).
    import inspect

    from aao import github_trial
    source = inspect.getsource(github_trial)
    call = source[source.index('"commit-tree",'):][:400]
    assert 'input="AAO trial staged merge' in call
