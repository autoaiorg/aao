"""Release staging must use only the exact, clean Git revision."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGER = REPO_ROOT / "scripts/bootstrap/stage_release_source.sh"
BOOTSTRAP = REPO_ROOT / "scripts/bootstrap"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_release_staging_rejects_dirty_code_and_excludes_local_files(tmp_path):
    repo = tmp_path / "repo"
    release = tmp_path / "release"
    repo.mkdir()
    release.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    (repo / "app.py").write_text("committed source\n")
    (repo / ".env.example").write_text("template\n")
    _git(repo, "add", "app.py", ".env.example")
    _git(repo, "commit", "-qm", "initial")
    revision = _git(repo, "rev-parse", "HEAD")

    (repo / "app.py").write_text("unreviewed changed source\n")
    dirty = subprocess.run(
        ["bash", str(STAGER), str(repo), revision, str(release)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert dirty.returncode != 0
    assert "Tracked source differs" in dirty.stderr
    assert list(release.iterdir()) == []

    _git(repo, "checkout", "-q", "--", "app.py")
    (repo / ".env").write_text("local secret\n")
    (repo / "node_modules").mkdir()
    (repo / "node_modules/cache").write_text("generated\n")
    subprocess.run(
        ["bash", str(STAGER), str(repo), revision, str(release)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (release / "app.py").read_text() == "committed source\n"
    assert (release / ".env.example").read_text() == "template\n"
    assert not (release / ".env").exists()
    assert not (release / "node_modules").exists()


def test_api_and_recovery_use_distinct_database_roles_and_secrets():
    api_unit = (REPO_ROOT / "deploy/systemd/aao-api.service").read_text()
    recovery_unit = (REPO_ROOT / "deploy/systemd/aao-conversation-recovery.service").read_text()
    secrets = (BOOTSTRAP / "init_secrets.sh").read_text()
    identities = (BOOTSTRAP / "init_identities.sh").read_text()
    recovery_grants = (BOOTSTRAP / "apply_runtime_grants.sql").read_text()
    api_grants = (BOOTSTRAP / "apply_api_grants.sql").read_text()

    assert "User=aao-api" in api_unit
    assert "EnvironmentFile=-/etc/aao/aao-api.env" in api_unit
    assert "User=aao-recovery" in recovery_unit
    assert "EnvironmentFile=-/etc/aao/aao-recovery.env" in recovery_unit
    assert "aao_runtime:${RUNTIME_DB_PASS}" in secrets
    assert "aao_recovery:${RECOVERY_DB_PASS}" in secrets
    assert "usermod -aG aao-host-id-read aao-api" in identities
    assert "principal_credentials" not in recovery_grants
    assert "project_grants" not in recovery_grants
    assert "principal_credentials" in api_grants


def test_api_runtime_can_resolve_but_not_manage_workload_identity_bindings():
    grants = (BOOTSTRAP / "apply_api_grants.sql").read_text()
    migration = (REPO_ROOT / "db/postgres/043_workload_identity_bindings.sql").read_text()

    assert "GRANT SELECT ON TABLE workload_identity_bindings TO aao_runtime" in grants
    assert "GRANT INSERT" not in grants.split(
        "GRANT SELECT ON TABLE workload_identity_bindings TO aao_runtime", 1
    )[0].split("workload_identity_bindings", 1)[-1]
    assert "REVOKE ALL ON TABLE workload_identity_bindings FROM PUBLIC" in migration
    assert "certificate_sha256 text PRIMARY KEY" in migration
