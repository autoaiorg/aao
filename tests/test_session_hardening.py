"""Codex audit 50033ae: session script and runner hardening (p2p3 A-02, A-05, B-01; r1 B-04, B-07)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = (ROOT / "scripts/governance/ceo_session.sh").read_text()
RUNNER = (ROOT / "scripts/trial/run_trial.sh").read_text()


def test_session_never_reads_code_from_a_working_copy():
    assert "REPO_DIR" not in SESSION and 'git -C "$REPO_DIR"' not in SESSION
    g = SESSION.split("g(){", 1)[1].split("}", 1)[0]
    for guard in ("GIT_NO_REPLACE_OBJECTS=1", "GIT_CONFIG_GLOBAL=/dev/null", "GIT_CONFIG_NOSYSTEM=1", "core.hooksPath=/dev/null"):
        assert guard in g
    assert 'g clone -q --no-checkout https://github.com/autoaiorg/aao.git "$SRC"' in SESSION
    assert 'g -C "$SRC" show "$1:${f%:*}" | sudo install' in SESSION


def test_session_apply_parses_the_exception_and_stops_on_unrestored_ruleset():
    apply = SESSION.split("  apply)", 1)[1].split(";;", 1)[0]
    assert 'EXC=(--audit-exception "$4")\n' in apply  # its own line (B-07)
    assert "((trial_rc != 99)) || die" in apply
    assert apply.index("((trial_rc != 99))") < apply.index("canonical_protection.py")


def test_supervisor_dependent_trial_results_require_the_supervisor_at_rev():
    assert "SUP_AT_REV=1" in RUNNER and 'sup_skip A-08' in RUNNER and "sup_skip A-07" in RUNNER and "sup_skip P3-11" in RUNNER
    assert '"supervisor_revision":sys.argv[9]' in RUNNER
    assert "core.fsmonitor=false" in RUNNER.split("sup_rev=$(", 1)[1].split(")", 1)[0]


def test_canonical_ruleset_b_does_not_gate_staging_creation():
    spec = importlib.util.spec_from_file_location("cp", ROOT / "scripts/governance/canonical_protection.py")
    cp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cp)
    b = next(r for r in cp.desired() if r["name"].startswith("B "))
    params = next(rule["parameters"] for rule in b["rules"] if rule["type"] == "required_status_checks")
    assert params["do_not_enforce_on_create"] is True
    assert cp.shape(b)["rules"]["required_status_checks"]["do_not_enforce_on_create"] is True
