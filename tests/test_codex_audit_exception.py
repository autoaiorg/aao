"""CEO-DEC-AUDIT-CODEX-2026-10-24: the substitute auditor path stays pinned and gated."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODEX_RUNNER = (ROOT / "scripts/audit/run_codex_audit.sh").read_text()
AGY_RUNNER = (ROOT / "scripts/audit/run_agy_audit.sh").read_text()
SESSION = (ROOT / "scripts/governance/ceo_session.sh").read_text()
BOOTSTRAP = (ROOT / "scripts/bootstrap/host_bootstrap.sh").read_text()
DECISION = ROOT / "docs/decisions/CEO-DEC-AUDIT-CODEX-2026-10-24.md"


def _prompts(text):
    return dict(re.findall(r"\[([a-z0-9-]+)\]=([0-9a-f]{64})", text))


def test_codex_runner_uses_the_same_reviewed_prompts_and_a_read_only_ephemeral_sandbox():
    assert _prompts(CODEX_RUNNER) == _prompts(AGY_RUNNER)
    assert "--sandbox read-only --ephemeral" in CODEX_RUNNER
    assert '[[ $me == aao-auditor-alt ]]' in CODEX_RUNNER
    assert '"auditor":"codex","exception":"$EXCEPTION"' in CODEX_RUNNER


def test_codex_binary_hash_is_pinned_identically_in_runner_and_session():
    runner = re.search(r"CODEX_SHA256=([0-9a-f]{64})", CODEX_RUNNER).group(1)
    session = re.search(r"CODEX_SHA256=([0-9a-f]{64})", SESSION).group(1)
    assert runner == session == "b93f6811d3f653f0fb83be4050d857fb9abbb111dfa2ce160563327daff7f306"


def test_bootstrap_accepts_codex_only_with_a_recorded_named_exception():
    assert "allowed=antigravity\n" in BOOTSTRAP
    gate = BOOTSTRAP.split("allowed=antigravity\n", 1)[1].split("PY\n", 1)[0]
    assert "docs/decisions/$AUDIT_EXCEPTION.md" in gate and "'^auditor_sustituto: codex$'" in gate
    assert 'att["auditor"] in allowed' in gate and 'att.get("exception") == exception' in gate
    assert "auditor_sustituto: codex" in DECISION.read_text().splitlines()
