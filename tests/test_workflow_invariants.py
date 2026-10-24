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


def violations(text: str) -> list[str]:
    """The single checker every workflow goes through (adversarial cases below use it too)."""
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    found = []
    if not re.search(r"(?m)^permissions:\s*$", code):
        found.append("missing explicit top-level permissions block")
    if re.search(r":\s*['\"]?write\b|write-all|read-all", code):
        found.append("a permission is not read-only/explicit")
    if re.search(r"\bpull_request_target\b|\bworkflow_run\b", code):
        found.append("privileged trigger")
    if "secrets." in code or "secrets[" in code:
        found.append("secret reference")
    return found


def test_workflows_are_found():
    names = {p.relative_to(ROOT).as_posix() for p in WORKFLOWS}
    assert {".github/workflows/ci.yml", "deploy/trial/test.yml"} <= names


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_workflow_is_safe_for_untrusted_pull_requests(path):
    assert violations(path.read_text()) == []


SAFE = "on: pull_request\npermissions:\n  contents: read\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n"


@pytest.mark.parametrize("bad, reason", [
    (SAFE.replace("      - run: true", "    permissions: {contents: write}\n      - run: true"), "not read-only"),
    (SAFE.replace("contents: read", "contents: 'write'"), "not read-only"),
    (SAFE.replace("contents: read", "write-all"), "not read-only"),
    (SAFE.replace("permissions:\n  contents: read\n", ""), "missing explicit"),
    (SAFE.replace("on: pull_request", "on: pull_request_target"), "privileged trigger"),
    (SAFE.replace("on: pull_request", "on:\n  workflow_run:"), "privileged trigger"),
    (SAFE.replace("run: true", "run: echo ${{ secrets.TOKEN }}"), "secret reference"),
])
def test_checker_rejects_each_adversarial_workflow(bad, reason):
    # Codex audit 2b3e9c1 B-04/C-01: the adversarial cases go through the same checker as the real files.
    assert any(reason in v for v in violations(bad)), violations(bad)
    assert violations(SAFE) == []
