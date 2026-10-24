"""Supervisor service entry points (run as the aao-supervisor uid by systemd).

Not part of the auditor closure pinned in trusted_auditor_revisions: the auditor's frozen tree stays at its
reviewed commit; this module is deployed only to the supervisor's frozen tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import stat
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aao.integration_authorization import canonical
from aao.supervisor import _persist_sequence, _sequence, _sign, serve_veto_intake, signed_heartbeat

CONFIG_PATH = Path("/etc/aao-supervisor/config.json")
CONFIG_SCHEMA = "aao.supervisor-config.v1"
INTEGRATOR_LOGIN = "aao-integrator[bot]"  # Registry may override this when it explicitly names the login.
EXPECTED_RULE_TYPES = {"update", "pull_request", "non_fast_forward", "deletion", "required_status_checks"}
AUDIT_INTEGRATION_ID = 5448107
_FIELDS = {"schema", "auditor_uid", "ledger_path", "state_path", "heartbeat_path", "intake_socket",
           "private_key", "key_id", "trust_registry", "validity_seconds", "repository", "attribution_path"}
_OPTIONAL_FIELDS = {"integrator_login", "watch_expected_types", "watch_required_checks", "events_path"}


def _read_owned(path: Path, owners: tuple[int, ...]) -> bytes:
    """A regular, non-symlink file owned by an allowed uid and not group/other writable."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_uid not in owners:
            raise ValueError(f"{path} is not a protected regular file owned by {owners}")
        return handle.read()


def load_config(path: Path = CONFIG_PATH, owners: tuple[int, ...] = (0,),
                registry_owners: tuple[int, ...] | None = None) -> dict[str, Any]:
    """Config is root-owned; the trust registry is root- or aao-trust-owned (P1 layout)."""
    if registry_owners is None:
        registry_owners = (0, pwd.getpwnam("aao-trust").pw_uid)
    config = json.loads(_read_owned(path, owners))
    if (not isinstance(config, dict) or not _FIELDS <= set(config) or
            set(config) - _FIELDS - _OPTIONAL_FIELDS or config["schema"] != CONFIG_SCHEMA):
        raise ValueError("supervisor config fields are not the expected set")
    if not isinstance(config["auditor_uid"], int) or not isinstance(config["validity_seconds"], int):
        raise TypeError("auditor_uid and validity_seconds must be integers")
    registry = json.loads(_read_owned(Path(config["trust_registry"]), registry_owners))
    keys, integrator = registry.get("ledger_keys"), registry.get("integrator_key_id")
    if not isinstance(keys, dict) or not keys or not isinstance(integrator, str):
        raise ValueError("trust registry lacks ledger_keys or integrator_key_id")
    push_principals = registry.get("push_principals")
    if not isinstance(push_principals, dict) or not push_principals or any(
            not isinstance(principal, str) or not principal or not isinstance(implementer, str) or not implementer
            for principal, implementer in push_principals.items()):
        raise ValueError("trust registry lacks push_principals")
    if len(set(push_principals.values())) != len(push_principals):
        raise ValueError("push principal attribution is ambiguous")
    return {**config, "trusted_keys": keys, "integrator_key_id": integrator,
            "integrator_login": config.get("integrator_login", registry.get("integrator_login", INTEGRATOR_LOGIN)),
            "push_principals": push_principals}


def _custody(config: dict[str, Any]) -> dict[str, Any]:
    return {"private_key": config["private_key"], "key_id": config["key_id"],
            "ledger_path": Path(config["ledger_path"]), "state_path": Path(config["state_path"]),
            "trusted_keys": config["trusted_keys"], "integrator_key_id": config["integrator_key_id"],
            "heartbeat_path": Path(config["heartbeat_path"])}


def heartbeat(config: dict[str, Any]) -> dict[str, Any]:
    """One periodic signed heartbeat; the publication guard rejects a stale sequence (timer retries)."""
    custody = _custody(config)
    now = datetime.now(UTC)
    sequence = _sequence(custody["state_path"], custody["private_key"]) + 1
    return signed_heartbeat(sequence, now.isoformat(), expires_at=(now + timedelta(
        seconds=config["validity_seconds"])).isoformat(), **custody)


def attribution(config: dict[str, Any], client: Any | None = None) -> dict[str, Any]:
    """Attribute PR head commits from GitHub push-event history; unresolved PRs fail closed."""
    from aao.github_app_auth import GitHubAppClient
    from aao.supervisor import record_attribution

    repo = config["repository"]
    if not isinstance(repo, str) or repo.count("/") != 1 or not all(repo.split("/")):
        raise ValueError("supervisor repository must be configured as owner/name")
    github = client if client is not None else GitHubAppClient("aao-supervisor")
    owner, name = repo.split("/", 1)
    if hasattr(github, "installation_token"):
        github.installation_token(owner, name)
    escaped = f"{quote(owner, safe='')}/{quote(name, safe='')}"

    def get(path: str) -> Any:
        response = github.request("GET", path)
        status = getattr(response, "status", 200)
        body = getattr(response, "body", response)
        if not 200 <= status < 300 or not isinstance(body, list):
            raise RuntimeError(f"GitHub attribution API failed (HTTP {status})")
        return body

    sha_re = re.compile(r"[0-9a-f]{40}\Z")
    pulls = get(f"/repos/{escaped}/pulls?state=open&per_page=100")
    prs: list[dict[str, Any]] = []
    skipped: set[int] = set()
    for pr in pulls:
        head = pr.get("head") if isinstance(pr, dict) else None
        repo_info = head.get("repo") if isinstance(head, dict) else None
        sha, ref = (head.get("sha"), head.get("ref")) if isinstance(head, dict) else (None, None)
        repo_name = repo_info.get("full_name") if isinstance(repo_info, dict) else None
        number = pr.get("number") if isinstance(pr, dict) else None
        if isinstance(number, int) and isinstance(sha, str) and sha_re.fullmatch(sha) and isinstance(ref, str) and isinstance(repo_name, str):
            prs.append({"number": number, "sha": sha, "ref": ref, "repo": repo_name})
        elif isinstance(number, int):
            skipped.add(number)

    repos: dict[str, list[dict[str, Any]]] = {}
    for pr in prs:
        repos.setdefault(pr["repo"], []).append(pr)
    attributed: dict[str, set[str]] = {}
    for head_repo, repo_prs in repos.items():
        repo_owner, repo_name = head_repo.split("/", 1) if head_repo.count("/") == 1 else (None, None)
        try:
            events = get(f"/repos/{quote(repo_owner or '', safe='')}/{quote(repo_name or '', safe='')}/events?per_page=100")
        except (RuntimeError, OSError, ValueError):
            skipped.update(pr["number"] for pr in repo_prs)
            continue
        pushes: list[tuple[str, str, str, str]] = []
        malformed = False
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "PushEvent":
                continue
            actor = event.get("actor")
            payload = event.get("payload")
            if (not isinstance(actor, dict) or not isinstance(actor.get("login"), str) or not actor["login"]
                    or not isinstance(payload, dict) or not isinstance(payload.get("head"), str)
                    or not sha_re.fullmatch(payload["head"]) or not isinstance(payload.get("before"), str)
                    or not sha_re.fullmatch(payload["before"]) or not isinstance(payload.get("ref"), str)):
                malformed = True
                break
            pushes.append((actor["login"], payload["head"], payload["before"], payload["ref"]))
        if malformed:
            skipped.update(pr["number"] for pr in repo_prs)
            continue
        for pr in repo_prs:
            try:
                commits = get(f"/repos/{escaped}/pulls/{pr['number']}/commits?per_page=100")
            except (RuntimeError, OSError, ValueError):
                skipped.add(pr["number"])
                continue
            if isinstance(commits, list) and len(commits) >= 100:
                # GitHub returns at most 100 commits per page; a truncated set cannot
                # establish complete commit-to-push attribution for this PR.
                skipped.add(pr["number"])
                continue
            commit_shas = {item.get("sha") for item in commits if isinstance(item, dict)
                           and isinstance(item.get("sha"), str) and sha_re.fullmatch(item["sha"])}
            matching = [push for push in pushes if push[1] == pr["sha"] and push[3] == f"refs/heads/{pr['ref']}"]
            if not matching:
                skipped.add(pr["number"])
                continue
            chain_events: dict[str, list[tuple[str, str]]] = {}
            for actor, head, before, ref in pushes:
                if ref == f"refs/heads/{pr['ref']}":
                    chain_events.setdefault(head, []).append((actor, before))
            principals: set[str] = set()
            visited: set[str] = set()
            pending = [pr["sha"]]
            complete = True
            reached_creation = False
            while pending:
                head_sha = pending.pop()
                if head_sha == "0" * 40:
                    reached_creation = True
                    continue
                if head_sha in visited:
                    continue
                visited.add(head_sha)
                links = chain_events.get(head_sha)
                if not links:
                    complete = False
                    continue
                for actor, before in links:
                    principals.add(actor)
                    pending.append(before)
            complete = complete and reached_creation
            if not complete:
                skipped.add(pr["number"])
                continue
            principals.update(actor for actor, head, _before, _ref in pushes if head in commit_shas)
            attributed.setdefault(pr["sha"], set()).update(principals)
    for sha, principals in sorted(attributed.items()):
        record_attribution(Path(config["attribution_path"]), sha, sorted(principals))
    return {"candidates": len(attributed), "skipped_prs": sorted(skipped)}


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _ruleset_missing(observed: list[Any], expected_types: set[str], required_checks: dict[str, Any]) -> list[str]:
    types = {item.get("type") for item in observed if isinstance(item, dict)}
    missing = sorted(expected_types - types)
    observed_checks = []
    for item in observed:
        if isinstance(item, dict) and item.get("type") == "required_status_checks":
            parameters = item.get("parameters")
            checks = parameters.get("required_status_checks") if isinstance(parameters, dict) else None
            observed_checks = checks if isinstance(checks, list) else []
    by_context = {check.get("context"): check for check in observed_checks if isinstance(check, dict)}
    for context, integration_id in required_checks.items():
        check = by_context.get(context)
        if not isinstance(check, dict):
            missing.append(f"required_status_checks:{context}")
        elif integration_id is not None and check.get("integration_id") != integration_id:
            missing.append(f"required_status_checks:{context}:integration_id")
    return sorted(missing)


def watch(config: dict[str, Any], client: Any | None = None, *,
          events_dir: Path | None = None) -> dict[str, int]:
    """Detect unauthorized main pushes and main ruleset drift, publishing signed notifier events."""
    from aao.github_app_auth import GitHubAppClient

    repo = config["repository"]
    if not isinstance(repo, str) or repo.count("/") != 1 or not all(repo.split("/")):
        raise ValueError("supervisor repository must be configured as owner/name")
    github = client if client is not None else GitHubAppClient("aao-supervisor")
    owner, name = repo.split("/", 1)
    github.installation_token(owner, name)
    escaped = f"{quote(owner, safe='')}/{quote(name, safe='')}"

    def get(path: str) -> list[Any]:
        response = github.request("GET", path)
        status = getattr(response, "status", 200)
        body = getattr(response, "body", response)
        if not 200 <= status < 300 or not isinstance(body, list):
            raise RuntimeError(f"GitHub supervisor watch API failed (HTTP {status})")
        return body

    # Fetch and validate both sources before changing state or publishing any event.
    events = get(f"/repos/{escaped}/events?per_page=100")
    observed = get(f"/repos/{escaped}/rules/branches/main")
    for event in events:
        if not isinstance(event, dict):
            raise TypeError("GitHub events response contains a malformed item")
        if event.get("type") == "PushEvent":
            payload, actor = event.get("payload"), event.get("actor")
            if (not isinstance(payload, dict) or not isinstance(actor, dict) or
                    not isinstance(actor.get("login"), str) or
                    not isinstance(payload.get("ref"), str) or
                    not isinstance(payload.get("push_id"), (str, int)) or
                    not isinstance(payload.get("before"), str) or not isinstance(payload.get("head"), str)):
                raise RuntimeError("GitHub PushEvent response has an invalid live payload")
    if any(not isinstance(item, dict) or not isinstance(item.get("type"), str) for item in observed):
        raise RuntimeError("GitHub rules response contains a malformed item")

    now = datetime.now(UTC)
    timestamp = now.isoformat()
    expiry = (now + timedelta(seconds=int(config["validity_seconds"]))).isoformat()
    state_path = Path(config["state_path"]).with_name("watch-state.json")
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    seen = set(state.get("push_ids", []))
    pending: list[dict[str, Any]] = []
    allowed = config.get("integrator_login", INTEGRATOR_LOGIN)
    for event in events:
        if event.get("type") != "PushEvent":
            continue
        payload, actor = event["payload"], event["actor"]["login"]
        push_id = str(payload["push_id"])
        if payload["ref"] == "refs/heads/main" and actor != allowed and push_id not in seen:
            pending.append({"type": "governance-violation", "repo": repo, "ref": payload["ref"],
                            "actor": actor, "before": payload["before"], "head": payload["head"],
                            "push_id": payload["push_id"], "detected_at": timestamp})
            seen.add(push_id)

    # Endpoint responses do not expose bypass_actors without admin; bypass-list drift is out of scope.
    expected_types = set(config.get("watch_expected_types", EXPECTED_RULE_TYPES))
    required_checks = config.get("watch_required_checks", {"aao-audit": AUDIT_INTEGRATION_ID, "test": None})
    if (not expected_types or any(not isinstance(item, str) or not item for item in expected_types) or
            not isinstance(required_checks, dict) or any(not isinstance(context, str) or
            (publisher is not None and not isinstance(publisher, int))
            for context, publisher in required_checks.items())):
        raise ValueError("watch expected rules configuration is malformed")
    missing = _ruleset_missing(observed, expected_types, required_checks)
    digest = hashlib.sha256(canonical(observed)).hexdigest()
    previous_drift = state.get("ruleset_drift_hash")
    if missing:
        if previous_drift != digest:
            pending.append({"type": "ruleset-drift", "repo": repo, "missing": missing,
                            "observed": observed, "detected_at": timestamp})
        next_drift = digest
    else:
        if previous_drift is not None:
            pending.append({"type": "ruleset-restored", "repo": repo, "detected_at": timestamp})
        next_drift = None

    directory = events_dir or Path(config.get("events_path", "/var/lib/aao-supervisor/events"))
    sequence = _sequence(Path(config["state_path"]), config["private_key"])
    for event in pending:
        sequence += 1
        signed = _sign({**event, "sequence": sequence, "key_id": config["key_id"], "expires_at": expiry},
                       config["private_key"])
        target = directory / f"{sequence:020d}.json"
        _atomic_json(target, signed)
    # The signed heartbeat sequence is shared with notifier anti-replay.
    if pending:
        _persist_sequence(Path(config["state_path"]), sequence, config["private_key"])
    _atomic_json(state_path, {"push_ids": sorted(seen), "ruleset_drift_hash": next_drift})
    return {"events": len(pending), "governance_violations": sum(e["type"] == "governance-violation" for e in pending),
            "ruleset_drift": sum(e["type"] == "ruleset-drift" for e in pending),
            "ruleset_restored": sum(e["type"] == "ruleset-restored" for e in pending)}


def main() -> int:
    parser = argparse.ArgumentParser(description="AAO supervisor service (config path is fixed)")
    parser.add_argument("command", choices=("serve", "heartbeat", "attribution", "watch"))
    args = parser.parse_args()
    config = load_config()
    if args.command == "heartbeat":
        event = heartbeat(config)
        print(json.dumps({"sequence": event["sequence"], "ledger_head": event["ledger_head"]}))
        return 0
    if args.command == "attribution":
        result = attribution(config)
        print(json.dumps({"status": "recorded", **result}))
        return 0
    if args.command == "watch":
        print(json.dumps({"status": "checked", **watch(config)}, sort_keys=True))
        return 0
    serve_veto_intake(Path(config["intake_socket"]), auditor_uid=config["auditor_uid"],
                      validity_seconds=config["validity_seconds"], **_custody(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
