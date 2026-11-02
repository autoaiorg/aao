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
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from aao.host_identity import HostIdentityError, current_host_id

_SHA = re.compile(r"^[0-9a-f]{40}$")
_EFFECT_LEASE_SECONDS = 180


class PublishError(RuntimeError):
    pass


def _publish_operation_id(step: str, work_id: str, candidate_sha: str) -> str:
    value = f"{step}:{work_id}:{candidate_sha}".encode()
    return hashlib.sha256(value).hexdigest()


def _record_publish_event(work_id: str, kind: str, details: dict) -> None:
    from aao.work_management_api import audit, tx

    with tx() as db:
        audit(db, work_id, kind, details)


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
    # Capture the decision and host fence briefly. Effect reservations are durable;
    # never hold a database transaction across the remote GitHub call.
    work = db.execute("SELECT project_id,status,author_id,title FROM work_items WHERE id=%s",
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
    # A GitHub publisher is also an external-effect worker. Validate its current
    # binding before authorizing each attempt. A later fence cannot revoke a call
    # already dispatched to GitHub; it does prevent a retry/new effect.
    registry = db.execute("SELECT to_regclass('public.host_worker_bindings')").fetchone()
    if not registry or registry[0] is None:
        raise PublishError("host fencing registry unavailable; publication rejected")
    try:
        local_host_id = current_host_id()
    except HostIdentityError as exc:
        raise PublishError("trusted local host identity unavailable; publication rejected") from exc
    bindings = db.execute(
        "SELECT host_id,status,fence_epoch FROM host_worker_bindings "
        "WHERE worker_id=%s ORDER BY created_at DESC", (str(principal),)
    ).fetchall()
    active = [row for row in bindings if row[1] == "ACTIVE"]
    if len(active) != 1:
        raise PublishError("publisher must have exactly one active host binding")
    host_id, _status, fence_epoch = active[0]
    if host_id != local_host_id:
        raise PublishError("publisher binding belongs to a different host")
    if not isinstance(fence_epoch, int) or fence_epoch < 1:
        raise PublishError("publisher host fencing epoch is invalid")
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
    if status != "VERIFIED":
        raise PublishError("only VERIFIED work can be published")
    if db.execute("SELECT 1 FROM reviews WHERE work_id=%s AND decision='VETO' LIMIT 1", (work_id,)).fetchone():
        raise PublishError("an active veto blocks publication")
    if kind_of_step in events:
        return {"done": events[kind_of_step]}
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


def _effect_key(work_id: str, candidate_sha: str, operation: str) -> str:
    stable = f"aao-publication:v1:{work_id}:{candidate_sha}:{operation}"
    if len(stable) <= 200:
        return stable
    digest = hashlib.sha256(stable.encode()).hexdigest()
    return f"aao-publication:v1:{digest}"


def _reserve_effect(db, c: dict, work_id: str, operation: str) -> dict:
    """Commit a durable attempt authorization before making a remote call."""
    from uuid import uuid4

    effect_key = _effect_key(work_id, c["candidate_sha"], operation)
    row = db.execute(
        "SELECT id,status,attempt_id,lease_expires_at,result,attempts FROM work_publication_effects "
        "WHERE work_id=%s AND candidate_sha=%s AND operation=%s FOR UPDATE",
        (work_id, c["candidate_sha"], operation),
    ).fetchone()
    if not row:
        raise PublishError("publication effect reservation disappeared")
    effect_id, status, _old_attempt, expiry, result, attempts = row
    if status == "COMPLETED":
        return {"completed": result}
    if status == "IN_PROGRESS":
        live = db.execute("SELECT %s > clock_timestamp()", (expiry,)).fetchone()[0]
        if live:
            return {"busy": True, "effect_key": effect_key}
        db.execute(
            "UPDATE work_publication_effects SET status='UNCERTAIN',attempt_id=NULL,lease_expires_at=NULL,"
            "error_class=COALESCE(error_class,'AttemptLeaseExpired'),updated_at=clock_timestamp() WHERE id=%s",
            (effect_id,),
        )
    attempt_id = str(uuid4())
    db.execute(
        "UPDATE work_publication_effects SET status='IN_PROGRESS',attempt_id=%s,attempts=attempts+1,"
        "lease_expires_at=clock_timestamp()+(%s * interval '1 second'),error_class=NULL,"
        "updated_at=clock_timestamp() WHERE id=%s",
        (attempt_id, _EFFECT_LEASE_SECONDS, effect_id),
    )
    from aao.work_management_api import audit
    audit(db, work_id, "work.publication_effect", {
        "effect_key": effect_key, "operation": operation, "status": "IN_PROGRESS",
        "attempt": attempts + 1, "candidate_sha": c["candidate_sha"],
    })
    return {"effect_id": str(effect_id), "attempt_id": attempt_id,
            "effect_key": effect_key, "attempt": attempts + 1}


def _finish_effect(work_id: str, operation: str, reservation: dict, *,
                   result: dict | None = None, error: Exception | None = None) -> None:
    """Record the known result in a new short transaction; ambiguity remains UNCERTAIN."""
    from aao.work_management_api import audit, tx

    final_status = "UNCERTAIN" if error is not None else "COMPLETED"
    safe_result = result or {}
    error_class = type(error).__name__ if error is not None else None
    with tx() as db:
        updated = db.execute(
            "UPDATE work_publication_effects SET status=%s,attempt_id=NULL,lease_expires_at=NULL,"
            "result=%s::jsonb,error_class=%s,updated_at=clock_timestamp() "
            "WHERE id=%s AND status='IN_PROGRESS' AND attempt_id=%s RETURNING id",
            (final_status, json.dumps(safe_result), error_class,
             reservation["effect_id"], reservation["attempt_id"]),
        ).fetchone()
        if not updated:
            existing = db.execute(
                "SELECT status FROM work_publication_effects WHERE id=%s FOR UPDATE",
                (reservation["effect_id"],),
            ).fetchone()
            if existing and existing[0] == "COMPLETED" and error is None:
                return
            raise PublishError("publication effect attempt was superseded before reconciliation")
        audit(db, work_id, "work.publication_effect", {
            "effect_key": reservation["effect_key"], "operation": operation,
            "status": final_status, "attempt": reservation["attempt"],
            "candidate_sha": safe_result.get("candidate_sha"),
            "error_class": error_class,
        })
        if error is None:
            event_kind = "work.candidate_pushed" if operation == "PUSH_CANDIDATE" else "work.pr_opened"
            audit(db, work_id, event_kind, safe_result)


def _prepare_effect(work_id: str, credential: str, operation: str) -> tuple[dict, dict]:
    from uuid import uuid4

    from aao.work_management_api import tx

    kind = "work.candidate_pushed" if operation == "PUSH_CANDIDATE" else "work.pr_opened"
    with tx() as db:
        candidate = _approved_candidate(db, work_id, credential, kind)
        if "done" in candidate:
            return candidate, {"completed": candidate["done"]}
        if operation == "OPEN_PULL_REQUEST":
            pushed = candidate.get("pushed")
            if not pushed or pushed["candidate_sha"] != candidate["candidate_sha"]:
                raise PublishError("the approved candidate has not been pushed")
        effect_key = _effect_key(work_id, candidate["candidate_sha"], operation)
        db.execute(
            "INSERT INTO work_publication_effects(id,work_id,candidate_sha,operation,effect_key,status) "
            "VALUES (%s,%s,%s,%s,%s,'PENDING') ON CONFLICT (work_id,candidate_sha,operation) DO NOTHING",
            (str(uuid4()), work_id, candidate["candidate_sha"], operation, effect_key),
        )
    # The durable PENDING intent commits independently. Re-authorize under fresh locks
    # before transitioning to IN_PROGRESS and releasing the transaction for remote I/O.
    with tx() as db:
        candidate = _approved_candidate(db, work_id, credential, kind)
        if "done" in candidate:
            return candidate, {"completed": candidate["done"]}
        if operation == "OPEN_PULL_REQUEST":
            pushed = candidate.get("pushed")
            if not pushed or pushed["candidate_sha"] != candidate["candidate_sha"]:
                raise PublishError("the approved candidate has not been pushed")
        reservation = _reserve_effect(db, candidate, work_id, operation)
    return candidate, reservation


def push_candidate(work_id: str, credential: str, *, store: str | Path,
                   push: Callable[[str, str], None]) -> dict:
    """Step 1 (implementer identity): verify the approved commit in the store and push exactly that SHA."""
    from aao.work_management_api import tx

    with tx() as db:
        c = _approved_candidate(db, work_id, credential, "work.candidate_pushed")
        if "done" in c:
            return {**c["done"], "status": "ALREADY_PUSHED"}
        candidate_data = c
    verify_candidate(Path(store).resolve(), candidate_data["candidate_sha"], candidate_data["base_sha"],
                     candidate_data["patch"])
    c, reservation = _prepare_effect(work_id, credential, "PUSH_CANDIDATE")
    if "done" in c:
        return {**c["done"], "status": "ALREADY_PUSHED"}
    if "completed" in reservation:
        return {**reservation["completed"], "status": "ALREADY_PUSHED"}
    if reservation.get("busy"):
        return {"status": "IN_PROGRESS", "effect_key": reservation["effect_key"],
                "candidate_sha": c["candidate_sha"]}
    branch = f"aao/work-{work_id}-{c['candidate_sha'][:12]}"
    operation_id = _publish_operation_id("candidate-push", work_id, c["candidate_sha"])
    effect = {"operation_id": operation_id, "candidate_sha": c["candidate_sha"], "branch": branch,
              "pusher": c["principal"]}
    record = {"candidate_sha": c["candidate_sha"], "base_sha": c["base_sha"], "branch": branch,
              "proposal_id": c["proposal_id"], "review_id": c["review_id"], "pusher": c["principal"],
              "operation_id": operation_id, "effect_key": reservation["effect_key"]}
    _record_publish_event(work_id, "work.candidate_push_started", effect)
    try:
        # Stable branch/SHA makes a retry after uncertain push reconcile idempotently.
        push(c["candidate_sha"], branch)
    except Exception as exc:
        _finish_effect(work_id, "PUSH_CANDIDATE", reservation, error=exc)
        _record_publish_event(work_id, "work.candidate_push_uncertain", effect)
        raise PublishError("candidate push outcome is uncertain; retry the same approved SHA to reconcile") from exc
    _finish_effect(work_id, "PUSH_CANDIDATE", reservation, result=record)
    return {**record, "status": "PUSHED"}


def open_pull_request(work_id: str, credential: str, *, open_pr: Callable[[str, str, str], dict]) -> dict:
    """Step 2 (PM identity): open the PR for the branch pushed in step 1, if it still holds the approved SHA."""
    c, reservation = _prepare_effect(work_id, credential, "OPEN_PULL_REQUEST")
    if "done" in c:
        return {**c["done"], "status": "ALREADY_PUBLISHED"}
    if "completed" in reservation:
        return {**reservation["completed"], "status": "ALREADY_PUBLISHED"}
    if reservation.get("busy"):
        return {"status": "IN_PROGRESS", "effect_key": reservation["effect_key"],
                "candidate_sha": c["candidate_sha"]}
    pushed = c["pushed"]
    operation_id = _publish_operation_id("pull-request", work_id, c["candidate_sha"])
    effect = {"operation_id": operation_id, "candidate_sha": c["candidate_sha"],
              "branch": pushed["branch"], "publisher": c["principal"]}
    _record_publish_event(work_id, "work.pr_open_started", effect)
    body = (f"AAO work `{work_id}`\n\n- candidate: `{c['candidate_sha']}` on base `{c['base_sha']}`\n"
            f"- proposal: `{c['proposal_id']}`\n- approval review: `{c['review_id']}`\n"
            f"- effect key: `{reservation['effect_key']}`\n"
            f"- pushed by: `{pushed['pusher']}`; opened by: `{c['principal']}`\n")
    try:
        # The adapter must look up this stable branch/key before creating a new PR.
        pr = open_pr(pushed["branch"], f"aao: {c['title']}", body)
    except Exception as exc:
        _finish_effect(work_id, "OPEN_PULL_REQUEST", reservation, error=exc)
        _record_publish_event(work_id, "work.pr_open_uncertain", effect)
        raise PublishError("pull request outcome is uncertain; retry to reconcile the same branch") from exc
    if pr.get("head_sha") != c["candidate_sha"]:
        # The fork branch moved after the push: never record an unapproved head as this task's PR.
        mismatch = PublishError("opened pull request head is not the approved candidate")
        _finish_effect(work_id, "OPEN_PULL_REQUEST", reservation, error=mismatch)
        raise mismatch
    record = {**pushed, "publisher": c["principal"], "pr_number": int(pr["number"]),
              "pr_url": str(pr["url"]), "operation_id": operation_id,
              "effect_key": reservation["effect_key"]}
    _finish_effect(work_id, "OPEN_PULL_REQUEST", reservation, result=record)
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
    _require_current_published_candidate(work_id, record)
    pr = get_pr(int(record["pr_number"]))
    if pr.get("head_sha") != record["candidate_sha"]:
        raise PublishError("pull request head no longer matches the approved candidate")
    if not pr.get("merged"):
        if pr.get("state") == "open":
            return {"status": "OPEN", "pr_number": record["pr_number"]}
        # Closed without merge: the approved candidate was not accepted; the work goes back to
        # IN_PROGRESS so a new attempt can be run, reviewed and published.
        with tx() as db:
            current_work = db.execute("SELECT status FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
            if not current_work or current_work[0] != "VERIFIED":
                raise PublishError("work is no longer VERIFIED")
            _require_current_published_candidate_in_transaction(db, work_id, record)
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
        current_work = db.execute("SELECT status FROM work_items WHERE id=%s FOR UPDATE", (work_id,)).fetchone()
        if not current_work or current_work[0] != "VERIFIED":
            raise PublishError("work is no longer VERIFIED")
        _require_current_published_candidate_in_transaction(db, work_id, record)
        updated = db.execute("UPDATE work_items SET status='DONE' WHERE id=%s AND status='VERIFIED' RETURNING id",
                             (work_id,)).fetchone()
        if not updated:
            raise PublishError("work is no longer VERIFIED")
        audit(db, work_id, "work.completed", result)
    return {**result, "status": "DONE"}


def _require_current_published_candidate(work_id: str, record: dict) -> None:
    """Refuse reconciliation if the PR no longer matches the currently approved execution."""
    from aao.work_management_api import tx

    with tx() as db:
        _require_current_published_candidate_in_transaction(db, work_id, record)


def _require_current_published_candidate_in_transaction(db, work_id: str, record: dict) -> None:
    current_review = db.execute(
        "SELECT id,candidate_sha FROM reviews WHERE work_id=%s AND decision='APPROVE' "
        "ORDER BY created_at DESC LIMIT 1", (work_id,),
    ).fetchone()
    if (not current_review or str(current_review[0]) != str(record.get("review_id"))
            or current_review[1] != record.get("candidate_sha")):
        raise PublishError("published pull request no longer matches the current approved candidate")
    current_execution = db.execute(
        "SELECT 1 FROM execution_queue q JOIN patch_proposals p "
        "ON p.id::text=q.result_json->>'proposal_id' AND p.work_id=q.work_id "
        "WHERE q.work_id=%s AND q.status='SUCCEEDED' AND q.result_json->>'candidate_sha'=%s "
        "AND p.id::text=%s LIMIT 1",
        (work_id, record.get("candidate_sha"), record.get("proposal_id")),
    ).fetchone()
    if not current_execution:
        raise PublishError("published pull request no longer matches a succeeded candidate execution")


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
            # Include closed PRs: a lost response followed by a close must not
            # create a duplicate for this deterministic branch/effect key.
            existing = client.request("GET", f"/repos/{base_repo}/pulls?state=all&head={head}")
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
        existing = _json.loads(gh("pr", "list", "--repo", repo, "--head", branch, "--state", "all",
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
