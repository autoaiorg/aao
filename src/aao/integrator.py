"""Fail-closed governed promotion using locally provisioned trust sources."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aao.git_paths import changed_paths as git_changed_paths
from aao.governance_ledger import active_vetoes, open_incidents, verify
from aao.integration_authorization import canonical, validate
from aao.pending_veto import PendingVetoError, pending_vetoes
from aao.supervisor import _sign

TRUST_VERIFICATION_PATH = Path("/var/lib/aao-trust-verify/status.json")
TRUST_VERIFICATION_ROOT = Path("/")
TRUST_VERIFICATION_SCHEMA = "aao.trust-root-verification.v1"
INTEGRATOR_HEARTBEAT_SEQUENCE = Path("/var/lib/aao-integrator/heartbeat.sequence")


@dataclass(frozen=True)
class TrustSources:
    trust_registry: Path
    ledger: Path
    ledger_anchor: Path
    heartbeat: Path
    freeze: Path
    integrator_private_key: Path
    heartbeat_sequence: Path = INTEGRATOR_HEARTBEAT_SEQUENCE
    # The production path and trust boundary are fixed. Tests may supply an
    # isolated status path and boundary; production callers use these defaults.
    trust_verification: Path = TRUST_VERIFICATION_PATH
    trust_verification_root: Path = TRUST_VERIFICATION_ROOT
    trust_verification_owner_uid: int = 0
    incident_inbox: Path = Path("/var/lib/aao-audit-inbox")


def _write_incident_request(inbox: Path, payload: dict[str, Any], private_key: str) -> None:
    """Publish an integrator-signed incident request without ledger custody."""
    import tempfile

    signed = _sign(payload, private_key)
    path = Path(inbox) / f"incident-{payload['intended_sha']}.json"
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(signed)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _require_trust_root_verification(sources: TrustSources, registry: dict[str, Any],
                                     current_time: datetime) -> None:
    """Require a fresh, protected verifier result for a statically trusted revision."""
    try:
        path = Path(sources.trust_verification)
        boundary = Path(sources.trust_verification_root)
        if path.is_symlink():
            raise ValueError("status file is a symlink")
        if not path.is_absolute() or not boundary.is_absolute() or boundary not in path.parents:
            raise ValueError("status path is outside the protected trust boundary")
        # Check each directory from the status parent through the configured
        # trust boundary, rejecting symlinks, foreign ownership, and writable
        # group/other permissions.
        for parent in (path.parent, *path.parent.parents):
            info = parent.lstat()
            if not parent.is_dir() or parent.is_symlink():
                raise ValueError(f"unprotected parent: {parent}")
            if info.st_uid != sources.trust_verification_owner_uid or info.st_mode & 0o022:
                raise ValueError(f"unprotected parent: {parent}")
            if parent == path.parent and info.st_mode & 0o777 != 0o755:
                raise ValueError("status directory mode is not 0755")
            if parent == boundary:
                break
        else:
            raise ValueError("trust boundary not reached")
        info = path.lstat()
        if not path.is_file() or path.is_symlink():
            raise ValueError("status is not a regular file")
        if info.st_uid != sources.trust_verification_owner_uid:
            raise ValueError("status owner is not root")
        if info.st_mode & 0o022:
            raise ValueError("status is writable by group or others")
        if info.st_mode & 0o777 != 0o644:
            raise ValueError("status file mode is not 0644")
        status = json.loads(path.read_text(encoding="utf-8"))
        fields = {"schema", "result", "expected_revision", "verified_at", "failed", "verifier_sha256"}
        if not isinstance(status, dict) or set(status) != fields:
            raise ValueError("status schema fields are invalid")
        if status["schema"] != TRUST_VERIFICATION_SCHEMA:
            raise ValueError("status schema is invalid")
        if status["result"] != "PASS":
            raise ValueError("verifier result is not PASS")
        if status["failed"] != []:
            raise ValueError("verifier reports failed checks")
        revision = status["expected_revision"]
        trusted_revisions = registry.get("trusted_auditor_revisions")
        if (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
                or not isinstance(trusted_revisions, list) or revision not in trusted_revisions):
            raise ValueError("revision is not trusted by the static registry")
        if (not isinstance(status["verifier_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", status["verifier_sha256"])):
            raise ValueError("verifier digest is invalid")
        if not isinstance(status["verified_at"], str):
            raise TypeError("verification timestamp is invalid")
        verified_at = datetime.fromisoformat(status["verified_at"])
        if verified_at.tzinfo is None or verified_at.utcoffset() != timedelta(0):
            raise ValueError("verification timestamp is not UTC")
        age = current_time.astimezone(UTC) - verified_at.astimezone(UTC)
        if age < timedelta(0):
            raise ValueError("verification timestamp is in the future")
        if age > timedelta(hours=26):
            raise ValueError("verification status is stale")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("trust root not verified:"):
            raise
        raise ValueError(f"trust root not verified: {error}") from error


def _public_key_der(public_key: str) -> bytes:
    result = subprocess.run(
        ["openssl", "pkey", "-pubin", "-in", public_key, "-outform", "DER"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError("trust registry contains an unreadable public key")
    return result.stdout


def _validate_integrator_key_separation(registry: dict[str, Any]) -> None:
    keys = registry.get("ledger_keys")
    key_id = registry.get("integrator_key_id")
    if not isinstance(keys, dict) or not isinstance(key_id, str):
        raise TypeError("integrator trust registry is incomplete")
    integrator = keys.get(key_id)
    if not isinstance(integrator, dict) or not integrator.get("public_key"):
        raise ValueError("integrator trust registry key is missing")
    if integrator.get("can_resolve_pending") is True or integrator.get("can_authorize") is True:
        raise ValueError("integrator key has a reserved ledger capability")
    integrator_key = _public_key_der(integrator["public_key"])
    for other_id, entry in keys.items():
        if other_id == key_id or not isinstance(entry, dict):
            continue
        if ((entry.get("can_resolve_pending") is True or entry.get("can_authorize") is True)
                and entry.get("public_key")
                and _public_key_der(entry["public_key"]) == integrator_key):
            raise ValueError("integrator public key is shared with a reserved ledger authority")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def _conditional_push(repo: Path, remote_url: str, ref: str, base: str, commit: str, token: str | None):
    """Push with memory-only App credentials; Git argv and repository config stay credential-free."""
    github_remote = "github.com" in remote_url.lower()
    if not token and github_remote:
        raise RuntimeError("GitHub installation token is unavailable")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_COUNT": "2",
           "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
           "GIT_CONFIG_KEY_1": "http.https://github.com/.extraheader",
           "GIT_CONFIG_VALUE_1": ("AUTHORIZATION: basic " +
               base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")) if token else ""}
    return subprocess.run(["git", "-C", str(repo), "push", "--atomic",
        f"--force-with-lease={ref}:{base}", remote_url, f"{commit}:{ref}"], check=False,
        capture_output=True, text=True, env=env)


def _heartbeat(path: Path, registry: dict[str, Any], now: datetime,
               sequence_path: Path = INTEGRATOR_HEARTBEAT_SEQUENCE) -> dict[str, Any] | None:
    event = json.loads(path.read_text())
    key_id = registry["supervisor_key_id"]
    if event.get("key_id") != key_id or event.get("type") != "heartbeat":
        return None
    if not isinstance(event.get("state_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", event["state_sha256"]):
        return None
    expiry = datetime.fromisoformat(event["expires_at"])
    issued = datetime.fromisoformat(event["issued_at"])
    prior = int(sequence_path.read_text()) if sequence_path.exists() else 0
    if (event.get("sequence", 0) <= prior or now >= expiry or issued > now.replace(microsecond=0) + __import__("datetime").timedelta(seconds=60)
            or (now - issued).total_seconds() > min(3600, registry.get("heartbeat_max_age_seconds", 3600))):
        return None
    signature = base64.b64decode(event["signature"], validate=True)
    signed = {k: v for k, v in event.items() if k != "signature"}
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        sig, msg = Path(directory) / "sig", Path(directory) / "msg"
        sig.write_bytes(signature); msg.write_bytes(canonical(signed))
        valid = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey",
            registry["supervisor_public_key"], "-sigfile", str(sig), "-in", str(msg), "-rawin"],
            check=False, capture_output=True).returncode == 0
    if valid:
        sequence_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        sequence_path.parent.chmod(0o700)
        sequence_path.write_text(str(event["sequence"]))
    return event if valid else None


def promote(repo: Path, remote: str, auth: dict[str, Any], signature: str,
            trust_sources: TrustSources, message: str = "Governed integration",
            before_push=None, identity_provider=None, after_push=None,
            after_recheck=None,
            observed_repo: str | None = None, observed_pr_number: int | None = None,
            staged_commit: str | None = None,
            ci_verified_sha: str | None = None,
            candidate_ref: str | None = None,
            git_token: str | Callable[[], str] | None = None,
            now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> str:
    if identity_provider is None:
        raise RuntimeError("identity provider is mandatory")
    if trust_sources.freeze.exists() or (repo / ".aao-freeze").exists():
        raise RuntimeError("integrator frozen")
    registry = json.loads(trust_sources.trust_registry.read_text())
    per_pr_registry_fields = {"ci_candidate_sha", "attribution_resolved", "repo", "pr_number", "pr_head"}
    if per_pr_registry_fields.intersection(registry):
        raise ValueError("trust registry contains per-PR fields")
    if not isinstance(observed_repo, str) or not observed_repo or not isinstance(observed_pr_number, int):
        raise ValueError("observed repository and PR number are required")
    ledger_keys = registry["ledger_keys"]
    _validate_integrator_key_separation(registry)
    rows = verify(trust_sources.ledger, ledger_keys)
    initial_ledger_head = rows[-1]["hash"] if rows else "0" * 64
    decisions = [row for row in rows if row.get("candidate_sha") == auth.get("candidate_sha") and
                 row.get("type") in {"audit-verdict", "veto"}]
    if (not decisions or decisions[-1].get("report_sha256") != auth.get("expediente_sha256") or
            decisions[-1].get("verdict") != "approve" or decisions[-1].get("veto") is True):
        raise ValueError("authorization is not bound to the current ledger audit decision")
    current_time = now()
    if current_time.tzinfo is None:
        raise ValueError("clock must return timezone-aware datetime")
    _require_trust_root_verification(trust_sources, registry, current_time)
    heartbeat = _heartbeat(trust_sources.heartbeat, registry, current_time,
                            getattr(trust_sources, "heartbeat_sequence", None))
    if heartbeat is None:
        raise ValueError("valid supervisor heartbeat unavailable")
    heartbeat_ok = True
    initial_heartbeat_digest = hashlib.sha256(trust_sources.heartbeat.read_bytes()).hexdigest()
    supervisor_head = heartbeat.get("ledger_head")
    supervisor_markers = heartbeat.get("pending_markers")
    if (not isinstance(supervisor_head, str) or not isinstance(supervisor_markers, dict) or
            any(not isinstance(candidate, str) or not isinstance(digests, list) or
                any(not isinstance(digest, str) for digest in digests)
                for candidate, digests in supervisor_markers.items())):
        raise ValueError("valid supervisor heartbeat unavailable: missing ledger custody state")
    terminal = rows[-1]["hash"] if rows else "0" * 64
    if terminal != supervisor_head:
        if supervisor_head == "0" * 64 or supervisor_head in {row["hash"] for row in rows}:
            raise ValueError("ledger not yet anchored")
        raise ValueError("ledger truncated or rewritten")
    try:
        markers = pending_vetoes(Path(str(trust_sources.ledger) + ".pending-vetoes"), auth["candidate_sha"],
                                 trust_sources.ledger.stat().st_uid)
    except (PendingVetoError, OSError, ValueError) as error:
        raise ValueError(f"pending vetoes cannot be verified: {error}") from error
    resolved: set[str] = set()
    for row in rows:
        if "resolves_pending" in row:
            values = row["resolves_pending"]
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError("pending vetoes cannot be verified: malformed resolves_pending ledger field")
            key_entry = ledger_keys.get(row.get("key_id"))
            if not isinstance(key_entry, dict) or key_entry.get("can_resolve_pending") is not True:
                raise ValueError("resolves_pending signer is not an enabled authority")
            resolved.update(values)
    seen = set(supervisor_markers.get(auth["candidate_sha"], []))
    present = set(markers)
    initial_markers = set(markers)
    deleted = seen - present - resolved
    if deleted:
        raise ValueError("pending veto marker deleted")
    if seen - resolved:
        raise ValueError("candidate has an unresolved pending veto")
    if any(digest not in resolved for digest in markers):
        raise ValueError("candidate has an unresolved pending veto")
    incident_resolvers = registry.get("incident_resolvers")
    if not isinstance(incident_resolvers, list) or any(
        row.get("type") == "incident-resolution" and row.get("key_id") not in incident_resolvers
        for row in rows
    ):
        raise ValueError("incident-resolution signer is not enabled in trust registry")
    if active_vetoes(rows, ledger_keys):
        raise ValueError("active ledger veto")
    if open_incidents(rows):
        raise RuntimeError("open ledger incident")
    ra = registry["ra_status"]
    ra01 = ra.get("RA-01") == "PASS"
    ra02 = ra.get("RA-02") == "PASS"
    ra03 = ra.get("RA-03") == "PASS"
    ra07 = ra.get("RA-07") == "PASS"
    ra09 = ra.get("RA-09") == "PASS"
    ref = auth["target_ref"]
    if ref not in registry["target_refs"]:
        raise ValueError("target ref not permitted")
    identity = identity_provider() if callable(identity_provider) else identity_provider
    if identity != registry["integrator_identity"]:
        raise RuntimeError("integrator identity mismatch")
    # R1 callers pass the authoritative remote URL directly. Legacy callers may
    # still pass a configured remote name; resolve only that form through the
    # repository config so a mirror's implicit `origin` is never substituted.
    is_explicit_url = (Path(remote).is_absolute() or "://" in remote or remote.startswith("git@"))
    remote_url = remote if is_explicit_url else _git(repo, "remote", "get-url", remote)
    remote_refs = subprocess.run(["git", "ls-remote", remote_url, ref],
                                 check=True, capture_output=True, text=True).stdout.splitlines()
    base = next((parts[0] for line in remote_refs
                 if len(parts := line.split()) == 2 and parts[1] == ref), None)
    head_ref = candidate_ref or auth.get("candidate_ref") or "refs/heads/candidate"
    candidates = subprocess.run(["git", "ls-remote", remote_url, head_ref], check=True,
                                capture_output=True, text=True).stdout.splitlines()
    head = next((line.split()[0] for line in candidates if len(line.split()) == 2 and line.split()[1] == head_ref), None)
    # Candidate is identified by signed SHA; require that object to be present locally and reachable remotely.
    if not base or not head:
        raise ValueError("remote base or candidate unavailable")
    try:
        subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{head}^{{commit}}"],
                       check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError) as error:
        raise ValueError("changed paths unavailable: local head commit missing") from error
    version = _git(repo, "--version").removeprefix("git version ")
    has_base = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{base}^{{commit}}"],
                              check=False, capture_output=True).returncode == 0
    if not has_base:
        raise ValueError("changed paths unavailable: local base commit missing")
    try:
        changed = git_changed_paths(repo, base, head)
    except (subprocess.CalledProcessError, OSError) as error:
        raise ValueError(f"changed paths unavailable: {error}") from error
    state = {**registry, "repo": observed_repo, "pr_number": observed_pr_number,
        "pr_head": head, "target_ref": ref, "target_sha": base,
        "merge_tree_sha": auth["merge_result_tree_sha"], "now": current_time.isoformat(),
        "heartbeat_valid": heartbeat_ok, "ra03_pass": ra03, "ra09_pass": ra09,
        "ra02_pass": ra02, "ledger": {"veto": bool(active_vetoes(rows, ledger_keys))},
        "git_version": version, "changed_paths": changed}
    # Verify staged identity before authorization validation so CI for M is only
    # accepted once M's authorized tree and parent list have been established.
    tree = _git(repo, "merge-tree", "--write-tree", base, head).splitlines()[0]
    expected_parents = auth["expected_parents"]
    if staged_commit is not None:
        try:
            staged_tree = _git(repo, "show", "-s", "--format=%T", staged_commit)
            staged_parents = _git(repo, "show", "-s", "--format=%P", staged_commit).split()
        except (subprocess.CalledProcessError, OSError) as error:
            raise ValueError("staged commit is unavailable") from error
        if staged_tree != tree:
            raise ValueError("staged commit tree differs from authorized merge tree")
        if staged_parents != expected_parents:
            raise ValueError("staged commit parents differ from authorized parents")
    # Required checks count only when verified on M itself (the staged merge commit that will be published), never on
    # the PR head (E2E_PR_PIPELINE invariant; Codex pre-audit r1 A-01).
    if staged_commit is not None and ci_verified_sha == staged_commit:
        state["ci_candidate_sha"] = auth["candidate_sha"]
    reasons = validate(auth, signature, state)
    if not all((ra01, ra02, ra03, ra07, ra09)):
        reasons.append("required RA status pending")
    if reasons:
        raise ValueError("authorization rejected: " + "; ".join(reasons))
    if tree != auth["merge_result_tree_sha"]:
        raise ValueError("computed merge tree differs from authorization")
    if staged_commit is None:
        commit = subprocess.run(["git", "-C", str(repo), "commit-tree", tree,
            *[arg for parent in expected_parents for arg in ("-p", parent)]],
            input=message + "\n", check=True, capture_output=True, text=True,
            env={**os.environ,
                 "GIT_AUTHOR_NAME": "aao-integrator",
                 "GIT_AUTHOR_EMAIL": "aao-integrator@users.noreply.github.com",
                 "GIT_COMMITTER_NAME": "aao-integrator",
                 "GIT_COMMITTER_EMAIL": "aao-integrator@users.noreply.github.com"}).stdout.strip()
    else:
        commit = staged_commit
    if not identity_provider.push_identity(ref, base, commit):
        raise RuntimeError("unattributed push")
    if before_push:
        before_push()
    # Re-read the remote immediately before the conditional push.
    latest_lines = subprocess.run(["git", "ls-remote", remote_url, ref], check=True,
                                  capture_output=True, text=True).stdout.splitlines()
    latest = next((parts[0] for line in latest_lines
                   if len(parts := line.split()) == 2 and parts[1] == ref), None)
    if latest is None:
        raise RuntimeError("remote base ref unavailable")
    if latest != base:
        raise RuntimeError("remote base moved")
    if after_recheck:
        after_recheck()
    if callable(git_token):
        git_token = git_token()
    # Final custody fence: changes after this read and before receive-pack are
    # an unavoidable residual race without a shared lock/transaction with the
    # independent supervisor and ledger writers.
    latest_rows = verify(trust_sources.ledger, ledger_keys)
    latest_head = latest_rows[-1]["hash"] if latest_rows else "0" * 64
    if latest_head != initial_ledger_head:
        raise RuntimeError("ledger changed during promotion")
    latest_decisions = [row for row in latest_rows if row.get("candidate_sha") == auth.get("candidate_sha") and
                        row.get("type") in {"audit-verdict", "veto"}]
    if (not latest_decisions or latest_decisions[-1].get("report_sha256") != auth.get("expediente_sha256") or
            latest_decisions[-1].get("verdict") != "approve" or latest_decisions[-1].get("veto") is True):
        raise RuntimeError("current audit decision changed during promotion")
    # Do not consume the monotonic heartbeat sequence twice in one promotion;
    # compare the freshly read signed heartbeat bytes to the validated snapshot.
    if hashlib.sha256(trust_sources.heartbeat.read_bytes()).hexdigest() != initial_heartbeat_digest:
        raise RuntimeError("supervisor heartbeat changed during promotion")
    try:
        latest_markers = set(pending_vetoes(Path(str(trust_sources.ledger) + ".pending-vetoes"),
                                           auth["candidate_sha"], trust_sources.ledger.stat().st_uid))
    except (PendingVetoError, OSError, ValueError) as error:
        raise RuntimeError(f"pending veto markers cannot be re-read before push: {error}") from error
    if latest_markers != initial_markers:
        raise RuntimeError("pending veto markers changed during promotion")
    if active_vetoes(latest_rows, ledger_keys) or open_incidents(latest_rows):
        raise RuntimeError("ledger veto or incident appeared during promotion")
    result = _conditional_push(repo, remote_url, ref, base, commit, git_token)
    if result.returncode:
        # A client/network error does not prove that the server rejected the
        # update. Read the ref before reporting failure; never try another
        # publication route after an ambiguous response.
        try:
            listing = subprocess.run(["git", "ls-remote", remote_url, ref], check=True,
                                     capture_output=True, text=True).stdout.splitlines()
            observed_sha = next((parts[0] for line in listing
                                 if len(parts := line.split()) == 2 and parts[1] == ref), None)
        except (OSError, subprocess.CalledProcessError) as error:
            observed_sha = None
            verify_error = f"state verification failed: {type(error).__name__}: {error}"
        else:
            verify_error = ""
        # A force-with-lease rejection explicitly identifies a stale expected
        # value; that is a known CAS failure, not an ambiguous transport result.
        if observed_sha != base and "stale info" in result.stderr.lower():
            raise RuntimeError("conditional push rejected; no fallback: " + result.stderr)
        if observed_sha == base:
            raise RuntimeError("conditional push rejected; no fallback: " + result.stderr)
        if observed_sha != commit:
            detail = ("ambiguous push response; " + verify_error if verify_error else
                      f"ambiguous push response; observed ref {observed_sha!r} differs from "
                      f"base {base} and intended {commit}")
            trust_sources.freeze.write_text(
                f"{detail}; intended_sha={commit}; observed_sha={observed_sha}\n"
            )
            try:
                payload = {"schema": "aao.integrator-incident.v1", "type": "incident",
                    "id": f"ambiguous-push-{commit}", "target_ref": ref, "detail": detail,
                    "intended_sha": commit, "observed_sha": observed_sha,
                    "intended_tree_sha": auth["merge_result_tree_sha"], "observed_tree_sha": None,
                    "intended_parents": auth["expected_parents"], "observed_parents": None,
                    "created_at": current_time.isoformat(), "key_id": registry["integrator_key_id"]}
                _write_incident_request(trust_sources.incident_inbox, payload,
                                        str(trust_sources.integrator_private_key))
            except Exception as incident_error:
                raise RuntimeError(f"post-publication incident; frozen; incident request recording failed: {incident_error}") from incident_error
            raise RuntimeError("post-publication incident; integrator frozen")
    expected_tree = auth["merge_result_tree_sha"]
    observed: dict[str, Any] = {"sha": None, "tree_sha": None, "parents": None}
    try:
        if after_push:
            after_push()
        listing = subprocess.run(["git", "ls-remote", remote_url, ref], check=True,
                                 capture_output=True, text=True).stdout.splitlines()
        observed["sha"] = next((parts[0] for line in listing
                                 if len(parts := line.split()) == 2 and parts[1] == ref), None)
        if observed["sha"] is None:
            raise RuntimeError("published remote ref is missing")
        _git(repo, "cat-file", "-e", f"{observed['sha']}^{{commit}}")
        observed["tree_sha"] = _git(repo, "show", "-s", "--format=%T", observed["sha"])
        observed["parents"] = _git(repo, "show", "-s", "--format=%P", observed["sha"]).split()
        if (observed["sha"] != commit or observed["tree_sha"] != expected_tree or
                observed["parents"] != expected_parents):
            raise RuntimeError("published ref SHA, tree, or parents differ from authorized promotion")
    except Exception as error:
        detail = f"post-push verification failed: {type(error).__name__}: {error}"
        trust_sources.freeze.write_text(
            f"{detail}; intended_sha={commit}; observed_sha={observed['sha']}\n"
        )
        try:
            payload = {"schema": "aao.integrator-incident.v1", "type": "incident",
                "id": f"post-push-{commit}", "target_ref": ref, "detail": detail,
                "intended_sha": commit, "observed_sha": observed["sha"],
                "intended_tree_sha": expected_tree, "observed_tree_sha": observed["tree_sha"],
                "intended_parents": expected_parents, "observed_parents": observed["parents"],
                "created_at": current_time.isoformat(), "key_id": registry["integrator_key_id"]}
            _write_incident_request(trust_sources.incident_inbox, payload,
                                    str(trust_sources.integrator_private_key))
        except Exception as incident_error:  # noqa: BLE001 - preserve freeze if recording itself fails.
            raise RuntimeError(f"post-publication incident; frozen; incident request recording failed: {incident_error}") from error
        raise RuntimeError("post-publication incident; integrator frozen") from error
    return commit
