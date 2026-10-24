import copy
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/governance/canonical_protection.py"
spec = importlib.util.spec_from_file_location("canonical_protection", SCRIPT)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


class FakeGh:
    """In-memory rulesets API recording writes."""

    def __init__(self, rulesets=(), login="alessbarb"):
        self.login = login
        self.store = {i + 1: {**copy.deepcopy(r), "id": i + 1} for i, r in enumerate(rulesets)}
        self.writes = []

    def __call__(self, method, path, body):
        if method == "GET" and path == "user":
            return {"login": self.login}
        if method == "GET" and "/rulesets?" in path:
            return [{"id": i, "name": r["name"]} for i, r in self.store.items()]
        if method == "GET" and "/rulesets/" in path:
            return copy.deepcopy(self.store[int(path.rsplit("/", 1)[1])])
        if method == "POST":
            new = max(self.store, default=0) + 1
            self.store[new] = {**copy.deepcopy(body), "id": new}
        elif method == "PUT" and "/rulesets/" in path:
            ident = int(path.rsplit("/", 1)[1])
            self.store[ident] = {**copy.deepcopy(body), "id": ident}
        self.writes.append((method, path))
        return {}


def test_apply_on_empty_repo_creates_three_rulesets_that_verify():
    gh = FakeGh()
    assert cp.apply(gh, "autoaiorg/aao") == []
    assert [w[0] for w in gh.writes] == ["POST", "POST", "POST"]
    assert cp.main(["--repo", "autoaiorg/aao", "verify"], gh=gh) == 0


def test_test_check_must_come_from_github_actions_and_aao_audit_from_auditor():
    b = next(r for r in cp.desired() if r["name"].startswith("B "))
    checks = b["rules"][2]["parameters"]["required_status_checks"]
    assert {"context": "aao-audit", "integration_id": 5448107} in checks
    assert {"context": "test", "integration_id": 15368} in checks


def test_verify_detects_each_weakening():
    def weakened(mutate):
        rulesets = copy.deepcopy(cp.desired())
        mutate({r["name"][0]: r for r in rulesets})
        return cp.verify(FakeGh(rulesets), "autoaiorg/aao-governance-trial")

    assert weakened(lambda r: r["A"].update(enforcement="disabled"))
    assert weakened(lambda r: r["B"]["bypass_actors"].append({"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}))
    assert weakened(lambda r: r["A"]["bypass_actors"].append({"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}))
    assert weakened(lambda r: r["B"]["rules"][2]["parameters"]["required_status_checks"].pop())
    assert weakened(lambda r: r["B"]["rules"][2]["parameters"]["required_status_checks"][1].pop("integration_id"))
    assert weakened(lambda r: r["B"]["rules"].pop(0))
    assert weakened(lambda r: r["B"]["conditions"]["ref_name"]["include"].remove("refs/heads/aao-staging/**"))
    assert weakened(lambda r: r["C"].update(target="branch"))
    assert not weakened(lambda r: None)


def test_apply_repairs_a_drifted_ruleset_in_place_and_reports_unexpected_ones():
    rulesets = copy.deepcopy(cp.desired())
    rulesets[1]["bypass_actors"] = [{"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}]
    gh = FakeGh([*rulesets, {"name": "legacy", "target": "branch"}])
    problems = cp.apply(gh, "autoaiorg/aao-governance-trial")
    assert ("PUT", "repos/autoaiorg/aao-governance-trial/rulesets/2") in gh.writes and not any(w[0] == "POST" for w in gh.writes)
    assert problems == ["unexpected ruleset (remove it or add it to this script after review): legacy"]
    assert cp.main(["--repo", "autoaiorg/aao-governance-trial", "verify"], gh=gh) == 1  # verify proves the applicable set is exactly A, B, C


def test_writes_require_the_ceo_login_and_an_allowlisted_repo():
    import pytest
    agent = FakeGh(login="aao-impl-codex[bot]")
    assert cp.main(["--repo", "autoaiorg/aao", "apply"], gh=agent) == 2 and not agent.writes
    assert cp.main(["--repo", "autoaiorg/aao", "approval"], gh=agent) == 2 and not agent.writes
    with pytest.raises(SystemExit):
        cp.main(["--repo", "someone/else", "verify"], gh=FakeGh())
