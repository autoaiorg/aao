"""P3-10 compensating controls (CEO-DEC-P2P3-2026-10-24, conditions 1-3) as executable invariants.

Fork PR workflows run without approval for bots of the same organization, so every workflow this repo
ships (canonical CI and the trial CI seeded by scripts/trial/seed_trial_ci.sh) must be harmless to run on
untrusted PR content: explicit read-only token, no privileged triggers, no secrets.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted([*ROOT.glob(".github/workflows/*.y*ml"), *ROOT.glob("deploy/trial/*.y*ml")])


def test_workflows_are_found():
    names = {p.relative_to(ROOT).as_posix() for p in WORKFLOWS}
    assert {".github/workflows/ci.yml", "deploy/trial/test.yml"} <= names


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_workflow_is_safe_for_untrusted_pull_requests(path):
    text = path.read_text()
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    # Condition 2: explicit top-level permissions, nothing writable anywhere (top level or per job).
    assert re.search(r"(?m)^permissions:\s*$", code), "missing explicit top-level permissions block"
    assert not re.search(r":\s*['\"]?write\b|write-all|read-all", code), "a permission is not read-only/explicit"
    # Condition 3: no trigger that runs untrusted content with base-repository privileges.
    assert not re.search(r"\bpull_request_target\b|\bworkflow_run\b", code)
    # Condition 1: no secrets referenced (GITHUB_TOKEN stays implicit and read-only).
    assert "secrets." not in code and "secrets[" not in code


def test_inline_write_permission_is_caught():
    # Codex audit 50033ae p2p3 B-03: `permissions: {contents: write}` inside a job must not pass.
    pattern = r":\s*['\"]?write\b|write-all|read-all"
    assert re.search(pattern, "    permissions: {contents: write}")
    assert re.search(pattern, "  contents: 'write'")
    assert not re.search(pattern, "permissions:\n  contents: read")
