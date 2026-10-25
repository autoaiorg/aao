import subprocess

import pytest

from aao.pr_publisher import PublishError, verify_candidate

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.hooksPath=/dev/null"]


def _commit(repo, name, text):
    (repo / name).write_text(text)
    subprocess.run([*GIT, "-C", str(repo), "add", "-A"], check=True)
    subprocess.run([*GIT, "-C", str(repo), "commit", "-qm", name], check=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def test_candidate_must_be_exactly_base_plus_the_proposal_patch(tmp_path):
    repo = tmp_path / "r"
    subprocess.run([*GIT, "init", "-q", str(repo)], check=True)
    base = _commit(repo, "a.txt", "a\n")
    candidate = _commit(repo, "b.txt", "b\n")
    later = _commit(repo, "c.txt", "c\n")
    patch = subprocess.run(["git", "-C", str(repo), "diff", "--binary", base, candidate], check=True, capture_output=True).stdout
    store = repo / ".git"

    verify_candidate(store, candidate, base, patch)
    with pytest.raises(PublishError, match="tree does not match"):
        verify_candidate(store, candidate, base, patch.replace(b"+b", b"+x"))
    with pytest.raises(PublishError, match="single commit on the proposal base"):
        verify_candidate(store, later, base, patch)
    with pytest.raises(PublishError, match="full SHAs"):
        verify_candidate(store, "HEAD", base, patch)
