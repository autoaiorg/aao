#!/usr/bin/python3 -I
"""Generate the trust anchor, the pinned policy and the supervisor config for one auditor revision.

Writes into --out (a fresh directory); the CEO then installs each file with the owner/mode in
docs/procedures/TRUST_ROOT_HOST_INSTALL.md. Pure: reads only the public keys and the policy template.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pwd
import re
from pathlib import Path

INTAKE_SOCKET = "/run/aao-veto-intake/veto.sock"
HEARTBEAT = "/var/lib/aao-heartbeat/heartbeat.json"
POLICY_PATH = "/var/lib/aao-auditor/policy.json"
LEDGER = "/var/lib/aao-auditor/ledger/governance.jsonl"
ROUTES_PATH = Path(__file__).resolve().parents[1] / "docs/protected-routes.json"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def build(revision: str, template: dict, auditor_pub: str, supervisor_pub: str, auditor_uid: int,
          developer_users: list[str], supervisor_key_id: str = "aao-supervisor",
          attribution_writer_uid: int | None = None, repo: str | None = None) -> dict[str, dict]:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full lowercase SHA")
    normative = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    routes = normative.get("routes") if isinstance(normative, dict) else None
    if (not isinstance(normative, dict) or normative.get("schema") != "aao.protected-routes.v1"
            or not isinstance(routes, list) or not routes
            or normative.get("semantics") != {
                "directory": "entry ending in '/' covers everything below it",
                "exact": "any other entry is an exact path unless it contains '*'",
                "glob": "'*' matches any sequence without '/'; a pattern without '/' matches the basename in any directory",
                "paths_considered": "added, modified, deleted and both sides of renamed files",
                "overlap": "highest class wins; overlaps never lower a class",
            }):
        raise ValueError("normative protected routes are invalid")
    if any(not isinstance(item, dict) or set(item) != {"path", "minimum_risk_class"}
           or not isinstance(item.get("path"), str) or not item["path"]
           or item.get("minimum_risk_class") not in {"R1", "R2", "R3"} for item in routes):
        raise ValueError("normative protected routes are invalid")
    protected_routes = {item["path"]: item["minimum_risk_class"] for item in routes}
    if len(protected_routes) != len(routes):
        raise ValueError("normative protected routes contain duplicates")
    required_check_publishers = normative.get("required_check_publishers")
    if (not isinstance(required_check_publishers, dict) or not required_check_publishers
            or any(not isinstance(name, str) or not name or not isinstance(ids, list) or not ids
                   or any(type(app_id) is not int for app_id in ids)
                   for name, ids in required_check_publishers.items())):
        raise ValueError("normative required check publishers are invalid")
    push_principals = normative.get("push_principals")
    if (not isinstance(push_principals, dict) or not push_principals
            or any(not isinstance(principal, str) or not principal or not isinstance(identity, str) or not identity
                   for principal, identity in push_principals.items())
            or len(set(push_principals.values())) != len(push_principals)):
        raise ValueError("normative push principals are invalid")
    routes_digest = hashlib.sha256(canonical(sorted(normative["routes"], key=lambda item: item["path"]))).hexdigest()
    policy = {**template, "protected_paths": sorted(protected_routes),
              "protected_routes": protected_routes, "protected_routes_sha256": routes_digest,
              "required_check_publishers": required_check_publishers,
              "push_principals": push_principals,
              "auditor_id": "aao-auditor", "auditor_os_user": "aao-auditor",
              "developer_os_users": sorted(set(developer_users)), "trusted_auditor_revisions": [revision]}
    if "aao-auditor" in policy["developer_os_users"]:
        raise ValueError("the auditor account cannot be a developer account")
    anchor = {"schema": "aao.audit-trust-anchor.v1", "policy_path": POLICY_PATH,
              "policy_sha256": hashlib.sha256(canonical(policy)).hexdigest(), "auditor_uid": auditor_uid,
              "auditor_public_key": auditor_pub, "ledger_path": LEDGER,
              "ledger_anchor_path": "/etc/aao-audit/ledger.anchor",
              # Written by the supervisor from authenticated push events (RA-02), so no PR needs root.
              "attribution_path": "/var/lib/aao-supervisor/attribution/attribution.json",
              "attribution_writer_uid": attribution_writer_uid if attribution_writer_uid is not None else -1,
              "supervisor_public_key": supervisor_pub, "supervisor_key_id": supervisor_key_id,
              "supervisor_heartbeat_path": HEARTBEAT, "supervisor_intake_socket": INTAKE_SOCKET}
    config = {"schema": "aao.supervisor-config.v1", "auditor_uid": auditor_uid, "ledger_path": LEDGER,
              "state_path": "/var/lib/aao-supervisor/state.json", "heartbeat_path": HEARTBEAT,
              "attribution_path": "/var/lib/aao-supervisor/attribution/attribution.json",
              "push_receipts_dir": "/var/lib/aao-supervisor/push-receipts",
              "webhook_secret_path": "/etc/aao-supervisor/github-webhook.secret",
              "webhook_repositories": [repo] if repo else [],
              "webhook_bind": "127.0.0.1", "webhook_port": 8765,
              "repository": repo or "",
              "intake_socket": INTAKE_SOCKET, "private_key": "/var/lib/aao-supervisor/keys/supervisor-ed25519.pem",
              "key_id": supervisor_key_id, "trust_registry": "/srv/aao/trust/registry.json", "validity_seconds": 600}
    return {"policy.json": policy, "trust-anchor.json": anchor, "supervisor-config.json": config}


# Fields promote() refuses in the registry: they describe one PR, and the registry is installed by root.
PER_PR_FIELDS = {"ci_candidate_sha", "attribution_resolved", "repo", "pr_number", "pr_head"}
RA_IDS = ("RA-01", "RA-02", "RA-03", "RA-07", "RA-09")
KEYS = "/srv/aao/trust/keys"


def build_registry(policy: dict, anchor: dict, *, auditor_models: dict[str, str],
                   author_models: dict[str, str], ra_status: dict[str, str] | None = None) -> dict:
    """Static integrator trust registry (feat/r1-runtime contract). Nothing per PR lives here.

    ra_status defaults to PENDING for every RA: the integrator stays fail-closed until the CEO reinstalls
    the registry with PASS backed by the trial evidence (A-01..A-14, P3-01..P3-12)."""
    status = {ra: "PENDING" for ra in RA_IDS} | (ra_status or {})
    if set(status) != set(RA_IDS) or any(v not in ("PASS", "PENDING") for v in status.values()):
        raise ValueError("ra_status must give PASS or PENDING for exactly RA-01/02/03/07/09")
    auditor_key_id = policy["auditors"][policy["auditor_id"]]
    registry = {
        "ledger_keys": {policy["auditor_id"]: {"public_key": f"{KEYS}/aao-auditor-ed25519.pub",
                                               "can_resolve_pending": True},
                        "aao-integrator": {"public_key": f"{KEYS}/aao-integrator-ed25519.pub"},
                        anchor["supervisor_key_id"]: {"public_key": f"{KEYS}/aao-supervisor-ed25519.pub",
                                                      "can_record_incidents": True}},
        "integrator_key_id": "aao-integrator", "integrator_identity": "aao-integrator",
        "supervisor_key_id": anchor["supervisor_key_id"],
        "supervisor_public_key": f"{KEYS}/aao-supervisor-ed25519.pub", "heartbeat_max_age_seconds": 600,
        "target_refs": ["refs/heads/main"], "ra_status": status, "incident_resolvers": [],
        "trusted_auditors": {policy["auditor_id"]: [auditor_key_id]},
        "trusted_keys": {auditor_key_id: f"{KEYS}/aao-auditor-ed25519.pub"},
        "enabled_risk_classes": ["R1"],  # R2 only after §12.5
        "required_checks_by_risk_class": {"R1": list(policy["required_checks"])},
        "policy_id": policy.get("policy_id", policy["version"]), "policy_sha256": anchor["policy_sha256"],
        "trusted_auditor_revisions": list(policy["trusted_auditor_revisions"]),
        "auditor_models": auditor_models, "author_models": author_models,
        "protected_routes": dict(policy["protected_routes"]),
        "protected_routes_sha256": policy["protected_routes_sha256"],
        "required_check_publishers": policy["required_check_publishers"],
        "push_principals": dict(policy["push_principals"]),
    }
    assert not PER_PR_FIELDS & set(registry)
    return registry


def build_runtime_configs(repo: str) -> dict[str, dict]:
    """Fixed configs of the R1 loop (aao.r1_pipeline, aao.auditor_dispatch). Paths match deploy/tmpfiles.d."""
    if len(repo.split("/")) != 2 or not all(part.replace("-", "").replace("_", "").replace(".", "").isalnum()
                                            for part in repo.split("/")):
        raise ValueError("repo must be owner/name")
    integrator = {"schema": "aao.integrator-config.v1", "repo": repo, "git_remote": f"https://github.com/{repo}.git",
                  "mirror": "/srv/aao/mirror/repo.git", "inbox": "/var/lib/aao-audit-inbox",
                  "reports": "/var/lib/aao-auditor/reports", "state_dir": "/var/lib/aao-integrator/state",
                  "trust_registry": "/srv/aao/trust/registry.json", "ledger": LEDGER,
                  "ledger_anchor": "/etc/aao-audit/ledger.anchor", "heartbeat": HEARTBEAT,
                  "heartbeat_sequence": "/var/lib/aao-integrator/heartbeat.sequence",
                  "freeze": "/var/lib/aao-integrator/freeze",
                  "integrator_private_key": "/var/lib/aao-integrator/integrator-ed25519.pem"}
    dispatch = {"schema": "aao.audit-dispatch-config.v1", "inbox": "/var/lib/aao-audit-inbox",
                "reports": "/var/lib/aao-auditor/reports", "key": "/var/lib/aao-auditor/keys/auditor-ed25519.pem",
                "repository_root": "/srv/aao/mirror/repo.git", "repo": repo}
    return {"integrator-config.json": integrator, "dispatch.json": dispatch}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--revision", required=True)
    parser.add_argument("--policy-template", type=Path, required=True)
    parser.add_argument("--auditor-public-key", type=Path, default=Path("/srv/aao/trust/keys/aao-auditor-ed25519.pub"))
    parser.add_argument("--supervisor-public-key", type=Path,
                        default=Path("/srv/aao/trust/keys/aao-supervisor-ed25519.pub"))
    parser.add_argument("--developer", action="append", default=["alessbarb", "aao-impl-codex", "aao-impl-claude",
                                                                 "aao-impl-ag", "aao-pm"])
    parser.add_argument("--repo", required=True, help="owner/name of the repository the R1 loop serves")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ra-status", action="append", default=[], metavar="RA-0x=PASS|PENDING",
                        help="CEO decision recorded in the registry; every RA not given stays PENDING")
    args = parser.parse_args()
    ra_status = {}
    for item in args.ra_status:
        ra, _, value = item.partition("=")
        if ra in ra_status:
            parser.error(f"duplicate --ra-status {ra}")
        ra_status[ra] = value
    files = build(args.revision, json.loads(args.policy_template.read_text()), args.auditor_public_key.read_text(),
                  args.supervisor_public_key.read_text(), pwd.getpwnam("aao-auditor").pw_uid, args.developer,
                  attribution_writer_uid=pwd.getpwnam("aao-supervisor").pw_uid, repo=args.repo)
    files["registry.json"] = build_registry(
        files["policy.json"], files["trust-anchor.json"],
        auditor_models={"aao-auditor": "claude", "aao-auditor-alt": "gemini"},
        author_models={"aao-impl-claude": "claude", "aao-impl-codex": "codex", "aao-impl-ag": "gemini"},
        ra_status=ra_status)
    files.update(build_runtime_configs(args.repo))
    args.out.mkdir(mode=0o700)
    for name, value in files.items():
        (args.out / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        print(f"{name} sha256={hashlib.sha256((args.out / name).read_bytes()).hexdigest()}")
    print(f"policy canonical sha256 (pinned in the anchor) = {files['trust-anchor.json']['policy_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
