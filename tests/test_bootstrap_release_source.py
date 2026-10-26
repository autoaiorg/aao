"""Release staging must use only the exact, clean Git revision."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGER = REPO_ROOT / "scripts/bootstrap/stage_release_source.sh"


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
