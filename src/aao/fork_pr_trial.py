"""A-11 (fork PR creation) and P3-10 (external workflow approval gate) for the disposable trial.

Three steps, each run by run_trial.sh under its own Linux uid with its own GitHub App key:
  FORK-BRANCH  implementer: push a workflow-changing branch to its own trial fork; prove it has
               no installation on the protected trial repository.
  A-11         aao-pm: open the PR fork -> trial repository (pull_requests: write only).
  P3-10        aao-supervisor (actions: read): verify the PR's workflow run waits for approval and
               executed no job. Creating the PR never counts as P3-10 evidence.
Nothing here approves a run, merges, or touches the canonical repository.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.parse
from typing import Any

from .github_app_auth import GitHubAppClient, GitHubAuthError, create_jwt
from .github_trial import _api, _git_push, _trial_repo_allowed, validate_role_uid, write_evidence

IMPLEMENTERS = {"aao-impl-claude", "aao-impl-codex", "aao-impl-agy"}
STEP_ROLES = {"FORK-BRANCH": IMPLEMENTERS, "A-11": {"aao-pm"}, "P3-10": {"aao-supervisor"}}
SHA = re.compile(r"[0-9a-f]{40}")
BRANCH = re.compile(r"aao-trial/[A-Za-z0-9._-]+")
P310_WAIT_SECONDS = int(os.environ.get("AAO_TRIAL_P310_WAIT", "600"))
P310_POLL_SECONDS = 20


def _env(name: str, pattern: re.Pattern[str]) -> str:
    value = os.environ.get(name, "")
    if not pattern.fullmatch(value):
        raise GitHubAuthError(f"{name} is missing or malformed")
    return value


def _repo_path(full: str) -> str:
    owner, name = full.split("/", 1)
    return f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}"


def fork_branch(fork: str, parent: str, client: GitHubAppClient) -> tuple[str, str, list[dict]]:
    branch = _env("AAO_GITHUB_TRIAL_BRANCH", BRANCH)
    head = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    changed = subprocess.run(["git", "diff", "--name-only", "HEAD^", "HEAD"], check=True, capture_output=True,
                             text=True, timeout=10).stdout.split()
    evidence: list[dict] = [{"method": "local candidate", "sha": head, "changed_paths": changed}]
    if not any(path.startswith(".github/workflows/") for path in changed):
        return "FAIL", "candidate does not change .github/workflows/", evidence
    info = _api(client, "GET", _repo_path(fork))
    evidence.append(info)
    response = info["response"] if isinstance(info["response"], dict) else {}
    if info["status"] != 200 or (response.get("parent") or {}).get("full_name", "").lower() != parent.lower():
        return "FAIL", f"{fork} is not a fork of {parent}", evidence
    # Negative half of A-11: the implementer App has no installation on the protected repository.
    installation = client._request("GET", _repo_path(parent) + "/installation",
                                   token=create_jwt(client.app_id, client._key_path))
    evidence.append({"method": "GET", "path": _repo_path(parent) + "/installation", "auth": "app-jwt",
                     "status": installation.status})
    if installation.status != 404:
        return "FAIL", f"implementer App installation lookup on {parent} returned {installation.status}, expected 404", evidence
    push = _git_push(client, fork, f"HEAD:refs/heads/{branch}", no_verify=True)
    evidence.append(push)
    ref = _api(client, "GET", _repo_path(fork) + f"/git/ref/heads/{urllib.parse.quote(branch, safe='/')}")
    evidence.append(ref)
    pushed = ref["response"].get("object", {}).get("sha") if isinstance(ref["response"], dict) else None
    if push.get("exit_code") != 0 or pushed != head:
        return "FAIL", "push of the workflow-changing branch to the implementer's own fork failed", evidence
    return "PASS", f"implementer pushed {head} to {fork}:{branch}; no installation on {parent}", evidence


def open_pr(parent: str, client: GitHubAppClient) -> tuple[str, str, list[dict]]:
    fork = _env("AAO_GITHUB_TRIAL_FORK", re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"))
    branch = _env("AAO_GITHUB_TRIAL_BRANCH", BRANCH)
    expected = _env("AAO_TRIAL_CANDIDATE_SHA", SHA)
    fork_owner, fork_name = fork.split("/", 1)
    evidence: list[dict] = []
    body = {"title": f"AAO trial A-11/P3-10 {branch}", "base": "main", "head": f"{fork_owner}:{branch}",
            "body": "Disposable trial PR opened by aao-pm from an implementer fork. Do not approve workflows or merge."}
    # GitHub documents head_repo as required for same-owner forks without a format; record each attempt.
    for head_repo in (fork_name, fork):
        record = _api(client, "POST", _repo_path(parent) + "/pulls", {**body, "head_repo": head_repo})
        evidence.append(record)
        if record["status"] != 422:
            break
    pr = record["response"] if isinstance(record["response"], dict) else {}
    head, base = pr.get("head") or {}, pr.get("base") or {}
    ok = (record["status"] == 201 and isinstance(pr.get("number"), int)
          and (head.get("repo") or {}).get("full_name", "").lower() == fork.lower()
          and head.get("sha") == expected
          and (base.get("repo") or {}).get("full_name", "").lower() == parent.lower()
          and (pr.get("user") or {}).get("login") == "aao-pm[bot]")
    if not ok:
        return "FAIL", f"fork PR was not created as aao-pm[bot] from {fork} at {expected}", evidence
    evidence.append({"method": "fork pull request", "number": pr["number"], "sha": expected, "head_repo": fork})
    return "PASS", f"aao-pm opened PR #{pr['number']} from {fork}", evidence


def approval_gate(parent: str, client: GitHubAppClient) -> tuple[str, str, list[dict]]:
    number = int(_env("AAO_GITHUB_TRIAL_PR", re.compile(r"[1-9][0-9]*")))
    head = _env("AAO_GITHUB_TRIAL_PR_HEAD", SHA)
    fork = _env("AAO_GITHUB_TRIAL_FORK", re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"))
    branch = _env("AAO_GITHUB_TRIAL_BRANCH", BRANCH)
    evidence: list[dict] = [{"method": "pull request under test", "number": number, "sha": head,
                             "head_repo": fork, "branch": branch}]
    # Fork-triggered runs leave run.pull_requests empty, so bind runs to the PR by its exact head repo/branch/SHA.
    pr = _api(client, "GET", _repo_path(parent) + f"/pulls/{number}")
    evidence.append(pr)
    body = pr["response"] if isinstance(pr["response"], dict) else {}
    pr_head = body.get("head") or {}
    if (pr["status"] != 200 or pr_head.get("sha") != head or pr_head.get("ref") != branch
            or (pr_head.get("repo") or {}).get("full_name", "").lower() != fork.lower()):
        return "INCONCLUSIVE", f"PR #{number} is not the fork PR {fork}:{branch} at {head}", evidence
    deadline = time.monotonic() + P310_WAIT_SECONDS
    while True:
        runs = _api(client, "GET", _repo_path(parent) + f"/actions/runs?event=pull_request&head_sha={head}&per_page=100")
        evidence.append(runs)
        if runs["status"] != 200 or not isinstance(runs["response"], dict):
            return "INCONCLUSIVE", f"workflow run query returned HTTP {runs['status']}", evidence
        listed = [run for run in runs["response"].get("workflow_runs") or []
                  if run.get("head_branch") == branch
                  and (run.get("head_repository") or {}).get("full_name", "").lower() == fork.lower()]
        gated = 0
        for run in listed:
            jobs = _api(client, "GET", _repo_path(parent) + f"/actions/runs/{int(run['id'])}/jobs?filter=all")
            evidence.append(jobs)
            count = jobs["response"].get("total_count") if isinstance(jobs["response"], dict) else None
            if jobs["status"] != 200 or not isinstance(count, int):
                return "INCONCLUSIVE", f"job query for run {run['id']} returned HTTP {jobs['status']}", evidence
            if count:
                return "FAIL", f"workflow run {run['id']} executed {count} job(s) without approval", evidence
            if "action_required" in (run.get("status"), run.get("conclusion")):
                gated += 1
        if listed and gated == len(listed):
            return "PASS", f"{gated} pull_request run(s) for {head} wait for approval with no job executed", evidence
        if time.monotonic() >= deadline:
            reason = "no pull_request workflow run appeared" if not listed else "runs neither gated nor executed"
            return "INCONCLUSIVE", f"{reason} within {P310_WAIT_SECONDS}s", evidence
        time.sleep(P310_POLL_SECONDS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=sorted(STEP_ROLES))
    parser.add_argument("--repo", required=True, help="fork for FORK-BRANCH; trial repository otherwise")
    parser.add_argument("--role", required=True)
    args = parser.parse_args(argv)
    status, reason, records, app_id = "NOT RUN", "", [], 0
    try:
        if args.role not in STEP_ROLES[args.step]:
            raise GitHubAuthError(f"{args.step} must run as {sorted(STEP_ROLES[args.step])}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo) or not _trial_repo_allowed(*args.repo.split("/", 1)):
            raise GitHubAuthError("--repo must be listed in AAO_GITHUB_TRIAL_REPOS and is never the canonical repository")
        validate_role_uid(args.role)
        parent = os.environ.get("AAO_GITHUB_TRIAL_FORK_PARENT", "")
        if args.step != "FORK-BRANCH" and args.repo.lower() != parent.lower():
            raise GitHubAuthError("A-11 and P3-10 target the trial repository named by AAO_GITHUB_TRIAL_FORK_PARENT")
        client = GitHubAppClient(args.role)
        app_id = client.app_id
        try:
            client.installation_token(*args.repo.split("/", 1))
            if args.step == "FORK-BRANCH":
                status, reason, records = fork_branch(args.repo, parent, client)
            elif args.step == "A-11":
                status, reason, records = open_pr(args.repo, client)
            else:
                status, reason, records = approval_gate(args.repo, client)
        finally:
            client.close()
    except (GitHubAuthError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, GitHubAuthError) else type(exc).__name__
        records = [{"method": "harness", "status": "error", "response": type(exc).__name__}]
    output = write_evidence(args.step, status, reason, args.repo, args.role, app_id, records)
    print(f"{status}: {reason}\nEvidence: {output}")
    return 0 if status == "PASS" else (1 if status == "FAIL" else 2)


if __name__ == "__main__":
    sys.exit(main())
