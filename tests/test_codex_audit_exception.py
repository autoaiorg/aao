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
    host_runner = re.search(r"HOST_SHA256=([0-9a-f]{64})", CODEX_RUNNER).group(1)
    host_session = re.search(r"HOST_SHA256=([0-9a-f]{64})", SESSION).group(1)
    assert host_runner == host_session == "8ee4f472e92ac226a189e98998633b2d07f989f208515750764db660369f2926"


def test_bootstrap_accepts_codex_only_with_a_recorded_named_exception():
    assert "allowed=antigravity\n" in BOOTSTRAP
    gate = BOOTSTRAP.split("allowed=antigravity\n", 1)[1].split("PY\n", 1)[0]
    assert "docs/decisions/$AUDIT_EXCEPTION.md" in gate and "'^auditor_sustituto: codex$'" in gate
    assert 'att["auditor"] in allowed' in gate and 'att.get("exception") == exception' in gate
    assert "auditor_sustituto: codex" in DECISION.read_text().splitlines()


def test_only_codex_arg0_aliases_to_the_pinned_binary_may_leave_the_state_dir():
    loop = CODEX_RUNNER.split("while IFS= read -r -d '' link; do", 1)[1].split("done <", 1)[0]
    assert '[[ $link == "$d"/tmp/arg0-linux/*/* && $target == "$CODEX" ]] && continue' in loop
    assert 'refusing: symlink $link resolves outside $d' in loop
    assert "umask 077; exec /usr/local/bin/codex login --device-auth" in SESSION


def test_symlink_rule_on_a_real_state_dir(tmp_path):
    import subprocess
    loop = "while IFS= read -r -d '' link; do" + CODEX_RUNNER.split("while IFS= read -r -d '' link; do", 1)[1].split("done <", 1)[0] \
        + 'done < <(find "$d" -type l -print0); echo OK'
    codex, d = tmp_path / "codex", tmp_path / "home" / ".codex"
    codex.write_text("bin")
    alias = d / "tmp" / "arg0-linux" / "codex-arg0X"
    alias.mkdir(parents=True)
    (alias / "apply_patch").symlink_to(codex)
    (d / "inside").write_text("x")
    (d / "ok-link").symlink_to(d / "inside")

    def run():
        return subprocess.run(["bash", "-c", loop], env={"CODEX": str(codex), "d": str(d), "PATH": "/usr/bin:/bin"},
                              capture_output=True, text=True, check=False)
    assert run().stdout.strip() == "OK"
    (alias / "evil").symlink_to("/etc/passwd")
    assert "refusing" in run().stderr
    (alias / "evil").unlink()
    (d / "evil").symlink_to(codex)  # the pinned binary is only allowed for arg0 aliases
    assert "refusing" in run().stderr


def test_audit_run_disables_plugins_browser_and_memory_and_drops_caches():
    disabled = CODEX_RUNNER.split("DISABLED=(", 1)[1].split(")", 1)[0].split()
    assert {"plugins", "plugin_sharing", "browser_use", "computer_use", "memories", "in_app_browser"} <= set(disabled)
    assert '"${DISABLED[@]/#/--disable=}"' in CODEX_RUNNER
    assert CODEX_RUNNER.index('rm -rf -- "$d/plugins" "$d/tmp"') < CODEX_RUNNER.index('bad=$(find "$d"')
