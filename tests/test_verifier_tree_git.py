"""Codex audit 50033ae r1 A-02: root must never execute a role-owned repository's git config."""
import importlib.util
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_trust_root_host.py"
spec = importlib.util.spec_from_file_location("verify_trust_root_host", SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_planted_fsmonitor_in_tree_config_is_never_executed(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "_owner_uid", lambda _p: 0)  # the root-owned path: config must still be neutralized
    tree = tmp_path / "tree"
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    (tree / "f").write_text("x")
    subprocess.run(["git", "-C", str(tree), "-c", "user.name=t", "-c", "user.email=t@t", "add", "f"], check=True)
    subprocess.run(["git", "-C", str(tree), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"], check=True)
    marker = tmp_path / "pwned"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    subprocess.run(["git", "-C", str(tree), "config", "core.fsmonitor", str(hook)], check=True)
    assert verifier.tree_git(tree, "status", "--porcelain") == ""
    assert verifier.tree_git(tree, "rev-parse", "HEAD")
    assert not marker.exists()


def test_role_owned_trees_are_read_as_their_owner(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(verifier.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    tree = tmp_path / "t"
    tree.mkdir()
    monkeypatch.setattr(verifier, "_owner_uid", lambda _p: os.getuid() or 1)
    verifier.tree_git(tree, "status")
    assert calls[-1][:2] == ["runuser", "-u"] and "env" in calls[-1][:5]
    assert "core.fsmonitor=false" in calls[-1] and "core.hooksPath=/dev/null" in calls[-1]
