import os
from pathlib import Path

from aao.trial_security import validate_role_workdir

RUNNER = Path(__file__).parents[1] / "scripts/trial/run_trial.sh"


def test_runner_binds_evidence_to_unique_run_and_harness_revision():
    source = RUNNER.read_text()
    assert "export AAO_TRIAL_RUN_ID=$TS AAO_TRIAL_HARNESS_REV=$REV" in source
    assert 'd.get("run_id")' in source
    assert "no evidence from this run" in source
    assert "GITHUB_SHA=" not in source


def test_runner_stages_candidate_from_app_clone_and_logs_helpers():
    source = RUNNER.read_text()
    stage = source.index('STAGE-COMMIT --repo')
    stage_context = source[source.rfind('(cd "$clone"', 0, stage):stage]
    assert '(cd "$clone"' in stage_context
    assert "AAO_GITHUB_TRIAL_EXPECTED_SHA=\"$candidate\"" in stage_context
    assert '"$LOG/$id-STAGE-COMMIT.out"' in source
    assert '"$LOG/$id-PUBLISH-AUDIT.out"' in source
    assert ">/dev/null 2>&1" not in source


def test_runner_fetch_and_symlink_checks_fail_closed_before_install():
    source = RUNNER.read_text()
    fetch = 'fetch --quiet origin main || {'
    assert fetch in source
    symlink_check = source.index('[[ ! -L /opt/aao-trial ]]')
    install = source.index('install -d -o root -g root -m 0755 /opt/aao-trial')
    assert symlink_check < install


def test_role_workdir_validator_rejects_wrong_owner_mode_and_symlink(tmp_path):
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    work.chmod(0o700)
    assert validate_role_workdir(work, os.getuid())
    assert not validate_role_workdir(work, os.getuid() + 1)
    work.chmod(0o755)
    assert not validate_role_workdir(work, os.getuid())
    link = tmp_path / "link"
    link.symlink_to(work, target_is_directory=True)
    assert not validate_role_workdir(link, os.getuid())


def test_runner_uses_root_only_work_parent_clean_role_git_and_run_scoped_evidence():
    source = RUNNER.read_text()
    assert "WORK_PARENT=/var/lib/aao-trial" in source
    assert "WORK_ROOT=$WORK_PARENT/work" in source
    assert "[[ ! -L /var/lib && ! -L $WORK_PARENT && ! -L $WORK_ROOT ]]" in source
    assert "role_work_safe \"$work\" \"$uid\"" in source
    assert "GIT_CONFIG_GLOBAL=/dev/null" in source
    assert "GIT_CONFIG_NOSYSTEM=1" in source
    assert "-c core.hooksPath=/dev/null -c core.fsmonitor=false" in source
    assert "runuser -u \"$uid\" -- env -i" in source
    assert "capture_evidence \"$uid\" \"$home\" \"$id\"" in source
    assert "find \"$evidence_dir\"" not in source
    assert '[[ $extra_state != FAIL && $extra_rc -ne 1 ]]' in source


def test_ruleset_gate_fetches_details_and_checks_rules_and_bypass_actors():
    source = RUNNER.read_text()
    assert 'gh api "repos/$REPO/rulesets?includes_parents=true"' in source
    assert 'gh api "repos/$REPO/rulesets/$id"' in source
    for rule in ('"non_fast_forward"', '"required_status_checks"', '"deletion"', '"pull_request"'):
        assert rule in source
    assert "bypass_actors" in source
    assert '[(x.get("actor_id"),x.get("actor_type")) for x in abypass]==[(5447984,"Integration")]' in source


def test_runner_passes_both_implementer_forks_and_runs_a10_for_all_apps():
    source = RUNNER.read_text()
    assert 'AAO_GITHUB_TRIAL_FORKS="autoaiorg/aao-codex,$impl_fork"' in source
    assert 'AAO_GITHUB_TRIAL_FORKS="$production_fork,$impl_fork"' in source
    assert "A10_ROLES=(aao-integrator aao-auditor aao-auditor-alt aao-supervisor aao-notifier aao-pm aao-impl-claude aao-impl-codex aao-impl-agy aao-probe-noworkflows)" in source
    assert "target=autoaiorg/aao-trial-probe" in source
    assert 'impl_uid=${APP_UID[$impl]}' in source


def test_runner_collects_p0_p4_and_p4b_before_equivalence_execution():
    source = RUNNER.read_text()
    assert 'GitHubAppClient("aao-integrator")' in source
    assert '"/repos/"+sys.argv[1]' in source
    assert 'EXPECTED_REPO_ID=' in source
    assert 'collect_impl_p4()' in source
    assert 'IFS=, read -r -a fork_list' in source
    assert 'for target in "$REPO" "${fork_list[@]}"' in source
    for check in ('hosts.yml', '.git-credentials', 'user_manager_state', '/var/lib/systemd/linger/',
                  'user@$n.service', '"systemd_user_manager"', 'token_environment_absent',
                  'deploy_keys_by_repository', 'outside_collaborators_clear', 'org_members_clear',
                  'not [x for x in outside if x]'):
        assert check in source
    assert 'systemctl","--user' not in source
    assert 'collect_p4b()' in source
    assert 'orgs/autoaiorg/members?role=admin' in source
    assert 'repos/$REPO/collaborators?permission=admin' in source
    assert 'P0_JSON=$(integrator_target_identity)' in source
    assert 'AAO_TRIAL_P0_EVIDENCE="$p0_run_json"' in source
    assert 'AAO_TRIAL_P4_EVIDENCE="$p4_json"' in source
    assert 'AAO_TRIAL_P4B_EVIDENCE="$p4b_json"' in source


def test_pinned_setup_inputs_come_from_revision_objects():
    runner = RUNNER.read_text()
    probe = (RUNNER.parent / "probe_app_setup.sh").read_text()
    form = (RUNNER.parents[1] / "github_apps" / "create_app_form.py").read_text()
    assert 'show "$REV:deploy/github-apps/aao-github-apps-registry.json"' in runner
    assert 'git -C "$REPO" archive "$REV" scripts/github_apps/create_app_form.py docs/proposals/github-apps' in probe
    assert '--manifest-dir "$form_tmp/docs/proposals/github-apps"' in probe
    assert 'manifest_dir = MANIFESTS' in form


def test_fixture_tree_is_sent_as_json_and_p3_07_candidate_keeps_main_tree():
    source = RUNNER.read_text()
    tree_line = next(line for line in source.splitlines() if 'repos/$REPO/git/trees' in line)
    assert "--input -" in tree_line and "-f 'tree[0]" not in source
    block = source.split('if [[ $id == P3-07 || $id == P3-12 ]]; then', 1)[1].split("else", 1)[0]
    assert "checkout -q -B trial-candidate origin/main^" in block and "checkout -q origin/main -- ." in block


def test_stage_branch_is_unique_per_run():
    # A fixed aao-trial/required-<id> branch from an earlier run makes the next STAGE-COMMIT a rejected non-fast-forward.
    assert 'AAO_GITHUB_TRIAL_BRANCH="aao-trial/required-$id-$TS"' in RUNNER.read_text()


def _seed_body():
    source = RUNNER.read_text()
    return source.split("seed_candidate(){", 1)[1].split("\n}\n", 1)[0]


def test_stage_commit_cli_branch_is_unique_per_run():
    # Live defect: the CLI --branch overrides AAO_GITHUB_TRIAL_BRANCH, so both must carry the run id.
    body = _seed_body()
    assert '--branch "aao-trial/required-$id-$TS"' in body and '--branch "aao-trial/required-$id")' not in body
    assert 'AAO_GITHUB_TRIAL_BRANCH="aao-trial/required-$id-$TS"' in body


def test_p3_04_fixture_uses_the_wrong_publisher_and_others_the_auditor():
    source = RUNNER.read_text()
    assert "pub=aao-auditor; [[ $id != P3-04 ]] || pub=aao-auditor-alt" in source
    assert '--role "$pub")' in _seed_body()


def test_ruleset_a_is_restored_on_any_exit_and_marked_disabled_before_it_is_disabled():
    source = RUNNER.read_text()
    assert "trap 'if ! restore_a; then rm -rf \"$tmp\"; exit 99; fi; rm -rf \"$tmp\"' EXIT" in source
    assert "trap 'exit 130' INT TERM HUP" in source
    block = source.split("if wants A-07 || wants P3-11; then", 1)[1]
    assert block.index("A_DISABLED=1") < block.index("enforcement=disabled") < block.index("restore_a ||")
    assert "check_rulesets && A_DISABLED=0" in source


def test_p3_07_candidate_is_divergent_and_keeps_the_workflow(tmp_path):
    """Run the runner's exact git steps on a real repository."""
    import subprocess

    def git(*args, cwd=tmp_path):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null", *args],
                              cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("x")
    git("add", "."); git("commit", "-qm", "base")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/test.yml").write_text("on: push\n")
    git("add", "."); git("commit", "-qm", "seed CI")
    main = git("rev-parse", "main")
    git("checkout", "-q", "-B", "trial-candidate", "main^")
    git("checkout", "-q", "main", "--", ".")
    git("commit", "-q", "--allow-empty", "-m", "AAO trial fixture P3-07")
    candidate = git("rev-parse", "HEAD")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", main, candidate], cwd=tmp_path, check=False).returncode
    assert ancestor == 1  # main is not an ancestor: the push is non-fast-forward
    assert ".github/workflows/test.yml" in git("ls-tree", "-r", "--name-only", candidate).split()


def test_a07_and_p3_11_events_are_correlated_to_this_repo_and_main():
    block = RUNNER.read_text().split("if wants A-07 || wants P3-11; then", 1)[1]
    assert 'e.get("ref")=="refs/heads/main" and e.get("repo")==sys.argv[3]' in block
    assert block.count('get("repo")==sys.argv[1]') >= 2  # drift and restored events
    assert "exit 99" in RUNNER.read_text().split("restore_a(){", 1)[1].split("if wants A-07", 1)[0]


def test_bootstrap_stops_only_loaded_units():
    source = (Path(__file__).parents[1] / "scripts/bootstrap/host_bootstrap.sh").read_text()
    assert 'systemctl list-units --all --no-legend --plain "${LOOP_UNITS[@]}"' in source
    assert 'run systemctl stop "${loaded[@]}"' in source and 'run systemctl stop "${LOOP_UNITS[@]}"' not in source
