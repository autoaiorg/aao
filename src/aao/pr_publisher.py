"""Publish an approved candidate as a pull request (W2b).

The publisher never trusts the executing agent's ``result_json``: before any external
effect it re-derives the candidate from the database (VERIFIED work, the latest
APPROVE on an exact SHA, no veto, a SUCCEEDED execution of that SHA and its proposal)
and re-checks in the candidate store that the commit's only parent is the proposal's
base and that its tree equals base + the stored patch. It pushes exactly that SHA.

Two steps, one per identity: ``push_candidate`` (implementer) and ``open_pull_request`` (PM).
GitHub access is injected: ``push(sha, branch)``, ``open_pr(branch, title, body)`` (returns number,
url and head_sha) and ``get_pr(number)`` (for ``reconcile``, W3, PM identity).
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


def _approved_candidate(db, work_id: str, credential: str, kind_of_step: str) -> dict:
    """Re-derive the approved candidate from the database; never from the agent's result_json."""
    from fastapi import HTTPException

    from aao.principal_credentials import PrincipalDenied
    from aao.work_management_api import _authenticate_request_principal, require_grant

    try:
        principal = _authenticate_request_principal(credential, "AGENT")
    except PrincipalDenied as exc:
        raise PublishError("active publisher credential required") from exc
    # The caller keeps this transaction (and the work-row lock) until the external
    # effect is reconciled into events. This serializes AAO publishers for a work
    # item and prevents an approval/veto/status transition racing the effect.
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
    review = db.execute("SELECT id,candidate_sha FROM reviews WHERE work_id=%s AND decision='APPROVE' "
                        "ORDER BY created_at DESC LIMIT 1", (work_id,)).fetchone()
    if not review:
        raise PublishError("no approval recorded")
    review_id, candidate_sha = str(review[0]), review[1]
    # Idempotent per approved candidate: a later attempt (after a closed PR) gets its own push and PR.
    events = {kind: details for kind, details in db.execute(
        "SELECT kind,details FROM events WHERE subject_id=%s AND kind IN ('work.candidate_pushed','work.pr_opened') "
        "AND details->>'candidate_sha'=%s AND created_at > COALESCE((SELECT max(created_at) FROM events "
        "WHERE subject_id=%s AND kind='work.pr_closed'), '-infinity') ORDER BY created_at",
        (work_id, candidate_sha, work_id)).fetchall()}
    if kind_of_step in events:
        return {"done": events[kind_of_step]}
    if status != "VERIFIED":
        raise PublishError("only VERIFIED work can be published")
    if db.execute("SELECT 1 FROM reviews WHERE work_id=%s AND decision='VETO' LIMIT 1", (work_id,)).fetchone():
        raise PublishError("an active veto blocks publication")
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

    with tx() as db:
        c = _approved_candidate(db, work_id, credential, "work.candidate_pushed")
        if "done" in c:
            return {**c["done"], "status": "ALREADY_PUSHED"}
        verify_candidate(Path(store).resolve(), c["candidate_sha"], c["base_sha"], c["patch"])
        branch = f"aao/work-{work_id}-{c['candidate_sha'][:12]}"
        # The deterministic ref makes a retry after an uncertain push reconcile to the same SHA.
        push(c["candidate_sha"], branch)
        record = {"candidate_sha": c["candidate_sha"], "base_sha": c["base_sha"], "branch": branch,
                  "proposal_id": c["proposal_id"], "review_id": c["review_id"], "pusher": c["principal"]}
        audit(db, work_id, "work.candidate_pushed", record)
    return {**record, "status": "PUSHED"}


def open_pull_request(work_id: str, credential: str, *, open_pr: Callable[[str, str, str], dict]) -> dict:
    """Step 2 (PM identity): open the PR for the branch pushed in step 1, if it still holds the approved SHA."""
    from aao.work_management_api import audit, tx

    with tx() as db:
        c = _approved_candidate(db, work_id, credential, "work.pr_opened")
        if "done" in c:
            return {**c["done"], "status": "ALREADY_PUBLISHED"}
        pushed = c["pushed"]
        if not pushed or pushed["candidate_sha"] != c["candidate_sha"]:
            raise PublishError("the approved candidate has not been pushed")
        body = (f"AAO work `{work_id}`\n\n- candidate: `{c['candidate_sha']}` on base `{c['base_sha']}`\n"
                f"- proposal: `{c['proposal_id']}`\n- approval review: `{c['review_id']}`\n"
                f"- pushed by: `{pushed['pusher']}`; opened by: `{c['principal']}`\n")
        # Keep the locked work row through the GitHub call and event commit. A timeout/crash
        # can still leave the remote result uncertain; retry must query/reconcile by this branch.
        pr = open_pr(pushed["branch"], f"aao: {c['title']}", body)
        if pr.get("head_sha") != c["candidate_sha"]:
            raise PublishError("opened pull request head is not the approved candidate")
        record = {**pushed, "publisher": c["principal"], "pr_number": int(pr["number"]), "pr_url": str(pr["url"])}
        audit(db, work_id, "work.pr_opened", record)
    return {**record, "status": "PUBLISHED"}


def reconcile(work_id: str, publisher_credential: str, *, get_pr: Callable[[int], dict]) -> dict:
    """W3: VERIFIED work becomes DONE once its PR is merged with the approved SHA as head.

    ``get_pr(number)`` returns ``{"state", "merged", "merge_commit_sha", "head_sha"}``.
    The CEO squash-merges, so the result is bound by the PR (head == approved SHA, merged)
    and its merge commit, not by ancestry.
    """
    from fastapi import HTTPException

    from aao.principal_credentials import PrincipalDenied
    from aao.work_management_api import _authenticate_request_principal, audit, require_grant, tx

    try:
        publisher = _authenticate_request_principal(publisher_credential, "AGENT")
    except PrincipalDenied as exc:
        raise PublishError("active publisher credential required") from exc
    with tx() as db:
        work = db.execute("SELECT project_id,status FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not work:
            raise PublishError("work not found")
        project_id, status = work
        try:
            require_grant(db, publisher, project_id, "code.publish")
        except HTTPException as exc:
            raise PublishError(str(exc.detail)) from exc
        published = db.execute("SELECT details FROM events WHERE subject_id=%s AND kind='work.pr_opened' "
                               "ORDER BY created_at DESC LIMIT 1", (work_id,)).fetchone()
    if status == "DONE":
        return {"status": "DONE"}
    if not published:
        raise PublishError("work has no published pull request")
    record = published[0]
    pr = get_pr(int(record["pr_number"]))
    if pr.get("head_sha") != record["candidate_sha"]:
        raise PublishError("pull request head no longer matches the approved candidate")
    if not pr.get("merged"):
        if pr.get("state") == "open":
            return {"status": "OPEN", "pr_number": record["pr_number"]}
        # Closed without merge: the approved candidate was not accepted; the work goes back to
        # IN_PROGRESS so a new attempt can be run, reviewed and published.
        with tx() as db:
            reopened = db.execute("UPDATE work_items SET status='IN_PROGRESS' WHERE id=%s AND status='VERIFIED' "
                                  "RETURNING id", (work_id,)).fetchone()
            if reopened:
                audit(db, work_id, "work.pr_closed", {"pr_number": record["pr_number"], "pr_url": record["pr_url"],
                                                      "candidate_sha": record["candidate_sha"],
                                                      "reconciled_by": str(publisher)})
        return {"status": "CLOSED_UNMERGED", "pr_number": record["pr_number"], "work_status": "IN_PROGRESS"}
    merge_sha = str(pr.get("merge_commit_sha") or "")
    if not _SHA.fullmatch(merge_sha):
        raise PublishError("merged pull request has no merge commit SHA")
    result = {"pr_number": record["pr_number"], "pr_url": record["pr_url"],
              "candidate_sha": record["candidate_sha"], "merge_commit_sha": merge_sha, "reconciled_by": publisher}
    with tx() as db:
        updated = db.execute("UPDATE work_items SET status='DONE' WHERE id=%s AND status='VERIFIED' RETURNING id",
                             (work_id,)).fetchone()
        if not updated:
            raise PublishError("work is no longer VERIFIED")
        audit(db, work_id, "work.completed", result)
    return {**result, "status": "DONE"}


def github_publisher(store: str | Path) -> tuple[Callable[[str, str], None], Callable[[str, str, str], dict],
                                                  Callable[[int], dict]]:
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

    def get_pr(number: int) -> dict:
        owner, repo = base_repo.split("/", 1)
        client = GitHubAppClient(os.environ["AAO_PUBLISH_PR_APP"])
        try:
            client.installation_token(owner, repo)
            response = client.request("GET", f"/repos/{base_repo}/pulls/{int(number)}")
            if response.status != 200 or not isinstance(response.body, dict):
                raise PublishError(f"pull request lookup failed with HTTP {response.status}")
            pr = response.body
            return {"state": pr.get("state"), "merged": bool(pr.get("merged")),
                    "merge_commit_sha": pr.get("merge_commit_sha"), "head_sha": (pr.get("head") or {}).get("sha")}
        finally:
            client.close()

    return push, open_pr, get_pr


def gh_publisher(store: str | Path, repo: str) -> tuple[Callable[[str, str], None], Callable[[str, str, str], dict],
                                                        Callable[[int], dict]]:
    """Construction-regime GitHub effects through the operator's authenticated ``gh`` CLI.

    Opt-in only (``publish_candidate.py --github gh``): the branch is pushed to ``repo`` itself and
    the PR is authored by the operator's account, not by the AAO GitHub Apps. It exists so the
    Self Development cycle can run end to end before the App identities are activated; the
    handover path is ``github_publisher``.
    """
    import json as _json

    store = Path(store).resolve()

    def gh(*args: str) -> str:
        proc = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, check=False)
        if proc.returncode:
            raise PublishError(f"gh {args[0]} {args[1]} failed")
        return proc.stdout

    def view(ref: str) -> dict:
        return _json.loads(gh("pr", "view", ref, "--repo", repo, "--json",
                              "number,url,state,mergedAt,mergeCommit,headRefOid"))

    def push(sha: str, branch: str) -> None:
        # Only the git credential helper comes from gh; no hooks or user config from the store.
        proc = subprocess.run(["git", "--git-dir", str(store), "-c", "credential.helper=",
                               "-c", "credential.helper=!gh auth git-credential", "push", "--quiet",
                               f"https://github.com/{repo}.git", f"{sha}:refs/heads/{branch}"],
                              capture_output=True, timeout=120, check=False, cwd="/",
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
        if proc.returncode:
            raise PublishError("git push failed")

    def open_pr(branch: str, title: str, body: str) -> dict:
        existing = _json.loads(gh("pr", "list", "--repo", repo, "--head", branch, "--state", "open",
                                  "--json", "number"))
        ref = str(existing[0]["number"]) if existing else gh(
            "pr", "create", "--repo", repo, "--base", "main", "--head", branch,
            "--title", title, "--body", body).strip().splitlines()[-1]
        pr = view(ref)
        return {"number": pr["number"], "url": pr["url"], "head_sha": pr["headRefOid"]}

    def get_pr(number: int) -> dict:
        pr = view(str(int(number)))
        return {"state": pr["state"].lower(), "merged": bool(pr["mergedAt"]),
                "merge_commit_sha": (pr.get("mergeCommit") or {}).get("oid"), "head_sha": pr["headRefOid"]}

    return push, open_pr, get_pr
