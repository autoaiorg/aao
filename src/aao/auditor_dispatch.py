"""Untrusted-inbox dispatcher for the isolated aao-auditor identity."""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from aao.authorization_issuer import TRUST_REGISTRY_PATH, issue_authorization
from aao.github_app_auth import GitHubAppClient
from aao.governance_ledger import append as append_ledger
from aao.integration_authorization import canonical
from aao.manifest_audit import (
    ANCHOR_PATH,
    _ledger,
    _ledger_keys,
    audit_manifest,
    ledger_rows,
    load_anchor,
    verify_promotion,
)

_ID = re.compile(r"^[0-9a-f]{64}$")
_INCIDENT_NAME = re.compile(r"^incident-([0-9a-f]{40})\.json$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_INCIDENT_FIELDS = {"schema", "type", "id", "target_ref", "detail", "intended_sha", "observed_sha",
                    "intended_tree_sha", "observed_tree_sha", "intended_parents", "observed_parents",
                    "created_at", "signature", "key_id"}
_MANIFEST_KEYS = {"schema", "repository", "target_ref", "target_sha", "candidate_sha",
                  "candidate_tree", "result_tree", "producer"}
CONFIG_PATH = Path("/etc/aao-audit/dispatch.json")
CONFIG_SCHEMA = "aao.audit-dispatch-config.v1"
_CONFIG_FIELDS = {"schema", "inbox", "reports", "key", "repository_root", "repo"}


def _read_owned(path: Path, owners: tuple[int, ...]) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_uid not in owners:
            raise ValueError(f"{path} is not a protected regular file owned by {owners}")
        return handle.read()


def load_config(path: Path | None = None, owners: tuple[int, ...] = (0,)) -> dict[str, Any]:
    path = CONFIG_PATH if path is None else Path(path)
    config = json.loads(_read_owned(path, owners))
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS or config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("auditor dispatch config fields are not the expected set")
    for field in _CONFIG_FIELDS - {"schema"}:
        if not isinstance(config[field], str) or not config[field]:
            raise ValueError(f"auditor dispatch config {field} must be a non-empty string")
    if config["repo"].count("/") != 1 or any(not part for part in config["repo"].split("/")):
        raise ValueError("auditor dispatch repo must be owner/name")
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="AAO auditor dispatcher (fixed config path)")
    parser.add_argument("command", choices=("once",))
    parser.parse_args()
    try:
        config = load_config(CONFIG_PATH)
        client = GitHubAppClient("aao-auditor")
        client.installation_token(*config["repo"].split("/", 1))
        results = dispatch_once(config["inbox"], config["reports"], config["key"], client,
                                anchor_path=ANCHOR_PATH,
                                repository_root=Path(config["repository_root"]),
                                expected_repo=config["repo"])
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "reason": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 1
    print(json.dumps(results, sort_keys=True))
    return 0


def _read_request(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("request is not a regular file")
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("request exceeds 64 KiB")
    return raw


def _atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    path.parent.chmod(0o750)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _publish(client: Any, repo: str, sha: str, conclusion: str, detail: str) -> None:
    if hasattr(client, "create_check_run"):
        client.create_check_run(repo, "aao-audit", sha, conclusion, detail)
        return
    owner, name = repo.split("/", 1)
    response = client.request("POST", f"/repos/{owner}/{name}/check-runs", body={
        "name": "aao-audit", "head_sha": sha, "status": "completed",
        "conclusion": conclusion, "output": {"title": "AAO promotion gate", "summary": detail[:1000]}})
    status = getattr(response, "status", 200)
    if status < 200 or status >= 300:
        raise RuntimeError(f"could not publish aao-audit check (HTTP {status})")


def dispatch_once(inbox: str | Path, reports: str | Path, key: str | Path,
                  github_auditor_client: Any, *, anchor_path: Path = ANCHOR_PATH,
                  anchor_owner_uids: tuple[int, ...] = (0,),
                  registry_owner_uids: tuple[int, ...] | None = None,
                  repository_root: Path | None = None,
                  expected_repo: str | None = None,
                  runner: Callable[[Path, list[str]], tuple[int, str, str]] | None = None,
                  trust_registry_path: Path = TRUST_REGISTRY_PATH,
                  trust_registry_owner_uids: tuple[int, ...] | None = None) -> list[dict[str, str]]:
    """Process each valid request once. The inbox is data only; no command is run from it."""
    inbox, reports, key = Path(inbox), Path(reports), Path(key)
    if trust_registry_owner_uids is None:
        try:
            trust_registry_owner_uids = (0, pwd.getpwnam("aao-trust").pw_uid)
        except KeyError:
            trust_registry_owner_uids = (0,)
    reports.mkdir(mode=0o750, parents=True, exist_ok=True)
    reports.chmod(0o750)
    results: list[dict[str, str]] = []
    try:
        entries = sorted(inbox.iterdir())
    except OSError as error:
        return [{"status": "failed", "reason": f"inbox unavailable: {error}"}]
    for path in entries:
        incident_name = _INCIDENT_NAME.fullmatch(path.name)
        if incident_name:
            request_id = incident_name.group(1)
            try:
                raw = _read_request(path)
                request = json.loads(raw)
                if not isinstance(request, dict) or set(request) != _INCIDENT_FIELDS:
                    raise ValueError("invalid incident request fields")
                if (request["schema"] != "aao.integrator-incident.v1" or request["type"] != "incident"
                        or not isinstance(request["id"], str) or not request["id"] or len(request["id"]) > 256
                        or not isinstance(request["target_ref"], str)
                        or not request["target_ref"].startswith("refs/heads/")
                        or not isinstance(request["detail"], str) or len(request["detail"]) > 4096):
                    raise ValueError("invalid incident request values")
                for field in ("intended_sha", "intended_tree_sha"):
                    if not isinstance(request[field], str) or not _SHA1.fullmatch(request[field]):
                        raise ValueError(f"invalid {field}")
                for field in ("observed_sha", "observed_tree_sha"):
                    if request[field] is not None and (not isinstance(request[field], str)
                                                       or not _SHA1.fullmatch(request[field])):
                        raise ValueError(f"invalid {field}")
                for field in ("intended_parents", "observed_parents"):
                    parents = request[field]
                    if parents is not None and (not isinstance(parents, list) or len(parents) > 2
                            or any(not isinstance(item, str) or not _SHA1.fullmatch(item) for item in parents)):
                        raise ValueError(f"invalid {field}")
                if request["intended_parents"] is None:
                    raise ValueError("intended_parents must be a list")
                if request["intended_sha"] != request_id:
                    raise ValueError("incident filename does not match intended SHA")
                if not isinstance(request["created_at"], str):
                    raise TypeError("invalid created_at")
                timestamp = datetime.fromisoformat(request["created_at"])
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    raise ValueError("created_at must include a timezone")
                if not isinstance(request["key_id"], str) or not request["key_id"]:
                    raise ValueError("invalid key_id")
                if not isinstance(request["signature"], str):
                    raise TypeError("invalid signature")
                signature = base64.b64decode(request["signature"], validate=True)
                registry = json.loads(_read_owned(Path(trust_registry_path), trust_registry_owner_uids))
                if not isinstance(registry, dict) or request["key_id"] != registry.get("integrator_key_id"):
                    raise ValueError("incident signer is not the registered integrator")
                trusted_keys = registry.get("ledger_keys")
                if not isinstance(trusted_keys, dict):
                    raise TypeError("integrator trust registry has no ledger key map")
                signer = trusted_keys.get(request["key_id"])
                if not isinstance(signer, dict) or not isinstance(signer.get("public_key"), str):
                    raise TypeError("integrator public key is unavailable")
                payload = {field: value for field, value in request.items() if field != "signature"}
                with tempfile.TemporaryDirectory(prefix="aao-incident-verify-") as temporary:
                    message = Path(temporary) / "message"
                    sig = Path(temporary) / "signature"
                    message.write_bytes(canonical(payload)); sig.write_bytes(signature)
                    verified = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey",
                        signer["public_key"], "-sigfile", str(sig), "-in", str(message), "-rawin"],
                        check=False, capture_output=True).returncode == 0
                if not verified:
                    raise ValueError("integrator incident signature is invalid")
                anchor = load_anchor(anchor_path, anchor_owner_uids)
                # Check-then-append under one lock: concurrent dispatchers cannot record the same incident twice.
                with Path(str(_ledger(anchor)) + ".lock").open("a") as ledger_lock:
                    fcntl.flock(ledger_lock, fcntl.LOCK_EX)
                    rows = ledger_rows(anchor)
                    if any(row.get("type") == "integrator-incident" and row.get("id") == request["id"]
                           for row in rows):
                        results.append({"id": request_id, "status": "ignored", "reason": "incident already recorded"})
                        continue
                    auditor_id = anchor["policy"]["auditor_id"]
                    with tempfile.TemporaryDirectory(prefix="aao-ledger-keys-") as temporary:
                        keys = _ledger_keys(anchor, Path(temporary))
                        append_ledger(_ledger(anchor), {"type": "integrator-incident", "id": request["id"],
                            "incident": payload,
                            "integrator_signature_sha256": hashlib.sha256(signature).hexdigest()}, auditor_id,
                            str(key), keys)
                results.append({"id": request_id, "status": "recorded"})
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError,
                    json.JSONDecodeError) as error:
                results.append({"id": request_id, "status": "failed",
                                "reason": f"{type(error).__name__}: {error}"})
            continue
        request_id = path.stem
        if path.suffix != ".json" or not _ID.fullmatch(request_id):
            results.append({"id": request_id, "status": "ignored", "reason": "invalid request id"}); continue
        if path.is_symlink() or not path.is_file():
            results.append({"id": request_id, "status": "ignored", "reason": "request is not a regular file"}); continue
        audit_dir = reports / request_id / "audit"
        gate_path = reports / request_id / "gate.json"
        try:
            raw = _read_request(path)
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get("schema") != "aao.audit-request.v1":
                raise ValueError("invalid request schema")
            kind = request.get("type")
            if kind == "audit":
                if (audit_dir / "report.json").is_file():
                    report = json.loads((audit_dir / "report.json").read_text())
                    if (report.get("verdict") == "approve" and
                            not ((reports / request_id / "authorization.json").is_file() and
                                 (reports / request_id / "authorization.sig").is_file())):
                        # A previous issuance may have raced the supervisor's ledger anchor.
                        # Retry issuance from the already signed report on the next dispatch tick.
                        auth_dir = reports / request_id / "authorization"
                        issue_authorization(audit_dir, request["repo"], request["pr_number"], key,
                                            auth_dir, anchor_path=anchor_path,
                                            anchor_owner_uids=anchor_owner_uids,
                                            registry_owner_uids=registry_owner_uids)
                        for name in ("authorization.json", "authorization.sig"):
                            target = reports / request_id / name
                            target.write_bytes((auth_dir / name).read_bytes())
                            target.chmod(0o640)
                        results.append({"id": request_id, "status": "approve",
                                        "reason": "authorization issuance retried"}); continue
                    results.append({"id": request_id, "status": "ignored",
                                    "reason": "request already has a report"}); continue
                if set(request) != {"schema", "type", "repo", "pr_number", "manifest"}:
                    raise ValueError("unexpected audit request fields")
                manifest = request["manifest"]
                if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
                    raise ValueError("invalid manifest fields")
                if repository_root is None:
                    raise ValueError("trusted repository root is required")
                if (not isinstance(manifest.get("repository"), str)
                        or Path(manifest["repository"]).resolve() != Path(repository_root).resolve()):
                    raise ValueError("manifest repository path is outside the configured mirror")
                if (not isinstance(request["repo"], str) or request["repo"].count("/") != 1
                        or not isinstance(request["pr_number"], int) or request["pr_number"] <= 0):
                    raise ValueError("invalid repository or PR")
                if expected_repo is not None and request["repo"] != expected_repo:
                    raise ValueError("request repository does not match configured repository")
                manifest_path = reports / request_id / "manifest.json"
                manifest_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                manifest_path.parent.chmod(0o750)
                manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
                verdict = audit_manifest(manifest_path, audit_dir, key, anchor_path=anchor_path,
                                         anchor_owner_uids=anchor_owner_uids, **({"runner": runner} if runner else {}))
                if verdict.get("verdict") == "approve":
                    auth_dir = reports / request_id / "authorization"
                    issue_authorization(audit_dir, request["repo"], request["pr_number"], key,
                                        auth_dir, anchor_path=anchor_path,
                                        anchor_owner_uids=anchor_owner_uids,
                                        registry_owner_uids=registry_owner_uids)
                    for name in ("authorization.json", "authorization.sig"):
                        target = reports / request_id / name
                        target.write_bytes((auth_dir / name).read_bytes())
                        target.chmod(0o640)
                results.append({"id": request_id, "status": str(verdict.get("verdict", "failed"))})
            elif kind == "gate":
                if set(request) != {"schema", "type", "id", "promoted_sha", "repo", "pr_number"}:
                    raise ValueError("unexpected gate request fields")
                audit_id, sha, repo = request["id"], request["promoted_sha"], request["repo"]
                if not isinstance(audit_id, str) or not _ID.fullmatch(audit_id):
                    raise ValueError("invalid audit id")
                if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise ValueError("invalid promoted SHA")
                if not isinstance(repo, str) or repo.count("/") != 1:
                    raise ValueError("invalid repository")
                if expected_repo is not None and repo != expected_repo:
                    raise ValueError("request repository does not match configured repository")
                current_anchor = load_anchor(anchor_path, anchor_owner_uids)
                current_rows = ledger_rows(current_anchor)
                current_head = current_rows[-1]["hash"] if current_rows else "0" * 64
                if gate_path.is_file():
                    try:
                        previous_gate = json.loads(gate_path.read_text())
                    except (OSError, ValueError):
                        previous_gate = None
                    decision_path = reports / audit_id / "audit" / "report.json"
                    current_decision = hashlib.sha256(decision_path.read_bytes()).hexdigest()
                    if (isinstance(previous_gate, dict) and previous_gate.get("promoted_sha") == sha and
                            previous_gate.get("ledger_head") == current_head and
                            previous_gate.get("audit_decision_sha256") == current_decision):
                        results.append({"id": request_id, "status": "ignored",
                                        "reason": "gate already published for current decision and promoted SHA"}); continue
                root = reports / audit_id
                conformant, reasons = verify_promotion(root / "manifest.json", root / "audit/report.json",
                    root / "audit/report.sig", sha, anchor_path=anchor_path,
                    anchor_owner_uids=anchor_owner_uids)
                decision_sha = hashlib.sha256((root / "audit/report.json").read_bytes()).hexdigest()
                ledger_head = current_rows[-1]["hash"] if current_rows else "0" * 64
                _publish(github_auditor_client, repo, sha, "success" if conformant else "failure",
                         "promotion gate passed" if conformant else "; ".join(reasons))
                _atomic(gate_path, {"schema": "aao.promotion-gate.v1", "conformant": conformant,
                                    "promoted_sha": sha, "audit_decision_sha256": decision_sha,
                                    "ledger_head": ledger_head, "reasons": list(reasons)})
                results.append({"id": request_id, "status": "success" if conformant else "failure"})
            else:
                raise ValueError("unknown request type")
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            results.append({"id": request_id, "status": "failed", "reason": f"{type(error).__name__}: {error}"})
    return results
