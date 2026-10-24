"""Run one bounded P2/P3 GitHub trial and write a redacted evidence record."""

from __future__ import annotations

import argparse
import base64
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .github_app_auth import ROLE_NAMES, GitHubAppClient, GitHubAuthError, linux_user

NOT_RUN = {
    "A-08": "Runner-side: run_trial.sh triggers the installed supervisor attribution unit and reads attribution.json as root.",
    "A-11": "Runner-side: run_trial.sh runs FORK-BRANCH (implementer), A-11 (aao-pm) via aao.fork_pr_trial.",
    "P3-10": "Runner-side: run_trial.sh runs P3-10 (aao-supervisor) via aao.fork_pr_trial.",
    "P3-11": "Runner-side: run_trial.sh disables/restores ruleset A with the CEO login and checks the supervisor alert.",
}

EXPECTED_PERMISSIONS = {
    "aao-integrator": {"contents": "write", "pull_requests": "write", "checks": "read", "statuses": "read", "metadata": "read"},
    "aao-auditor": {"contents": "read", "pull_requests": "read", "checks": "write", "statuses": "write", "metadata": "read"},
    "aao-auditor-alt": {"contents": "read", "pull_requests": "read", "checks": "write", "statuses": "write", "metadata": "read"},
    "aao-supervisor": {"contents": "read", "pull_requests": "read", "checks": "read", "actions": "read", "metadata": "read"},
    "aao-notifier": {"issues": "write", "metadata": "read"},
    "aao-pm": {"issues": "write", "pull_requests": "write", "contents": "read", "metadata": "read"},
    # Implementer app defaults describe the manifest, but A-10 rejects installing
    # these Apps on the canonical repository. Their fork installation is narrower.
    "aao-impl-codex": {"contents": "write", "pull_requests": "write", "workflows": "write", "metadata": "read"},
    "aao-impl-claude": {"contents": "write", "pull_requests": "write", "workflows": "write", "metadata": "read"},
    "aao-impl-agy": {"contents": "write", "pull_requests": "write", "workflows": "write", "metadata": "read"},
    "aao-probe-noworkflows": {"contents": "write", "metadata": "read"},
}
FORK_PERMISSIONS = {
    "aao-auditor": {"contents": "read", "metadata": "read"},
    "aao-auditor-alt": {"contents": "read", "metadata": "read"},
    "aao-impl-codex": {"contents": "write", "workflows": "write", "metadata": "read"},
    "aao-impl-claude": {"contents": "write", "workflows": "write", "metadata": "read"},
    "aao-impl-agy": {"contents": "write", "workflows": "write", "metadata": "read"},
}
CANONICAL_REPO = "autoaiorg/aao"
REQUIRED_CHECKS = ("aao-audit", "test")
CHECK_WAIT_SECONDS = 300
CHECK_POLL_SECONDS = 5


def validate_role_uid(role: str) -> None:
    if role == "ceo":
        try:
            expected = pwd.getpwnam("alessbarb").pw_uid
        except KeyError as exc:
            raise GitHubAuthError("CEO account alessbarb does not exist") from exc
        if expected != os.getuid():
            raise GitHubAuthError(f"uid {os.getuid()} does not match CEO uid {expected}")
        return
    if role not in ROLE_NAMES:
        raise GitHubAuthError("unknown app role")
    try:
        expected = pwd.getpwnam(linux_user(role)).pw_uid
    except KeyError as exc:
        raise GitHubAuthError(f"role account {role} does not exist") from exc
    if expected != os.getuid():
        raise GitHubAuthError(f"uid {os.getuid()} does not match role {role} uid {expected}")


def validate_ceo_gh_identity(repo: str) -> None:
    """Require the gh CLI token to identify the CEO and be admin on this trial repo."""
    user = subprocess.run(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"], check=True, capture_output=True,
                          text=True, timeout=10, stdin=subprocess.DEVNULL).stdout.strip()
    if user.lower() != "alessbarb":
        raise GitHubAuthError("gh authenticated user is not alessbarb")
    admin = subprocess.run(["gh", "api", "--hostname", "github.com", f"repos/{repo}", "--jq", ".permissions.admin"], check=True,
                          capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL).stdout.strip()
    if admin.lower() != "true":
        raise GitHubAuthError("CEO GitHub account lacks admin permission on the trial repository")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if re.search(r"token|authorization|private.?key", k, re.IGNORECASE) else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _api(client: GitHubAppClient, method: str, path: str, body: dict | None = None) -> dict:
    response = client.request(method, path, body=body)
    return {"method": method, "path": path, "body": body, "status": response.status, "response": _redact(response.body)}


def _git_push(client: GitHubAppClient, repo: str, refspec: str, *, force_with_lease: str | None = None, force: bool = False, no_verify: bool = False) -> dict:
    """Use HTTPS auth only in process environment; never put token in URL or output."""
    token = client._installation_token
    if not token:
        raise GitHubAuthError("installation token missing")
    credential = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    config = [("http.extraheader", f"AUTHORIZATION: basic {credential}")]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GIT_TRACE", "GIT_CURL_VERBOSE")):
            env.pop(key, None)
    env["GIT_TRACE_REDACT"] = "1"
    try:
        existing_count = int(env.get("GIT_CONFIG_COUNT", "0"))
        if existing_count < 0:
            existing_count = 0
    except ValueError:
        existing_count = 0
    env["GIT_CONFIG_COUNT"] = str(existing_count + len(config))
    for offset, (key, value) in enumerate(config):
        i = existing_count + offset
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    remote = f"https://github.com/{repo}.git"
    args = ["git", "-c", "credential.helper=", "push"]
    if force_with_lease is not None:
        args.append(f"--force-with-lease=refs/heads/main:{force_with_lease}")
    elif force:
        args.append("--force")
    if no_verify:
        args.append("--no-verify")
    args.extend([remote, refspec])
    try:
        result = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"method": "git push", "remote": remote, "refspec": refspec, "status": None, "response": type(exc).__name__}
    stderr = result.stderr.decode("utf-8", errors="replace")[:4000]
    stderr = re.sub(r"(Authorization:\s*(?:Basic|Bearer)\s+)\S+", r"\1[REDACTED]", stderr, flags=re.IGNORECASE)
    stderr = stderr.replace(token, "[REDACTED]")
    # Client-side [rejected] (non-fast-forward/stale info) is never evidence
    # that GitHub's receive-pack/ruleset rejected an update.
    server_rejected = _is_server_rejection(stderr)
    return {"method": "git push", "remote": remote, "refspec": refspec,
            "exit_code": result.returncode, "status": 0 if result.returncode == 0 else 1,
            "server_rejected": server_rejected, "response": stderr}


def _is_server_rejection(stderr: str) -> bool:
    """Distinguish receive-pack rejection from client-side push negotiation."""
    return bool(re.search(
        r"(?:^|\n)[^\n]*\[remote rejected\].*(?:\(|:)|"
        r"(?:^|\n)remote:.*(?:protected branch|permission to .* denied|"
        r"not permitted|GH\d+:|workflow|non-fast-forward|ruleset)",
        stderr, re.IGNORECASE,
    ))


def _trial_repo_allowed(owner: str, repo: str) -> bool:
    target = f"{owner}/{repo}".lower()
    if target == CANONICAL_REPO:
        return False
    allowed = {item.strip().lower() for item in os.environ.get("AAO_GITHUB_TRIAL_REPOS", "").split(",") if item.strip()}
    return bool(allowed) and target in allowed


def _main_sha(client: GitHubAppClient, base: str, evidence: list[dict]) -> str | None:
    record = _api(client, "GET", f"{base}/git/ref/heads/main")
    evidence.append(record)
    if record["status"] != 200 or not isinstance(record["response"], dict):
        return None
    return record["response"].get("object", {}).get("sha")


def _verify_unchanged(client: GitHubAppClient, base: str, before: str, evidence: list[dict]) -> bool:
    after = _main_sha(client, base, evidence)
    return bool(after and after == before)


def _ref_sha(client: GitHubAppClient, base: str, ref: str, evidence: list[dict]) -> tuple[int, str | None]:
    record = _api(client, "GET", f"{base}/git/ref/heads/{ref}")
    evidence.append(record)
    if record["status"] == 404:
        return 404, None
    if record["status"] != 200 or not isinstance(record["response"], dict):
        return record["status"], None
    return 200, record["response"].get("object", {}).get("sha")


def _ref_unchanged(client: GitHubAppClient, base: str, ref: str, before_status: int,
                   before_sha: str | None, evidence: list[dict]) -> bool:
    after_status, after_sha = _ref_sha(client, base, ref, evidence)
    return (after_status, after_sha) == (before_status, before_sha)


def _is_ancestor(ancestor: str, descendant: str) -> bool | None:
    try:
        result = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                                capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0 if result.returncode in (0, 1) else None


def _push_rejection_pass(item: dict, unchanged: bool, expected: str = "protected branch") -> bool:
    response = item.get("response", "").lower()
    reason_matches = expected.lower() in response or (
        expected == "protected branch" and (
            ("permission to " in response and " denied" in response)
            or "ruleset" in response or "gh013:" in response
        )
    )
    return item.get("exit_code", 0) != 0 and item.get("server_rejected") is True and reason_matches and unchanged


_REQUIRED_CHECKS_EXPECTED = re.compile(
    r"\d+ of \d+ required status checks? (?:is|are) expected|required status check \"[^\"]+\" is expected")


def _rejection_attributable(item: dict, rule: str) -> bool:
    """Require the server's own text for the rule under test, not generic GH013.

    Restrict updates: its bullet ("Cannot update this protected ref") comes only from ruleset A (B and C have no
    update rule), so it proves the actor has no bypass on A even when other rules are also listed (P3-01/P3-09
    claim exactly that). Non-fast-forward and deletion must be the sole cause (checks green first)."""
    response = item.get("response", "").lower()
    checks = _REQUIRED_CHECKS_EXPECTED.search(response) is not None
    if rule == "restrict updates":
        return "cannot update this protected ref" in response
    if rule in {"required status checks", "required status check", "required_status_check", "required check"}:
        return checks
    if rule == "non-fast-forward":
        return any(text in response for text in ("cannot force-push", "non-fast-forward", "non_fast_forward")) and not checks
    if rule == "deletion":
        return "cannot delete" in response and not checks
    if re.search(r"required (?:status )?checks?|status checks?|aao-audit|\btest\b", response):
        return False
    return rule.lower() in response


def _violated_rules(text: str) -> list[str]:
    """Every rule bullet GitHub listed (GH013 '- ...' lines, or the 422 message body), for the evidence reason."""
    lines = [re.sub(r"^remote:\s*", "", line).strip() for line in str(text).splitlines()]
    return [line[2:].strip() for line in lines if line.startswith("- ")] or [l for l in lines if "expected" in l.lower()]


def _denial_outcome(item: dict, unchanged: bool, rule: str, label: str) -> tuple[str, str]:
    if item.get("exit_code", 0) == 0 or not unchanged:
        return "FAIL", f"{label} was accepted or changed the protected ref"
    if item.get("server_rejected") is not True:
        return "FAIL", f"{label} did not receive a server-side rejection"
    if not _rejection_attributable(item, rule):
        return "INCONCLUSIVE", f"server rejection was not attributable to {rule}"
    return "PASS", f"server rejected {label} for {rule}; protected ref unchanged; rules listed by GitHub: {_violated_rules(item.get('response', ''))}"


def _merge_trial_pr(client: GitHubAppClient, base: str, evidence: list[dict]) -> tuple[str, str, list[dict]]:
    if base.lower() == f"/repos/{CANONICAL_REPO}":
        return "NOT RUN", "refusing to promote on the canonical repository; use the disposable trial", evidence
    pull_list = _api(client, "GET", f"{base}/pulls?state=open&per_page=100")
    evidence.append(pull_list)
    authorized_number = os.environ.get("AAO_GITHUB_TRIAL_PR")
    authorized_head = os.environ.get("AAO_GITHUB_TRIAL_PR_HEAD", "")
    if not authorized_number or not authorized_number.isdigit() or not re.fullmatch(r"[0-9a-f]{40,64}", authorized_head):
        return "NOT RUN", "Set AAO_GITHUB_TRIAL_PR and AAO_GITHUB_TRIAL_PR_HEAD to the explicitly authorized disposable PR and exact head SHA.", evidence
    if pull_list["status"] != 200 or not pull_list["response"]:
        return "NOT RUN", "Create an open trial PR with the exact authorized commit and required checks, then rerun.", evidence
    matches = [item for item in pull_list["response"] if item.get("number") == int(authorized_number)]
    if not matches:
        return "NOT RUN", "The authorized disposable PR is not among open trial PRs.", evidence
    pr = matches[0]
    number = pr.get("number")
    candidate = pr.get("head", {}).get("sha")
    if not isinstance(number, int) or not candidate:
        return "FAIL", "trial PR response lacks number or head SHA", evidence
    if candidate != authorized_head:
        return "FAIL", "authorized trial PR head SHA does not match AAO_GITHUB_TRIAL_PR_HEAD", evidence
    detail = _api(client, "GET", f"{base}/pulls/{number}")
    evidence.append(detail)
    if detail["status"] != 200 or not isinstance(detail["response"], dict):
        return "FAIL", "could not read trial PR details", evidence
    pr = detail["response"]
    candidate = pr.get("head", {}).get("sha")
    base_branch = pr.get("base", {}).get("ref")
    if not candidate or base_branch != "main":
        return "FAIL", "trial PR must have a head SHA and target main", evidence
    base_ref = _api(client, "GET", f"{base}/git/ref/heads/main")
    evidence.append(base_ref)
    base_sha = base_ref.get("response", {}).get("object", {}).get("sha") if isinstance(base_ref.get("response"), dict) else None
    if base_ref["status"] != 200 or not base_sha:
        return "FAIL", "could not read main base SHA", evidence

    # Resolve the auditor App's canonical ID, then require that exact source for aao-audit.
    auditor = _api(client, "GET", "/apps/aao-auditor")
    evidence.append(auditor)
    auditor_id = auditor.get("response", {}).get("id") if isinstance(auditor.get("response"), dict) else None
    auditor_owner = auditor.get("response", {}).get("owner", {}).get("login", "").lower() if isinstance(auditor.get("response"), dict) else ""
    expected_owner = CANONICAL_REPO.split("/", 1)[0].lower()
    if auditor["status"] != 200 or not isinstance(auditor_id, int) or auditor_owner != expected_owner:
        return "FAIL", "could not resolve aao-auditor App id", evidence

    phase = os.environ.get("AAO_GITHUB_TRIAL_PHASE", "")
    if phase not in {"stage", "promote"}:
        return "NOT RUN", "Set AAO_GITHUB_TRIAL_PHASE=stage, then run phase=promote with AAO_GITHUB_TRIAL_PROMOTE_SHA after audit publication.", evidence
    if phase == "stage":
        try:
            tree = subprocess.run(["git", "merge-tree", "--write-tree", base_sha, candidate], check=True,
                                  capture_output=True, text=True, timeout=60).stdout.splitlines()[0].strip()
            merge_sha = subprocess.run(["git", "-c", "user.name=AAO Integrator", "-c",
                                        "user.email=aao-integrator@users.noreply.github.com", "commit-tree",
                                        tree, "-p", base_sha, "-p", candidate], input="AAO trial staged merge\n",
                                       check=True, capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            evidence.append({"method": "git merge-tree/commit-tree", "status": "error", "response": type(exc).__name__})
            return "FAIL", "could not construct local merge commit", evidence
        evidence.append({"method": "git merge-tree --write-tree + git commit-tree", "tree": tree,
                         "parents": [base_sha, candidate], "sha": merge_sha})
        if not re.fullmatch(r"[0-9a-f]{40,64}", tree) or not re.fullmatch(r"[0-9a-f]{40,64}", merge_sha):
            return "FAIL", "local merge tree or commit returned an invalid object id", evidence
    else:
        merge_sha = os.environ.get("AAO_GITHUB_TRIAL_PROMOTE_SHA", "")
        if not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
            return "FAIL", "promote phase requires AAO_GITHUB_TRIAL_PROMOTE_SHA with the staged full SHA", evidence
        commit_record = _api(client, "GET", f"{base}/git/commits/{merge_sha}")
        evidence.append(commit_record)
        data = commit_record.get("response", {}) if isinstance(commit_record.get("response"), dict) else {}
        parents = [item.get("sha") for item in data.get("parents", [])]
        tree = data.get("tree", {}).get("sha")
        if commit_record["status"] != 200 or parents != [base_sha, candidate] or not re.fullmatch(r"[0-9a-f]{40}", str(tree)):
            return "FAIL", "supplied promotion SHA is not a merge of the current main and authorized PR head", evidence
    # B requires checks on aao-staging/**; seed the workflow on an unprotected
    # trial ref first, then move the same checked commit into staging.
    candidate_ref = f"refs/heads/aao-trial/merge-{number}-{candidate[:8]}"
    staging = f"refs/heads/aao-staging/{number}-{candidate[:8]}"
    if phase == "stage":
        push = _git_push(client, f"{owner_repo(base)}", f"{merge_sha}:{candidate_ref}")
        evidence.append(push)
        if push["status"] != 0:
            return "FAIL", "integrator could not push merge commit to the unprotected trial candidate ref", evidence
    else:
        staged_status, staged_sha = _ref_sha(client, base, candidate_ref.removeprefix("refs/heads/"), evidence)
        if staged_status != 200 or staged_sha != merge_sha:
            return "FAIL", "supplied promotion SHA does not match the authorized trial candidate ref", evidence
    if phase == "stage":
        evidence.append({"method": "staged merge commit", "sha": merge_sha, "ref": candidate_ref})
        return "STAGED", f"merge commit staged at {merge_sha} on {candidate_ref}; publish aao-audit, then rerun with phase=promote and this SHA", evidence

    deadline = time.monotonic() + CHECK_WAIT_SECONDS
    checks_ok = False
    while time.monotonic() < deadline:
        checks = _api(client, "GET", f"{base}/commits/{merge_sha}/check-runs?per_page=100")
        evidence.append(checks)
        runs = checks.get("response", {}).get("check_runs", []) if isinstance(checks.get("response"), dict) else []
        selected = {}
        for run in runs:
            name = run.get("name")
            if name == "aao-audit" and run.get("app", {}).get("id") != auditor_id:
                return "FAIL", f"aao-audit check came from app_id {run.get('app', {}).get('id')}, expected {auditor_id}", evidence
            if name in ("aao-audit", "test"):
                selected[name] = run
        if checks["status"] != 200:
            return "FAIL", f"check-runs query returned HTTP {checks['status']}", evidence
        if all(name in selected and selected[name].get("status") == "completed" and selected[name].get("conclusion") == "success" for name in ("aao-audit", "test")):
            checks_ok = True
            break
        time.sleep(min(CHECK_POLL_SECONDS, max(0, deadline - time.monotonic())))
    if not checks_ok:
        return "FAIL", f"required checks did not become green within {CHECK_WAIT_SECONDS}s", evidence
    evidence.append({"method": "required checks", "sha": merge_sha, "status": "green",
                     "checks": list(REQUIRED_CHECKS), "auditor_app_id": auditor_id})

    # Only now introduce the checked commit into ruleset B's staging namespace.
    push = _git_push(client, owner_repo(base), f"{merge_sha}:{staging}")
    evidence.append(push)
    if push.get("status") != 0:
        return "FAIL", "required checks were green but protected aao-staging update failed", evidence
    staged_status, staged_sha = _ref_sha(client, base, staging.removeprefix("refs/heads/"), evidence)
    if staged_status != 200 or staged_sha != merge_sha:
        return "FAIL", "protected aao-staging ref does not match the checked merge commit", evidence

    repository = _api(client, "GET", base)
    evidence.append(repository)
    repository_id = repository.get("response", {}).get("node_id") if isinstance(repository.get("response"), dict) else None
    if repository["status"] != 200 or not repository_id:
        return "FAIL", "could not resolve repository node id for updateRefs", evidence
    query = {"query": "mutation($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }",
             "variables": {"input": {"repositoryId": repository_id, "refUpdates": [{"name": "refs/heads/main", "oid": merge_sha,
                                                        "beforeOid": base_sha}]}}}
    update = _api(client, "POST", "/graphql", query)
    evidence.append(update)
    errors = update["status"] >= 400 or (isinstance(update["response"], dict) and bool(update["response"].get("errors")))
    if errors:
        return "FAIL", "GraphQL updateRefs promotion failed", evidence
    main_after = _api(client, "GET", f"{base}/git/ref/heads/main")
    commit_after = _api(client, "GET", f"{base}/git/commits/{merge_sha}")
    pr_after = _api(client, "GET", f"{base}/pulls/{number}")
    evidence.extend([main_after, commit_after, pr_after])
    actual_main = main_after.get("response", {}).get("object", {}).get("sha") if isinstance(main_after.get("response"), dict) else None
    commit = commit_after.get("response", {})
    parents = [item.get("sha") for item in commit.get("parents", [])] if isinstance(commit, dict) else []
    actual_tree = commit.get("tree", {}).get("sha") if isinstance(commit, dict) else None
    merged = isinstance(pr_after.get("response"), dict) and pr_after["response"].get("merged") is True
    if actual_main == merge_sha and actual_tree == tree and parents == [base_sha, candidate] and merged:
        return "PASS", f"main promoted to verified merge commit {merge_sha}; PR {number} is merged", evidence
    return "FAIL", "promotion verification failed: main, tree, parents, or PR merged state differs", evidence


def _local_head() -> str | None:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD^{commit}"], check=True, capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _wait_wrong_publisher(client: GitHubAppClient, base: str, sha: str, evidence: list[dict]) -> tuple[bool, str]:
    """P3-04 precondition: `test` green and every `aao-audit` run on sha published by an App other than aao-auditor."""
    app = _api(client, "GET", "/apps/aao-auditor")
    evidence.append(app)
    auditor_id = app.get("response", {}).get("id") if isinstance(app.get("response"), dict) else None
    if app["status"] != 200 or not isinstance(auditor_id, int):
        return False, "could not establish the aao-auditor App identity"
    deadline = time.monotonic() + CHECK_WAIT_SECONDS
    while True:
        result = _api(client, "GET", f"{base}/commits/{sha}/check-runs?per_page=100")
        evidence.append(result)
        runs = result.get("response", {}).get("check_runs", []) if isinstance(result.get("response"), dict) else []
        audits = [r for r in runs if r.get("name") == "aao-audit"]
        tests = [r for r in runs if r.get("name") == "test"]
        if any(r.get("app", {}).get("id") == auditor_id for r in audits):
            return False, "an aao-audit run from the real auditor exists on the P3-04 candidate"
        if audits and tests and all(r.get("status") == "completed" and r.get("conclusion") == "success" for r in tests):
            evidence.append({"method": "P3-04 precondition", "sha": sha, "test": "green",
                             "aao_audit_publishers": sorted({r.get("app", {}).get("id") for r in audits})})
            return True, "ready"
        if time.monotonic() >= deadline:
            return False, f"P3-04 precondition (test green + wrong-publisher aao-audit) not met within {CHECK_WAIT_SECONDS}s"
        time.sleep(CHECK_POLL_SECONDS)


def owner_repo(base: str) -> str:
    return base.removeprefix("/repos/")


def _wait_required_checks(client: GitHubAppClient, base: str, sha: str,
                          evidence: list[dict]) -> tuple[bool, str]:
    app = _api(client, "GET", "/apps/aao-auditor")
    evidence.append(app)
    app_id = app.get("response", {}).get("id") if isinstance(app.get("response"), dict) else None
    owner = app.get("response", {}).get("owner", {}).get("login", "").lower() if isinstance(app.get("response"), dict) else ""
    if app["status"] != 200 or not isinstance(app_id, int) or owner != CANONICAL_REPO.split("/", 1)[0].lower():
        return False, "could not establish canonical aao-auditor App identity"
    deadline = time.monotonic() + CHECK_WAIT_SECONDS
    while time.monotonic() < deadline:
        result = _api(client, "GET", f"{base}/commits/{sha}/check-runs?per_page=100")
        evidence.append(result)
        if result["status"] != 200:
            return False, f"required-check query returned HTTP {result['status']}"
        runs = result.get("response", {}).get("check_runs", []) if isinstance(result.get("response"), dict) else []
        selected = {}
        for run in runs:
            if run.get("name") in REQUIRED_CHECKS:
                name = run["name"]
                if name == "aao-audit" and run.get("app", {}).get("id") != app_id:
                    return False, f"aao-audit check came from app_id {run.get('app', {}).get('id')}, expected {app_id}"
                selected[name] = run
        if all(name in selected and selected[name].get("status") == "completed"
               and selected[name].get("conclusion") == "success" for name in REQUIRED_CHECKS):
            evidence.append({"method": "required checks", "sha": sha, "status": "green",
                             "checks": list(REQUIRED_CHECKS), "auditor_app_id": app_id})
            return True, "required checks are green for candidate"
        time.sleep(min(CHECK_POLL_SECONDS, max(0, deadline - time.monotonic())))
    evidence.append({"method": "required checks", "sha": sha, "status": "timeout", "checks": list(REQUIRED_CHECKS)})
    return False, f"required checks {', '.join(REQUIRED_CHECKS)} did not become green within {CHECK_WAIT_SECONDS}s"


def _run_equivalence(owner: str, repo: str, role: str, client: GitHubAppClient) -> tuple[str, str, list[dict]]:
    evidence: list[dict] = []
    allowed_roles = {"aao-impl-claude", "aao-impl-codex", "aao-impl-agy"}
    if role not in allowed_roles:
        return "NOT RUN", "equivalence evidence is restricted to implementer Apps", evidence
    target = f"{owner}/{repo}".lower()
    if target != "autoaiorg/aao-governance-trial" or target == CANONICAL_REPO:
        return "NOT RUN", "equivalence mode is restricted to autoaiorg/aao-governance-trial", evidence
    try:
        target_identity = json.loads(os.environ.get("AAO_TRIAL_P0_EVIDENCE", "{}"))
        p4_evidence = json.loads(os.environ.get("AAO_TRIAL_P4_EVIDENCE", "{}"))
        p4b_evidence = json.loads(os.environ.get("AAO_TRIAL_P4B_EVIDENCE", "{}"))
        expected_repo_id = int(os.environ.get("AAO_TRIAL_EXPECTED_REPO_ID", ""))
    except (ValueError, json.JSONDecodeError):
        target_identity, p4_evidence, p4b_evidence, expected_repo_id = {}, {}, {}, 0
    premises = evaluate_equivalence_premises(target_identity, p4_evidence, p4b_evidence,
                                             expected_repo_id=expected_repo_id)
    evidence.append({"method": "equivalence premises", "premises": premises})
    failed = [item["id"] for item in premises if item["result"] != "PASS"]
    if failed:
        return "FAIL", "equivalence premises failed: " + ", ".join(failed), evidence
    installed = client.app_request("GET", f"/repos/{owner}/{repo}/installation")
    evidence.append({"method": "GET", "path": f"/repos/{owner}/{repo}/installation", "status": installed.status,
                     "response": _redact(installed.body)})
    if installed.status != 404:
        return "FAIL", f"implementer App trial-repository installation lookup returned HTTP {installed.status}, expected 404", evidence
    forks = sorted({item.strip().lower() for item in os.environ.get("AAO_GITHUB_TRIAL_FORKS", "").split(",") if item.strip()})
    if not forks or any("/" not in item for item in forks) or target in forks or CANONICAL_REPO in forks:
        return "FAIL", "AAO_GITHUB_TRIAL_FORKS must list only explicit non-canonical implementer forks", evidence
    fork = os.environ.get("AAO_GITHUB_TRIAL_FORK", "").lower()
    if fork not in forks:
        return "FAIL", "AAO_GITHUB_TRIAL_FORK must name one of AAO_GITHUB_TRIAL_FORKS", evidence
    try:
        client.installation_token(*fork.split("/", 1), repository_names=False)
    except GitHubAuthError as exc:
        evidence.append({"method": "installation token", "status": "error", "response": str(exc)})
        return "FAIL", "could not authenticate against the implementer's configured fork", evidence
    installation = client.app_request("GET", f"/app/installations/{client._installation_id}")
    evidence.append({"method": "GET", "path": f"/app/installations/{client._installation_id}",
                     "status": installation.status, "response": _redact(installation.body)})
    if installation.status != 200 or not isinstance(installation.body, dict) or installation.body.get("repository_selection") != "selected":
        return "FAIL", "installation must have selected repository scope", evidence
    actual_names: list[str] = []
    total_count = None
    page = 1
    while True:
        listing = _api(client, "GET", f"/installation/repositories?per_page=100&page={page}")
        evidence.append(listing)
        body = listing.get("response")
        if listing["status"] != 200 or not isinstance(body, dict) or not isinstance(body.get("total_count"), int) or not isinstance(body.get("repositories"), list):
            return "FAIL", "could not enumerate installation repositories consistently", evidence
        if total_count is None:
            total_count = body["total_count"]
        elif body["total_count"] != total_count:
            return "FAIL", "installation repository total_count changed during pagination", evidence
        actual_names.extend(item["full_name"].lower() for item in body["repositories"]
                            if isinstance(item, dict) and isinstance(item.get("full_name"), str))
        if len(actual_names) == total_count:
            break
        if not body["repositories"] or len(actual_names) > total_count:
            return "FAIL", "installation repository listing inconsistent with total_count", evidence
        page += 1
    actual = sorted(actual_names)
    evidence.append({"method": "repository scope comparison", "expected": forks, "actual": actual,
                     "trial_excluded": target not in actual, "canonical_excluded": CANONICAL_REPO not in actual})
    if actual != forks or target in actual or CANONICAL_REPO in actual:
        return "FAIL", "installation repository scope differs from configured fork set or includes protected repositories", evidence
    revoked = client.revoke()
    evidence.append({"method": "DELETE", "path": "/installation/token",
                     "status": revoked.status if revoked else None})
    if revoked is None or revoked.status != 204:
        return "FAIL", "could not revoke unrestricted scope-audit token", evidence
    try:
        client.installation_token(*fork.split("/", 1))
    except GitHubAuthError as exc:
        evidence.append({"method": "scoped positive-control token", "status": "error", "response": str(exc)})
        return "FAIL", "could not mint fork-scoped positive-control token", evidence
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "FAIL", "positive-control candidate SHA unavailable in local clone", evidence
    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        return "FAIL", "positive-control candidate SHA is malformed", evidence
    ref = f"refs/heads/aao-trial/equivalence-{sha[:12]}"
    push = _git_push(client, fork, f"{sha}:{ref}")
    evidence.append(push)
    if push.get("status") != 0:
        return "FAIL", "positive-control push to own non-protected fork branch failed", evidence
    return "EQUIVALENCE-PENDING", "trial installation absent, configured fork scope exact, positive fork push accepted; CEO formal equivalence validation required before PASS", evidence


def evaluate_equivalence_premises(p0: dict, p4: dict, p4b: dict, *, expected_repo_id: int) -> list[dict]:
    """Evaluate only the newly required P0/P4/P4b premises; missing facts fail closed."""
    expected_name = "autoaiorg/aao-governance-trial"
    p0 = p0 if isinstance(p0, dict) else {}
    p4 = p4 if isinstance(p4, dict) else {}
    p4b = p4b if isinstance(p4b, dict) else {}
    full_name = p0.get("full_name")
    p0_ok = (p0.get("status") == 200 and isinstance(full_name, str) and full_name.lower() == expected_name
             and isinstance(p0.get("id"), int) and p0.get("id") == expected_repo_id and expected_repo_id > 0)
    p4_fields = ("gh_hosts_yml_absent", "git_credentials_absent", "token_environment_absent",
                 "runner_environment_token_absent", "aao_config_exact",
                 "deploy_keys_empty", "outside_collaborators_clear", "org_members_clear")
    p4_ok = all(p4.get(field) is True for field in p4_fields)
    p4b_ok = (p4b.get("ceo_login") == "alessbarb"
              and p4b.get("org_owners") == ["alessbarb"]
              and p4b.get("repo_admins") == ["alessbarb"])
    return [
        {"id": "P0", "result": "PASS" if p0_ok else "FAIL",
         "expected_full_name": expected_name, "expected_id": expected_repo_id,
         "pinned_at_run_start_id": expected_repo_id,
         "observed_status": p0.get("status"), "observed_full_name": p0.get("full_name"),
         "observed_id": p0.get("id")},
        {"id": "P4", "result": "PASS" if p4_ok else "FAIL",
         "checks": {field: p4.get(field) is True for field in p4_fields},
         "uid": p4.get("uid"), "aao_config_names": p4.get("config_names"),
         "systemd_checked": p4.get("systemd_checked"),
         "runner_environment": p4.get("runner_environment"),
         "deploy_keys_by_repository": p4.get("deploy_keys_by_repository"),
         "outside_collaborators": p4.get("outside_collaborators"),
         "org_members": p4.get("org_members")},
        {"id": "P4b", "result": "PASS" if p4b_ok else "FAIL",
         "expected_org_owners": ["alessbarb"], "observed_org_owners": p4b.get("org_owners"),
         "expected_repo_admins": ["alessbarb"], "observed_repo_admins": p4b.get("repo_admins"),
         "expected_ceo_login": "alessbarb", "observed_ceo_login": p4b.get("ceo_login")},
    ]


def _run_test(test_id: str, owner: str, repo: str, role: str, client: GitHubAppClient) -> tuple[str, str, list[dict]]:
    base = f"/repos/{owner}/{repo}"
    evidence: list[dict] = []
    if test_id == "EQUIVALENCE":
        return _run_equivalence(owner, repo, role, client)
    if test_id in {"PUBLISH-AUDIT", "STAGE-COMMIT"} and not _trial_repo_allowed(owner, repo):
        return "NOT RUN", "trial helper is restricted to an explicitly allowlisted non-canonical trial repository", evidence
    if test_id == "PUBLISH-AUDIT":
        if role not in ("aao-auditor", "aao-auditor-alt"):
            return "NOT RUN", "aao-audit publication requires aao-auditor (or aao-auditor-alt for the P3-04 wrong-publisher fixture)", evidence
        sha = os.environ.get("AAO_GITHUB_TRIAL_SHA", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return "FAIL", "AAO_GITHUB_TRIAL_SHA must be an explicit full 40-hex commit SHA", evidence
        item = _api(client, "POST", f"{base}/check-runs", {"name": "aao-audit", "head_sha": sha,
                     "status": "completed", "conclusion": "success", "output": {"title": "Trial check evidence", "summary": "Auditor App trial helper; not an independent audit."}})
        evidence.append(item)
        actual_app = item.get("response", {}).get("app", {}).get("id") if isinstance(item.get("response"), dict) else None
        if item["status"] not in (200, 201) or actual_app != client.app_id:
            return "FAIL", "auditor check run rejected or returned a different App identity", evidence
        return "PASS", f"completed aao-audit check published by configured auditor App on explicit trial SHA {sha}", evidence
    if test_id == "STAGE-COMMIT":
        if role != "aao-integrator":
            return "NOT RUN", "explicit commit staging requires role aao-integrator", evidence
        branch = os.environ.get("AAO_GITHUB_TRIAL_BRANCH", "")
        if not re.fullmatch(r"aao-trial/[A-Za-z0-9._/-]{1,90}", branch) or ".." in branch:
            return "FAIL", "AAO_GITHUB_TRIAL_BRANCH must be a safe named aao-trial/* branch", evidence
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD^{commit}"], check=True, capture_output=True,
                                 text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "FAIL", "local commit unavailable for staging", evidence
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return "FAIL", "local commit SHA is malformed", evidence
        expected_sha = os.environ.get("AAO_GITHUB_TRIAL_EXPECTED_SHA", "")
        if expected_sha and (not re.fullmatch(r"[0-9a-f]{40}", expected_sha) or sha != expected_sha):
            return "FAIL", "local staged commit SHA does not match runner candidate", evidence
        item = _git_push(client, f"{owner}/{repo}", f"{sha}:refs/heads/{branch}")
        evidence.append(item)
        if item.get("status") != 0:
            return "FAIL", "integrator could not stage explicit local commit", evidence
        evidence.append({"method": "staged commit", "sha": sha, "branch": branch})
        return "PASS", f"staged local commit {sha} on {branch}", evidence
    if not _trial_repo_allowed(owner, repo):
        return "NOT RUN", "Repository is not explicitly listed in AAO_GITHUB_TRIAL_REPOS or is the canonical repository; no operation performed.", evidence
    implementers = {"aao-impl-codex", "aao-impl-claude", "aao-impl-agy"}
    required_roles = {
        "A-01": implementers, "A-02": implementers, "A-03": {"aao-integrator"},
        "A-04": {"aao-integrator"}, "A-05": {"aao-integrator"}, "A-09": {"aao-notifier"},
        "P3-02": implementers, "P3-03": {"aao-integrator"}, "P3-05": {"aao-integrator"},
        "P3-06": {"aao-integrator"}, "P3-12": {"aao-integrator"},
        "P3-01": {"aao-integrator", "ceo"}, "P3-07": {"aao-integrator"},
        "P3-09": {"ceo"},
        "A-14": {"aao-probe-noworkflows"},
    }
    if test_id in required_roles and role not in required_roles[test_id]:
        names = ", ".join(sorted(required_roles[test_id]))
        role_hint = "an implementer App" if test_id == "A-14" else f"role: {names}"
        return "NOT RUN", f"This test must run with {role_hint}.", evidence
    if test_id in {"A-01", "A-02", "P3-02"} and role in implementers:
        return "FAIL", "this equivalence-sensitive test cannot emit PASS outside explicit equivalence mode", evidence
    if test_id in NOT_RUN:
        return "NOT RUN", NOT_RUN[test_id], evidence
    if test_id == "A-01":
        before = _main_sha(client, base, evidence)
        if not before:
            return "FAIL", "could not read main before push attempt", evidence
        item = _git_push(client, f"{owner}/{repo}", "HEAD:refs/heads/main")
        evidence.append(item)
        unchanged = _verify_unchanged(client, base, before, evidence)
        return ("PASS", "server denied push to protected branch; main unchanged", evidence) if _push_rejection_pass(item, unchanged, "protected branch") else ("FAIL", "push failed for an unproven cause, changed main, or was accepted", evidence)
    if test_id == "A-04":
        ref = _api(client, "GET", f"{base}/git/ref/heads/main")
        evidence.append(ref)
        if ref["status"] != 200 or not isinstance(ref["response"], dict):
            return "FAIL", "could not read main SHA for stale lease trial", evidence
        actual = ref["response"].get("object", {}).get("sha")
        if not actual:
            return "FAIL", "main response has no SHA", evidence
        # First move main to a distinct, real commit, then use its actual prior SHA as the lease.
        try:
            local = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "NOT RUN", "local candidate commit unavailable for stale-lease trial", evidence
        if not re.fullmatch(r"[0-9a-f]{40,64}", local) or local == actual:
            return "NOT RUN", "trial needs a distinct local commit to move main before stale-lease attempt", evidence
        stage = f"refs/heads/aao-trial/stale-lease-{local[:8]}"
        staged = _git_push(client, f"{owner}/{repo}", f"{local}:{stage}")
        evidence.append(staged)
        if staged.get("exit_code") != 0:
            return "FAIL", "could not stage the distinct candidate commit", evidence
        checks_ok, checks_reason = _wait_required_checks(client, base, local, evidence)
        if not checks_ok:
            return "FAIL", f"cannot move main before stale-lease test: {checks_reason}", evidence
        repository = _api(client, "GET", base)
        evidence.append(repository)
        repository_id = repository.get("response", {}).get("node_id") if isinstance(repository.get("response"), dict) else None
        if repository["status"] != 200 or not repository_id:
            return "FAIL", "could not resolve repository node id for updateRefs", evidence
        moved = _api(client, "POST", "/graphql", {"query": "mutation($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }", "variables": {"input": {"repositoryId": repository_id, "refUpdates": [{"name": "refs/heads/main", "oid": local, "beforeOid": actual}]}}})
        evidence.append(moved)
        moved_ok = moved["status"] == 200 and isinstance(moved["response"], dict) and not moved["response"].get("errors")
        if not moved_ok or _main_sha(client, base, evidence) != local:
            return "FAIL", "could not move main to distinct candidate before stale lease", evidence
        item = _git_push(client, f"{owner}/{repo}", f"{actual}:refs/heads/main", force_with_lease=actual)
        evidence.append(item)
        unchanged = _verify_unchanged(client, base, local, evidence)
        response = item.get("response", "").lower()
        # Git's force-with-lease stale-info check is client-side; this cannot prove a
        # receive-pack denial. A-03/P3-05 provide server-side protected-ref CAS evidence.
        evidence.append({"method": "A-04 limitation", "client_response": response,
                         "server_side_demonstrated": False, "related_server_test": "A-03/P3-05",
                         "main_unchanged": unchanged})
        return "NOT RUN", "Git client stale-info rejection does not demonstrate a server-side denial; see A-03/P3-05", evidence
    if test_id == "A-09":
        item = _api(client, "POST", f"{base}/issues", {"title": "AAO P2/P3 trial notification", "body": "Disposable trial harness check."})
        evidence.append(item)
        if item["status"] not in (200, 201):
            return "FAIL", f"issue creation returned HTTP {item['status']}", evidence
        before = _main_sha(client, base, evidence)
        if not before:
            return "FAIL", "issue created but could not read main before push", evidence
        push = _git_push(client, f"{owner}/{repo}", "HEAD:refs/heads/main")
        evidence.append(push)
        unchanged = _verify_unchanged(client, base, before, evidence)
        return ("PASS", "issue created; server denied protected-branch push; main unchanged", evidence) if _push_rejection_pass(push, unchanged) else ("FAIL", "issue created but push failure cause or remote state did not match", evidence)
    if test_id == "A-10":
        target = _api(client, "GET", base)
        evidence.append(target)
        if target["status"] != 200 or not isinstance(target["response"], dict):
            return "INCONCLUSIVE", "could not identify whether the trial repository is the configured canonical repo or its fork", evidence
        repo_info = target["response"]
        is_fork = repo_info.get("fork") is True
        parent = repo_info.get("parent", {}).get("full_name", "").lower() if isinstance(repo_info.get("parent"), dict) else ""
        expected_parent = os.environ.get("AAO_GITHUB_TRIAL_FORK_PARENT", "").lower()
        target_repo = f"{owner}/{repo}".lower()
        is_configured_canonical = bool(expected_parent) and target_repo == expected_parent
        is_trial_fork = is_fork and bool(expected_parent) and parent == expected_parent and not is_configured_canonical
        if is_fork and not (is_trial_fork or is_configured_canonical):
            return "INCONCLUSIVE", "target is a fork but its configured canonical parent was not established", evidence
        if role in {"aao-impl-codex", "aao-impl-claude", "aao-impl-agy"} and not is_trial_fork:
            return "FAIL", "implementer App is installed on the trial canonical repository; it must be installed only on its verified fork", evidence
        item = client.app_request("GET", f"/repos/{owner}/{repo}/installation")
        evidence.append({"method": "GET", "path": f"/repos/{owner}/{repo}/installation",
                         "status": item.status, "response": _redact(item.body)})
        if item.status != 200:
            return "INCONCLUSIVE", f"App installation lookup returned HTTP {item.status}; permissions could not be verified", evidence
        actual = item.body.get("permissions", {}) if isinstance(item.body, dict) else {}
        expected_table = FORK_PERMISSIONS if is_trial_fork else EXPECTED_PERMISSIONS
        if role not in expected_table:
            return "NOT RUN", "this App has no permission column for the verified repository class in P2 §4", evidence
        expected = expected_table[role]
        clean = {k: v for k, v in actual.items() if v not in (None, "none")}
        return ("PASS", "installation permissions match role manifest", evidence) if clean == expected else ("FAIL", f"installation permissions differ from expected table: expected {expected}, got {clean}", evidence)
    if test_id == "A-12":
        item = client.revoke()
        evidence.append({"method": "DELETE", "path": "/installation/token", "body": None,
                         "status": item.status if item else None, "response": _redact(item.body) if item else None})
        return ("NOT RUN", "current token revocation was exercised; full A-12 still requires deleting this App key or suspending its installation, then proving new token issuance fails", evidence) if item and item.status in (200, 204) else ("FAIL", "installation token revocation failed", evidence)
    if test_id == "A-13" and os.environ.get("AAO_TRIAL_A13_WAIT") == "1":
        # Long-running: the runner starts this detached (systemd-run) and collects it later. The token minted
        # by main() is kept only in this process' memory, used once after it has expired, and never written.
        minted = time.time()
        wait = int(os.environ.get("AAO_TRIAL_A13_SECONDS", "3720"))
        evidence.append({"method": "installation token minted", "minted_at": datetime.fromtimestamp(minted, UTC).isoformat(),
                         "use_after_seconds": wait})
        time.sleep(max(0, minted + wait - time.time()))
        item = _api(client, "GET", base)
        evidence.append(item)
        if item["status"] == 401:
            return "PASS", f"installation token used {wait}s after minting was rejected with HTTP 401", evidence
        return "FAIL", f"expired installation token returned HTTP {item['status']}, expected 401", evidence
    if test_id == "A-13":
        return "NOT RUN", "Manual expiry step: use an installation token after its expires_at time (or revoke it), then verify GitHub returns HTTP 401; harness cannot wait an hour within one-test invocation.", evidence
    if test_id == "A-14":
        if role != "aao-probe-noworkflows" or f"{owner}/{repo}".lower() == CANONICAL_REPO:
            return "NOT RUN", "A-14 requires the dedicated aao-probe-noworkflows App on its disposable fork.", evidence
        fork_parent = os.environ.get("AAO_GITHUB_TRIAL_FORK_PARENT", "").lower()
        if not fork_parent or fork_parent == CANONICAL_REPO:
            return "NOT RUN", "Set AAO_GITHUB_TRIAL_FORK_PARENT to the explicit disposable trial parent repository.", evidence
        fork_info = _api(client, "GET", base)
        evidence.append(fork_info)
        parent = fork_info.get("response", {}).get("parent", {}).get("full_name", "").lower() if isinstance(fork_info.get("response"), dict) else ""
        if fork_info["status"] != 200 or not isinstance(fork_info["response"], dict) or fork_info["response"].get("fork") is not True or parent != fork_parent:
            return "NOT RUN", "Target is not the explicitly configured disposable fork of the trial repository.", evidence
        try:
            changed = subprocess.run(["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"],
                                     check=True, capture_output=True, text=True, timeout=10).stdout.splitlines()
            parent_sha = subprocess.run(["git", "rev-parse", "HEAD^"], check=True, capture_output=True,
                                        text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "NOT RUN", "Run from a local disposable clone containing a workflow-changing commit with a parent.", evidence
        if not any(path.startswith(".github/workflows/") for path in changed):
            return "NOT RUN", "Prepare a disposable local commit changing .github/workflows/ and rerun; the harness will attempt that commit's push to main.", evidence
        before = _main_sha(client, base, evidence)
        if not before:
            return "FAIL", "could not read fork main before workflow push", evidence
        item = _git_push(client, f"{owner}/{repo}", "HEAD:refs/heads/main")
        evidence.append(item)
        message = item.get("response", "").lower()
        expected = (item.get("exit_code", 0) != 0 and item.get("server_rejected")
                    and re.search(r"workflows?.{0,12}permission", message) is not None)
        unchanged = _verify_unchanged(client, base, before, evidence)
        if not expected or not unchanged:
            return "FAIL", "workflow push was not rejected for missing workflows permission or fork main changed", evidence
        branch = f"refs/heads/aao-trial/no-workflows-{parent_sha[:12]}"
        positive = _git_push(client, f"{owner}/{repo}", f"{parent_sha}:{branch}")
        evidence.append(positive)
        accepted = positive.get("exit_code") == 0 and positive.get("status") == 0
        return ("PASS", "workflow push denied for missing workflows permission; non-workflow control push accepted", evidence) if accepted else ("FAIL", "workflow push denial passed but non-workflow control push was not accepted", evidence)
    if test_id == "A-07":
        # The runner disabled ruleset A first (P3-11). The CEO pushes a fully checked fast-forward to main; the
        # verdict (the supervisor's governance-violation alert) is evaluated by the runner, not here.
        if role != "ceo":
            return "NOT RUN", "A-07 pushes with the CEO identity", evidence
        sha = _local_head()
        before = _main_sha(client, base, evidence)
        if not sha or not before or _is_ancestor(before, sha) is not True:
            return "NOT RUN", "A-07 requires a local fast-forward candidate of main", evidence
        item = _git_push(client, f"{owner}/{repo}", f"{sha}:refs/heads/main", no_verify=True)
        evidence.append(item)
        after = _main_sha(client, base, evidence)
        if item.get("exit_code") == 0 and after == sha:
            return "PUSHED", f"CEO push landed {sha} on main; supervisor detection is checked by the runner", evidence
        return "FAIL", "CEO push did not land on main (ruleset A still enforced?)", evidence
    if test_id == "P3-09":
        if role != "ceo":
            return "NOT RUN", "Run explicitly with --role ceo to test the CEO identity.", evidence
        pulls = _api(client, "GET", f"{base}/pulls?state=open&per_page=100")
        evidence.append(pulls)
        if pulls["status"] != 200 or not pulls["response"]:
            return "NOT RUN", "Create an open disposable PR, then rerun this test.", evidence
        number = pulls["response"][0].get("number")
        if not isinstance(number, int):
            return "FAIL", "open PR response lacks a number", evidence
        item = _api(client, "PUT", f"{base}/pulls/{number}/merge", {"merge_method": "merge"})
        evidence.append(item)
        after = _api(client, "GET", f"{base}/pulls/{number}")
        evidence.append(after)
        message = item.get("response", {}).get("message", "").lower() if isinstance(item.get("response"), dict) else ""
        expected = item["status"] in (403, 405) and _rejection_attributable({"response": message}, "restrict updates")
        unchanged = after["status"] == 200 and after["response"].get("merged") is False and after["response"].get("state") == "open"
        if unchanged and item["status"] in (403, 405) and not expected:
            return "INCONCLUSIVE", "merge was denied but response did not attribute it to Restrict updates", evidence
        return ("PASS", f"CEO merge denied by Restrict updates; PR remains open; GitHub message: {message[:300]}", evidence) if expected and unchanged else ("FAIL", "CEO merge attempt was not denied by Restrict updates or PR state changed", evidence)
    if test_id == "A-02":
        pulls = _api(client, "GET", f"{base}/pulls?state=open&per_page=1")
        evidence.append(pulls)
        if pulls["status"] != 200 or not pulls["response"]:
            return "NOT RUN", "Create an open disposable PR, then rerun this test.", evidence
        number = pulls["response"][0]["number"]
        item = _api(client, "PUT", f"{base}/pulls/{number}/merge", {"merge_method": "merge"})
        evidence.append(item)
        after = _api(client, "GET", f"{base}/pulls/{number}")
        evidence.append(after)
        rejected = item["status"] == 403 and isinstance(item["response"], dict) and "resource not accessible" in item["response"].get("message", "").lower()
        unchanged = after["status"] == 200 and after["response"].get("merged") is False and after["response"].get("state") == "open"
        return ("PASS", "merge denied with HTTP 403 permission reason; PR remains open", evidence) if rejected and unchanged else ("FAIL", "merge was not denied for the expected permission reason or PR state changed", evidence)
    if test_id in ("A-03", "P3-05"):
        # Make a real distinct update, then exercise CAS with the previous actual OID.
        sha = _main_sha(client, base, evidence)
        if not sha:
            return "NOT RUN", "main ref unavailable; prepare the disposable trial repository", evidence
        try:
            candidate = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "NOT RUN", "local candidate commit unavailable for stale updateRefs trial", evidence
        if not re.fullmatch(r"[0-9a-f]{40,64}", candidate) or candidate == sha:
            return "NOT RUN", "trial needs a distinct local commit to move main before stale updateRefs", evidence
        staged = _git_push(client, f"{owner}/{repo}", f"{candidate}:refs/heads/aao-trial/stale-ref-{candidate[:8]}")
        evidence.append(staged)
        if staged.get("exit_code") != 0:
            return "FAIL", "could not stage distinct candidate commit", evidence
        checks_ok, checks_reason = _wait_required_checks(client, base, candidate, evidence)
        if not checks_ok:
            return "FAIL", f"cannot move main before stale updateRefs test: {checks_reason}", evidence
        repository = _api(client, "GET", base)
        evidence.append(repository)
        repository_id = repository.get("response", {}).get("node_id") if isinstance(repository.get("response"), dict) else None
        if repository["status"] != 200 or not repository_id:
            return "FAIL", "could not resolve repository node id for updateRefs", evidence
        query = {"query": "mutation($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }", "variables": {"input": {"repositoryId": repository_id, "refUpdates": [{"name": "refs/heads/main", "oid": candidate, "beforeOid": sha}]}}}
        moved = _api(client, "POST", "/graphql", query)
        evidence.append(moved)
        moved_ok = moved["status"] == 200 and isinstance(moved["response"], dict) and not moved["response"].get("errors")
        if not moved_ok or _main_sha(client, base, evidence) != candidate:
            return "FAIL", "could not move main to distinct candidate before stale updateRefs attempt", evidence
        query = {"query": "mutation($input: UpdateRefsInput!) { updateRefs(input: $input) { clientMutationId } }",
                 "variables": {"input": {"repositoryId": repository_id, "refUpdates": [{"name": "refs/heads/main", "oid": sha, "beforeOid": sha}]}}}
        item = _api(client, "POST", "/graphql", query)
        evidence.append(item)
        errors = item["status"] == 200 and isinstance(item["response"], dict) and any("before" in e.get("message", "").lower() or "stale" in e.get("message", "").lower() for e in item["response"].get("errors", []))
        unchanged = _verify_unchanged(client, base, candidate, evidence)
        return ("PASS", "updateRefs rejected stale beforeOid; moved main unchanged", evidence) if errors and unchanged else ("FAIL", "updateRefs did not report expected stale precondition rejection or main changed", evidence)
    if test_id in ("P3-01", "P3-02", "P3-07", "P3-12"):
        if test_id == "P3-01":
            if role != "ceo":
                return "NOT RUN", "Run explicitly with --role ceo to test the CEO identity.", evidence
            before = _main_sha(client, base, evidence)
            if not before:
                return "FAIL", "could not read main before CEO push", evidence
            item = _git_push(client, f"{owner}/{repo}", "HEAD:refs/heads/main")
            evidence.append(item)
            unchanged = _verify_unchanged(client, base, before, evidence)
            status, reason = _denial_outcome(item, unchanged, "restrict updates", "CEO push")
            return status, reason, evidence
        if test_id == "P3-02" and role not in ("aao-impl-codex", "aao-impl-claude", "aao-impl-agy"):
            return "NOT RUN", "Run with one of the implementer App roles to test its denial on canonical main.", evidence
        if test_id == "P3-12" and role != "aao-integrator":
            return "NOT RUN", "Run as aao-integrator with a non-fast-forward candidate on the disposable trial main.", evidence
        before = _main_sha(client, base, evidence)
        if not before:
            return "FAIL", "could not read main before protected push attempt", evidence
        if test_id == "P3-07":
            # Force-update main and staging so Git sends both updates to receive-pack.
            try:
                candidate = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                                           text=True, timeout=10).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                return "NOT RUN", "P3-07 requires a local candidate commit for a forced non-fast-forward attempt", evidence
            if not re.fullmatch(r"[0-9a-f]{40,64}", candidate) or candidate == before:
                return "NOT RUN", "P3-07 requires a candidate SHA distinct from main", evidence
            stage = f"aao-staging/{candidate[:12]}"
            stage_status, stage_before = _ref_sha(client, base, stage, evidence)
            if stage_status not in (200, 404):
                return "FAIL", "could not read staging ref before forced update", evidence
            if _is_ancestor(before, candidate) is not False or (
                stage_status == 200 and _is_ancestor(stage_before or "", candidate) is not False
            ):
                return "NOT RUN", "P3-07 candidate must be divergent from both main and the selected staging ref", evidence
            checks_ok, checks_reason = _wait_required_checks(client, base, candidate, evidence)
            if not checks_ok:
                return "INCONCLUSIVE", checks_reason, evidence
            main_item = _git_push(client, f"{owner}/{repo}", f"+{candidate}:refs/heads/main", no_verify=True)
            evidence.append(main_item)
            stage_item = _git_push(client, f"{owner}/{repo}", f"+{candidate}:refs/heads/{stage}", no_verify=True)
            evidence.append(stage_item)
            main_unchanged = _verify_unchanged(client, base, before, evidence)
            stage_unchanged = _ref_unchanged(client, base, stage, stage_status, stage_before, evidence)
            if main_unchanged and stage_unchanged and all(item.get("exit_code", 0) != 0 and item.get("server_rejected") is True for item in (main_item, stage_item)):
                if not all(_rejection_attributable(item, "non-fast-forward") for item in (main_item, stage_item)):
                    return "INCONCLUSIVE", "server rejected forced updates but did not attribute both to non_fast_forward", evidence
                return "PASS", "server rejected forced updates specifically for non_fast_forward; both refs unchanged", evidence
            return "FAIL", "forced main/staging updates were accepted, not server-rejected, or a ref changed", evidence
        else:
            candidate = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                                       text=True, timeout=10).stdout.strip()
            if _is_ancestor(before, candidate) is not False:
                return "NOT RUN", "P3-12 requires a candidate that is genuinely non-fast-forward to main", evidence
            checks_ok, checks_reason = _wait_required_checks(client, base, candidate, evidence)
            if not checks_ok:
                return "INCONCLUSIVE", checks_reason, evidence
            item = _git_push(client, f"{owner}/{repo}", "+HEAD:refs/heads/main", no_verify=True)
        evidence.append(item)
        unchanged = _verify_unchanged(client, base, before, evidence)
        expected = "non-fast-forward" if test_id == "P3-12" else "protected branch"
        if test_id == "P3-12":
            status, reason = _denial_outcome(item, unchanged, "non-fast-forward", "P3-12 push")
            return status, reason, evidence
        return ("PASS", f"server denied {test_id} push for expected reason; main unchanged", evidence) if _push_rejection_pass(item, unchanged, expected) else ("FAIL", "push was not rejected by the server for the expected reason or main changed", evidence)
    if test_id == "P3-08":
        # main is the default branch (GitHub refuses deleting it regardless of rulesets), so ruleset B's
        # deletion rule is exercised on a protected aao-staging/* ref created from a fully checked candidate.
        if role != "aao-integrator":
            return "NOT RUN", "P3-08 runs as aao-integrator on a protected aao-staging/* ref", evidence
        sha = _local_head()
        if not sha:
            return "NOT RUN", "P3-08 requires a local candidate commit", evidence
        checks_ok, checks_reason = _wait_required_checks(client, base, sha, evidence)
        if not checks_ok:
            return "INCONCLUSIVE", checks_reason, evidence
        ref = f"aao-staging/p308-{sha[:12]}"
        created = _git_push(client, f"{owner}/{repo}", f"{sha}:refs/heads/{ref}", no_verify=True)
        evidence.append(created)
        status_before, sha_before = _ref_sha(client, base, ref, evidence)
        if created.get("exit_code") != 0 or status_before != 200 or sha_before != sha:
            return "INCONCLUSIVE", "could not create the protected staging ref to attempt its deletion", evidence
        item = _git_push(client, f"{owner}/{repo}", f":refs/heads/{ref}", no_verify=True)
        evidence.append(item)
        unchanged = _ref_unchanged(client, base, ref, status_before, sha_before, evidence)
        status, reason = _denial_outcome(item, unchanged, "deletion", "P3-08 deletion of protected staging ref")
        return status, reason, evidence
    if test_id in ("A-05", "P3-06"):
        if role != "aao-integrator":
            return "NOT RUN", "Run as aao-integrator on the disposable trial repository after authorization and all required checks are present.", evidence
        try:
            return _merge_trial_pr(client, base, evidence)
        except (GitHubAuthError, OSError, subprocess.SubprocessError, ValueError) as exc:
            evidence.append({"method": "promotion flow", "status": "error", "response": type(exc).__name__})
            return "FAIL", f"promotion flow failed: {type(exc).__name__}", evidence
    if test_id == "A-06":
        head = _api(client, "GET", f"{base}/commits/HEAD")
        evidence.append(head)
        if head["status"] != 200:
            return "FAIL", "could not read HEAD SHA", evidence
        sha = head["response"].get("sha") if isinstance(head["response"], dict) else None
        if not sha:
            return "FAIL", "HEAD response has no SHA", evidence
        item = _api(client, "POST", f"{base}/check-runs", {"name": "aao-audit", "head_sha": sha, "status": "completed", "conclusion": "success"})
        evidence.append(item)
        if role == "aao-auditor":
            actual_app = item["response"].get("app", {}).get("id") if isinstance(item["response"], dict) else None
            return ("PASS", "aao-audit check was accepted from the configured auditor app_id", evidence) if item["status"] in (200, 201) and actual_app == client.app_id else ("FAIL", "auditor check run rejected or returned a different app_id", evidence)
        if role not in ("aao-impl-codex", "aao-impl-claude", "aao-impl-agy"):
            return "NOT RUN", "Use aao-auditor for the positive source-attribution check or an implementer for the expected 403.", evidence
        denied = item["status"] == 403 and isinstance(item["response"], dict) and "resource not accessible" in item["response"].get("message", "").lower()
        return ("PASS", "implementer check-run publication denied with HTTP 403 permission reason", evidence) if denied else ("FAIL", "check-run publication was not denied for the expected permission reason", evidence)
    if test_id == "P3-03":
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return "NOT RUN", "Run from a disposable local clone containing a candidate commit without aao-audit.", evidence
        staged = _git_push(client, f"{owner}/{repo}", f"{sha}:refs/heads/aao-trial/no-audit-{sha[:8]}")
        evidence.append(staged)
        if staged.get("exit_code") != 0:
            return "FAIL", "candidate without required check could not be staged on the trial repository", evidence
        before = _main_sha(client, base, evidence)
        if not before:
            return "FAIL", "could not read main before required-check update attempt", evidence
        item = _api(client, "PATCH", f"{base}/git/refs/heads/main", {"sha": sha, "force": True})
        evidence.append(item)
        message = item["response"].get("message", "").lower() if isinstance(item["response"], dict) else ""
        expected = item["status"] in (403, 422) and _rejection_attributable(
            {"response": message}, "required status check")
        unchanged = _verify_unchanged(client, base, before, evidence)
        return ("PASS", f"protected branch denied missing-check update with HTTP {item['status']}; main unchanged", evidence) if expected and unchanged else ("FAIL", "update was not rejected for required-check protection or main changed", evidence)
    if test_id == "P3-04":
        # The runner staged HEAD (a fast-forward of main) and published `aao-audit` on it from aao-auditor-alt.
        # Ruleset A is bypassed by the integrator, so once `test` is green the only unmet rule is the publisher.
        if role != "aao-integrator":
            return "NOT RUN", "P3-04 runs as aao-integrator", evidence
        sha = _local_head()
        before = _main_sha(client, base, evidence)
        if not sha or not before:
            return "NOT RUN", "P3-04 requires a local candidate and a readable main", evidence
        if _is_ancestor(before, sha) is not True:
            return "NOT RUN", "P3-04 candidate must be a fast-forward of main", evidence
        ready, why = _wait_wrong_publisher(client, base, sha, evidence)
        if not ready:
            return "INCONCLUSIVE", why, evidence
        item = _api(client, "PATCH", f"{base}/git/refs/heads/main", {"sha": sha, "force": False})
        evidence.append(item)
        message = item["response"].get("message", "").lower() if isinstance(item["response"], dict) else ""
        unchanged = _verify_unchanged(client, base, before, evidence)
        if item["status"] in (200, 201) or not unchanged:
            return "FAIL", "main accepted a candidate whose aao-audit came from a non-auditor App", evidence
        if item["status"] in (403, 422) and _rejection_attributable({"response": message}, "required status check") \
                and ("aao-audit" in message or "1 of 2" in message):
            return "PASS", f"main update denied: aao-audit from a non-auditor App does not satisfy ruleset B ({message[:200]})", evidence
        return "INCONCLUSIVE", "update denied but not attributable to the aao-audit publisher requirement", evidence
    raise ValueError(f"unsupported test id: {test_id}")


def run_test(test_id: str, owner: str, repo: str, role: str,
             client: GitHubAppClient) -> tuple[str, str, list[dict]]:
    """Keep malformed API response shapes as explicit, recorded failures."""
    try:
        return _run_test(test_id, owner, repo, role, client)
    except (AttributeError, KeyError) as exc:
        evidence = [{"method": "trial evaluation", "status": "error",
                     "exception": type(exc).__name__, "detail": str(exc)[:300]}]
        return "FAIL", f"trial response handling failed: {type(exc).__name__}", evidence


def write_evidence(test_id: str, status: str, reason: str, repo: str, role: str, app_id: int, evidence: list[dict]) -> Path:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    safe_ts = timestamp.replace(":", "").replace("+00:00", "Z")
    directory = Path.home() / "aao-trial-evidence"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    shas: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"sha", "oid", "beforeOid"} and isinstance(item, str) and re.fullmatch(r"[0-9a-f]{40,64}", item):
                    shas.add(item)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(evidence)
    candidate_sha = os.environ.get("AAO_TRIAL_CANDIDATE_SHA")
    if candidate_sha and re.fullmatch(r"[0-9a-f]{40,64}", candidate_sha):
        shas.add(candidate_sha)
    payload = {"test_id": test_id, "status": status, "reason": reason, "repo": repo, "role": role,
               "app_id": app_id, "timestamp": timestamp, "shas": sorted(shas),
               "run_id": os.environ.get("AAO_TRIAL_RUN_ID", ""),
               "harness_revision": os.environ.get("AAO_TRIAL_HARNESS_REV", ""),
               "candidate_sha": candidate_sha or "",
               "evidence": _redact(evidence)}
    fd, name = tempfile.mkstemp(prefix=f".{test_id}-", suffix=".tmp", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        target = directory / f"{test_id}-{safe_ts}.json"
        suffix = 1
        while target.exists():
            suffix += 1
            target = directory / f"{test_id}-{safe_ts}-{suffix}.json"
        os.replace(name, target)
        os.chmod(target, 0o600)
        return target
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_id", choices=[*(f"A-{i:02}" for i in range(1, 15)), *(f"P3-{i:02}" for i in range(1, 13)), "PUBLISH-AUDIT", "STAGE-COMMIT", "EQUIVALENCE"])
    parser.add_argument("--repo", required=True, help="OWNER/REPO disposable trial repository")
    parser.add_argument("--role", required=True, choices=[*sorted(ROLE_NAMES), "ceo"])
    parser.add_argument("--sha", help="explicit SHA for PUBLISH-AUDIT; also accepted through AAO_GITHUB_TRIAL_SHA")
    parser.add_argument("--branch", help="explicit branch for STAGE-COMMIT; also accepted through AAO_GITHUB_TRIAL_BRANCH")
    parser.add_argument("--equivalence", action="store_true", help="record implementer scope evidence without claiming PASS")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("--repo must be OWNER/REPO")
    try:
        if args.equivalence and (args.test_id not in {"A-01", "A-02", "P3-02"} or args.role not in {"aao-impl-claude", "aao-impl-codex", "aao-impl-agy"}):
            raise GitHubAuthError("--equivalence is limited to A-01, A-02, P3-02 for implementer roles")
        if args.sha:
            os.environ["AAO_GITHUB_TRIAL_SHA"] = args.sha
        if args.branch:
            os.environ["AAO_GITHUB_TRIAL_BRANCH"] = args.branch
        validate_role_uid(args.role)
        if not _trial_repo_allowed(*args.repo.split("/", 1)):
            raise GitHubAuthError("--repo must be explicitly listed in AAO_GITHUB_TRIAL_REPOS and cannot be " + CANONICAL_REPO)
        if args.role == "ceo":
            if args.test_id not in ("P3-01", "P3-09", "A-07"):
                raise GitHubAuthError("--role ceo is allowed only for P3-01, P3-09 and A-07")
            token_result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"], check=True, capture_output=True,
                                          text=True, timeout=10, stdin=subprocess.DEVNULL)
            token = token_result.stdout.strip()
            if not token:
                raise GitHubAuthError("gh auth token returned no token")
            validate_ceo_gh_identity(args.repo)
            client = object.__new__(GitHubAppClient)
            client.app_id, client._installation_token = 0, token
            client.api_base, client.timeout = "https://api.github.com", 15.0
            client.close = lambda: None
        else:
            client = GitHubAppClient(args.role)
        owner, repo = args.repo.split("/", 1)
        # Manual tests require no API call and do not need private credentials.
        if args.role == "ceo":
            status, reason, records = run_test(args.test_id, owner, repo, args.role, client)
        else:
            if args.equivalence or args.test_id == "EQUIVALENCE":
                token_repo = os.environ.get("AAO_GITHUB_TRIAL_FORK", "")
                if "/" not in token_repo:
                    raise GitHubAuthError("EQUIVALENCE requires AAO_GITHUB_TRIAL_FORK=OWNER/REPO")
                client.installation_token(*token_repo.split("/", 1))
            else:
                client.installation_token(owner, repo)
            status, reason, records = (_run_equivalence(owner, repo, args.role, client) if args.equivalence
                                       else run_test(args.test_id, owner, repo, args.role, client))
        output = write_evidence(args.test_id, status, reason, args.repo, args.role, client.app_id, records)
        print(f"{status}: {reason}\nEvidence: {output}")
        return 0 if status == "PASS" else (1 if status == "FAIL" else 2)
    except (GitHubAuthError, OSError, ValueError, subprocess.SubprocessError,
            KeyError, TypeError, AttributeError, IndexError, StopIteration) as exc:
        message = str(exc) if isinstance(exc, GitHubAuthError) else type(exc).__name__
        try:
            output = write_evidence(args.test_id, "NOT RUN", message, args.repo, args.role,
                                    getattr(locals().get("client"), "app_id", 0),
                                    [{"method": "harness", "status": "error", "response": type(exc).__name__}])
            print(f"NOT RUN: {message}\nEvidence: {output}")
        except OSError:
            print(f"NOT RUN: {message}")
        return 2
    finally:
        if "client" in locals():
            try:
                client.close()
            except GitHubAuthError:
                pass


if __name__ == "__main__":
    sys.exit(main())
