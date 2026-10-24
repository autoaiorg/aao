import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aao import fork_pr_trial as fpt

TRIAL, FORK = "autoaiorg/aao-governance-trial", "autoaiorg/aao-trial-codex"
HEAD = "a" * 40
RUNNER = Path(__file__).resolve().parents[1] / "scripts/trial/run_trial.sh"


class FakeClient:
    """Answers request(method, path) from a list of (predicate, status, body) routes; records calls."""

    def __init__(self, routes):
        self.routes, self.calls, self.app_id, self._key_path = routes, [], 1, Path("/nonexistent")

    def request(self, method, path, *, body=None):
        self.calls.append((method, path, body))
        for match, status, payload in self.routes:
            if match(method, path, body):
                return SimpleNamespace(status=status, body=payload)
        raise AssertionError(f"unexpected call {method} {path}")


BRANCH_NAME = "aao-trial/a11-p310-x"


def run(run_id, status="completed", conclusion="action_required", repo=FORK, branch=BRANCH_NAME):
    return {"id": run_id, "status": status, "conclusion": conclusion, "head_branch": branch,
            "head_repository": {"full_name": repo}}


def runs(*items):
    return lambda m, p, b: m == "GET" and "/actions/runs?" in p, 200, {"workflow_runs": list(items)}


def the_pr(sha=HEAD, repo=FORK, ref=BRANCH_NAME):
    return lambda m, p, b: m == "GET" and p.endswith("/pulls/7"), 200, {"head": {"sha": sha, "ref": ref, "repo": {"full_name": repo}}}


def jobs(count, status=200):
    return lambda m, p, b: m == "GET" and p.endswith("/jobs?filter=all"), status, {"total_count": count}


@pytest.fixture
def gate_env(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PR", "7")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_PR_HEAD", HEAD)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORK", FORK)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_BRANCH", BRANCH_NAME)
    monkeypatch.setattr(fpt, "P310_WAIT_SECONDS", 0)
    monkeypatch.setattr(fpt.time, "sleep", lambda _s: None)


def test_p310_passes_only_when_every_run_waits_for_approval_with_no_job(gate_env):
    client = FakeClient([the_pr(), runs(run(1)), jobs(0)])
    status, _reason, _ev = fpt.approval_gate(TRIAL, client)
    assert status == "PASS"


def test_p310_ignores_runs_not_bound_to_the_fork_pr_and_checks_the_pr_head(gate_env):
    for other in (run(1, repo="autoaiorg/aao-trial-claude"), run(1, branch="aao-trial/other")):
        assert fpt.approval_gate(TRIAL, FakeClient([the_pr(), runs(other), jobs(0)]))[0] == "INCONCLUSIVE"
    moved = FakeClient([the_pr(sha="b" * 40), runs(run(1)), jobs(0)])
    assert fpt.approval_gate(TRIAL, moved)[0] == "INCONCLUSIVE"
    assert not any("/actions/" in c[1] for c in moved.calls)


def test_p310_fails_when_a_run_executed_jobs_even_if_marked_action_required(gate_env):
    client = FakeClient([the_pr(), runs(run(1)), jobs(1)])
    assert fpt.approval_gate(TRIAL, client)[0] == "FAIL"


def test_p310_without_runs_or_with_ungated_runs_is_inconclusive_never_pass(gate_env):
    assert fpt.approval_gate(TRIAL, FakeClient([the_pr(), runs()]))[0] == "INCONCLUSIVE"
    queued = FakeClient([the_pr(), runs(run(1, status="queued", conclusion=None)), jobs(0)])
    assert fpt.approval_gate(TRIAL, queued)[0] == "INCONCLUSIVE"
    broken = FakeClient([the_pr(), runs(run(1)), jobs(0, status=403)])
    assert fpt.approval_gate(TRIAL, broken)[0] == "INCONCLUSIVE"


@pytest.fixture
def pr_env(monkeypatch):
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORK", FORK)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_BRANCH", "aao-trial/a11-p310-x")
    monkeypatch.setenv("AAO_TRIAL_CANDIDATE_SHA", HEAD)


def pr_body(login="aao-pm[bot]", head_repo=FORK, sha=HEAD):
    return {"number": 9, "user": {"login": login}, "head": {"sha": sha, "repo": {"full_name": head_repo}},
            "base": {"repo": {"full_name": TRIAL}}}


def test_a11_pr_must_come_from_the_fork_and_be_opened_by_aao_pm(pr_env):
    ok = FakeClient([(lambda m, p, b: m == "POST", 201, pr_body())])
    status, _r, evidence = fpt.open_pr(TRIAL, ok)
    assert status == "PASS" and {"method": "fork pull request", "number": 9, "sha": HEAD, "head_repo": FORK} in evidence
    for wrong in (pr_body(login="alessbarb"), pr_body(head_repo=TRIAL), pr_body(sha="b" * 40)):
        assert fpt.open_pr(TRIAL, FakeClient([(lambda m, p, b: m == "POST", 201, wrong)]))[0] == "FAIL"


def test_a11_retries_head_repo_format_only_after_422_and_records_both(pr_env):
    client = FakeClient([(lambda m, p, b: b["head_repo"] == "aao-trial-codex", 422, {"message": "Validation Failed"}),
                         (lambda m, p, b: b["head_repo"] == FORK, 201, pr_body())])
    assert fpt.open_pr(TRIAL, client)[0] == "PASS"
    assert [c[2]["head_repo"] for c in client.calls] == ["aao-trial-codex", FORK]


@pytest.fixture
def fork_repo(tmp_path, monkeypatch):
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("x")
    subprocess.run([*git, "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run([*git, "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/test.yml").write_text("on: pull_request\n")
    subprocess.run([*git, "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run([*git, "-C", str(tmp_path), "commit", "-qm", "workflow"], check=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AAO_GITHUB_TRIAL_BRANCH", "aao-trial/a11-p310-x")
    monkeypatch.setattr(fpt, "create_jwt", lambda *_a: "jwt")
    return tmp_path


def fork_client(installation_status):
    client = FakeClient([(lambda m, p, b: p == f"/repos/{FORK}", 200, {"parent": {"full_name": TRIAL}})])
    client._request = lambda method, path, *, token, body=None: SimpleNamespace(status=installation_status, body={})
    return client


def test_fork_branch_refuses_to_push_when_implementer_is_installed_on_protected_repo(fork_repo, monkeypatch):
    pushed = []
    monkeypatch.setattr(fpt, "_git_push", lambda *a, **k: pushed.append(a) or {"exit_code": 0})
    status, _r, _e = fpt.fork_branch(FORK, TRIAL, fork_client(200))
    assert status == "FAIL" and pushed == []


def test_fork_branch_passes_when_pushed_ref_matches_and_no_installation(fork_repo, monkeypatch):
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    monkeypatch.setattr(fpt, "_git_push", lambda *a, **k: {"exit_code": 0})
    client = fork_client(404)
    client.routes.append((lambda m, p, b: "/git/ref/heads/" in p, 200, {"object": {"sha": head}}))
    assert fpt.fork_branch(FORK, TRIAL, client)[0] == "PASS"


def test_steps_are_bound_to_their_roles_and_never_the_canonical_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AAO_GITHUB_TRIAL_REPOS", f"{TRIAL},autoaiorg/aao")
    monkeypatch.setenv("AAO_GITHUB_TRIAL_FORK_PARENT", TRIAL)
    monkeypatch.setattr(fpt, "GitHubAppClient", lambda *_a: pytest.fail("no credential may be loaded"))
    assert fpt.main(["A-11", "--repo", TRIAL, "--role", "aao-impl-codex"]) == 2
    assert fpt.main(["P3-10", "--repo", TRIAL, "--role", "aao-pm"]) == 2
    assert fpt.main(["FORK-BRANCH", "--repo", TRIAL, "--role", "aao-supervisor"]) == 2
    assert fpt.main(["A-11", "--repo", "autoaiorg/aao", "--role", "aao-pm"]) == 2


def test_runner_separates_creation_from_approval_check_under_distinct_uids():
    source = RUNNER.read_text()
    assert 'fork_step "$impl_uid" FORK-BRANCH "$fork" "$impl"' in source
    assert 'fork_step "${APP_UID[aao-pm]}" A-11 "$REPO" aao-pm' in source
    assert 'fork_step "${APP_UID[aao-supervisor]}" P3-10 "$REPO" aao-supervisor' in source
    assert source.index("FORK-BRANCH \"$fork\"") < source.index("A-11 \"$REPO\"") < source.index("P3-10 \"$REPO\"")
    assert "for id in A-07 A-08 A-13 P3-04 P3-08 P3-11; do" in source
    assert "from aao.fork_pr_trial import main" in source
    assert 'AAO_GITHUB_TRIAL_FORK="$fork" AAO_GITHUB_TRIAL_BRANCH="$fork_branch"' in source.split('P3-10 "$REPO"', 1)[1].splitlines()[0]
    assert '".config/systemd/user"' in source and '".config/environment.d"' in source
