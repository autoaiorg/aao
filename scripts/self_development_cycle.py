#!/usr/bin/env python3
"""Drive one Self Development cycle on the development instance, one role per step.

  setup   (CEO)          issue implementer/auditor/publisher credentials with scoped 8h grants,
                         register the agent-runner capability; tokens go only to private runtime files
  task    (implementer)  create a task, select the capability, admit it and stage an agent run
  submit  (implementer)  after a SUCCEEDED run: register its check output as evidence, move to review
  review  (auditor)      APPROVE or REJECT exactly the tested candidate SHA
  verify  (read-only)    print the task's whole chain from PostgreSQL and check its consistency

The agent run itself is scripts/run_self_development_worker.py; publication and the result are
scripts/publish_candidate.py --step push|open|reconcile. Everything goes through the same API and
PostgreSQL state that the Control Center reads. Tokens are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
API = os.environ.get("AAO_API", "http://127.0.0.1:8001")
TOKENS = {"implementer": "aao-self-development-agent.token", "auditor": "aao-auditor.token",
          "publisher": "aao-publisher.token"}
CAPABILITY = {"capability_id": "aao.agent-runner", "version": "1.0.0"}


def call(path: str, *, method: str = "GET", headers: dict | None = None, body: dict | None = None):
    request = Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                      headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"null")
    except HTTPError as exc:
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from None


def runtime_dir() -> Path:
    directory = Path(os.environ["XDG_RUNTIME_DIR"])
    if directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
        raise SystemExit("XDG_RUNTIME_DIR must be private to this user")
    return directory


def save_token(role: str, token: str) -> None:
    path = runtime_dir() / TOKENS[role]
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(token + "\n")
    os.replace(temporary, path)


def token(role: str) -> str:
    from run_self_development_worker import _read_agent_token
    return _read_agent_token(TOKENS[role])


def agent(role: str = "implementer") -> dict:
    return {"X-Agent-Token": token(role)}


def setup(project_id: str) -> None:
    ceo = {"X-CEO-Token": os.environ["AAO_CEO_TOKEN"]}
    expiry = (datetime.now(UTC) + timedelta(hours=8)).isoformat()
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
    roles = {
        "implementer": ("AGENT", ("project.read", "work.create", "work.admit", "work.progress", "execution.claim",
                                  "code.propose", "evidence.submit")),
        "auditor": ("AUDITOR", ("work.review",)),
        "publisher": ("AGENT", ("project.read", "code.publish")),
    }
    for role, (kind, grants) in roles.items():
        principal = f"aao-{role}-{stamp}"
        issued = call("/v1/principals/credentials", method="POST", headers=ceo,
                      body={"principal_id": principal, "kind": kind})
        save_token(role, issued["token"])
        for capability in grants:
            call(f"/v1/projects/{project_id}/grants", method="POST", headers=ceo,
                 body={"principal_id": principal, "capability": capability, "expires_at": expiry})
        print(f"{role}: {principal} ({kind}) grants={','.join(grants)} until {expiry}")
    existing = call(f"/v1/projects/{project_id}/capabilities?capability_type=agent", headers=agent())
    if not any(c.get("capability_id") == CAPABILITY["capability_id"] for c in existing):
        call(f"/v1/projects/{project_id}/capabilities", method="POST", headers=agent(), body={
            **CAPABILITY, "capability_type": "agent", "provenance": {"kind": "repository", "path": "src/aao/agent_runner.py"},
            "contract": {"purpose": "Turn a task into a tested candidate and patch proposal",
                         "entrypoint": "aao.agent_runner:patch", "inputs": ["task", "base_sha"],
                         "outputs": ["patch proposal", "candidate commit", "sandbox check"], "platform": "Linux",
                         "authority_boundary": "edits only a disposable clone; proposes, never applies or merges",
                         "compatible_roles": ["implementer"]},
            "required_permissions": ["execution.claim", "code.propose"],
            "risks": ["agent edits a disposable clone"], "dependencies": [],
            "tests": ["tests/test_agent_runner.py", "tests/test_project_workflow_integration.py"],
            "compatibility": {}, "evidence": ["src/aao/agent_runner.py"]})
        print("registered capability aao.agent-runner 1.0.0")


def task(project_id: str, title: str, description: str, criteria: list[str], base_sha: str) -> None:
    work = call(f"/v1/projects/{project_id}/work", method="POST", headers=agent(), body={
        "title": title, "description": description, "acceptance_criteria": criteria,
        "author_id": principal_of("implementer")})["id"]
    call(f"/v1/projects/{project_id}/capability-evaluations", method="POST", headers=agent(), body={
        "task_id": work, **CAPABILITY,
        "options": [{"choice": c, "fit": f, "security": f, "cost": f, "time": f, "tokens": f, "maintenance": f}
                    for c, f in (("reuse", 5), ("adapt", 3), ("build", 1))],
        "rationale": "The registered agent runner covers patch, candidate and sandbox check.",
        "evidence": ["src/aao/agent_runner.py"]})
    call(f"/v1/work/{work}/admit", method="POST", headers=agent())
    staged = call(f"/v1/work/{work}/stage-agent-run", method="POST", headers=agent(),
                  body={**CAPABILITY, "base_sha": base_sha})
    call(f"/v1/work/{work}/progress", method="POST", headers=agent())
    print(json.dumps({"work_id": work, "execution_id": staged["execution_id"], "status": "IN_PROGRESS"}))


def latest_success(project_id: str, work_id: str) -> dict:
    board = call(f"/v1/projects/{project_id}/board", headers=agent())
    item = next(i for i in board if str(i["id"]) == work_id)
    runs = [e for e in item["executions"] if e["status"] == "SUCCEEDED" and e["result"].get("candidate_sha")]
    if not runs:
        raise SystemExit("no SUCCEEDED execution with a candidate for this work")
    return runs[-1]["result"]


def submit(project_id: str, work_id: str) -> None:
    from aao.evidence_registry import register_evidence
    result = latest_success(project_id, work_id)
    check = result["check"]
    record = json.dumps({"candidate_sha": result["candidate_sha"], "check": {k: check.get(k) for k in (
        "check_id", "extra_tests", "conclusion", "exit_code", "duration_ms", "stdout", "stderr", "limits")}},
        sort_keys=True).encode()
    evidence = register_evidence(project_id, record, agent_id=principal_of("implementer"),
                                 agent_credential=token("implementer"), media_type="application/json")
    call(f"/v1/work/{work_id}/progress", method="POST", headers=agent())
    print(json.dumps({"work_id": work_id, "status": "IN_REVIEW", "candidate_sha": result["candidate_sha"],
                      "evidence": evidence}))


def principal_of(role: str) -> str:
    return call("/v1/principals/me", headers=agent(role))["principal_id"]


def review(project_id: str, work_id: str, decision: str, evidence: str) -> None:
    result = latest_success(project_id, work_id)
    reviewed = call(f"/v1/work/{work_id}/reviews", method="POST", headers={"X-Auditor-Token": token("auditor")},
                    body={"decision": decision, "candidate_sha": result["candidate_sha"], "evidence": [evidence]})
    print(json.dumps(reviewed))


def verify(project_id: str, work_id: str) -> int:
    """Read the whole chain for one task straight from PostgreSQL and check that it is consistent."""
    from aao.postgresql_connection import connect_postgres
    problems: list[str] = []
    with connect_postgres() as db:
        work = db.execute("SELECT w.title,w.status,w.author_id,c.kind FROM work_items w LEFT JOIN principal_credentials c "
                          "ON c.principal_id=w.author_id WHERE w.id=%s AND w.project_id=%s", (work_id, project_id)).fetchone()
        if not work:
            raise SystemExit("work not found in this project")
        kinds = dict(db.execute("SELECT principal_id,kind FROM principal_credentials").fetchall())
        runs = db.execute("SELECT id,status,worker_id,result_json,created_at FROM execution_queue WHERE work_id=%s "
                          "ORDER BY created_at", (work_id,)).fetchall()
        proposals = db.execute("SELECT id,proposer_id,base_sha,patch_sha256,changed_paths FROM patch_proposals "
                               "WHERE work_id=%s ORDER BY created_at", (work_id,)).fetchall()
        reviews = db.execute("SELECT id,reviewer_id,decision,candidate_sha,evidence FROM reviews WHERE work_id=%s "
                             "ORDER BY created_at", (work_id,)).fetchall()
        evidence = {d: (s, m) for d, s, m in db.execute(
            "SELECT digest,submitted_by,media_type FROM evidence_artifacts WHERE project_id=%s", (project_id,)).fetchall()}
        events = db.execute("SELECT kind,details,created_at FROM events WHERE subject_id=%s AND kind IN "
                            "('work.candidate_pushed','work.pr_opened','work.pr_closed','work.completed',"
                            "'work.resolved_outside_cycle') ORDER BY created_at", (work_id,)).fetchall()
    title, status, author, author_kind = work
    print(f"TASK {work_id} [{status}] {title}\n  author {author} ({author_kind})")
    for rid, rstatus, worker, result, _ in runs:
        result = result or {}
        check = result.get("check") or {}
        print(f"  EXECUTION {rid} {rstatus} worker={worker} ({kinds.get(worker)}) backend={result.get('backend')} "
              f"candidate={result.get('candidate_sha')} check={check.get('conclusion')} proposal={result.get('proposal_id')}")
    for pid, proposer, base, digest, paths in proposals:
        print(f"  PROPOSAL {pid} by {proposer} base={base[:12]} patch_sha256={digest[:16]} paths={paths}")
    for rid, reviewer, decision, sha, refs in reviews:
        print(f"  REVIEW {rid} {decision} by {reviewer} ({kinds.get(reviewer)}) candidate={sha}")
        for ref in refs or []:
            stored = evidence.get(str(ref).removeprefix("sha256:"))
            print(f"    evidence {ref}: " + (f"stored, submitted by {stored[0]} ({stored[1]})" if stored else "MISSING"))
            if not stored:
                problems.append(f"review {rid} cites missing evidence {ref}")
        if decision == "APPROVE" and not any(r[1] == "SUCCEEDED" and (r[3] or {}).get("candidate_sha") == sha for r in runs):
            problems.append(f"approval {rid} has no SUCCEEDED execution of {sha}")
    for kind, details, created in events:
        keys = {k: details.get(k) for k in ("pr_number", "candidate_sha", "merge_commit_sha", "publisher", "pusher",
                                            "reconciled_by", "resolved_by", "reason") if k in details}
        print(f"  EVENT {created:%Y-%m-%d %H:%M:%S} {kind} {json.dumps(keys)}")
    completed = [d for k, d, _ in events if k == "work.completed"]
    if status == "DONE" and not completed and not any(k == "work.resolved_outside_cycle" for k, _, _ in events):
        problems.append("DONE without work.completed or a CEO resolution")
    for done in completed:
        approved = [r[3] for r in reviews if r[2] == "APPROVE"]
        if not approved or done.get("candidate_sha") != approved[-1]:
            problems.append("completed candidate is not the latest approved SHA")
    print("CONSISTENT" if not problems else "INCONSISTENT:\n  " + "\n  ".join(problems))
    return 0 if not problems else 1


def main() -> int:
    os.environ.setdefault("AAO_ENV", "development")
    os.environ.setdefault("AAO_ENV_FILE", ".env.local")
    os.chdir(ROOT)
    from aao.environment_settings import load_local_env
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True)
    sub = parser.add_subparsers(dest="step", required=True)
    sub.add_parser("setup")
    t = sub.add_parser("task")
    t.add_argument("--title", required=True)
    t.add_argument("--description", required=True)
    t.add_argument("--criterion", action="append", required=True)
    t.add_argument("--base-sha", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--work-id", required=True)
    r = sub.add_parser("review")
    r.add_argument("--work-id", required=True)
    r.add_argument("--decision", choices=("APPROVE", "REJECT"), required=True)
    r.add_argument("--evidence", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--work-id", required=True)
    args = parser.parse_args()
    if args.step == "verify":
        return verify(args.project_id, args.work_id)
    if args.step == "setup":
        setup(args.project_id)
    elif args.step == "task":
        task(args.project_id, args.title, args.description, args.criterion, args.base_sha)
    elif args.step == "submit":
        submit(args.project_id, args.work_id)
    else:
        review(args.project_id, args.work_id, args.decision, args.evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
