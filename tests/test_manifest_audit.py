import base64
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import tempfile

import pytest

from aao import manifest_audit
from aao.independent_audit import AuditError
from aao.manifest_audit import audit_manifest, verify_promotion
from aao.pr_conformity import _canonical
from aao.protected_routes import load_document, route_map, routes_digest

UID = os.geteuid()
USER = pwd.getpwuid(UID).pw_name
REVIEWED = "b" * 40


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, files, message):
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def ok_runner(tree, argv):
    assert (tree / "src" / "app.py").is_file()
    parents = subprocess.run(["git", "-C", str(tree), "rev-list", "--parents", "-n", "1", "HEAD"], check=True,
                             capture_output=True, text=True).stdout.split()
    assert len(parents) == 3  # checks see git metadata of a [target, candidate] merge commit
    return 0, "1 passed", ""


@pytest.fixture
def env(tmp_path, monkeypatch, request):
    if not shutil.which("openssl"):
        pytest.skip("openssl is required for auditor signatures")
    monkeypatch.setattr(manifest_audit, "auditor_revision", lambda: REVIEWED)
    tmp_path.chmod(0o700)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "implementer")
    git(repo, "config", "user.email", "implementer@example.invalid")
    commit(repo, {"src/app.py": "X = 1\n", "src/other.py": "Y = 1\n", "tests/test_app.py": "def test():\n    assert 1\n"},
           "base")
    git(repo, "switch", "-q", "-c", "candidate")
    commit(repo, {"src/app.py": "X = 2\n"}, "candidate change")
    git(repo, "switch", "-q", "main")
    commit(repo, {"src/other.py": "Y = 2\n"}, "target moved on")
    trust = tmp_path / "trust"
    state = tmp_path / "state"
    for directory in (trust, state):
        directory.mkdir(mode=0o700)
    key = state / "auditor.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True)
    key.chmod(0o600)
    public = subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout"], check=True, capture_output=True,
                            text=True).stdout
    policy_path = trust / "policy.json"
    registry_path = state / "registry.json"
    anchor_path = trust / "anchor.json"
    attribution_path = trust / "attribution.json"
    ledger_anchor_path = trust / "ledger.anchor"
    attributed = {}

    def write_private(path, text):
        if path.exists():
            path.chmod(0o600)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)

    def attribute(sha, identities=("aao-impl-codex[bot]",)):
        attributed[sha] = list(identities)
        write_private(attribution_path, json.dumps({"schema": "aao.implementer-attribution.v1",
                                                    "candidates": attributed}))

    write_private(attribution_path, json.dumps({"schema": "aao.implementer-attribution.v1", "candidates": {}}))
    supervisor_key = state / "supervisor.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(supervisor_key)], check=True)
    supervisor_key.chmod(0o600)
    supervisor_public = subprocess.run(["openssl", "pkey", "-in", str(supervisor_key), "-pubout"], check=True,
                                       capture_output=True, text=True).stdout
    heartbeat_path = state / "heartbeat.json"
    intake_dir = tempfile.mkdtemp(prefix="aaoi", dir="/tmp")
    intake_socket = os.path.join(intake_dir, "s")
    _start_intake(request, intake_socket, state, supervisor_key, heartbeat_path, public)
    write_private(ledger_anchor_path, "0" * 64)

    def configure(policy_overrides=None, **anchor_overrides):
        policy = {
            "version": "GOV-REV-001/v1.1", "auditor_id": "aao-auditor", "auditor_os_user": USER,
            "developer_os_users": ["implementer-account"], "required_checks": [],
            "auditors": {"aao-auditor": "anchored"}, "audit_checks": {"unit": ["-m", "pytest"]},
            "protected_paths": ["src/aao/pr_conformity.py"], "push_principals": {
                "aao-impl-claude[bot]": "claude", "aao-impl-codex[bot]": "codex",
                "aao-impl-agy[bot]": "antigravity"}, "dispositions": {},
            "protected_routes": route_map(load_document()),
            "protected_routes_sha256": routes_digest(load_document()["routes"]),
            "trusted_auditor_revisions": [REVIEWED], **(policy_overrides or {}),
        }
        for path in (policy_path, anchor_path):
            if path.exists():
                path.chmod(0o600)
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        policy_path.chmod(0o600)
        registry_path.write_text(json.dumps({
            "protected_routes": policy["protected_routes"],
            "protected_routes_sha256": policy["protected_routes_sha256"],
            "required_check_publishers": {"aao-audit": [5448107], "test": [15368]},
            "push_principals": policy["push_principals"],
        }), encoding="utf-8")
        registry_path.chmod(0o600)
        anchor = {"schema": "aao.audit-trust-anchor.v1", "policy_path": str(policy_path),
                  "policy_sha256": hashlib.sha256(_canonical(policy)).hexdigest(), "auditor_uid": UID,
                  "auditor_public_key": public, "ledger_path": str(state / "ledger.jsonl"),
                  "ledger_anchor_path": str(ledger_anchor_path), "attribution_path": str(attribution_path),
                  "attribution_writer_uid": UID,
                  "supervisor_public_key": supervisor_public, "supervisor_key_id": "supervisor",
                  "supervisor_heartbeat_path": str(heartbeat_path), "supervisor_intake_socket": intake_socket,
                  **anchor_overrides}
        anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
        anchor_path.chmod(0o600)

    configure()
    return {"tmp": tmp_path, "repo": repo, "key": key, "state": state, "anchor": anchor_path,
            "policy": policy_path, "registry": registry_path, "configure": configure, "attribute": attribute,
            "ledger_anchor": ledger_anchor_path, "write_private": write_private,
            "heartbeat": lambda: _supervisor_heartbeat(state, supervisor_key, heartbeat_path, public),
            "heartbeat_path": heartbeat_path}


def manifest(env, name="manifest.json", candidate="candidate", attribute=True, **overrides):
    repo = env["repo"]
    target = git(repo, "rev-parse", "main")
    sha = git(repo, "rev-parse", candidate)
    if attribute:
        env["attribute"](sha)
    merged = subprocess.run(["git", "-C", str(repo), "merge-tree", "--write-tree", target, sha],
                            capture_output=True, text=True, check=False).stdout.split()
    data = {"schema": "aao.candidate-manifest.v1", "repository": str(repo), "target_ref": "refs/heads/main",
            "target_sha": target, "candidate_sha": sha, "candidate_tree": git(repo, "rev-parse", f"{sha}^{{tree}}"),
            "result_tree": merged[0] if merged else "0" * 40, "producer": "integration-controller", **overrides}
    path = env["tmp"] / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def audit(env, path, run="run", **kwargs):
    kwargs.setdefault("key_path", env["key"])
    return audit_manifest(path, env["state"] / run, kwargs.pop("key_path"), anchor_path=env["anchor"],
                          anchor_owner_uids=(UID,), runner=kwargs.pop("runner", ok_runner), **kwargs)


_HEARTBEAT_SEQUENCE = [0]


def _start_intake(request, socket_path, state, supervisor_key, heartbeat_path, auditor_public, uid=None):
    """Real supervisor veto intake (aao.supervisor.handle_veto_report) served from a thread."""
    import socket as socket_module
    import threading

    from aao.supervisor import handle_veto_report

    auditor_pub = state / "auditor-for-supervisor.pub"
    auditor_pub.write_text(auditor_public, encoding="ascii")
    ledger = state / "ledger.jsonl"
    if not ledger.exists():
        ledger.touch(mode=0o600)
    server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(4)
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                handle_veto_report(conn, auditor_uid=UID if uid is None else uid,
                                   state_path=state / "supervisor-state.json", private_key=str(supervisor_key),
                                   key_id="supervisor", ledger_path=ledger, integrator_key_id="integrator",
                                   trusted_keys={"aao-auditor": {"public_key": str(auditor_pub),
                                                                 "can_resolve_pending": True}},
                                   heartbeat_path=heartbeat_path)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()

    def close():
        stop.set()
        server.close()
        shutil.rmtree(os.path.dirname(socket_path), ignore_errors=True)

    request.addfinalizer(close)


def _supervisor_heartbeat(state, supervisor_key, heartbeat_path, auditor_public):
    """Run the real supervisor (aao.supervisor.signed_heartbeat) over the current ledger and markers."""
    from datetime import UTC, datetime, timedelta

    from aao.supervisor import signed_heartbeat

    ledger = state / "ledger.jsonl"
    if not ledger.exists():
        ledger.touch(mode=0o600)
    auditor_pub = state / "auditor-for-supervisor.pub"
    auditor_pub.write_text(auditor_public, encoding="ascii")
    import time

    sequence = time.time_ns() // 1000   # monotonic across helper and intake publications
    now = datetime.now(UTC)
    event = signed_heartbeat(sequence, now.isoformat(), str(supervisor_key), key_id="supervisor",
                             expires_at=(now + timedelta(minutes=10)).isoformat(), ledger_path=ledger,
                             state_path=state / "supervisor-state.json", integrator_key_id="integrator",
                             trusted_keys={"aao-auditor": {"public_key": str(auditor_pub), "can_resolve_pending": True}},
                             heartbeat_path=heartbeat_path)
    return event


def gate(env, path, run="run", promoted=None, refresh=True):
    if refresh:
        try:
            env["heartbeat"]()
        except (ValueError, OSError):
            pass  # the real supervisor refuses to sign a tampered state: the previous heartbeat stays in place
    out = env["state"] / run
    return verify_promotion(path, out / "report.json", out / "report.sig", promoted,
                            anchor_path=env["anchor"], anchor_owner_uids=(UID,))


def merge_commit(env, data, tree=None, parents=None):
    parents = parents or [data["target_sha"], data["candidate_sha"]]
    args = [arg for parent in parents for arg in ("-p", parent)]
    return git(env["repo"], "commit-tree", tree or data["result_tree"], *args, "-m", "promote")


def test_resulting_tree_is_audited_signed_and_promotable(env):
    path, data = manifest(env)
    report = audit(env, path)
    assert report["verdict"] == "approve", report["custody_problems"] + report["blocking_findings"]
    assert report["result_tree"] == data["result_tree"] != data["candidate_tree"]
    assert gate(env, path) == (True, ())
    assert gate(env, path, promoted=merge_commit(env, data)) == (True, ())


def test_fast_forward_promotion_of_candidate_is_accepted(env):
    git(env["repo"], "switch", "-q", "-c", "ff", "main")
    commit(env["repo"], {"src/app.py": "X = 3\n"}, "ff change")
    git(env["repo"], "switch", "-q", "main")
    path, data = manifest(env, candidate="ff")
    assert data["result_tree"] == data["candidate_tree"]
    audit(env, path)
    assert gate(env, path, promoted=data["candidate_sha"]) == (True, ())


@pytest.mark.parametrize("field", ["candidate_tree", "result_tree"])
def test_tree_claim_that_does_not_match_git_is_refused(env, field):
    path, _ = manifest(env, **{field: "c" * 40})
    with pytest.raises(AuditError, match=field):
        audit(env, path)


@pytest.mark.nt("NT-03-7")
def test_conflicting_candidate_is_refused(env):
    git(env["repo"], "switch", "-q", "-c", "conflict", "main~1")
    commit(env["repo"], {"src/other.py": "Y = 99\n"}, "conflict")
    git(env["repo"], "switch", "-q", "main")
    path, _ = manifest(env, candidate="conflict")
    with pytest.raises(AuditError, match="merge cleanly"):
        audit(env, path)


@pytest.mark.nt("NT-03-2")
def test_target_moving_after_audit_blocks_the_gate(env):
    path, _ = manifest(env)
    audit(env, path)
    commit(env["repo"], {"src/third.py": "Z = 1\n"}, "concurrent push")
    ok, reasons = gate(env, path)
    assert not ok and "target ref no longer points to the manifest target_sha" in reasons


def test_absent_promoted_commit_raises_even_after_target_moved(env):
    # Callers publish a check for any (ok, reasons) answer; an absent commit must raise instead, whatever
    # other check would fail first (git 2.56 moves the mirror target on push-by-URL, git 2.43 does not).
    path, _ = manifest(env)
    audit(env, path)
    commit(env["repo"], {"src/third.py": "Z = 1\n"}, "concurrent push")
    with pytest.raises(subprocess.CalledProcessError):
        gate(env, path, promoted="f" * 40)


@pytest.mark.nt("NT-03-3")
@pytest.mark.nt("NT-03-5")
def test_promoted_commit_must_carry_the_audited_tree_and_parents(env):
    path, data = manifest(env)
    audit(env, path)
    wrong_tree = merge_commit(env, data, tree=data["candidate_tree"])
    assert "promoted commit tree is not the audited result_tree" in gate(env, path, promoted=wrong_tree)[1]
    wrong_parent = merge_commit(env, data, parents=[data["candidate_sha"], data["target_sha"]])
    assert "promoted commit parents are not [target_sha, candidate_sha]" in gate(env, path, promoted=wrong_parent)[1]


@pytest.mark.parametrize("overrides", [
    {"policy_path": "/tmp/attacker-policy.json"},
    {"target_ref": "main"},
    {"candidate_sha": "candidate"},
    {"repository": "relative/path"},
])
def test_malformed_or_overreaching_manifest_is_refused(env, overrides):
    path, _ = manifest(env, **overrides)
    with pytest.raises(AuditError, match="manifest is invalid"):
        audit(env, path)


def test_anchor_must_be_a_private_regular_file_with_safe_parents(env):
    path, _ = manifest(env)
    env["anchor"].chmod(0o660)
    with pytest.raises(AuditError, match="group/other writable"):
        audit(env, path)
    env["anchor"].chmod(0o600)
    link = env["tmp"] / "trust" / "link.json"
    link.symlink_to(env["anchor"])
    with pytest.raises(AuditError, match="symlink"):
        audit_manifest(path, env["state"] / "x", env["key"], anchor_path=link, anchor_owner_uids=(UID,))
    (env["tmp"] / "trust").chmod(0o770)
    with pytest.raises(AuditError, match="replaced"):
        audit(env, path)
    (env["tmp"] / "trust").chmod(0o700)
    with pytest.raises(AuditError, match="missing"):
        audit_manifest(path, env["state"] / "x", env["key"], anchor_path=env["tmp"] / "none.json",
                       anchor_owner_uids=(UID,))
    assert gate(env, path, run="never")[0] is False


def test_policy_must_match_the_anchor_pin_and_owner(env):
    path, _ = manifest(env)
    env["configure"](policy_sha256="d" * 64)
    with pytest.raises(AuditError, match="pinned"):
        audit(env, path)
    env["configure"](auditor_uid=UID + 1)
    with pytest.raises(AuditError, match="trusted uid"):
        audit(env, path)


def test_key_not_pinned_by_anchor_or_developer_account_is_provisional_and_unsigned(env):
    path, _ = manifest(env)
    other = env["state"] / "other.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(other)], check=True)
    other.chmod(0o600)
    report = audit(env, path, key_path=other)
    assert report["verdict"] == "provisional"
    assert "signing key does not match the anchored auditor public key" in report["custody_problems"]
    assert "signed audit report is absent" in gate(env, path)[1]
    env["configure"]({"developer_os_users": [USER]})
    assert audit(env, path, run="dev")["verdict"] == "provisional"


def test_tampered_evidence_or_report_fails_the_gate(env):
    path, _ = manifest(env)
    report = audit(env, path)
    evidence = next(iter(report["evidence_files"].values()))
    os.chmod(evidence, 0o600)
    with open(evidence, "ab") as handle:
        handle.write(b" ")
    os.chmod(evidence, 0o444)
    assert any("does not match its digest" in r for r in gate(env, path)[1])
    report_path = env["state"] / "run" / "report.json"
    report_path.chmod(0o600)
    report_path.write_bytes(_canonical({**report, "blocking_findings": []}).replace(b'"approve"', b'"approve" '))
    assert not gate(env, path)[0]


def test_veto_after_approval_is_sticky(env):
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", veto_reason="unsafe")
    reasons = gate(env, path)[1]
    assert "candidate has a recorded audit veto" in reasons
    assert "report is not the latest recorded decision for this candidate" in reasons


def test_group_writable_ledger_is_not_trusted(env):
    path, _ = manifest(env)
    audit(env, path)
    (env["state"] / "ledger.jsonl").chmod(0o660)
    assert any("ledger is not trustworthy" in r for r in gate(env, path)[1])


def test_protected_path_in_result_tree_blocks(env):
    git(env["repo"], "switch", "-q", "candidate")
    commit(env["repo"], {"src/aao/pr_conformity.py": "weak = True\n"}, "touch gate")
    git(env["repo"], "switch", "-q", "main")
    path, _ = manifest(env)
    report = audit(env, path)
    assert report["verdict"] == "reject"
    assert "protected-path:src/aao/pr_conformity.py" in report["blocking_findings"]
    assert not gate(env, path)[0]


def test_gate_rejects_report_from_auditor_revision_no_longer_trusted(env):
    path, _ = manifest(env)
    audit(env, path)
    env["configure"]({"trusted_auditor_revisions": ["c" * 40]})
    reasons = gate(env, path)[1]
    assert "report was produced by an auditor revision the anchored policy does not trust" in reasons


# --- Second-line review SL-02/SL-03 (trust root) ------------------------------------------------------------

@pytest.mark.nt("NT-02-9")
def test_unattributed_candidate_is_provisional_even_with_valid_custody(env):
    path, _ = manifest(env, attribute=False)
    report = audit(env, path)
    assert report["verdict"] == "provisional"
    assert "implementer attribution is unresolved" in report["custody_problems"]
    assert report["implementer_ids"] == [] and "integration-controller" in report["declared_implementers"]
    assert not gate(env, path)[0]


@pytest.mark.nt("NT-02-1")
@pytest.mark.nt("NT-02-2")
def test_manifest_and_git_metadata_do_not_authenticate_the_implementer(env):
    path, data = manifest(env, producer="forged-producer")
    # Git author and committer metadata are mutable candidate claims too.
    previous = git(env["repo"], "rev-parse", "--abbrev-ref", "HEAD")
    git(env["repo"], "checkout", "-q", "candidate")
    git(env["repo"], "-c", "user.name=forged-committer", "-c", "user.email=forged-committer@example.invalid",
        "commit", "--allow-empty", "--amend", "--no-edit", "--author=forged-author <forged-author@example.invalid>")
    git(env["repo"], "checkout", "-q", previous)
    candidate = git(env["repo"], "rev-parse", "candidate")
    data["candidate_sha"] = candidate
    data["candidate_tree"] = git(env["repo"], "rev-parse", f"{candidate}^{{tree}}")
    data["result_tree"] = subprocess.run(
        ["git", "-C", str(env["repo"]), "merge-tree", "--write-tree", data["target_sha"], candidate],
        capture_output=True, text=True, check=False).stdout.split()[0]
    data["producer"] = "forged-producer"
    path.write_text(json.dumps(data), encoding="utf-8")
    env["attribute"](candidate, ["aao-impl-codex[bot]"])

    report = audit(env, path, run="forged-metadata")
    assert report["implementer_ids"] == ["codex"]
    assert set(report["declared_implementers"]) >= {"forged-producer", "forged-author@example.invalid"}
    assert git(env["repo"], "show", "-s", "--format=%ce", candidate) == "forged-committer@example.invalid"
    assert "forged-committer@example.invalid" not in report["implementer_ids"]
    # The declared claims may only tighten recusal; they never become the attribution result.
    assert "implementer attribution is unresolved" not in report["custody_problems"]


@pytest.mark.nt("NT-02-8")
def test_recusal_uses_attribution_and_declared_identities_only_tighten(env):
    path, data = manifest(env)
    env["attribute"](data["candidate_sha"], ["aao-auditor"])  # authenticated pusher is the auditor itself
    assert "auditor-is-implementer" in audit(env, path)["blocking_findings"]
    path, data = manifest(env, name="declared.json", producer="aao-auditor")
    env["attribute"](data["candidate_sha"], ["aao-impl-codex[bot]"])  # a declared match still blocks (stricter only)
    assert "auditor-is-implementer" in audit(env, path, run="declared")["blocking_findings"]


def test_attribution_file_writable_by_others_is_not_trusted(env):
    path, _ = manifest(env)
    attribution = env["tmp"] / "trust" / "attribution.json"
    attribution.chmod(0o660)
    assert "implementer attribution is unresolved" in audit(env, path)["custody_problems"]


def _ledger_lines(env):
    return (env["state"] / "ledger.jsonl").read_bytes().splitlines()


def _rewrite_chain(rows):
    """What an attacker with file access but no auditor key can do: drop rows and recompute the hash chain."""
    previous, out = "0" * 64, []
    for number, row in enumerate(rows, 1):
        row = {k: v for k, v in row.items() if k != "hash"}
        row.update(sequence=number, previous_hash=previous)
        row["hash"] = hashlib.sha256(_canonical(row)).hexdigest()
        previous = row["hash"]
        out.append(_canonical(row))
    return b"\n".join(out) + b"\n"


@pytest.mark.nt("NT-02-6")
def test_ledger_rewritten_without_an_intermediate_veto_and_rehashed_is_rejected(env):
    # SL-06: delete a veto in the middle and recompute the hash chain. Later entries change sequence and
    # previous_hash, which are signed, so the rewrite fails without the auditor key.
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", veto_reason="unsafe")
    audit(env, path, run="again")
    rows = [json.loads(line) for line in _ledger_lines(env)]
    assert [r["type"] for r in rows] == ["audit-verdict", "veto", "audit-verdict"]
    (env["state"] / "ledger.jsonl").write_bytes(_rewrite_chain([rows[0], rows[2]]))
    assert any("ledger is not trustworthy" in r for r in gate(env, path, run="again")[1])


@pytest.mark.nt("NT-02-7")
def test_ledger_tail_truncation_below_the_external_anchor_is_rejected(env):
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", veto_reason="unsafe")
    lines = _ledger_lines(env)
    env["write_private"](env["ledger_anchor"], json.loads(lines[-1])["hash"])  # custodian anchors the veto
    (env["state"] / "ledger.jsonl").write_bytes(lines[0] + b"\n")  # signed prefix kept, veto truncated
    reasons = gate(env, path)[1]
    assert any("does not contain its external anchor" in r for r in reasons)


def test_ledger_entry_signed_by_another_key_is_rejected(env):
    path, data = manifest(env)
    audit(env, path)
    rogue = env["state"] / "rogue.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(rogue)], check=True)
    previous = json.loads(_ledger_lines(env)[-1])
    report = (env["state"] / "run" / "report.json").read_bytes()
    entry = {"sequence": 2, "previous_hash": previous["hash"], "key_id": "aao-auditor", "type": "audit-verdict",
             "candidate_sha": data["candidate_sha"], "result_tree": data["result_tree"],
             "report_sha256": hashlib.sha256(report).hexdigest(), "verdict": "approve", "veto": False}
    message = env["state"] / "msg"
    message.write_bytes(_canonical(entry))
    signature = subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(rogue), "-in", str(message)],
                               check=True, capture_output=True).stdout
    entry["signature"] = base64.b64encode(signature).decode()
    entry["hash"] = hashlib.sha256(_canonical(entry)).hexdigest()
    with (env["state"] / "ledger.jsonl").open("ab") as handle:
        handle.write(_canonical(entry) + b"\n")
    assert any("ledger is not trustworthy" in r for r in gate(env, path)[1])


def test_provisional_and_custody_less_veto_write_a_report_but_record_nothing(env):
    # SL-07: the contract distinguishes "report emitted" from "decision recorded in the ledger".
    path, _ = manifest(env, attribute=False)
    ledger = env["state"] / "ledger.jsonl"
    report = audit(env, path)
    assert report["verdict"] == "provisional"
    assert (env["state"] / "run" / "report.json").is_file()
    assert not (env["state"] / "run" / "report.sig").exists()
    assert ledger.read_bytes() == b""  # nothing recorded for a provisional run
    veto = audit(env, path, run="veto", veto_reason="unsafe")  # veto without resolved attribution = no custody
    assert veto["verdict"] == "veto" and veto["custody_problems"]
    assert ledger.read_bytes() == b""  # an unsigned veto is not a recorded decision


# --- F4-02: a veto without custody must never allow an improper integration -------------------------------

def _rogue_key(env):
    other = env["state"] / "rogue-veto.pem"
    if not other.exists():
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(other)], check=True)
        other.chmod(0o600)
    return other


def test_custodyless_veto_after_recorded_approval_blocks_integration(env):
    path, _ = manifest(env)
    assert audit(env, path)["verdict"] == "approve"
    assert gate(env, path) == (True, ())
    veto = audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    assert veto["verdict"] == "veto" and veto["custody_problems"]
    conformant, reasons = gate(env, path)  # the earlier signed approval is still the latest ledger decision
    assert not conformant
    assert "candidate has an unresolved pending veto (recorded without custody)" in reasons


def test_later_signed_approval_does_not_lift_a_pending_veto_unless_explicit(env):
    path, _ = manifest(env)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    audit(env, path, run="again")
    assert not gate(env, path, run="again")[0]
    audit(env, path, run="resolved", resolve_pending_vetoes=True)
    assert gate(env, path, run="resolved") == (True, ())


def test_tampered_or_exposed_pending_veto_marker_fails_closed(env):
    path, _ = manifest(env)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    audit(env, path, run="resolved", resolve_pending_vetoes=True)
    directory = env["state"] / "ledger.jsonl.pending-vetoes"
    marker = next(directory.iterdir())
    marker.chmod(0o600)
    marker.write_bytes(marker.read_bytes().replace(b"unsafe", b"safe!!"))
    assert any("pending vetoes cannot be verified" in r for r in gate(env, path, run="resolved")[1])
    marker.unlink()
    directory.chmod(0o770)
    assert any("pending vetoes cannot be verified" in r for r in gate(env, path, run="resolved")[1])


def test_veto_that_cannot_record_its_marker_raises(env):
    path, _ = manifest(env)
    directory = env["state"] / "ledger.jsonl.pending-vetoes"
    directory.mkdir(mode=0o500)
    with pytest.raises(AuditError, match="cannot record pending veto marker"):
        audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    directory.chmod(0o700)


def test_pending_veto_marker_is_written_before_any_analysis(env, monkeypatch):
    # A-1 (Codex review of #30): the marker must exist even if the run fails during analysis.
    path, _ = manifest(env)
    monkeypatch.setattr("aao.manifest_audit._check_parents", lambda _path, _owners: None)
    monkeypatch.setattr("aao.pending_veto._check_parents", lambda _path, _owners: None)
    assert audit(env, path)["verdict"] == "approve"

    def exploding_derive(_manifest, _clone):
        assert list((env["state"] / "ledger.jsonl.pending-vetoes").glob("*.json"))
        raise RuntimeError("analysis interrupted")

    with pytest.MonkeyPatch.context() as local_monkeypatch:
        local_monkeypatch.setattr(manifest_audit, "_derive", exploding_derive)
        with pytest.raises(RuntimeError, match="analysis interrupted"):
            audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    assert "candidate has an unresolved pending veto (recorded without custody)" in gate(env, path)[1]


def test_pending_veto_marker_uses_supervisor_readable_modes(env):
    path, _ = manifest(env)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    directory = env["state"] / "ledger.jsonl.pending-vetoes"
    marker = next(directory.iterdir())
    assert directory.stat().st_mode & 0o777 == 0o750
    assert marker.stat().st_mode & 0o777 == 0o640


def test_pending_veto_modes_ignore_restrictive_umask(env, monkeypatch):
    monkeypatch.setattr("aao.manifest_audit._check_parents", lambda path, owners: None)
    path, _ = manifest(env)
    previous = os.umask(0o077)
    try:
        audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    finally:
        os.umask(previous)
    directory = env["state"] / "ledger.jsonl.pending-vetoes"
    marker = next(directory.iterdir())
    assert directory.stat().st_mode & 0o777 == 0o750
    assert marker.stat().st_mode & 0o777 == 0o640


# --- F4-01b: supervisor custody on the manifest gate path ---------------------------------------------------

def test_gate_rejects_ledger_truncated_and_marker_removed_after_supervisor_anchor(env):
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", veto_reason="unsafe")   # custody-valid veto: marker + signed ledger row
    env["heartbeat"]()                                    # the supervisor anchors head and the marker
    ledger = env["state"] / "ledger.jsonl"
    ledger.write_bytes(ledger.read_bytes().splitlines(keepends=True)[0])   # drop the veto row
    for marker in (env["state"] / "ledger.jsonl.pending-vetoes").iterdir():
        marker.unlink()                                   # and the marker: without F4-01b the gate would pass
    conformant, reasons = gate(env, path)
    assert not conformant
    assert any("ledger truncated or rewritten since the supervisor anchored it" in r for r in reasons)


def test_gate_rejects_marker_deleted_after_supervisor_saw_it(env):
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")   # marker only, no ledger row
    env["heartbeat"]()
    for marker in (env["state"] / "ledger.jsonl.pending-vetoes").iterdir():
        marker.unlink()
    conformant, reasons = gate(env, path, refresh=False)
    assert not conformant
    assert any("pending veto marker deleted after the supervisor recorded it" in r for r in reasons)


def test_gate_requires_a_valid_supervisor_heartbeat(env):
    path, _ = manifest(env)
    audit(env, path)
    env["heartbeat_path"].unlink(missing_ok=True)
    assert any("supervisor custody check failed" in r for r in gate(env, path, refresh=False)[1])
    event = env["heartbeat"]()
    env["heartbeat_path"].write_text(json.dumps({**event, "ledger_head": "f" * 64}), encoding="utf-8")
    assert any("signature does not verify" in r for r in gate(env, path, refresh=False)[1])


def test_gate_waits_for_entries_not_yet_anchored_by_the_supervisor(env):
    path, _ = manifest(env)
    env["heartbeat"]()            # anchors the empty ledger
    audit(env, path)              # new signed entry, not anchored yet
    assert any("ledger not yet anchored by the supervisor" in r for r in gate(env, path, refresh=False)[1])
    assert gate(env, path) == (True, ())


def test_gate_uses_one_snapshot_so_a_marker_deleted_between_reads_still_blocks(env, monkeypatch):
    # A-3 (Codex second-line review of F4-01b): delete the marker right after the gate reads it.
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    env["heartbeat"]()
    real = manifest_audit.pending_vetoes
    calls = []

    def read_then_delete(anchor, candidate_sha):
        result = real(anchor, candidate_sha)
        calls.append(len(result))
        for marker in (env["state"] / "ledger.jsonl.pending-vetoes").iterdir():
            marker.unlink()
        return result

    monkeypatch.setattr(manifest_audit, "pending_vetoes", read_then_delete)
    conformant, reasons = gate(env, path, refresh=False)
    assert not conformant
    assert calls == [1]  # a single read of the markers per gate decision
    assert "candidate has an unresolved pending veto (recorded without custody)" in reasons


# --- F4-03: synchronous veto hand-off to the supervisor --------------------------------------------------

def test_veto_marker_deleted_before_any_scheduled_heartbeat_is_still_detected(env):
    # Closes the pre-heartbeat window of A-2: the veto run itself hands the marker to the supervisor.
    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    for marker in (env["state"] / "ledger.jsonl.pending-vetoes").iterdir():
        marker.unlink()          # another process of the auditor uid removes it right away
    conformant, reasons = gate(env, path, refresh=False)
    assert not conformant
    assert any("pending veto marker deleted after the supervisor recorded it" in r for r in reasons)


def test_veto_run_aborts_when_the_supervisor_is_unreachable_and_the_marker_still_blocks(env):
    path, _ = manifest(env)
    audit(env, path)
    env["configure"](supervisor_intake_socket="/nonexistent/aao-intake.sock")
    with pytest.raises(AuditError, match="supervisor did not acknowledge the veto"):
        audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    assert any("unresolved pending veto" in r for r in gate(env, path)[1])


def test_supervisor_intake_rejects_a_peer_that_is_not_the_auditor_uid(env, request):
    path, _ = manifest(env)
    other = os.path.join(tempfile.mkdtemp(prefix="aaoj", dir="/tmp"), "s")
    _start_intake(request, other, env["state"], env["state"] / "supervisor.pem", env["heartbeat_path"],
                  subprocess.run(["openssl", "pkey", "-in", str(env["key"]), "-pubout"], check=True,
                                 capture_output=True, text=True).stdout, uid=UID + 4242)
    env["configure"](supervisor_intake_socket=other)
    with pytest.raises(AuditError, match="peer is not the auditor uid"):
        audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")



def test_periodic_heartbeat_computed_before_the_intake_cannot_overwrite_it(env):
    # F4-03 r1 A (Codex): publication is serialized with the state and never moves backwards.
    from datetime import UTC, datetime, timedelta

    from aao.supervisor import signed_heartbeat

    path, _ = manifest(env)
    audit(env, path)
    audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")
    published = json.loads(env["heartbeat_path"].read_text())
    candidate = next(iter(published["pending_markers"]))
    now = datetime.now(UTC)
    auditor_pub = env["state"] / "auditor-for-supervisor.pub"
    with pytest.raises(ValueError, match="equal or newer sequence is already published"):
        signed_heartbeat(1, now.isoformat(), str(env["state"] / "supervisor.pem"), key_id="supervisor",
                         expires_at=(now + timedelta(minutes=10)).isoformat(),
                         ledger_path=env["state"] / "ledger.jsonl", state_path=env["state"] / "supervisor-state.json",
                         integrator_key_id="integrator",
                         trusted_keys={"aao-auditor": {"public_key": str(auditor_pub), "can_resolve_pending": True}},
                         heartbeat_path=env["heartbeat_path"])
    assert json.loads(env["heartbeat_path"].read_text())["pending_markers"][candidate]  # the veto is still there


def test_spoofed_intake_acknowledgement_without_a_signed_heartbeat_is_rejected(env, request):
    import socket as socket_module
    import threading

    path, _ = manifest(env)
    fake = os.path.join(tempfile.mkdtemp(prefix="aaok", dir="/tmp"), "s")
    server = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    server.bind(fake)
    server.listen(1)

    def lie():
        conn, _ = server.accept()
        with conn:
            conn.recv(4096)
            conn.sendall(b'{"ok": true, "heartbeat_sequence": 99}\n')

    threading.Thread(target=lie, daemon=True).start()
    request.addfinalizer(server.close)
    env["configure"](supervisor_intake_socket=fake)
    with pytest.raises(AuditError, match="not backed by a signed heartbeat"):
        audit(env, path, run="veto", key_path=_rogue_key(env), veto_reason="unsafe")


def test_supervisor_intake_rejects_oversized_or_unexpected_reports(env):
    import socket as socket_module

    from aao.supervisor import handle_veto_report

    for payload in (b'{"candidate_sha": "' + b"a" * 5000 + b'"}\n',
                    b'{"candidate_sha": "' + b"a" * 40 + b'", "marker_digest": "' + b"b" * 64 + b'", "x": 1}\n'):
        left, right = socket_module.socketpair(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        with left, right:
            left.sendall(payload)
            left.shutdown(socket_module.SHUT_WR)
            reply = handle_veto_report(right, auditor_uid=UID, state_path=env["state"] / "supervisor-state.json",
                                       private_key=str(env["state"] / "supervisor.pem"), key_id="supervisor",
                                       ledger_path=env["state"] / "ledger.jsonl", trusted_keys={"x": "y"},
                                       integrator_key_id="integrator", heartbeat_path=env["heartbeat_path"])
        assert reply["ok"] is False
