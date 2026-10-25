"""Publish an approved candidate as a pull request (W2b).

The publisher never trusts the executing agent's ``result_json``: before any external
effect it re-derives the candidate from the database (VERIFIED work, the latest
APPROVE on an exact SHA, no veto, a SUCCEEDED execution of that SHA and its proposal)
and re-checks in the candidate store that the commit's only parent is the proposal's
base and that its tree equals base + the stored patch. It pushes exactly that SHA.

GitHub access is injected: ``push(sha, branch)`` and ``open_pr(branch, title, body)``.
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


def publish(work_id: str, publisher_credential: str, *, store: str | Path,
            push: Callable[[str, str], None], open_pr: Callable[[str, str, str], dict]) -> dict:
    from fastapi import HTTPException

    from aao.principal_credentials import PrincipalDenied
    from aao.work_management_api import _authenticate_request_principal, audit, require_grant, tx

    store = Path(store).resolve()
    try:
        publisher = _authenticate_request_principal(publisher_credential, "AGENT")
    except PrincipalDenied as exc:
        raise PublishError("active publisher credential required") from exc
    with tx() as db:
        work = db.execute("SELECT project_id,status,author_id,title FROM work_items WHERE id=%s FOR UPDATE",
                          (work_id,)).fetchone()
        if not work:
            raise PublishError("work not found")
        project_id, status, author_id, title = work
        try:
            require_grant(db, publisher, project_id, "code.publish")
        except HTTPException as exc:
            raise PublishError(str(exc.detail)) from exc
        if publisher == author_id:
            raise PublishError("the implementing agent cannot publish its own work")
        published = db.execute("SELECT details FROM events WHERE subject_id=%s AND kind='work.pr_opened' "
                               "ORDER BY created_at DESC LIMIT 1", (work_id,)).fetchone()
        if published:
            return {**published[0], "status": "ALREADY_PUBLISHED"}
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
        proposal_id, base_sha, patch = str(proposal[0]), proposal[1], bytes(proposal[2])
    verify_candidate(store, candidate_sha, base_sha, patch)
    branch = f"aao/work-{work_id}-{candidate_sha[:12]}"
    body = (f"AAO work `{work_id}`\n\n- candidate: `{candidate_sha}` on base `{base_sha}`\n"
            f"- proposal: `{proposal_id}`\n- approval review: `{review_id}`\n- published by: `{publisher}`\n")
    # ponytail: push/open are idempotent at GitHub (same SHA, same branch, existing PR is reused), so a crash
    # before the event below is recovered by re-running; use external_effects if UNCERTAIN tracking is needed.
    push(candidate_sha, branch)
    pr = open_pr(branch, f"aao: {title}", body)
    record = {"candidate_sha": candidate_sha, "base_sha": base_sha, "branch": branch, "proposal_id": proposal_id,
              "review_id": review_id, "publisher": publisher,
              "pr_number": int(pr["number"]), "pr_url": str(pr["url"])}
    with tx() as db:
        audit(db, work_id, "work.pr_opened", record)
    return {**record, "status": "PUBLISHED"}


def github_publisher(store: str | Path) -> tuple[Callable[[str, str], None], Callable[[str, str, str], dict]]:
    """Real GitHub effects: the implementer App pushes to its fork, the PM App opens the PR.

    Configuration: AAO_PUBLISH_BASE_REPO (owner/repo, PR target), AAO_PUBLISH_HEAD_REPO (fork),
    AAO_PUBLISH_PUSH_APP and AAO_PUBLISH_PR_APP (App names whose keys this uid can read).
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
            if existing.status == 200 and isinstance(existing.body, list) and existing.body:
                pr = existing.body[0]
            else:
                created = client.request("POST", f"/repos/{base_repo}/pulls",
                                         body={"title": title, "head": head, "base": "main", "body": body})
                if created.status != 201 or not isinstance(created.body, dict):
                    raise PublishError(f"pull request creation failed with HTTP {created.status}")
                pr = created.body
            return {"number": pr["number"], "url": pr["html_url"]}
        finally:
            client.close()

    return push, open_pr
