"""Offline end-to-end acceptance for the audit-to-bare-remote R1 path."""
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_manifest_audit import audit as run_audit
from test_manifest_audit import env as _base_audit_env  # noqa: F401
from test_manifest_audit import git
from test_manifest_audit import manifest as make_manifest

from aao import authorization_issuer
from aao.authorization_issuer import issue_authorization
from aao.independent_audit import AuditError
from aao.integration_authorization import FIELDS, canonical
from aao.integration_authorization import sign as sign_authorization
from aao.integrator import TrustSources, promote


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _keypair(directory, name):
    private = directory / f"{name}.pem"
    public = directory / f"{name}.pub"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True)
    private.chmod(0o600)
    return private, public


def _identity():
    return type("Identity", (), {"__call__": lambda self: "integrator",
                                  "push_identity": lambda self, *args: True})()


def _bare_chain(env, data, output, tmp_path):
    """Build integrator trust registration from the issuer's exact anchor/policy inputs.

    trusted_auditors maps policy.auditor_id to policy.auditors' key id;
    trusted_keys maps that key id to the anchor's auditor_public_key;
    enabled_risk_classes and required_checks_by_risk_class map the policy's
    risk-class/check declarations; policy_id uses policy.policy_id or version;
    trusted_auditor_revisions is copied from the pinned policy revision list.
    """
    anchor = json.loads(env["anchor"].read_text())
    policy = json.loads(env["policy"].read_text())
    repo = env["repo"]
    bare = tmp_path / "remote.git"
    if not bare.exists():
        subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    existing_remotes = _git(repo, "remote").splitlines()
    if "origin" in existing_remotes:
        _git(repo, "remote", "set-url", "origin", str(bare))
    else:
        _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "origin", f"{data['target_sha']}:refs/heads/main")
    _git(repo, "push", "origin", f"{data['candidate_sha']}:refs/heads/candidate")
    keydir = tmp_path / "integrator-keys"
    keydir.mkdir()
    integrator_private, integrator_public = _keypair(keydir, "integrator")
    supervisor_public = env["state"] / "supervisor-public.pem"
    supervisor_public.write_text(anchor["supervisor_public_key"])
    ledger = env["state"] / "ledger.jsonl"
    ledger_anchor = env["ledger_anchor"]
    trust_id = policy["auditors"][policy["auditor_id"]]
    auditor_public = env["state"] / "integrator-auditor-public.pem"
    auditor_public.write_text(anchor["auditor_public_key"])
    required = policy.get("required_checks", [])
    enabled = policy.get("enabled_risk_classes", ["R1"])
    protected = policy["protected_routes"]
    reg = {
        "ledger_keys": {policy["auditor_id"]: {"public_key": str(env["state"] / "auditor-for-supervisor.pub"),
                                    "can_resolve_pending": True},
                        "integrator": {"public_key": str(integrator_public)}},
        "integrator_key_id": "integrator", "supervisor_key_id": anchor["supervisor_key_id"],
        "supervisor_public_key": str(supervisor_public), "heartbeat_max_age_seconds": 3600,
        "target_refs": ["refs/heads/main"], "integrator_identity": "integrator",
        "ra_status": {f"RA-{n}": "PASS" for n in ("01", "02", "03", "07", "09")},
        "incident_resolvers": [], "trusted_auditors": {policy["auditor_id"]: [trust_id]},
        "trusted_keys": {trust_id: str(auditor_public)},
        "enabled_risk_classes": enabled,
        "required_checks_by_risk_class": {risk: required for risk in enabled},
        "policy_id": policy.get("policy_id", policy["version"]),
        "policy_sha256": anchor["policy_sha256"],
        "trusted_auditor_revisions": policy["trusted_auditor_revisions"],
        "auditor_models": {}, "author_models": {}, "protected_routes": protected,
        "protected_routes_sha256": policy["protected_routes_sha256"],
        "required_check_publishers": {"aao-audit": [5448107], "test": [15368]},
        "push_principals": policy["push_principals"],
    }
    registry = env["state"] / "integrator-trust.json"
    registry.write_text(json.dumps(reg))
    heartbeat = env["heartbeat_path"]
    # The real supervisor helper emits the anchored ledger head and marker snapshot.
    env["heartbeat"]()
    verification_dir = env["state"] / "trust-verification"
    verification_dir.mkdir(mode=0o755)
    verification_path = verification_dir / "status.json"
    verification_path.write_text(json.dumps({
        "schema": "aao.trust-root-verification.v1", "result": "PASS",
        "expected_revision": policy["trusted_auditor_revisions"][0],
        "verified_at": datetime.now(UTC).isoformat(), "failed": [],
        "verifier_sha256": "b" * 64,
    }))
    verification_path.chmod(0o644)
    verification_dir.chmod(0o755)
    sources = TrustSources(registry, ledger, ledger_anchor, heartbeat,
                           env["state"] / "freeze", integrator_private,
                           heartbeat_sequence=env["state"] / "heartbeat.sequence",
                           trust_verification=verification_path,
                           trust_verification_root=verification_dir,
                           trust_verification_owner_uid=os.getuid())
    doc = json.loads((output / "authorization.json").read_text())
    sig = (output / "authorization.sig").read_text().strip()
    return bare, sources, doc, sig


def _assert_bare(bare, commit, base, candidate, tree):
    main = subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "refs/heads/main"],
                          check=True, capture_output=True, text=True).stdout.strip()
    assert main == commit
    assert subprocess.run(["git", "--git-dir", str(bare), "show", "-s", "--format=%P", main],
                          check=True, capture_output=True, text=True).stdout.split() == [base, candidate]
    assert subprocess.run(["git", "--git-dir", str(bare), "show", "-s", "--format=%T", main],
                          check=True, capture_output=True, text=True).stdout.strip() == tree


@pytest.fixture
def audit_setup(_base_audit_env, monkeypatch):  # noqa: F811
    monkeypatch.setattr(authorization_issuer, "TRUST_REGISTRY_PATH", _base_audit_env["registry"])
    return _base_audit_env


def test_r1_signed_audit_issues_exact_authorization(audit_setup, tmp_path, monkeypatch):
    env = audit_setup
    env["configure"](policy_overrides={
        "auditors": {"aao-auditor": "auditor-key"},
        "enabled_risk_classes": ["R1"],
    })
    manifest_path, data = make_manifest(env)
    run_audit(env, manifest_path, "e2e-r1")
    env["heartbeat"]()  # signed supervisor custody snapshot is required by promotion verification
    output = tmp_path / "authorization"
    document = issue_authorization(
        env["state"] / "e2e-r1", "example/project", 17, env["key"], output,
        anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
        registry_owner_uids=(os.getuid(),),
    )
    assert document["candidate_sha"] == data["candidate_sha"]
    assert document["base_sha"] == data["target_sha"]
    assert document["risk_class"] == "R1"
    assert set(document) == set(FIELDS)
    assert (output / "authorization.json").is_file()
    assert (output / "authorization.sig").is_file()
    bare, sources, doc, sig = _bare_chain(env, data, output, tmp_path)
    registry_digest = hashlib.sha256(sources.trust_registry.read_bytes()).hexdigest()
    registry_data = json.loads(sources.trust_registry.read_text())
    assert not {"ci_candidate_sha", "attribution_resolved", "repo", "pr_number", "pr_head"}.intersection(registry_data)
    sources.trust_registry.write_text(json.dumps({**registry_data, "ci_candidate_sha": data["candidate_sha"]}))
    with pytest.raises(ValueError, match="trust registry contains per-PR fields"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                ci_verified_sha=data["candidate_sha"], now=lambda: datetime.now(UTC))
    sources.trust_registry.write_text(json.dumps(registry_data))
    with pytest.raises(ValueError, match="repository or PR mismatch"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"] + 1,
                ci_verified_sha=data["candidate_sha"], now=lambda: datetime.now(UTC))
    env["heartbeat"]()
    with pytest.raises(ValueError, match="CI evidence is for another candidate"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                ci_verified_sha="f" * 40, now=lambda: datetime.now(UTC))
    staged = subprocess.run(["git", "-C", str(env["repo"]), "commit-tree", data["result_tree"],
                             "-p", data["target_sha"], "-p", data["candidate_sha"]],
                            input="staged for negative CI check\n", check=True,
                            capture_output=True, text=True).stdout.strip()
    env["heartbeat"]()
    with pytest.raises(ValueError, match="CI evidence is for another candidate"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                staged_commit=staged, ci_verified_sha="f" * 40,
                now=lambda: datetime.now(UTC))
    env["heartbeat"]()
    unattributed = {**doc, "attribution": []}
    unattributed_sig = sign_authorization(unattributed, str(env["key"]))
    with pytest.raises(ValueError, match="actor attribution inconclusive"):
        promote(env["repo"], "origin", unattributed, unattributed_sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                ci_verified_sha=data["candidate_sha"], now=lambda: datetime.now(UTC))
    assert subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "refs/heads/main"],
                          check=True, capture_output=True, text=True).stdout.strip() == data["target_sha"]
    env["heartbeat"]()  # integrator consumes heartbeat sequence even on rejected attempts
    # Required checks are only accepted on M (the staged merge), as r1_pipeline does.
    m = subprocess.run(["git", "-C", str(env["repo"]), "commit-tree", data["result_tree"],
                        "-p", data["target_sha"], "-p", data["candidate_sha"]], input="R1 staged merge\n",
                       check=True, capture_output=True, text=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "aao-integrator",
                            "GIT_AUTHOR_EMAIL": "aao-integrator@users.noreply.github.com",
                            "GIT_COMMITTER_NAME": "aao-integrator",
                            "GIT_COMMITTER_EMAIL": "aao-integrator@users.noreply.github.com"}).stdout.strip()
    def move_main_after_authorization():
        subprocess.run(["git", "--git-dir", str(bare), "update-ref", "refs/heads/main",
                        data["candidate_sha"]], check=True)
    with pytest.raises(RuntimeError, match="remote base moved"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                staged_commit=m, ci_verified_sha=m,
                before_push=move_main_after_authorization, now=lambda: datetime.now(UTC))
    assert subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "refs/heads/main"],
                          check=True, capture_output=True, text=True).stdout.strip() == data["candidate_sha"]
    subprocess.run(["git", "--git-dir", str(bare), "update-ref", "refs/heads/main",
                    data["target_sha"]], check=True)
    env["heartbeat"]()
    monkeypatch.setenv("HOME", "/nonexistent")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    commit = promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                     observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                     staged_commit=m, ci_verified_sha=m,
                     now=lambda: datetime.now(UTC))
    assert _git(env["repo"], "show", "-s", "--format=%an <%ae>%n%cn <%ce>", commit).splitlines() == [
        "aao-integrator <aao-integrator@users.noreply.github.com>",
        "aao-integrator <aao-integrator@users.noreply.github.com>",
    ]
    assert hashlib.sha256(sources.trust_registry.read_bytes()).hexdigest() == registry_digest
    _assert_bare(bare, commit, data["target_sha"], data["candidate_sha"], data["result_tree"])


@pytest.mark.parametrize("mismatch", ["tree", "parents"])
@pytest.mark.nt("NT-03-3")
@pytest.mark.nt("NT-03-5")
def test_integrator_rejects_staged_commit_mismatch(audit_setup, tmp_path, mismatch):
    env = audit_setup
    env["configure"](policy_overrides={"auditors": {"aao-auditor": "auditor-key"},
                                       "enabled_risk_classes": ["R1"]})
    manifest_path, data = make_manifest(env)
    run_audit(env, manifest_path, f"e2e-staged-{mismatch}")
    env["heartbeat"]()  # issue_authorization verifies supervisor custody as well as the report signature
    output = tmp_path / "authorization"
    issue_authorization(env["state"] / f"e2e-staged-{mismatch}", "example/project", 17,
                        env["key"], output, anchor_path=env["anchor"],
                        anchor_owner_uids=(env["anchor"].stat().st_uid,),
                        registry_owner_uids=(os.getuid(),))
    _bare, sources, doc, sig = _bare_chain(env, data, output, tmp_path)
    tree = data["result_tree"] if mismatch == "parents" else _git(env["repo"], "rev-parse", f"{data['candidate_sha']}^{{tree}}")
    parents = [data["target_sha"], data["candidate_sha"]]
    if mismatch == "parents":
        parents = [data["candidate_sha"]]
    staged = subprocess.run(["git", "-C", str(env["repo"]), "commit-tree", tree,
                             *[arg for parent in parents for arg in ("-p", parent)]],
                            input="staged mismatch\n", check=True, capture_output=True,
                            text=True).stdout.strip()
    with pytest.raises(ValueError, match=f"staged commit {mismatch}"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                staged_commit=staged, ci_verified_sha=staged,
                now=lambda: datetime.now(UTC))


def test_issuer_rejects_tampered_report_signature(audit_setup):
    env = audit_setup
    env["configure"](policy_overrides={"auditors": {"aao-auditor": "auditor-key"}})
    manifest_path, _ = make_manifest(env)
    run_audit(env, manifest_path, "e2e-tampered")
    report_dir = env["state"] / "e2e-tampered"
    (report_dir / "report.sig").write_text("invalid\n", encoding="ascii")
    with pytest.raises(AuditError, match="not promotion-valid"):
        issue_authorization(report_dir, "example/project", 17, env["key"],
                            env["tmp"] / "must-not-exist", anchor_path=env["anchor"],
                            anchor_owner_uids=(env["anchor"].stat().st_uid,),
                        registry_owner_uids=(os.getuid(),))


def test_protected_path_does_not_emit_when_r2_is_disabled(audit_setup):
    env = audit_setup
    # Exercise an actual CEO-approved R2 route, not the fixture-only src/app.py path.
    git(env["repo"], "switch", "candidate")
    (env["repo"] / "src/aao/manifest_audit.py").parent.mkdir(parents=True, exist_ok=True)
    (env["repo"] / "src/aao/manifest_audit.py").write_text("# protected route fixture\n")
    git(env["repo"], "add", "src/aao/manifest_audit.py")
    subprocess.run(["git", "-C", str(env["repo"]), "-c", "user.name=implementer",
                    "-c", "user.email=implementer@example.invalid", "commit", "-m",
                    "touch approved R2 route"], check=True, capture_output=True, text=True)
    git(env["repo"], "switch", "main")
    manifest_path, data = make_manifest(env)
    env["configure"](policy_overrides={"auditors": {"aao-auditor": "auditor-key"},
                                       "protected_paths": ["src/app"],
                                       "dispositions": {f"{data['candidate_sha']}:{data['result_tree']}:protected-path:src/app.py": "reviewed"},
                                       "enabled_risk_classes": ["R1"]})
    run_audit(env, manifest_path, "e2e-protected")
    env["heartbeat"]()
    with pytest.raises(AuditError, match="R2 is not enabled"):
        issue_authorization(env["state"] / "e2e-protected", "example/project", 17,
                            env["key"], env["tmp"] / "must-not-exist",
                            anchor_path=env["anchor"], anchor_owner_uids=(env["anchor"].stat().st_uid,),
                        registry_owner_uids=(os.getuid(),))
    assert not (env["tmp"] / "must-not-exist").exists()


def test_integrator_refuses_signed_supervisor_pending_veto(audit_setup, tmp_path):
    env = audit_setup
    env["configure"](policy_overrides={"auditors": {"aao-auditor": "auditor-key"},
                                       "enabled_risk_classes": ["R1"]})
    manifest_path, data = make_manifest(env)
    run_audit(env, manifest_path, "e2e-pending-veto")
    env["heartbeat"]()
    output = tmp_path / "authorization"
    issue_authorization(env["state"] / "e2e-pending-veto", "example/project", 17,
                        env["key"], output, anchor_path=env["anchor"],
                        anchor_owner_uids=(env["anchor"].stat().st_uid,),
                        registry_owner_uids=(os.getuid(),))
    bare, sources, doc, sig = _bare_chain(env, data, output, tmp_path)
    directory = Path(str(sources.ledger) + ".pending-vetoes")
    directory.mkdir(mode=0o700)
    marker = {"schema": "aao.pending-veto.v1", "candidate_sha": data["candidate_sha"],
              "manifest_sha256": "d" * 64, "reason": "pending veto"}
    raw = canonical(marker)
    digest = hashlib.sha256(raw).hexdigest()
    marker_path = directory / f"{data['candidate_sha']}-{digest}.json"
    marker_path.write_bytes(raw)
    marker_path.chmod(0o600)
    env["heartbeat"]()
    with pytest.raises(ValueError, match="candidate has an unresolved pending veto"):
        promote(env["repo"], "origin", doc, sig, sources, identity_provider=_identity(),
                observed_repo=doc["repo"], observed_pr_number=doc["pr_number"],
                ci_verified_sha=data["candidate_sha"],
                now=lambda: datetime.now(UTC))
    assert subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "refs/heads/main"],
                          check=True, capture_output=True, text=True).stdout.strip() == data["target_sha"]


def test_supervisor_record_attribution_is_atomic_and_keeps_other_entries(tmp_path):
    from aao.supervisor import record_attribution

    path = tmp_path / "attribution.json"
    first, second = "a" * 40, "b" * 40
    record_attribution(path, first, ["push:alice"])
    record_attribution(path, first, ["push:carol"])
    record_attribution(path, second, ["push:bob", "push:bob"])
    assert json.loads(path.read_text()) == {
        "schema": "aao.implementer-attribution.v1",
        "candidates": {first: ["push:alice", "push:carol"], second: ["push:bob"]},
    }
    assert path.stat().st_mode & 0o777 == 0o644
    with pytest.raises(ValueError, match="candidate_sha"):
        record_attribution(path, "short", ["push:alice"])
    with pytest.raises(ValueError, match="principals"):
        record_attribution(path, first, [])


@pytest.mark.nt("NT-02-9")
def test_attribution_owned_by_untrusted_uid_is_unresolved(audit_setup):
    from aao.manifest_audit import attributed_implementers, attributed_principals

    env = audit_setup
    env["attribute"]("c" * 40, ("push:alice",))
    anchor = {"attribution_path": env["anchor"].parent / "attribution.json",
              "anchor_owner_uids": (os.geteuid() + 100,),
              "attribution_writer_uid": os.geteuid()}
    # The authenticated identity stays recorded for recusal, but no registry is
    # supplied here, so it cannot resolve to an implementer.
    assert attributed_principals(anchor, "c" * 40) == ["push:alice"]
    assert attributed_implementers(anchor, "c" * 40) == []
    anchor["attribution_writer_uid"] = os.geteuid() + 101
    assert attributed_principals(anchor, "c" * 40) == []
    assert attributed_implementers(anchor, "c" * 40) == []
