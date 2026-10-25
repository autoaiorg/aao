"""Publish an approved candidate as a pull request (W2b).

The publisher never trusts the executing agent's ``result_json``: before any external
effect it re-derives the candidate from the database (VERIFIED work, the latest
APPROVE on an exact SHA, no veto, a SUCCEEDED execution of that SHA and its proposal)
and re-checks in the candidate store that the commit's only parent is the proposal's
base and that its tree equals base + the stored patch. It pushes exactly that SHA.

Two steps, one per identity: ``push_candidate`` (implementer) and ``open_pull_request`` (PM).
GitHub access is injected: ``push(sha, branch)`` and ``open_pr(branch, title, body)`` (returns number, url and head_sha).
``github_publisher`` builds them from GitHub Apps; tests use local bare remotes.
Run it as a one-shot process (scripts/publish_candidate.py) so App keys never reach the API.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

_SHA = re.compile(r"^[0-9a-f]{40}$")


class PublishError(RuntimeError):
    pass


def _git(repo: Path, *args: str, env: dict | None = None, input: bytes | None = None) -> str:
    base = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1"}
    proc = subprocess.run(["git", "--git-dir", str(repo), *args], env={**base, **(env or {})}, input=input,
                          capture_output=True, cwd="/", timeout=60, check=False)
    if proc.returncode:
        raise PublishError(f"git {args[0]} failed")
    return proc.stdout.decode("utf-8", errors="replace")


def verify_candidate(store: Path, candidate_sha: str, base_sha: str, patch: bytes) -> None:
    """The stored commit must be exactly base + the proposal's patch."""
    if not (_SHA.fullmatch(candidate_sha) and _SHA.fullmatch(base_sha)):
        raise PublishError("full SHAs required")
    parents = _git(store, "rev-list", "--parents", "-n", "1", candidate_sha).split()
    if parents != [candidate_sha, base_sha]:
        raise PublishError("candidate is not a single commit on the proposal base")
    with tempfile.TemporaryDirectory(prefix="aao-publish-") as tmp:
        index = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(store, "read-tree", base_sha, env=index)
        _git(store, "apply", "--cached", "--binary", "-", env=index, input=patch)
        expected = _git(store, "write-tree", env=index).strip()
    if expected != _git(store, "rev-parse", f"{candidate_sha}^{{tree}}").strip():
        raise PublishError("candidate tree does not match base + proposal patch")


def _approved_candidate(work_id: str, credential: str, kind_of_step: str) -> dict:
    """Re-derive the approved candidate from the database; never from the agent's result_json."""
    from fastapi import HTTPException

    from aao.principal_credentials import PrincipalDenied
    from aao.work_management_api import _authenticate_request_principal, require_grant, tx

    try:
        principal = _authenticate_request_principal(credential, "AGENT")
    except PrincipalDenied as exc:
        raise PublishError("active publisher credential required") from exc
    with tx() as db:
        work = db.execute("SELECT project_id,status,author_id,title FROM work_items WHERE id=%s FOR UPDATE",
                          (work_id,)).fetchone()
        if not work:
            raise PublishError("work not found")
        project_id, status, author_id, title = work
        try:
            require_grant(db, principal, project_id, "code.publish")
        except HTTPException as exc:
            raise PublishError(str(exc.detail)) from exc
        if principal == author_id:
            raise PublishError("the implementing agent cannot publish its own work")
        events = {kind: details for kind, details in db.execute(
            "SELECT kind,details FROM events WHERE subject_id=%s AND kind IN ('work.candidate_pushed','work.pr_opened') "
            "ORDER BY created_at", (work_id,)).fetchall()}
        if kind_of_step in events:
            return {"done": events[kind_of_step]}
        if status != "VERIFIED":
            raise PublishError("only VERIFIED work can be published")
        if db.execute("SELECT 1 FROM reviews WHERE work_id=%s AND decision='VETO' LIMIT 1", (work_id,)).fetchone():
            raise PublishError("an active veto blocks publication")
        review = db.execute("SELECT id,candidate_sha FROM reviews WHERE work_id=%s AND decision='APPROVE' "
                            "ORDER BY created_at DESC LIMIT 1", (work_id,)).fetchone()
        if not review:
            raise PublishError("no approval recorded")
        review_id, candidate_sha = str(review[0]), review[1]
        proposal = db.execute(
            "SELECT p.id,p.base_sha,p.patch_bytes FROM execution_queue q JOIN patch_proposals p "
            "ON p.id::text = q.result_json->>'proposal_id' AND p.work_id=q.work_id "
            "WHERE q.work_id=%s AND q.status='SUCCEEDED' AND q.result_json->>'candidate_sha'=%s "
            "ORDER BY q.created_at DESC LIMIT 1", (work_id, candidate_sha)).fetchone()
        if not proposal:
            raise PublishError("approved SHA has no succeeded execution with a proposal")
    return {"principal": str(principal), "title": title, "candidate_sha": candidate_sha, "review_id": review_id,
            "proposal_id": str(proposal[0]), "base_sha": proposal[1], "patch": bytes(proposal[2]),
            "pushed": events.get("work.candidate_pushed")}


def push_candidate(work_id: str, credential: str, *, store: str | Path,
                   push: Callable[[str, str], None]) -> dict:
    """Step 1 (implementer identity): verify the approved commit in the store and push exactly that SHA."""
    from aao.work_management_api import audit, tx

    c = _approved_candidate(work_id, credential, "work.candidate_pushed")
    if "done" in c:
        return {**c["done"], "status": "ALREADY_PUSHED"}
    verify_candidate(Path(store).resolve(), c["candidate_sha"], c["base_sha"], c["patch"])
    branch = f"aao/work-{work_id}-{c['candidate_sha'][:12]}"
    # ponytail: pushing the same SHA to the same branch is idempotent, so a crash before the event is
    # recovered by re-running; move to external_effects if UNCERTAIN tracking becomes necessary.
    push(c["candidate_sha"], branch)
    record = {"candidate_sha": c["candidate_sha"], "base_sha": c["base_sha"], "branch": branch,
              "proposal_id": c["proposal_id"], "review_id": c["review_id"], "pusher": c["principal"]}
    with tx() as db:
        audit(db, work_id, "work.candidate_pushed", record)
    return {**record, "status": "PUSHED"}


def open_pull_request(work_id: str, credential: str, *, open_pr: Callable[[str, str, str], dict]) -> dict:
    """Step 2 (PM identity): open the PR for the branch pushed in step 1, if it still holds the approved SHA."""
    from aao.work_management_api import audit, tx

    c = _approved_candidate(work_id, credential, "work.pr_opened")
    if "done" in c:
        return {**c["done"], "status": "ALREADY_PUBLISHED"}
    pushed = c["pushed"]
    if not pushed or pushed["candidate_sha"] != c["candidate_sha"]:
        raise PublishError("the approved candidate has not been pushed")
    body = (f"AAO work `{work_id}`\n\n- candidate: `{c['candidate_sha']}` on base `{c['base_sha']}`\n"
            f"- proposal: `{c['proposal_id']}`\n- approval review: `{c['review_id']}`\n"
            f"- pushed by: `{pushed['pusher']}`; opened by: `{c['principal']}`\n")
    pr = open_pr(pushed["branch"], f"aao: {c['title']}", body)
    if pr.get("head_sha") != c["candidate_sha"]:
        # The fork branch moved after the push: never record an unapproved head as this task's PR.
        raise PublishError("opened pull request head is not the approved candidate")
    record = {**pushed, "publisher": c["principal"], "pr_number": int(pr["number"]), "pr_url": str(pr["url"])}
    with tx() as db:
        audit(db, work_id, "work.pr_opened", record)
    return {**record, "status": "PUBLISHED"}


def github_publisher(store: str | Path) -> tuple[Callable[[str, str], None], Callable[[str, str, str], dict]]:
    """Real GitHub effects: the implementer App pushes to its fork, the PM App opens the PR.

    Each App key is readable only by its own uid (github_app_auth.load_app), so ``push`` must run
    as the implementer's uid and ``open_pr`` as aao-pm's: two processes, one per step.
    Configuration: AAO_PUBLISH_BASE_REPO (owner/repo, PR target), AAO_PUBLISH_HEAD_REPO (fork),
    AAO_PUBLISH_PUSH_APP and AAO_PUBLISH_PR_APP. Clients are created lazily, per step.
    """
    from aao.github_app_auth import GitHubAppClient

    base_repo = os.environ["AAO_PUBLISH_BASE_REPO"]
    head_repo = os.environ["AAO_PUBLISH_HEAD_REPO"]
    store = Path(store).resolve()

    def push(sha: str, branch: str) -> None:
        owner, repo = head_repo.split("/", 1)
        client = GitHubAppClient(os.environ["AAO_PUBLISH_PUSH_APP"])
        try:
            token = client.installation_token(owner, repo)
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
            _git(store, "-c", f"http.extraheader=AUTHORIZATION: basic {basic}", "push", "--quiet",
                 f"https://github.com/{head_repo}.git", f"{sha}:refs/heads/{branch}")
        finally:
            client.close()

    def open_pr(branch: str, title: str, body: str) -> dict:
        owner, repo = base_repo.split("/", 1)
        head = f"{head_repo.split('/', 1)[0]}:{branch}"
        client = GitHubAppClient(os.environ["AAO_PUBLISH_PR_APP"])
        try:
            client.installation_token(owner, repo)
            existing = client.request("GET", f"/repos/{base_repo}/pulls?state=open&head={head}")
            if existing.status != 200 or not isinstance(existing.body, list):
                raise PublishError(f"pull request lookup failed with HTTP {existing.status}")
            if existing.body:
                pr = existing.body[0]
            else:
                created = client.request("POST", f"/repos/{base_repo}/pulls",
                                         body={"title": title, "head": head, "base": "main", "body": body})
                if created.status != 201 or not isinstance(created.body, dict):
                    raise PublishError(f"pull request creation failed with HTTP {created.status}")
                pr = created.body
            return {"number": pr["number"], "url": pr["html_url"], "head_sha": (pr.get("head") or {}).get("sha")}
        finally:
            client.close()

    return push, open_pr
