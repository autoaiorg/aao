"""Issue integration authorizations from a custody-verified manifest audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import pwd
import stat
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aao import integration_authorization as authorization
from aao.git_paths import changed_paths
from aao.independent_audit import AuditError
from aao.manifest_audit import ANCHOR_PATH, load_anchor, read_protected, verify_promotion
from aao.pr_conformity import _canonical
from aao.protected_routes import classify, compare_copies, load_document, route_map

TRUST_REGISTRY_PATH = Path("/srv/aao/trust/registry.json")


def _git(repository: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repository, *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _checks(report: dict[str, Any], report_dir: Path, auditor_uid: int) -> list[dict[str, str]]:
    evidence_by_check: dict[str, str] = {}
    for digest, relative in report.get("evidence_files", {}).items():
        try:
            raw = read_protected(report_dir / relative, (auditor_uid,))
            if hashlib.sha256(raw).hexdigest() != digest:
                raise AuditError("audit evidence digest mismatch")
            artifact = json.loads(raw)
        except (OSError, ValueError, TypeError):
            continue
        if artifact.get("check"):
            evidence_by_check[artifact["check"]] = digest
    result = []
    for name, check in sorted(report.get("audit_checks", {}).items()):
        digest = evidence_by_check.get(name)
        if digest is None:
            raise AuditError(f"audit check {name} has no evidence digest")
        result.append({"name": name, "cmd": " ".join(check.get("argv", [])) or name,
                       "result": "PASS" if check.get("conclusion") == "success" else "FAIL",
                       "evidence_sha256": digest})
    return result


def issue_authorization(
    report_dir: Path, repo: str, pr_number: int, key: Path, output: Path, *,
    anchor_path: Path = ANCHOR_PATH, anchor_owner_uids: tuple[int, ...] = (0,),
    now: datetime | None = None, registry_path: Path | None = None,
    registry_owner_uids: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    """Verify the signed audit and emit an exact §6.1 authorization document."""
    anchor = load_anchor(anchor_path, anchor_owner_uids)
    if registry_owner_uids is None:
        try:
            registry_owner_uids = (0, pwd.getpwnam("aao-trust").pw_uid)
        except KeyError:
            registry_owner_uids = (0,)
    report_path, signature_path = report_dir / "report.json", report_dir / "report.sig"
    report_info = report_dir.lstat()
    if (not stat.S_ISDIR(report_info.st_mode) or report_info.st_uid != anchor["auditor_uid"]
            or report_info.st_mode & 0o022):
        raise AuditError("report directory is not auditor-owned or is group/other writable")
    raw = read_protected(report_path, (anchor["auditor_uid"],))
    report = json.loads(raw)
    if not isinstance(report, dict) or not isinstance(report.get("manifest"), dict):
        raise AuditError("signed report has no manifest")
    manifest = report["manifest"]
    with tempfile.TemporaryDirectory(prefix="aao-authorization-issuer-") as temporary:
        manifest_path = Path(temporary) / "manifest.json"
        manifest_path.write_bytes(_canonical(manifest))
        valid, reasons = verify_promotion(manifest_path, report_path, signature_path,
                                          anchor_path=anchor_path, anchor_owner_uids=anchor_owner_uids,
                                          report_bytes=raw)
    if not valid:
        raise AuditError("audit report is not promotion-valid: " + "; ".join(reasons))
    if report.get("verdict") != "approve" or report.get("veto") is not False or report.get("blocking_findings") or report.get("custody_problems"):
        raise AuditError("audit report is not an unvetoed, unblocked approval")

    policy = anchor["policy"]
    candidate, base = report["candidate_sha"], report["target_sha"]
    implementers = report.get("implementer_ids")
    auditor_id = report.get("auditor_id")
    if not isinstance(implementers, list) or not implementers:
        raise AuditError("implementer attribution is unresolved")
    if auditor_id in implementers:
        raise AuditError("auditor is recused because they are an implementer")
    paths = changed_paths(manifest["repository"], base, candidate)
    operational = {"protected_routes": policy.get("protected_routes"),
                   "protected_routes_sha256": policy.get("protected_routes_sha256")}
    try:
        normative = load_document()
        registry = json.loads(read_protected(registry_path or TRUST_REGISTRY_PATH, registry_owner_uids))
        compare_copies(normative, registry, operational)
    except (OSError, ValueError, TypeError) as error:
        raise AuditError(str(error)) from error
    risk_class = classify(paths, route_map(normative))
    enabled = policy.get("enabled_risk_classes", ["R1"])
    if not isinstance(enabled, list) or any(not isinstance(item, str) for item in enabled):
        raise AuditError("enabled risk classes are not pinned by policy")
    if risk_class == "R2" and "R2" not in enabled:
        raise AuditError("R2 is not enabled for this auditor")
    if risk_class == "R3":  # Defensive invariant; this issuer never classifies R3.
        raise AuditError("R3 authorizations are never issued")
    if risk_class != "R1":
        raise AuditError(f"R1 autonomy refused: protected route classification is {risk_class}")

    protected_digest = operational["protected_routes_sha256"]
    issued = now or datetime.now(UTC)
    if issued.tzinfo is None:
        raise ValueError("issuer clock must be timezone-aware")
    issued = issued.astimezone(UTC)
    attribution = [{"sha": candidate, "principal": identity, "source": "anchored-audit-attribution",
                    "evidence_sha256": hashlib.sha256(raw).hexdigest()}
                   for identity in sorted(set(implementers))]
    auditor_key_id = policy["auditors"].get(auditor_id)
    if not isinstance(auditor_key_id, str) or not auditor_key_id:
        raise AuditError("auditor key id is not pinned by policy")
    document = {
        "repo": repo, "pr_number": pr_number, "candidate_sha": candidate, "base_sha": base,
        "target_ref": manifest["target_ref"], "merge_method": "merge-commit",
        "merge_result_tree_sha": report["result_tree"], "risk_class": risk_class,
        "assurance_level": report.get("assurance_level", "A"),
        "policy_id": policy.get("policy_id", policy["version"]), "policy_sha256": anchor["policy_sha256"],
        "protected_paths_sha256": protected_digest, "expected_parents": [base, candidate],
        # Integrator records the version payload (without Git's display prefix).
        "git_version": report["git_version"].removeprefix("git version "),
        "auditor_id": auditor_id, "auditor_key_id": auditor_key_id,
        "auditor_code_revision": report["auditor_revision"], "attribution": attribution,
        "checks_executed": _checks(report, report_dir, anchor["auditor_uid"]),
        "scope": "exact audited candidate and merge result",
        "known_limitations": report.get("limitations", []), "residual_risks": report.get("limitations", []),
        "permitted_operations": ["merge-commit to the authorized target ref"],
        "prohibited_operations": ["fast-forward", "squash", "rebase", "R3 promotion"],
        "findings": [{**finding, "severity": "CRITICAL" if finding["id"] in report.get("blocking_findings", [])
                      else "HIGH", "disposition": "OPEN" if finding["id"] in report.get("blocking_findings", [])
                      else "RESOLVED"} for finding in report.get("findings", [])],
        "expediente_sha256": hashlib.sha256(raw).hexdigest(),
        "verdict": "APPROVE", "issued_at": issued.isoformat(timespec="seconds"),
        "expires_at": (issued + timedelta(hours=1)).isoformat(timespec="seconds"),
    }
    if set(document) != set(authorization.FIELDS):
        raise AssertionError("issuer document fields diverged from integration_authorization.FIELDS")
    signature = authorization.sign(document, str(key))
    output.mkdir(mode=0o750, parents=True, exist_ok=False)
    for name, content in (("authorization.json", authorization.canonical(document)),
                          ("authorization.sig", (signature + "\n").encode("ascii"))):
        path = output / name
        path.write_bytes(content)
        path.chmod(0o640)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a signed promotion authorization from a verified audit")
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        issue_authorization(args.report_dir, args.repo, args.pr_number, args.key, args.output)
    except (AuditError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
