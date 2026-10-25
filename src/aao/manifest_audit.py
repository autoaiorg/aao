"""Audit local Git candidate manifests by exact SHA and resulting merge tree.

A manifest only selects a candidate; the auditor re-derives every fact it
asserts. Policy, auditor key, uid and ledger location come from a fixed trust
anchor that the caller cannot choose (Codex review H-01 on PR #14). The gate in
``verify_promotion`` is what an integration controller runs immediately before a
compare-and-swap ref update. See docs/AUDIT_MANIFEST_CONTRACT.md.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pwd
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aao import governance_ledger
from aao.independent_audit import (
    _LIMITATIONS,
    POLICY_VERSION,
    AuditError,
    _git,
    _is_sha,
    _visible_in_sandbox,
    _write_evidence,
    adversarial_findings,
    auditor_revision,
    parse_policy,
    run_sandboxed,
)
from aao.pending_veto import PendingVetoError
from aao.pending_veto import pending_vetoes as verify_pending_vetoes
from aao.pr_conformity import _canonical, _sha

ANCHOR_PATH = Path("/etc/aao-audit/trust-anchor.json")
ANCHOR_SCHEMA = "aao.audit-trust-anchor.v1"
MANIFEST_SCHEMA = "aao.candidate-manifest.v1"
REPORT_SCHEMA = "aao.manifest-audit-report.v1"
_MANIFEST_FIELDS = {"schema", "repository", "target_ref", "target_sha", "candidate_sha",
                    "candidate_tree", "result_tree", "producer"}
_GIT_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "LANG": "C.UTF-8"}
_ANCHOR_FIELDS = {"schema", "policy_path", "policy_sha256", "auditor_uid", "auditor_public_key", "ledger_path",
                  "ledger_anchor_path", "attribution_path",
                  "attribution_writer_uid",
                  "supervisor_public_key", "supervisor_key_id", "supervisor_heartbeat_path",
                  "supervisor_intake_socket"}
ATTRIBUTION_SCHEMA = "aao.implementer-attribution.v1"


def read_protected(path: Path, owner_uids: tuple[int, ...]) -> bytes:
    """Read a regular, non-symlink file owned by an allowed uid, with no group/other write on it or its parents."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        raise AuditError(f"{path} is missing or is a symlink") from error
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in owner_uids or info.st_mode & 0o022:
            raise AuditError(f"{path} is not owned by a trusted uid or is group/other writable")
        _check_parents(Path(path), owner_uids)
        return handle.read()


def _check_parents(path: Path, owner_uids: tuple[int, ...]) -> None:
    for parent in Path(os.path.abspath(path)).parents:
        info = os.lstat(parent)
        if stat.S_ISLNK(info.st_mode):
            raise AuditError(f"{parent} is a symlink")
        writable = info.st_mode & 0o022
        sticky_root = info.st_mode & stat.S_ISVTX and info.st_uid == 0
        if (writable and not sticky_root) or info.st_uid not in (0, *owner_uids):
            raise AuditError(f"{parent} allows the protected path to be replaced")


def load_anchor(anchor_path: Path = ANCHOR_PATH, anchor_owner_uids: tuple[int, ...] = (0,)) -> dict[str, Any]:
    """Load the fixed anchor and the policy it pins. Paths are never supplied by the caller in production."""
    raw = read_protected(anchor_path, anchor_owner_uids)
    try:
        anchor = json.loads(raw)
        if not isinstance(anchor, dict) or set(anchor) != _ANCHOR_FIELDS or anchor["schema"] != ANCHOR_SCHEMA:
            raise ValueError("unexpected anchor fields")
        if (not isinstance(anchor["auditor_uid"], int) or not isinstance(anchor["auditor_public_key"], str) or
                not isinstance(anchor["attribution_writer_uid"], int)):
            raise TypeError("malformed anchor identity")
    except (ValueError, TypeError) as error:
        raise AuditError(f"trust anchor is invalid: {error}") from error
    uid = anchor["auditor_uid"]
    policy, digest = parse_policy(read_protected(Path(anchor["policy_path"]), (uid,)))
    if digest != anchor["policy_sha256"]:
        raise AuditError("policy digest is not the one pinned by the trust anchor")
    return {**anchor, "policy": policy, "anchor_sha256": _sha(raw), "anchor_owner_uids": anchor_owner_uids}


def _pending_dir(anchor: dict[str, Any]) -> Path:
    """Pending-veto markers live next to the ledger, with the ledger's custody (auditor uid, no group/other write)."""
    return Path(anchor["ledger_path"] + ".pending-vetoes")


def record_pending_veto(anchor: dict[str, Any], candidate_sha: str, manifest_sha256: str, reason: str) -> str:
    """F4-02: every --veto leaves a marker, signed or not. Failing to write it is an error, never a silent pass."""
    directory = _pending_dir(anchor)
    try:
        if not directory.exists():
            _check_parents(directory, (anchor["auditor_uid"],))
            directory.mkdir(mode=0o750)
            directory.chmod(0o750)
        marker = {"schema": "aao.pending-veto.v1", "candidate_sha": candidate_sha,
                  "manifest_sha256": manifest_sha256, "reason": reason}
        data = _canonical(marker)
        digest = _sha(data)
        path = directory / f"{candidate_sha}-{digest}.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640)
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except FileExistsError:
        return digest
    except OSError as error:
        raise AuditError(f"cannot record pending veto marker: {error}") from error
    return digest


def pending_vetoes(anchor: dict[str, Any], candidate_sha: str) -> list[str]:
    """Digests of pending-veto markers for a candidate. Unreadable or unsafe markers raise (fail closed)."""
    directory = _pending_dir(anchor)
    try:
        return verify_pending_vetoes(directory, candidate_sha, anchor["auditor_uid"])
    except PendingVetoError as error:
        raise AuditError(str(error)) from error


def _report_veto_to_supervisor(anchor: dict[str, Any], candidate_sha: str, digest: str) -> None:
    """F4-03: hand the veto to the supervisor's custody before analysis continues; no ack, no audit."""
    import socket

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(30)
            client.connect(anchor["supervisor_intake_socket"])
            try:
                client.sendall(json.dumps({"candidate_sha": candidate_sha, "marker_digest": digest}).encode() + b"\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # the supervisor may refuse the peer and close before reading; its reply is still readable
            answer = b""
            while not answer.endswith(b"\n"):
                chunk = client.recv(4096)
                if not chunk:
                    break
                answer += chunk
        reply = json.loads(answer)
    except (OSError, ValueError) as error:
        raise AuditError(f"supervisor did not acknowledge the veto (marker kept, run aborted): {error}") from error
    if reply.get("ok") is not True:
        raise AuditError(f"supervisor refused the veto report (marker kept, run aborted): {reply.get('error')}")
    # The acknowledgement itself is unauthenticated; the proof is the supervisor-signed heartbeat that must
    # now list this marker (a spoofed socket cannot produce it without the supervisor key).
    from aao.supervisor import verify_heartbeat

    try:
        with tempfile.TemporaryDirectory(prefix="aao-supervisor-key-") as temporary:
            public = Path(temporary) / "supervisor.pub"
            public.write_text(anchor["supervisor_public_key"], encoding="ascii")
            heartbeat = verify_heartbeat(json.loads(Path(anchor["supervisor_heartbeat_path"]).read_bytes()),
                                         str(public), anchor["supervisor_key_id"], datetime.now(UTC))
    except (OSError, ValueError) as error:
        raise AuditError(f"supervisor acknowledgement not backed by a signed heartbeat: {error}") from error
    if digest not in heartbeat["pending_markers"].get(candidate_sha, []):
        raise AuditError("supervisor acknowledgement not backed by a signed heartbeat listing the marker")


def _supervisor_custody(anchor: dict[str, Any], candidate_sha: str, rows: list[dict[str, Any]],
                        markers: list[str]) -> None:
    """F4-01b: the ledger terminal must equal the head the supervisor signed, and no marker the supervisor
    has seen for this candidate may have disappeared without an authorized resolution."""
    from aao.supervisor import verify_heartbeat

    raw = Path(anchor["supervisor_heartbeat_path"]).read_bytes()
    with tempfile.TemporaryDirectory(prefix="aao-supervisor-key-") as temporary:
        public = Path(temporary) / "supervisor.pub"
        public.write_text(anchor["supervisor_public_key"], encoding="ascii")
        heartbeat = verify_heartbeat(json.loads(raw), str(public), anchor["supervisor_key_id"], datetime.now(UTC))
    terminal = rows[-1]["hash"] if rows else "0" * 64
    if terminal != heartbeat["ledger_head"]:
        if heartbeat["ledger_head"] == "0" * 64 or heartbeat["ledger_head"] in {r["hash"] for r in rows}:
            raise AuditError("ledger not yet anchored by the supervisor")
        raise AuditError("ledger truncated or rewritten since the supervisor anchored it")
    resolved = {d for r in rows for d in r.get("resolves_pending") or []}
    present = set(markers)
    seen = set(heartbeat["pending_markers"].get(candidate_sha, []))
    if seen - present - resolved:
        raise AuditError("pending veto marker deleted after the supervisor recorded it")


def attributed_principals(anchor: dict[str, Any], candidate_sha: str) -> list[str]:
    """Authenticated push principals from the protected attribution source.

    Keep these even when the registry cannot resolve them: their presence can only
    tighten recusal, never establish an implementer identity.
    """
    try:
        owners = tuple(dict.fromkeys((*anchor["anchor_owner_uids"], anchor["attribution_writer_uid"])))
        data = json.loads(read_protected(Path(anchor["attribution_path"]), owners))
        identities = data["candidates"][candidate_sha] if data.get("schema") == ATTRIBUTION_SCHEMA else None
    except (AuditError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    if not isinstance(identities, list) or not identities or not all(isinstance(i, str) for i in identities):
        return []
    return sorted(set(identities))


def attributed_implementers(anchor: dict[str, Any], candidate_sha: str) -> list[str]:
    """Implementer identities from registered principals in the anchored source only.

    The file is written by the merge authority from authenticated push events (RA-02) and is owned like the
    trust anchor. An absent file, unknown candidate or empty list means attribution is unresolved."""
    identities = attributed_principals(anchor, candidate_sha)
    principal_map = anchor.get("policy", {}).get("push_principals")
    if (not isinstance(principal_map, dict) or not principal_map
            or len(set(principal_map.values())) != len(principal_map)
            or not isinstance(identities, list) or not identities
            or not all(isinstance(i, str) and i in principal_map for i in identities)):
        return []
    return sorted({principal_map[principal] for principal in identities})


def _ledger_keys(anchor: dict[str, Any], directory: Path) -> dict[str, Any]:
    """Trusted signer registry for the audit ledger: only the anchored auditor key."""
    public = directory / "auditor.pub"
    public.write_text(anchor["auditor_public_key"], encoding="ascii")
    return {anchor["policy"]["auditor_id"]: {
        "public_key": str(public), "can_resolve_pending": True,
    }}


def ledger_rows(anchor: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify every entry signature and that the externally anchored hash is still part of the chain."""
    ledger = _ledger(anchor)
    try:
        expected = read_protected(Path(anchor["ledger_anchor_path"]), anchor["anchor_owner_uids"]).decode().strip()
        with tempfile.TemporaryDirectory(prefix="aao-ledger-keys-") as temporary:
            rows = governance_ledger.verify(ledger, _ledger_keys(anchor, Path(temporary)))
    except (OSError, ValueError, UnicodeDecodeError) as error:
        raise AuditError(f"audit ledger is not trustworthy: {error}") from error
    if expected != "0" * 64 and expected not in {r["hash"] for r in rows}:
        raise AuditError("audit ledger does not contain its external anchor (truncated or rewritten)")
    return rows


def parse_manifest(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
            raise ValueError("manifest fields must be exactly " + ", ".join(sorted(_MANIFEST_FIELDS)))
        if manifest["schema"] != MANIFEST_SCHEMA:
            raise ValueError("unsupported manifest schema")
        for field in ("target_sha", "candidate_sha", "candidate_tree", "result_tree"):
            if not _is_sha(manifest[field]):
                raise ValueError(f"{field} must be a full lowercase SHA-1")
        if not isinstance(manifest["target_ref"], str) or not manifest["target_ref"].startswith("refs/heads/"):
            raise ValueError("target_ref must be a full refs/heads/ name")
        if not isinstance(manifest["repository"], str) or not os.path.isabs(manifest["repository"]):
            raise ValueError("repository must be an absolute local path")
        if not isinstance(manifest["producer"], str) or not manifest["producer"]:
            raise ValueError("producer is required")
    except (OSError, ValueError, TypeError) as error:
        raise AuditError(f"candidate manifest is invalid: {error}") from error
    return manifest, _sha(_canonical(manifest))


def _derive(manifest: dict[str, Any], clone: Path) -> None:
    """Clone the producer's repository and re-derive both trees; never write to the producer's object store."""
    if _ref_value(manifest) != manifest["target_sha"]:
        raise AuditError("target ref no longer points to the manifest target_sha")
    try:
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks", manifest["repository"],
                        str(clone)], check=True, capture_output=True, env=_GIT_ENV)
        for sha in (manifest["target_sha"], manifest["candidate_sha"]):
            if _git(clone, "cat-file", "-t", sha).strip() != "commit":
                raise AuditError(f"{sha} is not a commit")
        if _git(clone, "rev-parse", f"{manifest['candidate_sha']}^{{tree}}").strip() != manifest["candidate_tree"]:
            raise AuditError("candidate_tree does not match the candidate commit")
        merged = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(clone), "merge-tree", "--write-tree",
             manifest["target_sha"], manifest["candidate_sha"]],
            check=False, capture_output=True, text=True, env=_GIT_ENV,
        )
    except subprocess.SubprocessError as error:
        raise AuditError("candidate commits are unavailable in the manifest repository") from error
    if merged.returncode != 0:
        raise AuditError("candidate does not merge cleanly into target")
    if merged.stdout.split()[0] != manifest["result_tree"]:
        raise AuditError("result_tree does not match the merge of candidate into target")


def _checkout_result(clone: Path, manifest: dict[str, Any]) -> Path:
    """Check out a fixed-metadata commit of result_tree (parents target, candidate) so git-aware tests run."""
    identity = {"GIT_AUTHOR_NAME": "aao-audit", "GIT_AUTHOR_EMAIL": "aao-audit@invalid",
                "GIT_COMMITTER_NAME": "aao-audit", "GIT_COMMITTER_EMAIL": "aao-audit@invalid",
                "GIT_AUTHOR_DATE": "1970-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "1970-01-01T00:00:00Z"}
    commit = subprocess.run(
        ["git", "-C", str(clone), "commit-tree", manifest["result_tree"], "-p", manifest["target_sha"],
         "-p", manifest["candidate_sha"], "-m", "aao audit result tree"],
        check=True, capture_output=True, text=True, env={**_GIT_ENV, **identity},
    ).stdout.strip()
    _git(clone, "-c", "core.hooksPath=/dev/null", "checkout", "--quiet", "--detach", commit)
    if _git(clone, "rev-parse", "HEAD^{tree}").strip() != manifest["result_tree"] or _git(
            clone, "status", "--porcelain", "--untracked-files=all").strip():
        raise AuditError("result tree checkout is not exact")
    return clone


def _ref_value(manifest: dict[str, Any]) -> str:
    try:
        return _git(Path(manifest["repository"]), "rev-parse", "--verify", f"{manifest['target_ref']}^{{commit}}").strip()
    except subprocess.SubprocessError as error:
        raise AuditError("target ref is unavailable") from error


def _custody(anchor: dict[str, Any], key_path: Path | None) -> list[str]:
    policy, uid = anchor["policy"], anchor["auditor_uid"]
    problems = []
    if os.geteuid() != uid:
        problems.append("audit is not running as the anchored auditor uid")
    if pwd.getpwuid(os.geteuid()).pw_name in policy["developer_os_users"]:
        problems.append("running account is a developer account")
    if auditor_revision() not in policy["trusted_auditor_revisions"]:
        problems.append("auditor code revision is not an independently reviewed revision")
    if key_path is None:
        return [*problems, "no auditor signing key was provided"]
    try:
        read_protected(key_path, (uid,))
        if os.stat(key_path).st_mode & 0o077:
            problems.append("signing key is readable by other accounts")
        public = subprocess.run(["openssl", "pkey", "-in", str(key_path), "-pubout"], check=True,
                                capture_output=True, text=True).stdout
        if public.strip() != anchor["auditor_public_key"].strip():
            problems.append("signing key does not match the anchored auditor public key")
    except (AuditError, OSError, subprocess.SubprocessError):
        problems.append("signing key is unavailable or not private to the auditor uid")
    return problems


def _ledger(anchor: dict[str, Any]) -> Path:
    ledger = Path(anchor["ledger_path"])
    if not ledger.exists():
        _check_parents(ledger, (anchor["auditor_uid"],))
        os.close(os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
    read_protected(ledger, (anchor["auditor_uid"],))
    return ledger


def audit_manifest(
    manifest_path: Path, output: Path, key_path: Path | None, veto_reason: str | None = None, *,
    anchor_path: Path = ANCHOR_PATH, anchor_owner_uids: tuple[int, ...] = (0,), runner=run_sandboxed,
    resolve_pending_vetoes: bool = False,
) -> dict[str, Any]:
    anchor = load_anchor(anchor_path, anchor_owner_uids)
    policy = anchor["policy"]
    manifest, manifest_digest = parse_manifest(manifest_path)
    if veto_reason:
        # A-1: the marker exists before any analysis, so no gate can run in a window where the veto is unseen.
        digest = record_pending_veto(anchor, manifest["candidate_sha"], manifest_digest, veto_reason)
        _report_veto_to_supervisor(anchor, manifest["candidate_sha"], digest)
    for secret in (key_path, output, Path(anchor["ledger_path"]), Path(anchor["policy_path"])):
        if secret is not None and _visible_in_sandbox(secret):
            raise AuditError(f"{secret} would be readable by candidate code inside the sandbox")
    ledger = _ledger(anchor)
    with tempfile.TemporaryDirectory(prefix="aao-manifest-audit-") as temporary:
        clone = Path(temporary) / "repo"
        _derive(manifest, clone)
        tree = _checkout_result(clone, manifest)
        findings = adversarial_findings(clone, manifest["target_sha"], manifest["result_tree"], policy)
        authors = _git(clone, "log", "--format=%ae", f"{manifest['target_sha']}..{manifest['candidate_sha']}")
        # Declared identities can only make the decision stricter; recusal relies on attribution (SL-02).
        declared = sorted({manifest["producer"], *authors.split()})
        push_principals = attributed_principals(anchor, manifest["candidate_sha"])
        implementers = attributed_implementers(anchor, manifest["candidate_sha"])
        output.mkdir(mode=0o750, exist_ok=False)
        evidence_dir = output / "evidence"
        evidence_dir.mkdir(mode=0o700)
        evidence: dict[str, str] = {}
        checks: dict[str, dict[str, Any]] = {}
        for name, argv in sorted(policy["audit_checks"].items()):
            code, stdout, stderr = runner(tree, argv)
            checks[name] = {"conclusion": "success" if code == 0 else "failure", "exit_code": code}
            digest, path = _write_evidence(evidence_dir, f"check-{name}", {
                "result_tree": manifest["result_tree"], "check": name, "argv": argv, "exit_code": code,
                "stdout_tail": stdout, "stderr_tail": stderr})
            evidence[digest] = path
        git_version = subprocess.run(["git", "--version"], check=True, capture_output=True, text=True).stdout.strip()
    digest, path = _write_evidence(evidence_dir, "adversarial-findings", {
        "target_sha": manifest["target_sha"], "result_tree": manifest["result_tree"], "findings": findings})
    evidence[digest] = path
    key = f"{manifest['candidate_sha']}:{manifest['result_tree']}"
    blocking = [f["id"] for f in findings if f"{key}:{f['id']}" not in policy["dispositions"]]
    blocking += [f"audit-check-failed:{n}" for n, c in checks.items() if c["conclusion"] != "success"]
    if policy["auditor_id"] in {*implementers, *push_principals, *declared}:
        blocking.append("auditor-is-implementer")
    custody = _custody(anchor, key_path)
    if not implementers:
        custody.append("implementer attribution is unresolved")
    verdict = "veto" if veto_reason else "provisional" if custody else "reject" if blocking else "approve"
    report = {
        "schema": REPORT_SCHEMA, "manifest_sha256": manifest_digest, "manifest": manifest,
        "candidate_sha": manifest["candidate_sha"], "target_sha": manifest["target_sha"],
        "result_tree": manifest["result_tree"], "git_version": git_version,
        "policy_version": POLICY_VERSION, "policy_sha256": anchor["policy_sha256"],
        "anchor_sha256": anchor["anchor_sha256"], "auditor_id": policy["auditor_id"],
        "auditor_uid": anchor["auditor_uid"], "auditor_revision": auditor_revision(),
        "implementer_ids": implementers, "declared_implementers": declared, "verdict": verdict, "veto": bool(veto_reason),
        "veto_reason": veto_reason or "", "blocking_findings": blocking, "findings": findings,
        "audit_checks": checks, "custody_problems": custody, "evidence_files": evidence,
        "assurance_level": "A", "limitations": list(_LIMITATIONS),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    if _ref_value(manifest) != manifest["target_sha"]:
        raise AuditError("target ref moved before the verdict was recorded")
    report_bytes = _canonical(report)
    (output / "report.json").write_bytes(report_bytes)
    (output / "report.json").chmod(0o640)
    if not custody:
        signature = subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key_path), "-rawin", "-in",
                                    str(output / "report.json")], check=True, capture_output=True).stdout
        (output / "report.sig").write_text(base64.b64encode(signature).decode("ascii"), encoding="ascii")
        # Only a custody-valid auditor can record decisions; every entry is signed (SL-03).
        ledger_rows(anchor)
        with tempfile.TemporaryDirectory(prefix="aao-ledger-keys-") as temporary:
            governance_ledger.append(
                ledger, {"type": "veto" if verdict == "veto" else "audit-verdict",
                         "candidate_sha": manifest["candidate_sha"], "result_tree": manifest["result_tree"],
                         "report_sha256": _sha(report_bytes), "verdict": verdict, "veto": verdict == "veto",
                         "resolves_pending": pending_vetoes(anchor, manifest["candidate_sha"])
                         if resolve_pending_vetoes or verdict == "veto" else [],
                         "recorded_at": report["created_at"]},
                policy["auditor_id"], str(key_path), _ledger_keys(anchor, Path(temporary)))
    return report


def verify_promotion(
    manifest_path: Path, report_path: Path, signature_path: Path | None, promoted_sha: str | None = None, *,
    anchor_path: Path = ANCHOR_PATH, anchor_owner_uids: tuple[int, ...] = (0,),
    report_bytes: bytes | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Fail-closed decision for the controller; run immediately before a compare-and-swap ref update."""
    reasons: list[str] = []
    try:
        anchor = load_anchor(anchor_path, anchor_owner_uids)
        manifest, manifest_digest = parse_manifest(manifest_path)
        raw = report_bytes if report_bytes is not None else report_path.read_bytes()
        report = json.loads(raw)
    except (AuditError, OSError, ValueError) as error:
        return False, (f"cannot evaluate promotion: {error}",)
    expected = {"schema": REPORT_SCHEMA, "manifest_sha256": manifest_digest, "target_sha": manifest["target_sha"],
                "candidate_sha": manifest["candidate_sha"], "result_tree": manifest["result_tree"],
                "policy_sha256": anchor["policy_sha256"], "anchor_sha256": anchor["anchor_sha256"],
                "auditor_uid": anchor["auditor_uid"], "verdict": "approve", "veto": False, "blocking_findings": []}
    reasons += [f"report {k} is not {v!r}" for k, v in expected.items() if report.get(k) != v]
    if report.get("auditor_revision") not in anchor["policy"]["trusted_auditor_revisions"]:
        reasons.append("report was produced by an auditor revision the anchored policy does not trust")
    if _canonical(report) != raw:
        reasons.append("report is not in canonical signed form")
    if signature_path is None or not signature_path.is_file():
        reasons.append("signed audit report is absent")
    else:
        with tempfile.TemporaryDirectory(prefix="aao-manifest-gate-") as temporary:
            public, signature = Path(temporary) / "auditor.pub", Path(temporary) / "report.sig"
            public.write_text(anchor["auditor_public_key"], encoding="ascii")
            try:
                signature.write_bytes(base64.b64decode(signature_path.read_text(encoding="ascii").strip(), validate=True))
            except ValueError:
                signature.write_bytes(b"")
            signed_report = Path(temporary) / "report.json"
            signed_report.write_bytes(raw)
            if subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public), "-rawin", "-in",
                               str(signed_report), "-sigfile", str(signature)], check=False,
                              capture_output=True).returncode:
                reasons.append("report signature does not verify against the anchored auditor key")
    for digest, path in (report.get("evidence_files") or {}).items():
        try:
            if _sha(read_protected(Path(path), (anchor["auditor_uid"],))) != digest:
                reasons.append(f"evidence {path} does not match its digest")
        except AuditError:
            reasons.append(f"evidence {path} is unavailable or not auditor-owned")
    if not report.get("evidence_files"):
        reasons.append("report has no evidence")
    # A-3: one snapshot of the ledger and the markers feeds every check, so a marker or row removed
    # between two reads cannot pass one check and vanish from the next.
    rows: list[dict[str, Any]] | None = None
    markers: list[str] | None = None
    try:
        rows = ledger_rows(anchor)
    except AuditError as error:
        reasons.append(f"audit ledger is not trustworthy: {error}")
    try:
        markers = pending_vetoes(anchor, manifest["candidate_sha"])
    except (AuditError, OSError, ValueError) as error:
        reasons.append(f"pending vetoes cannot be verified: {error}")
    if rows is not None and markers is not None:
        try:
            _supervisor_custody(anchor, manifest["candidate_sha"], rows, markers)
        except (AuditError, OSError, ValueError) as error:
            reasons.append(f"supervisor custody check failed: {error}")
        resolved = {d for e in rows for d in e.get("resolves_pending") or []}
        if [d for d in markers if d not in resolved]:
            reasons.append("candidate has an unresolved pending veto (recorded without custody)")
    else:
        reasons.append("supervisor custody check failed: ledger or markers unavailable")
    if rows is not None:
        entries = [e for e in rows if e.get("candidate_sha") == manifest["candidate_sha"]]
        if any(e.get("veto") for e in entries):
            reasons.append("candidate has a recorded audit veto")
        if not entries or entries[-1].get("report_sha256") != _sha(raw):
            reasons.append("report is not the latest recorded decision for this candidate")
    with tempfile.TemporaryDirectory(prefix="aao-manifest-gate-") as temporary:
        try:
            clone = Path(temporary) / "repo"
            _derive(manifest, clone)
            if promoted_sha is not None:
                _check_promoted(clone, manifest, promoted_sha)
        except AuditError as error:
            reasons.append(str(error))
    return not reasons, tuple(dict.fromkeys(reasons))


def _check_promoted(clone: Path, manifest: dict[str, Any], promoted_sha: str) -> None:
    if not _is_sha(promoted_sha):
        raise AuditError("promoted commit must be a full SHA")
    try:
        if _git(clone, "cat-file", "-t", promoted_sha).strip() != "commit":
            raise AuditError("promoted object is not a commit")
    except subprocess.SubprocessError:
        _git(clone, "fetch", "--quiet", "--no-tags", "origin", promoted_sha)
    tree = _git(clone, "rev-parse", f"{promoted_sha}^{{tree}}").strip()
    parents = _git(clone, "rev-list", "--parents", "-n", "1", promoted_sha).split()[1:]
    fast_forward = promoted_sha == manifest["candidate_sha"] and not subprocess.run(
        ["git", "-C", str(clone), "merge-base", "--is-ancestor", manifest["target_sha"], promoted_sha],
        check=False, capture_output=True, env=_GIT_ENV).returncode
    if tree != manifest["result_tree"]:
        raise AuditError("promoted commit tree is not the audited result_tree")
    if not fast_forward and parents != [manifest["target_sha"], manifest["candidate_sha"]]:
        raise AuditError("promoted commit parents are not [target_sha, candidate_sha]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and gate local candidate manifests (no path overrides)")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--manifest", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    audit.add_argument("--key", type=Path)
    audit.add_argument("--veto", metavar="REASON")
    audit.add_argument("--resolve-pending-vetoes", action="store_true",
                       help="custody-valid run explicitly resolves this candidate's pending-veto markers")
    gate = commands.add_parser("gate")
    gate.add_argument("--manifest", type=Path, required=True)
    gate.add_argument("--report", type=Path, required=True)
    gate.add_argument("--signature", type=Path)
    gate.add_argument("--promoted-sha")
    args = parser.parse_args()
    if args.command == "gate":
        conformant, reasons = verify_promotion(args.manifest, args.report, args.signature, args.promoted_sha)
        print(json.dumps({"conformant": conformant, "reasons": reasons}, sort_keys=True))
        return 0 if conformant else 1
    try:
        report = audit_manifest(args.manifest, args.output, args.key, args.veto,
                                resolve_pending_vetoes=args.resolve_pending_vetoes)
    except (AuditError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}))
        return 2
    print(json.dumps({k: report[k] for k in ("candidate_sha", "result_tree", "verdict", "blocking_findings",
                                             "custody_problems")}, sort_keys=True))
    return 0 if report["verdict"] == "approve" else 1


if __name__ == "__main__":
    raise SystemExit(main())
