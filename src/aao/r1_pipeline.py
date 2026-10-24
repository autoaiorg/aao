"""Fail-closed integrator tick for the R1 pull-request pipeline.

The GitHub object may expose the small method protocol used below or a
GitHubAppClient-compatible ``request`` method. Persistent state and inbox files
are content-addressed and replaced atomically; they never carry credentials.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pwd
import stat
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aao.github_app_auth import GitHubAppClient
from aao.identity_attribution import GitHubIdentityProvider
from aao.integrator import TrustSources, promote

CONFIG_PATH = Path("/etc/aao-integrator/config.json")
CONFIG_SCHEMA = "aao.integrator-config.v1"
_CONFIG_FIELDS = {"schema", "repo", "git_remote", "mirror", "inbox", "reports", "state_dir",
                  "trust_registry", "ledger", "ledger_anchor", "heartbeat", "freeze",
                  "heartbeat_sequence", "integrator_private_key"}


def _read_config_file(path: Path, owners: tuple[int, ...]) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_uid not in owners:
            raise ValueError(f"{path} is not a protected regular file owned by {owners}")
        return handle.read()


def load_config(path: Path | None = None, owners: tuple[int, ...] = (0,),
                registry_owners: tuple[int, ...] | None = None) -> dict[str, Any]:
    """Load fixed-schema root custody configuration and protected trust registry."""
    if registry_owners is None:
        registry_owners = (0, pwd.getpwnam("aao-trust").pw_uid)
    path = CONFIG_PATH if path is None else Path(path)
    config = json.loads(_read_config_file(Path(path), owners))
    if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS or config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("integrator config fields are not the expected set")
    for field in _CONFIG_FIELDS - {"schema"}:
        if not isinstance(config[field], str) or not config[field]:
            raise ValueError(f"integrator config {field} must be a non-empty string")
    if config["repo"].count("/") != 1 or any(not part for part in config["repo"].split("/")):
        raise ValueError("integrator repo must be owner/name")
    remote = config["git_remote"]
    if not ("://" in remote or remote.startswith("git@")):
        raise ValueError("integrator git_remote must be a URL")
    registry = json.loads(_read_config_file(Path(config["trust_registry"]), registry_owners))
    if not isinstance(registry, dict):
        raise TypeError("integrator trust registry must be an object")
    identity = registry.get("integrator_identity")
    if not isinstance(identity, str) or not identity:
        raise ValueError("integrator trust registry lacks integrator_identity")
    return {**config, "integrator_identity": identity}


def run_configured_tick(config: dict[str, Any], *, github_client: Any | None = None) -> list[dict[str, Any]]:
    """Run one configured production tick; github_client is injectable for offline tests."""
    github = github_client if github_client is not None else GitHubAppClient("aao-integrator")
    github.repository = config["repo"]
    git_token = None
    git_token_provider = None
    if hasattr(github, "installation_token"):
        git_token = github.installation_token(*config["repo"].split("/", 1))
        git_token_provider = lambda: github.installation_token(*config["repo"].split("/", 1))
    sources = TrustSources(Path(config["trust_registry"]), Path(config["ledger"]),
                           Path(config["ledger_anchor"]), Path(config["heartbeat"]),
                           Path(config["freeze"]), Path(config["integrator_private_key"]),
                           Path(config["heartbeat_sequence"]), incident_inbox=Path(config["inbox"]))
    identity_name = config["integrator_identity"]
    if not isinstance(identity_name, str) or not identity_name:
        raise ValueError("integrator config lacks integrator_identity")
    identity = GitHubIdentityProvider(identity_name, github, config["repo"])
    return integrator_tick(github, config["git_remote"], config["mirror"], config["inbox"],
                           config["reports"], config["state_dir"], sources, identity,
                           lambda: datetime.now(UTC),
                           git_token=git_token_provider or git_token)


def main(*, owners: tuple[int, ...] = (0,),
         registry_owners: tuple[int, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AAO R1 integrator service (fixed config path)")
    parser.add_argument("command", choices=("tick",))
    parser.parse_args()
    try:
        config = load_config(CONFIG_PATH, owners=owners, registry_owners=registry_owners)
        results = run_configured_tick(config)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "reason": f"{type(error).__name__}: {error}"}), file=sys.stderr)
        return 1
    print(json.dumps(results, sort_keys=True))
    return 0


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _atomic_json(path: Path, value: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _git(repo: Path, *args: str, token: str | Any | None = None) -> str:
    if callable(token):
        token = token()
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
                "GIT_CONFIG_KEY_1": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_1": ""})
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
        env["GIT_CONFIG_VALUE_1"] = f"AUTHORIZATION: basic {basic}"
    elif any("github.com" in arg.lower() for arg in args):
        raise RuntimeError("GitHub installation token is unavailable")
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


def _body(response: Any) -> Any:
    return getattr(response, "body", response)


def _request(client: Any, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    response = client.request(method, path, body=body)
    status = getattr(response, "status", 200)
    if status < 200 or status >= 300:
        raise RuntimeError(f"GitHub API {method} failed with HTTP {status}")
    return _body(response)


def _pulls(client: Any, repository: str) -> list[dict[str, Any]]:
    if hasattr(client, "list_open_pull_requests"):
        values = client.list_open_pull_requests(repository, base="main")
    else:
        values = _request(client, "GET", f"/repos/{quote(repository, safe='/')}/pulls?state=open&base=main")
    if not isinstance(values, list):
        raise TypeError("GitHub returned malformed pull request list")
    return [p for p in values if isinstance(p, dict) and p.get("state", "open") == "open"
            and (p.get("base", {}).get("ref", "main") == "main")]


def _check_passed(client: Any, repository: str, sha: str, name: str,
                  required_publishers: dict[str, list[int]]) -> tuple[bool, str]:
    allowed = required_publishers.get(name)
    if not isinstance(allowed, list) or not allowed or any(type(item) is not int for item in allowed):
        return False, f"required check publisher registration missing: {name}"
    if hasattr(client, "check_conclusion"):
        # The legacy protocol exposes no publishing App identity, so cannot establish trust.
        return False, f"required check publisher identity unavailable: {name}"
    owner, repo = repository.split("/", 1)
    checks = _request(client, "GET", f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/commits/{sha}/check-runs")
    runs = [run for run in checks.get("check_runs", []) if isinstance(run, dict) and run.get("name") == name] \
        if isinstance(checks, dict) else []
    if not runs:
        return False, f"required check is absent: {name}"
    latest = max(runs, key=lambda run: (run.get("id", 0) if isinstance(run.get("id", 0), int) else 0,
                                        run.get("run_attempt", 0) if isinstance(run.get("run_attempt", 0), int) else 0))
    app = latest.get("app")
    app_id = app.get("id") if isinstance(app, dict) else None
    if type(app_id) is not int or app_id not in allowed:
        return False, f"required check publisher is unauthorized: {name}"
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        return False, f"required check is not successful: {name}"
    return True, "passed"


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def integrator_tick(github: Any, git_remote: str, mirror: str | Path, inbox: str | Path,
                    reports: str | Path, state_dir: str | Path, trust_sources: TrustSources,
                    identity_provider: Any, now: Any, *, git_token: Any = None) -> list[dict[str, Any]]:
    """Advance each open main-targeting PR at most one safely evidenced step."""
    mirror, inbox, reports, state_dir = map(Path, (mirror, inbox, reports, state_dir))
    for path in (inbox, reports, state_dir):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        owner_repo = getattr(github, "repository", None) or os.environ.get("AAO_GITHUB_REPOSITORY")
        if not isinstance(owner_repo, str) or owner_repo.count("/") != 1:
            raise ValueError("GitHub client must identify repository as owner/name")
        pulls = _pulls(github, owner_repo)
        _git(mirror, "fetch", "--prune", git_remote, "+refs/heads/main:refs/remotes/aao/main", token=git_token)
        base = _git(mirror, "rev-parse", "refs/remotes/aao/main")
        # Auditors verify the manifest target_ref inside this mirror. Keep that
        # local branch aligned with the fetched remote tip before creating manifests.
        _git(mirror, "update-ref", "refs/heads/main", base)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        return [{"status": "failed", "reason": str(error)}]

    results: list[dict[str, Any]] = []
    try:
        trust_registry = json.loads(trust_sources.trust_registry.read_text())
        required_publishers = trust_registry.get("required_check_publishers")
        if not isinstance(required_publishers, dict):
            raise TypeError("required check publisher registration missing")
    except (OSError, ValueError, TypeError) as error:
        return [{"status": "failed", "reason": f"required check publisher registration missing: {error}"}]
    for pr in pulls:
        number = pr.get("number")
        head = pr.get("head", {}).get("sha") if isinstance(pr.get("head"), dict) else None
        if not isinstance(number, int) or number <= 0 or not _sha(head):
            results.append({"status": "failed", "reason": "malformed pull request identity"}); continue
        # Base is part of audit identity: authorization for an older main tip
        # must never be reused when main moves.
        key = hashlib.sha256(_canonical([owner_repo, number, head, base])).hexdigest()
        state_path = state_dir / f"{key}.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else {
                "schema": "aao.r1-integrator-state.v1", "id": key, "repo": owner_repo,
                "pr_number": number, "head_sha": head, "base_sha": base, "status": "queued"}
            if state.get("head_sha") != head or state.get("base_sha") != base:
                state = {"schema": "aao.r1-integrator-state.v1", "id": key, "repo": owner_repo,
                         "pr_number": number, "head_sha": head, "base_sha": base, "status": "queued"}
            if state["status"] in ("promoted", "failed"):
                results.append(state); continue
            pr_ref = f"refs/pull/{number}/head"
            _git(mirror, "fetch", git_remote, f"+{pr_ref}:refs/remotes/aao/pr/{number}", token=git_token)
            candidate = _git(mirror, "rev-parse", f"refs/remotes/aao/pr/{number}")
            if candidate != head:
                raise ValueError("fetched pull request head differs from observed API head")
            manifest = {"schema": "aao.candidate-manifest.v1", "repository": str(mirror.resolve()),
                        "target_ref": "refs/heads/main", "target_sha": base,
                        "candidate_sha": candidate,
                        "candidate_tree": _git(mirror, "rev-parse", f"{candidate}^{{tree}}"),
                        "result_tree": _git(mirror, "merge-tree", "--write-tree", base, candidate).splitlines()[0],
                        "producer": "aao-integrator:r1-pipeline"}
            report_dir = reports / key
            auth_path = report_dir / "authorization.json"
            sig_path = report_dir / "authorization.sig"
            verdict_path = report_dir / "audit" / "report.json"
            if auth_path.is_file() != sig_path.is_file():
                raise ValueError("authorization document/signature pair is incomplete")
            if verdict_path.is_file() and not auth_path.is_file():
                verdict = json.loads(verdict_path.read_text())
                if verdict.get("verdict") != "approve":
                    state.update(status="failed", reason=f"audit verdict: {verdict.get('verdict', 'unknown')}")
                    _atomic_json(state_path, state); results.append(state); continue
            if not auth_path.is_file() or not sig_path.is_file():
                request = {"schema": "aao.audit-request.v1", "type": "audit", "repo": owner_repo,
                           "pr_number": number, "manifest": manifest}
                _atomic_json(inbox / f"{key}.json", request, mode=0o644)
                state.update(status="queued", audit_request=key)
                _atomic_json(state_path, state); results.append(state); continue
            auth = json.loads(auth_path.read_text())
            state.update(status="audited", authorization_sha256=hashlib.sha256(auth_path.read_bytes()).hexdigest())
            _atomic_json(state_path, state)
            staged = state.get("staged_commit")
            if not staged:
                staged = subprocess.run(["git", "-C", str(mirror), "commit-tree", manifest["result_tree"],
                                         "-p", base, "-p", candidate], input="R1 staged merge\n",
                                        check=True, capture_output=True, text=True,
                                        env={**os.environ,
                                             "GIT_AUTHOR_NAME": "aao-integrator",
                                             "GIT_AUTHOR_EMAIL": "aao-integrator@users.noreply.github.com",
                                             "GIT_COMMITTER_NAME": "aao-integrator",
                                             "GIT_COMMITTER_EMAIL": "aao-integrator@users.noreply.github.com"}).stdout.strip()
                staged_ref = f"refs/heads/aao-staging/{number}-{staged}"
                _git(mirror, "push", git_remote, f"{staged}:{staged_ref}", token=git_token)
                state.update(status="staged", staged_commit=staged, staged_ref=staged_ref)
            gate_id = hashlib.sha256(_canonical([key, "gate", staged])).hexdigest()
            gate_path = reports / gate_id / "gate.json"
            if not gate_path.is_file():
                _atomic_json(inbox / f"{gate_id}.json", {"schema": "aao.audit-request.v1", "type": "gate",
                            "id": key, "promoted_sha": staged, "repo": owner_repo, "pr_number": number}, mode=0o644)
                _atomic_json(state_path, state); results.append(state); continue
            gate = json.loads(gate_path.read_text())
            if gate.get("conformant") is not True:
                raise ValueError("auditor gate is non-conformant")
            state.update(status="gated", gate_id=gate_id)
            _atomic_json(state_path, state)
            check_results = [_check_passed(github, owner_repo, staged, name, required_publishers)
                             for name in ("test", "aao-audit")]
            failed_check = next((reason for passed, reason in check_results if not passed), None)
            if failed_check:
                state.update(status="gated", reason=failed_check)
                _atomic_json(state_path, state); results.append(state); continue
            signature = sig_path.read_text(encoding="ascii").strip()
            clock = now if callable(now) else lambda: now
            promoted = promote(mirror, git_remote, auth, signature, trust_sources,
                               identity_provider=identity_provider, observed_repo=owner_repo,
                               observed_pr_number=number, staged_commit=staged,
                               ci_verified_sha=staged,
                               candidate_ref=f"refs/pull/{number}/head", now=clock, git_token=git_token)
            state.update(status="promoted", promoted_sha=promoted)
        except (OSError, ValueError, TypeError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
            moved = isinstance(error, RuntimeError) and str(error) == "remote base moved"
            if (isinstance(error, RuntimeError)
                    and str(error).startswith("conditional push rejected; no fallback:")):
                try:
                    latest = subprocess.run(["git", "-C", str(mirror), "ls-remote", git_remote,
                                             "refs/heads/main"], check=True, capture_output=True,
                                            text=True).stdout.split()
                    moved = bool(latest and latest[0] != base)
                except (OSError, subprocess.SubprocessError):
                    moved = False
            if moved:
                state.update(status="queued", reason="remote base moved during promotion; re-audit new base")
            else:
                state.update(status="failed", reason=f"{type(error).__name__}: {error}")
        _atomic_json(state_path, state)
        results.append(state)
    return results
