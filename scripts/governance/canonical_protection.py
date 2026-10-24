#!/usr/bin/env python3
"""Rulesets A/B/C (P3) and the fork-PR approval policy for a repository, through the CEO's `gh` login.

Run as the CEO (repository admin), never as root and never as an agent:
  python3 -I scripts/governance/canonical_protection.py --repo autoaiorg/aao plan     # read-only
  python3 -I scripts/governance/canonical_protection.py --repo autoaiorg/aao verify   # read-only, exit 1 on drift
  python3 -I scripts/governance/canonical_protection.py --repo autoaiorg/aao apply    # create/update, then verify
  python3 -I scripts/governance/canonical_protection.py --repo autoaiorg/aao approval # set all_external_contributors

The rulesets reproduce the ones verified in the P2/P3 trial (autoaiorg/aao-governance-trial 25776805-07),
with one tightening: `test` must come from GitHub Actions (app 15368), as RA-02 registers it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

INTEGRATOR_APP = 5447984
AUDITOR_APP = 5448107
ACTIONS_APP = 15368
APPROVAL_POLICY = "all_external_contributors"
ALLOWED_REPOS = {"autoaiorg/aao", "autoaiorg/aao-governance-trial"}
CEO_LOGIN = "alessbarb"

Gh = Callable[[str, str, Any], Any]


def desired() -> list[dict[str, Any]]:
    integrator = [{"actor_id": INTEGRATOR_APP, "actor_type": "Integration", "bypass_mode": "always"}]
    return [
        {"name": "A main: integrator only", "target": "branch", "enforcement": "active",
         "bypass_actors": integrator,
         "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
         "rules": [{"type": "update"},
                   {"type": "pull_request", "parameters": {
                       "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                       "require_code_owner_review": False, "require_last_push_approval": False,
                       "required_review_thread_resolution": False}}]},
        {"name": "B main+staging: integrity (no bypass)", "target": "branch", "enforcement": "active",
         "bypass_actors": [],
         "conditions": {"ref_name": {"include": ["refs/heads/main", "refs/heads/aao-staging/**"], "exclude": []}},
         "rules": [{"type": "non_fast_forward"}, {"type": "deletion"},
                   {"type": "required_status_checks", "parameters": {
                       "strict_required_status_checks_policy": False, "do_not_enforce_on_create": False,
                       "required_status_checks": [{"context": "aao-audit", "integration_id": AUDITOR_APP},
                                                  {"context": "test", "integration_id": ACTIONS_APP}]}}]},
        {"name": "C tags", "target": "tag", "enforcement": "active", "bypass_actors": integrator,
         "conditions": {"ref_name": {"include": ["~ALL"], "exclude": []}},
         "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}]},
    ]


def shape(ruleset: dict[str, Any]) -> dict[str, Any]:
    """The security-relevant shape of a ruleset; anything outside it is ignored when comparing."""
    rules = {}
    for rule in ruleset.get("rules") or []:
        params = rule.get("parameters") or {}
        if rule.get("type") == "required_status_checks":
            params = {"checks": sorted((c.get("context"), c.get("integration_id"))
                                       for c in params.get("required_status_checks") or []),
                      "do_not_enforce_on_create": params.get("do_not_enforce_on_create")}
        elif rule.get("type") == "pull_request":
            params = {}
        rules[rule.get("type")] = params
    ref = (ruleset.get("conditions") or {}).get("ref_name") or {}
    return {"target": ruleset.get("target"), "enforcement": ruleset.get("enforcement"),
            "include": sorted(ref.get("include") or []), "exclude": sorted(ref.get("exclude") or []),
            "bypass": sorted((b.get("actor_id"), b.get("actor_type"), b.get("bypass_mode"))
                             for b in ruleset.get("bypass_actors") or []),
            "rules": rules}


def current(gh: Gh, repo: str) -> dict[str, dict[str, Any]]:
    listing = gh("GET", f"repos/{repo}/rulesets?includes_parents=true", None)
    out = {}
    for item in listing or []:
        full = gh("GET", f"repos/{repo}/rulesets/{int(item['id'])}", None)
        out[full["name"]] = full
    return out


def verify(gh: Gh, repo: str) -> list[str]:
    have = current(gh, repo)
    problems = []
    for want in desired():
        got = have.get(want["name"])
        if got is None:
            problems.append(f"missing ruleset: {want['name']}")
        elif shape(got) != shape(want):
            problems.append(f"{want['name']}: expected {json.dumps(shape(want))}, got {json.dumps(shape(got))}")
    extra = sorted(set(have) - {w["name"] for w in desired()})
    problems += [f"unexpected ruleset (remove it or add it to this script after review): {name}" for name in extra]
    return problems


def apply(gh: Gh, repo: str) -> list[str]:
    have = current(gh, repo)
    for want in desired():
        got = have.get(want["name"])
        if got is None:
            gh("POST", f"repos/{repo}/rulesets", want)
        elif shape(got) != shape(want):
            gh("PUT", f"repos/{repo}/rulesets/{int(got['id'])}", want)
    return verify(gh, repo)


def approval(gh: Gh, repo: str) -> str:
    gh("PUT", f"repos/{repo}/actions/permissions/fork-pr-contributor-approval", {"approval_policy": APPROVAL_POLICY})
    return gh("GET", f"repos/{repo}/actions/permissions/fork-pr-contributor-approval", None).get("approval_policy")


def gh_cli(method: str, path: str, body: Any) -> Any:
    cmd = ["gh", "api", "-X", method, "-H", "Accept: application/vnd.github+json", path]
    if body is not None:
        cmd += ["--input", "-"]
    result = subprocess.run(cmd, input=json.dumps(body) if body is not None else None, capture_output=True,
                            text=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError(f"gh api {method} {path} failed: {result.stderr.strip()[:500]}")
    return json.loads(result.stdout) if result.stdout.strip() else None


def main(argv: list[str] | None = None, gh: Gh = gh_cli) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("action", choices=("plan", "verify", "apply", "approval"))
    args = parser.parse_args(argv)
    if args.repo not in ALLOWED_REPOS:
        parser.error(f"--repo must be one of {sorted(ALLOWED_REPOS)}")
    if args.action in ("apply", "approval"):
        # Writes only with the CEO's own login (repository admin); never an agent's or an App's token.
        login = (gh("GET", "user", None) or {}).get("login")
        if login != CEO_LOGIN:
            print(f"refusing to write: gh is authenticated as {login!r}, not the CEO {CEO_LOGIN!r}")
            return 2
    if args.action == "plan":
        print(json.dumps(desired(), indent=1))
        problems = verify(gh, args.repo)
        print("\n".join(problems) if problems else "current rulesets already match")
        return 0
    if args.action == "approval":
        policy = approval(gh, args.repo)
        print(f"approval_policy={policy}")
        return 0 if policy == APPROVAL_POLICY else 1
    problems = apply(gh, args.repo) if args.action == "apply" else verify(gh, args.repo)
    for problem in problems:
        print(f"FAIL {problem}")
    # Any unexpected ruleset blocks: verify must prove the applicable set is exactly A, B and C.
    print("RESULT", "FAIL" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
