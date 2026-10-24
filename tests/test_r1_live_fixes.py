import base64
import importlib.util
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aao import auditor_dispatch, authorization_issuer, integrator, supervisor_service
from aao.protected_routes import load_document, route_map, routes_digest


class _AttributionClient:
    def __init__(self, responses):
        self.responses = responses

    def installation_token(self, *_args):
        return "test-token"

    def request(self, _method, path):
        value = self.responses.get(path, [])
        if isinstance(value, Exception):
            raise value
        return type("Response", (), {"status": 200, "body": value})()


def test_integrator_heartbeat_sequence_is_written_under_integrator_state(tmp_path, monkeypatch):
    heartbeat = tmp_path / "heartbeat.json"
    sequence = tmp_path / "integrator" / "heartbeat.sequence"
    now = datetime.now(UTC)
    heartbeat.write_text(json.dumps({"key_id": "supervisor", "type": "heartbeat", "state_sha256": "a" * 64,
        "sequence": 1, "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=2)).isoformat(),
        "signature": base64.b64encode(b"signature").decode()}))

    class Verified:
        returncode = 0

    monkeypatch.setattr(integrator.subprocess, "run", lambda *args, **kwargs: Verified())
    event = integrator._heartbeat(heartbeat, {"supervisor_key_id": "supervisor", "supervisor_public_key": "key"},
                                  now, sequence)
    assert event["sequence"] == 1
    assert sequence.read_text() == "1"
    assert not heartbeat.with_suffix(".json.sequence").exists()


def test_promote_push_uses_app_auth_header_only_in_git_environment(monkeypatch, tmp_path):
    captured = {}

    class Result:
        returncode, stdout, stderr = 0, "", ""

    def run(argv, **kwargs):
        captured["argv"], captured["env"] = argv, kwargs["env"]
        return Result()

    monkeypatch.setattr(integrator.subprocess, "run", run)
    integrator._conditional_push(tmp_path, "https://github.com/owner/repo.git", "refs/heads/main",
                                 "b" * 40, "c" * 40, "installation-secret")
    assert "installation-secret" not in " ".join(captured["argv"])
    env = captured["env"]
    expected = "AUTHORIZATION: basic " + base64.b64encode(b"x-access-token:installation-secret").decode()
    assert env["GIT_CONFIG_VALUE_1"] == expected
    assert env["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_KEY_0"] == "credential.helper" and env["GIT_CONFIG_VALUE_0"] == ""
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == "/dev/null"


def test_dispatch_gate_path_and_file_are_group_readable_not_writable(tmp_path, monkeypatch):
    inbox, reports = tmp_path / "inbox", tmp_path / "reports"
    inbox.mkdir(); reports.mkdir()
    request_id = "a" * 64
    (reports / request_id).mkdir(mode=0o700)
    (inbox / f"{request_id}.json").write_text(json.dumps({"schema": "aao.audit-request.v1", "type": "gate",
        "id": "b" * 64, "promoted_sha": "c" * 40, "repo": "owner/project", "pr_number": 1}))
    monkeypatch.setattr(auditor_dispatch, "verify_promotion", lambda *args, **kwargs: (True, ()))
    class Client:
        def create_check_run(self, *args):
            pass

    auditor_dispatch.dispatch_once(inbox, reports, tmp_path / "key", Client())
    directory = reports / request_id
    info = directory.stat()
    assert stat.S_IMODE(info.st_mode) == 0o750
    assert stat.S_IMODE((directory / "gate.json").stat().st_mode) == 0o640


def test_issued_authorization_files_are_group_readable_not_writable(tmp_path, monkeypatch):
    report_dir = tmp_path / "report"
    report_dir.mkdir(mode=0o750)
    report = {"manifest": {"repository": str(tmp_path), "target_ref": "refs/heads/main"},
              "candidate_sha": "a" * 40, "target_sha": "b" * 40, "result_tree": "c" * 40,
              "implementer_ids": ["author"], "auditor_id": "auditor", "git_version": "git version 2.0",
              "auditor_revision": "d" * 40, "verdict": "approve", "veto": False,
              "blocking_findings": [], "custody_problems": [], "audit_checks": {},
              "limitations": [], "findings": [], "assurance_level": "A"}
    raw = json.dumps(report).encode()
    route_doc = load_document()
    route_copy = route_map(route_doc)
    anchor = {"auditor_uid": os.getuid(), "policy": {"protected_paths": [],
              "protected_routes": route_copy,
              "protected_routes_sha256": routes_digest(route_doc["routes"]),
              "enabled_risk_classes": ["R1"], "auditors": {"auditor": "auditor-key"},
              "version": "v1", "policy_id": "v1"}, "policy_sha256": "e" * 64}
    monkeypatch.setattr(authorization_issuer, "load_anchor", lambda *args: anchor)
    registry = {"protected_routes": route_copy,
                "protected_routes_sha256": routes_digest(route_doc["routes"])}
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry))
    monkeypatch.setattr(authorization_issuer, "TRUST_REGISTRY_PATH", registry_path)
    read_owners = {}
    monkeypatch.setattr(authorization_issuer.pwd, "getpwnam", lambda _name: type("User", (), {"pw_uid": 4242})())
    def read_protected(path, owners):
        if path == registry_path:
            read_owners["registry"] = owners
            return registry_path.read_bytes()
        return raw
    monkeypatch.setattr(authorization_issuer, "read_protected", read_protected)
    monkeypatch.setattr(authorization_issuer, "verify_promotion", lambda *args, **kwargs: (True, ()))
    monkeypatch.setattr(authorization_issuer, "changed_paths", lambda *args: [])
    monkeypatch.setattr(authorization_issuer.authorization, "sign", lambda *args: "test-signature")
    output = tmp_path / "out"
    authorization_issuer.issue_authorization(report_dir, "owner/repo", 1, tmp_path / "key", output,
                                               anchor_path=tmp_path / "anchor",
                                               anchor_owner_uids=(os.getuid(),))
    assert read_owners["registry"] == (0, 4242)
    assert stat.S_IMODE(output.stat().st_mode) == 0o750
    for name in ("authorization.json", "authorization.sig"):
        mode = stat.S_IMODE((output / name).stat().st_mode)
        assert mode == 0o640 and mode & 0o022 == 0


def test_attribution_records_pr_head_chain_and_requires_pull_api(tmp_path):
    sha_push, prior = "a" * 40, "b" * 40

    class Client:
        def installation_token(self, owner, repo):
            assert (owner, repo) == ("owner", "repo")
        def request(self, method, path):
            body = {
                "/repos/owner/repo/pulls?state=open&per_page=100": [{"number": 3, "head": {
                    "sha": sha_push, "ref": "feature", "repo": {"full_name": "owner/repo"}}}],
                "/repos/owner/repo/events?per_page=100": [
                    {"type": "PushEvent", "actor": {"login": "aao-impl-codex[bot]"}, "payload": {
                        "head": sha_push, "before": prior, "ref": "refs/heads/feature"}},
                    {"type": "PushEvent", "actor": {"login": "aao-pm[bot]"}, "payload": {
                        "head": prior, "before": "0" * 40, "ref": "refs/heads/feature"}}],
                "/repos/owner/repo/pulls/3/commits?per_page=100": [{"sha": sha_push}]}
            return type("Response", (), {"status": 200, "body": body[path]})()

    path = tmp_path / "attribution.json"
    config = {"repository": "owner/repo", "attribution_path": str(path)}
    assert supervisor_service.attribution(config, Client()) == {"candidates": 1, "skipped_prs": []}
    assert json.loads(path.read_text())["candidates"][sha_push] == ["aao-impl-codex[bot]", "aao-pm[bot]"]

    class Failed(Client):
        def request(self, method, path):
            return type("Response", (), {"status": 503, "body": []})()
    failed_path = tmp_path / "failed.json"
    with pytest.raises(RuntimeError):
        supervisor_service.attribution({**config, "attribution_path": str(failed_path)}, Failed())
    assert not failed_path.exists()


def test_attribution_duplicate_push_heads_preserve_all_actors(tmp_path):
    sha, first_parent, second_parent = "a" * 40, "b" * 40, "c" * 40
    pulls = "/repos/owner/repo/pulls?state=open&per_page=100"
    client = type("Client", (), {
        "installation_token": lambda *_args: None,
        "request": lambda self, _method, path: type("Response", (), {"status": 200, "body": {
            pulls: [{"number": 4, "head": {"sha": sha, "ref": "feature",
                       "repo": {"full_name": "owner/repo"}}}],
            "/repos/owner/repo/events?per_page=100": [
                {"type": "PushEvent", "actor": {"login": "first"}, "payload": {
                    "head": sha, "before": first_parent, "ref": "refs/heads/feature"}},
                {"type": "PushEvent", "actor": {"login": "second"}, "payload": {
                    "head": sha, "before": second_parent, "ref": "refs/heads/feature"}},
                {"type": "PushEvent", "actor": {"login": "older-first"}, "payload": {
                    "head": first_parent, "before": "0" * 40, "ref": "refs/heads/feature"}},
                {"type": "PushEvent", "actor": {"login": "older-second"}, "payload": {
                    "head": second_parent, "before": "0" * 40, "ref": "refs/heads/feature"}}],
            "/repos/owner/repo/pulls/4/commits?per_page=100": [{"sha": sha}],
        }[path]})()
    })()
    path = tmp_path / "attribution.json"
    result = supervisor_service.attribution({"repository": "owner/repo", "attribution_path": str(path)}, client)
    assert result == {"candidates": 1, "skipped_prs": []}
    assert json.loads(path.read_text())["candidates"][sha] == ["first", "older-first", "older-second", "second"]


def test_attribution_cycle_without_creation_path_skips_pr(tmp_path):
    sha_a, sha_b = "a" * 40, "b" * 40
    pulls = "/repos/owner/repo/pulls?state=open&per_page=100"
    responses = {
        pulls: [{"number": 5, "head": {"sha": sha_a, "ref": "feature",
                  "repo": {"full_name": "owner/repo"}}}],
        "/repos/owner/repo/events?per_page=100": [
            {"type": "PushEvent", "actor": {"login": "actor-a"}, "payload": {
                "head": sha_a, "before": sha_b, "ref": "refs/heads/feature"}},
            {"type": "PushEvent", "actor": {"login": "actor-b"}, "payload": {
                "head": sha_b, "before": sha_a, "ref": "refs/heads/feature"}}],
        "/repos/owner/repo/pulls/5/commits?per_page=100": [{"sha": sha_a}],
    }
    path = tmp_path / "attribution.json"
    assert supervisor_service.attribution({"repository": "owner/repo", "attribution_path": str(path)},
        _AttributionClient(responses)) == {"candidates": 0, "skipped_prs": [5]}
    assert not path.exists()


def test_attribution_skips_pull_with_commit_pagination_limit(tmp_path):
    sha = "a" * 40
    pulls = "/repos/owner/repo/pulls?state=open&per_page=100"
    responses = {
        pulls: [{"number": 6, "head": {"sha": sha, "ref": "feature",
                  "repo": {"full_name": "owner/repo"}}}],
        "/repos/owner/repo/events?per_page=100": [
            {"type": "PushEvent", "actor": {"login": "actor"}, "payload": {
                "head": sha, "before": "0" * 40, "ref": "refs/heads/feature"}}],
        "/repos/owner/repo/pulls/6/commits?per_page=100": [{"sha": f"{i:040x}"} for i in range(100)],
    }
    path = tmp_path / "attribution.json"
    assert supervisor_service.attribution({"repository": "owner/repo", "attribution_path": str(path)},
        _AttributionClient(responses)) == {"candidates": 0, "skipped_prs": [6]}
    assert not path.exists()


def test_verifier_lists_dispatch_integrator_and_attribution_units():
    path = Path(__file__).parents[1] / "scripts/verify_trust_root_host.py"
    spec = importlib.util.spec_from_file_location("trust_root_verifier", path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)

    expected = {"aao-auditor-dispatch.service", "aao-auditor-dispatch.path", "aao-auditor-dispatch.timer",
                "aao-integrator-tick.service", "aao-integrator-tick.timer",
                "aao-supervisor-attribution.service", "aao-supervisor-attribution.timer"}
    assert expected <= set(verifier.UNITS)
