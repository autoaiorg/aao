"""Offline R1 orchestration tests with a fake GitHub client and local bare remotes."""
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime

import pytest
from test_e2e_r1_integration import _bare_chain, _identity
from test_manifest_audit import env as _base_audit_env  # noqa: F401
from test_manifest_audit import manifest as make_manifest
from test_manifest_audit import ok_runner

from aao import authorization_issuer, auditor_dispatch, r1_pipeline
from aao.git_paths import changed_paths, path_matches_prefix
from aao.integrator import TrustSources
from aao.protected_routes import compare_copies, load_document, route_map, routes_digest


@pytest.fixture
def audit_setup(_base_audit_env, monkeypatch):  # noqa: F811
    monkeypatch.setattr(authorization_issuer, "TRUST_REGISTRY_PATH", _base_audit_env["registry"])
    return _base_audit_env


def _run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True).stdout.strip()


def _git(path, *args):
    return _run("git", "-C", str(path), *args)


def _fixture(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "config", "user.email", "test@example.invalid")
    _git(work, "config", "user.name", "Test")
    (work / "README.md").write_text("base\n")
    _git(work, "add", "."); _git(work, "commit", "-m", "base")
    base = _git(work, "rev-parse", "HEAD")
    _git(work, "switch", "-c", "feature")
    (work / "README.md").write_text("candidate\n")
    _git(work, "commit", "-am", "candidate")
    head = _git(work, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    _run("git", "init", "--bare", str(remote))
    _git(work, "push", str(remote), "main:refs/heads/main")
    _git(work, "push", str(remote), f"{head}:refs/pull/1/head")
    mirror = tmp_path / "mirror.git"
    _run("git", "clone", "--mirror", str(remote), str(mirror))
    gh = FakeGitHub(base, head)
    inbox, reports, state = (tmp_path / name for name in ("inbox", "reports", "state"))
    trust = TrustSources(*(tmp_path / f"trust-{i}" for i in range(7)))
    routes = load_document()
    trust.trust_registry.write_text(json.dumps({
        "protected_routes": route_map(routes),
        "protected_routes_sha256": routes_digest(routes["routes"]),
        "required_check_publishers": {"aao-audit": [5448107], "test": [15368]},
        "push_principals": routes["push_principals"],
    }))
    registered = json.loads(trust.trust_registry.read_text())
    assert registered["protected_routes"] == route_map(routes)
    assert registered["protected_routes_sha256"] == routes_digest(routes["routes"])
    assert registered["required_check_publishers"] == {"aao-audit": [5448107], "test": [15368]}
    return remote, mirror, gh, inbox, reports, state, trust, base, head


class FakeGitHub:
    repository = "owner/project"

    def __init__(self, base, head):
        self.base, self.head = base, head
        self.checks = {}
        self.published = []

    def list_open_pull_requests(self, repository, *, base):
        return [{"number": 1, "state": "open", "base": {"ref": "main", "sha": self.base},
                 "head": {"sha": self.head}}]

    def request(self, method, path, body=None):
        sha = path.split("/commits/", 1)[1].split("/check-runs", 1)[0]
        runs = [{"id": index, "name": name, "status": "completed", "conclusion": conclusion,
                 "app": {"id": 5448107 if name == "aao-audit" else 15368}}
                for index, ((candidate, name), conclusion) in enumerate(self.checks.items(), 1)
                if candidate == sha]
        return {"check_runs": runs}

    def create_check_run(self, repository, name, sha, conclusion, detail):
        self.published.append((name, sha, conclusion))
        self.checks[(sha, name)] = conclusion


def _tick(remote, mirror, gh, inbox, reports, state, trust, *, git_token=None):
    return r1_pipeline.integrator_tick(gh, str(remote), mirror, inbox, reports, state,
                                       trust, object(), lambda: __import__("datetime").datetime.now(
                                           __import__("datetime").UTC), git_token=git_token)


def _request(inbox, kind):
    return next(json.loads(p.read_text()) for p in inbox.glob("*.json")
                if json.loads(p.read_text()).get("type") == kind)


def test_stage2_and4_alternating_ticks_promote_the_exact_staged_commit(tmp_path, monkeypatch):
    remote, mirror, gh, inbox, reports, state, trust, base, head = _fixture(tmp_path)
    monkeypatch.setenv("HOME", "/nonexistent")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")

    def fake_audit(manifest_path, output, key, **kwargs):
        output.mkdir(parents=True)
        return {"verdict": "approve"}

    def fake_issue(report_dir, repo, pr_number, key, output, **kwargs):
        output.mkdir(parents=True)
        (output / "authorization.json").write_text("{}")
        (output / "authorization.sig").write_text("signature")

    monkeypatch.setattr(auditor_dispatch, "audit_manifest", fake_audit)
    monkeypatch.setattr(auditor_dispatch, "issue_authorization", fake_issue)
    monkeypatch.setattr(auditor_dispatch, "verify_promotion", lambda *a, **k: (True, ()))
    first = _tick(remote, mirror, gh, inbox, reports, state, trust)
    assert first[0]["status"] == "queued"
    audit = _request(inbox, "audit")
    assert audit["manifest"]["target_sha"] == base
    auditor_dispatch.dispatch_once(inbox, reports, tmp_path / "key", gh,
                                   repository_root=mirror)

    second = _tick(remote, mirror, gh, inbox, reports, state, trust)
    assert second[0]["status"] == "staged"
    staged = second[0]["staged_commit"]
    assert _git(mirror, "show", "-s", "--format=%an <%ae>%n%cn <%ce>", staged).splitlines() == [
        "aao-integrator <aao-integrator@users.noreply.github.com>",
        "aao-integrator <aao-integrator@users.noreply.github.com>",
    ]
    gate = _request(inbox, "gate")
    assert gate["promoted_sha"] == staged
    auditor_dispatch.dispatch_once(inbox, reports, tmp_path / "key", gh,
                                   repository_root=mirror)
    gh.checks[(staged, "test")] = "success"
    assert gh.checks[(staged, "aao-audit")] == "success"

    def fake_promote(repo, git_remote, auth, signature, sources, **kwargs):
        assert kwargs["staged_commit"] == staged
        assert kwargs["ci_verified_sha"] == staged
        assert kwargs["git_token"] == token
        _run("git", "--git-dir", str(remote), "update-ref", "refs/heads/main", staged, base)
        return staged

    monkeypatch.setattr(r1_pipeline, "promote", fake_promote)
    token = "test-installation-token"
    final = _tick(remote, mirror, gh, inbox, reports, state, trust, git_token=token)
    assert final[0]["status"] == "promoted"
    assert _run("git", "--git-dir", str(remote), "rev-parse", "refs/heads/main") == staged
    assert _run("git", "--git-dir", str(remote), "show", "-s", "--format=%P", staged).split() == [base, head]


def test_stage2_red_test_check_never_promotes(tmp_path, monkeypatch):
    remote, mirror, gh, inbox, reports, state, trust, _base, _head = _fixture(tmp_path)
    _tick(remote, mirror, gh, inbox, reports, state, trust)
    request = _request(inbox, "audit")
    audit_id = next(p.stem for p in inbox.glob("*.json") if json.loads(p.read_text()) == request)
    report = reports / audit_id
    report.mkdir(parents=True)
    (report / "authorization.json").write_text("{}")
    (report / "authorization.sig").write_text("signature")
    staged_state = _tick(remote, mirror, gh, inbox, reports, state, trust)[0]
    staged = staged_state["staged_commit"]
    gate = _request(inbox, "gate")
    gate_id = next(p.stem for p in inbox.glob("*.json") if json.loads(p.read_text()) == gate)
    (reports / gate_id).mkdir(parents=True)
    (reports / gate_id / "gate.json").write_text('{"conformant":true}')
    gh.checks[(staged, "test")] = "failure"
    gh.checks[(staged, "aao-audit")] = "success"
    monkeypatch.setattr(r1_pipeline, "promote", lambda *a, **k: (_ for _ in ()).throw(AssertionError("promoted")))
    result = _tick(remote, mirror, gh, inbox, reports, state, trust)
    assert result[0]["status"] == "gated"
    assert _run("git", "--git-dir", str(remote), "rev-parse", "refs/heads/main") == staged_state["base_sha"]


def test_stage3_invalid_inbox_id_is_ignored_and_failed_gate_is_not_success(tmp_path, monkeypatch):
    inbox, reports = tmp_path / "inbox", tmp_path / "reports"
    inbox.mkdir(); reports.mkdir()
    (inbox / "invalid.json").write_text("{}")
    valid_id = "a" * 64
    (inbox / f"{valid_id}.json").write_text(json.dumps({"schema": "aao.audit-request.v1", "type": "gate",
        "id": "b" * 64, "promoted_sha": "c" * 40, "repo": "owner/project", "pr_number": 1}))
    monkeypatch.setattr(auditor_dispatch, "verify_promotion", lambda *a, **k: (False, ("not conformant",)))
    client = FakeGitHub("d" * 40, "e" * 40)
    result = auditor_dispatch.dispatch_once(inbox, reports, tmp_path / "key", client)
    assert any(item["status"] == "ignored" for item in result)
    assert ("aao-audit", "c" * 40, "failure") in client.published
    assert not any(item[2] == "success" for item in client.published)


def test_stage3_rejects_extra_fields_and_oversize_requests(tmp_path):
    inbox, reports = tmp_path / "inbox", tmp_path / "reports"
    inbox.mkdir(); reports.mkdir()
    (inbox / ("a" * 64 + ".json")).write_text(json.dumps({"schema": "aao.audit-request.v1",
        "type": "audit", "repo": "owner/project", "pr_number": 1, "manifest": {}, "path": "/etc/passwd"}))
    (inbox / ("b" * 64 + ".json")).write_bytes(b" " * 65537)
    result = auditor_dispatch.dispatch_once(inbox, reports, tmp_path / "key", FakeGitHub("a", "b"))
    assert sorted(item["status"] for item in result) == ["failed", "failed"]
    assert not list(reports.rglob("report.json"))


def test_shared_git_paths_keep_non_ascii_and_rename_endpoints(tmp_path):
    repository = tmp_path / "path-policy.git"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Test")
    workflow = repository / ".github" / "workflows" / "é.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: workflow\n")
    old = repository / "old.txt"
    old.write_text("rename content\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "base")
    base = _git(repository, "rev-parse", "HEAD")
    old.rename(repository / "new.txt")
    workflow.write_text("name: changed workflow\n")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-m", "candidate")
    candidate = _git(repository, "rev-parse", "HEAD")
    paths = changed_paths(repository, base, candidate)
    assert set(paths) == {"old.txt", "new.txt", ".github/workflows/é.yml"}
    assert any(path_matches_prefix(path, ".github/workflows/") for path in paths)


def test_real_r1_authorizes_and_promotes_over_alternating_ticks(tmp_path, audit_setup, monkeypatch):
    """Exercise real manifest audit, issuer, promotion verification, and push using only local remotes."""
    env = audit_setup
    env["configure"](policy_overrides={"auditors": {"aao-auditor": "auditor-key"},
                                       "enabled_risk_classes": ["R1"]})
    _manifest, data = make_manifest(env)
    bare = tmp_path / "remote.git"
    _run("git", "init", "--bare", str(bare))
    _git(env["repo"], "remote", "add", "origin", str(bare))
    _git(env["repo"], "push", "origin", f"{data['target_sha']}:refs/heads/main")
    _git(env["repo"], "push", "origin", f"{data['candidate_sha']}:refs/pull/17/head")
    mirror = tmp_path / "mirror.git"
    _run("git", "clone", "--mirror", str(bare), str(mirror))
    output = tmp_path / "authorization"
    trust = TrustSources(*(tmp_path / f"placeholder-{index}" for index in range(7)))
    routes = load_document()
    trust.trust_registry.write_text(json.dumps({
        "protected_routes": route_map(routes),
        "protected_routes_sha256": routes_digest(routes["routes"]),
        "required_check_publishers": {"aao-audit": [5448107], "test": [15368]},
        "push_principals": routes["push_principals"],
    }))
    operational = json.loads(env["policy"].read_text())
    registered = json.loads(trust.trust_registry.read_text())
    compare_copies(routes, registered, {
        "protected_routes": operational["protected_routes"],
        "protected_routes_sha256": operational["protected_routes_sha256"],
    })
    assert operational["push_principals"]["aao-impl-codex[bot]"] == "codex"
    assert registered["required_check_publishers"] == {"aao-audit": [5448107], "test": [15368]}
    inbox, reports, state = (tmp_path / name for name in ("pipeline-inbox", "pipeline-reports", "pipeline-state"))

    class PipelineGitHub:
        repository = "example/project"

        def __init__(self):
            self.checks = {}
            self.published = []
            self.pull_requests = [{"number": 17, "state": "open", "base": {"ref": "main"},
                                   "head": {"sha": data["candidate_sha"]}}]

        def list_open_pull_requests(self, repository, *, base):
            return self.pull_requests

        def request(self, method, path, body=None):
            sha = path.split("/commits/", 1)[1].split("/check-runs", 1)[0]
            runs = [{"id": index, "name": name, "status": "completed", "conclusion": conclusion,
                     "app": {"id": 5448107 if name == "aao-audit" else 15368}}
                    for index, ((candidate, name), conclusion) in enumerate(self.checks.items(), 1)
                    if candidate == sha]
            return {"check_runs": runs}

        def create_check_run(self, repository, name, sha, conclusion, detail):
            self.published.append((name, sha, conclusion))
            self.checks[(sha, name)] = conclusion

    github = PipelineGitHub()
    now = lambda: datetime.now(UTC)

    def tick():
        return r1_pipeline.integrator_tick(github, str(bare), mirror, inbox, reports, state,
                                           trust, _identity(), now)

    assert tick()[0]["status"] == "queued"
    audit_request = _request(inbox, "audit")
    audit_file = next(path for path in inbox.glob("*.json")
                      if json.loads(path.read_text()) == audit_request)

    # The heartbeat must include the real audit's appended ledger row before authorization is issued.
    real_issue = auditor_dispatch.issue_authorization

    def issue_after_anchoring(*args, **kwargs):
        env["heartbeat"]()
        return real_issue(*args, **kwargs)

    monkeypatch.setattr(auditor_dispatch, "issue_authorization", issue_after_anchoring)
    result = auditor_dispatch.dispatch_once(inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror, runner=ok_runner)
    assert result[0]["status"] == "approve", result
    assert audit_file.exists()
    output.mkdir()
    (output / "authorization.json").write_bytes((reports / audit_file.stem / "authorization.json").read_bytes())
    (output / "authorization.sig").write_bytes((reports / audit_file.stem / "authorization.sig").read_bytes())
    # Rebuild the trusted integrator inputs from the actual signed document and fixture's pinned anchor.
    _bare, trust, _doc, _sig = _bare_chain(env, data, output, tmp_path)
    registry_path = trust.trust_registry
    registry_digest_before = hashlib.sha256(registry_path.read_bytes()).hexdigest()

    staged_result = tick()
    assert staged_result[0]["status"] == "staged"
    staged = staged_result[0]["staged_commit"]
    github.checks[(staged, "test")] = "success"
    gate_request = _request(inbox, "gate")
    gate_id = next(path.stem for path in inbox.glob("*.json")
                   if json.loads(path.read_text()) == gate_request)
    gate_result = auditor_dispatch.dispatch_once(inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror)
    assert any(item["id"] == gate_id and item["status"] == "success" for item in gate_result)
    assert github.checks[(staged, "aao-audit")] == "success"
    promoted = tick()
    assert promoted[0]["status"] == "promoted"
    assert _run("git", "--git-dir", str(bare), "rev-parse", "refs/heads/main") == staged
    registry_digest_between = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    assert registry_digest_between == registry_digest_before

    # Prepare a second, consecutive R1 candidate whose base is PR 17's promoted merge.
    _git(env["repo"], "fetch", "origin", "refs/heads/main")
    _git(env["repo"], "checkout", "-B", "main", "FETCH_HEAD")
    _git(env["repo"], "checkout", "-B", "candidate2")
    (env["repo"] / "second-r1.txt").write_text("second R1 change\n")
    _git(env["repo"], "add", "second-r1.txt")
    _git(env["repo"], "commit", "-m", "second R1 candidate")
    second_head = _git(env["repo"], "rev-parse", "HEAD")
    env["attribute"](second_head)
    _git(env["repo"], "push", "origin", f"{second_head}:refs/pull/18/head")
    github.pull_requests = [{"number": 18, "state": "open", "base": {"ref": "main"},
                             "head": {"sha": second_head}}]
    assert tick()[0]["status"] == "queued"
    second_audit_request = next(path for path in inbox.glob("*.json")
                                if json.loads(path.read_text()).get("type") == "audit"
                                and json.loads(path.read_text()).get("pr_number") == 18)
    second_audit_key = second_audit_request.stem
    second_audit_result = auditor_dispatch.dispatch_once(
        inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror, runner=ok_runner,
    )
    assert any(item.get("id") == second_audit_key and item["status"] == "approve"
               for item in second_audit_result)
    # The same static trust registry is reused; only signed per-PR authorization changes.
    second_staged_result = tick()
    assert second_staged_result[0]["status"] == "staged"
    second_staged = second_staged_result[0]["staged_commit"]
    github.checks[(second_staged, "test")] = "success"
    second_gate_request = next(path for path in inbox.glob("*.json")
                               if json.loads(path.read_text()).get("type") == "gate"
                               and json.loads(path.read_text()).get("pr_number") == 18)
    # Gate dispatch keys its result by the inbox filename, not the report id in the request.
    second_gate_id = second_gate_request.stem
    second_gate_result = auditor_dispatch.dispatch_once(
        inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror,
    )
    assert any(item.get("id") == second_gate_id and item["status"] == "success"
               for item in second_gate_result)
    assert github.checks[(second_staged, "aao-audit")] == "success"
    second_promoted = tick()
    assert second_promoted[0]["status"] == "promoted"
    assert _run("git", "--git-dir", str(bare), "rev-parse", "refs/heads/main") == second_staged
    published_before_repeat = list(github.published)
    repeated_gate_result = auditor_dispatch.dispatch_once(
        inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror,
    )
    assert any(item.get("id") == second_gate_id and item["status"] == "ignored"
               and item.get("reason") == "gate already published for promoted SHA"
               for item in repeated_gate_result)
    assert github.published == published_before_repeat

    second_gate_request_data = json.loads(second_gate_request.read_text())
    unauthorized_sha = staged
    second_gate_request_data["promoted_sha"] = unauthorized_sha
    second_gate_request.write_text(json.dumps(second_gate_request_data))
    new_sha_gate_result = auditor_dispatch.dispatch_once(
        inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror,
    )
    assert any(item.get("id") == second_gate_id and item["status"] == "failure"
               for item in new_sha_gate_result)
    assert len(github.published) == len(published_before_repeat) + 1
    assert github.published[-1] == ("aao-audit", unauthorized_sha, "failure")
    assert json.loads((reports / second_gate_id / "gate.json").read_text())["promoted_sha"] == unauthorized_sha

    # A nonexistent commit cannot receive a GitHub check; fail closed without publishing one.
    second_gate_request_data["promoted_sha"] = "f" * 40
    second_gate_request.write_text(json.dumps(second_gate_request_data))
    published_before_missing_sha = list(github.published)
    missing_sha_result = auditor_dispatch.dispatch_once(
        inbox, reports, env["key"], github,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
        repository_root=mirror,
    )
    assert any(item.get("id") == second_gate_id and item["status"] == "failed"
               for item in missing_sha_result)
    assert github.published == published_before_missing_sha
    registry_digest_after = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    assert registry_digest_after == registry_digest_before


def test_stage2_main_movement_requeues_against_new_base(tmp_path):
    remote, mirror, gh, inbox, reports, state, trust, base, _head = _fixture(tmp_path)
    _tick(remote, mirror, gh, inbox, reports, state, trust)
    work = tmp_path / "work"
    _git(work, "switch", "main")
    (work / "main-only.txt").write_text("moved\n")
    _git(work, "add", "."); _git(work, "commit", "-m", "main moved")
    moved = _git(work, "rev-parse", "HEAD")
    _git(work, "push", str(remote), "main:refs/heads/main")
    gh.base = moved
    result = _tick(remote, mirror, gh, inbox, reports, state, trust)
    assert result[0]["status"] == "queued"
    request = next(json.loads(path.read_text()) for path in inbox.glob("*.json")
                   if json.loads(path.read_text()).get("type") == "audit"
                   and json.loads(path.read_text()).get("manifest", {}).get("target_sha") == moved)
    assert request["manifest"]["target_sha"] == moved
    assert request["manifest"]["target_sha"] != base
    assert _run("git", "--git-dir", str(remote), "rev-parse", "refs/heads/main") == moved


def test_stage2_rejected_protected_change_stays_off_main(tmp_path):
    remote, mirror, gh, inbox, reports, state, trust, base, _head = _fixture(tmp_path)
    queued = _tick(remote, mirror, gh, inbox, reports, state, trust)[0]
    (reports / queued["id"] / "audit").mkdir(parents=True)
    (reports / queued["id"] / "audit" / "report.json").write_text(
        '{"verdict":"reject","blocking_findings":["protected-path:R2"]}')
    result = _tick(remote, mirror, gh, inbox, reports, state, trust)
    assert result[0]["status"] == "failed"
    assert "reject" in result[0]["reason"]
    assert _run("git", "--git-dir", str(remote), "rev-parse", "refs/heads/main") == base
