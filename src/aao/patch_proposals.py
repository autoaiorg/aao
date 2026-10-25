"""Validate constrained source patches without modifying the canonical checkout."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

_MAX_PATCH_BYTES = 65_536
_MAX_PATCH_LINES = 1_200
_MAX_FILES = 8
_ALLOWED_ROOTS = ("src/aao/", "tests/")
_DIFF_HEADER = re.compile(r"^diff --git a/([^\s]+) b/([^\s]+)$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class PatchProposalError(ValueError):
    """A proposed patch is invalid or cannot be safely checked."""


def _run_git(repository: Path, *arguments: str, timeout: int = 10) -> str:
    env = {
        "PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
    }
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout, check=False, cwd="/", env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PatchProposalError("isolated Git validation failed") from exc
    if result.returncode:
        raise PatchProposalError("patch does not apply cleanly to the declared base revision")
    return result.stdout


def _patch_paths(patch: str) -> list[str]:
    paths: list[str] = []
    current_path: str | None = None
    seen_old = False
    seen_new = False
    seen_hunk = False
    new_file = deleted_file = False
    for line in patch.splitlines():
        if line.startswith(("GIT binary patch", "Binary files ", "rename ", "copy ",
                            "old mode ", "new mode ", "Submodule ")):
            raise PatchProposalError("binary, rename, copy, and mode changes are not allowed")
        if line.startswith(("old file mode ", "new file mode ")) and line.rsplit(" ", 1)[-1] != "100644":
            raise PatchProposalError("only non-executable regular files are allowed")
        # A created (deleted) file has /dev/null on its old (new) side; only then is /dev/null accepted.
        if line == "new file mode 100644":
            new_file = True
        elif line == "deleted file mode 100644":
            deleted_file = True
        elif line.startswith("deleted file mode "):
            raise PatchProposalError("only non-executable regular files are allowed")
        if not line.startswith("diff --git "):
            if line.startswith(("--- ", "+++ ")):
                expected_side = "a/" if line.startswith("--- ") else "b/"
                value = line[4:].split("\t", 1)[0]
                created = expected_side == "a/" and value == "/dev/null" and new_file and not deleted_file
                removed = expected_side == "b/" and value == "/dev/null" and deleted_file and not new_file
                if current_path is None or (value != expected_side + current_path and not (created or removed)):
                    raise PatchProposalError("patch content paths must match the declared file path")
                if expected_side == "a/":
                    seen_old = True
                else:
                    seen_new = True
            elif line.startswith("@@ "):
                seen_hunk = True
            continue
        if current_path is not None and not (seen_old and seen_new and seen_hunk):
            raise PatchProposalError("each changed file must contain matching paths and a diff hunk")
        match = _DIFF_HEADER.fullmatch(line)
        if not match or match.group(1) != match.group(2):
            raise PatchProposalError("patch must use simple same-path git diff headers")
        path = match.group(1)
        parts = Path(path).parts
        if path.startswith("/") or ".." in parts or ".git" in parts:
            raise PatchProposalError("unsafe patch path")
        if not path.startswith(_ALLOWED_ROOTS):
            raise PatchProposalError("patch path is outside the allowed source and test roots")
        paths.append(path)
        current_path = path
        seen_old = seen_new = seen_hunk = False
        new_file = deleted_file = False
    if (current_path is None or not (seen_old and seen_new and seen_hunk)
            or len(paths) > _MAX_FILES or len(set(paths)) != len(paths)):
        raise PatchProposalError("patch must change between 1 and 8 unique allowed files")
    return paths


def inspect_patch(patch: str) -> dict[str, object]:
    """Check proposal bounds and declared paths without applying the diff."""
    if not isinstance(patch, str) or not patch.strip():
        raise PatchProposalError("non-empty unified Git patch required")
    encoded = patch.encode("utf-8")
    if len(encoded) > _MAX_PATCH_BYTES or patch.count("\n") > _MAX_PATCH_LINES:
        raise PatchProposalError("patch exceeds size or line limits")
    paths = _patch_paths(patch)
    return {
        "patch_sha256": hashlib.sha256(encoded).hexdigest(),
        "changed_paths": paths,
        "patch_bytes": len(encoded),
    }


def validate_patch(repository: str | Path, base_sha: str, patch: str) -> dict[str, object]:
    """Validate a diff by applying it only to a disposable detached clone.

    This function never changes the supplied checkout and never executes code from
    the patch. Its result is validation metadata, not authorization to promote.
    """
    if not _SHA.fullmatch(base_sha):
        raise PatchProposalError("full base commit SHA required")
    inspected = inspect_patch(patch)
    encoded = patch.encode("utf-8")
    paths = inspected["changed_paths"]
    source = Path(repository).resolve()
    if not source.is_dir():
        raise PatchProposalError("source repository is unavailable")
    source_root = Path(_run_git(source, "rev-parse", "--show-toplevel").strip()).resolve()
    if source_root != source:
        source = source_root
    _run_git(source, "cat-file", "-e", f"{base_sha}^{{commit}}")

    with tempfile.TemporaryDirectory(prefix="aao-patch-proposal-") as scratch:
        scratch_path = Path(scratch)
        clone = scratch_path / "candidate"
        clone.mkdir(mode=0o700)
        patch_path = scratch_path / "proposal.patch"
        patch_path.write_bytes(encoded)
        os.chmod(patch_path, 0o600)
        _run_git(clone, "init", "--quiet")
        _run_git(
            clone, "-c", "protocol.file.allow=always", "fetch", "--no-tags",
            "--no-recurse-submodules", str(source), base_sha,
        )
        _run_git(
            clone, "-c", "core.hooksPath=/dev/null", "checkout", "--quiet",
            "--detach", "FETCH_HEAD",
        )
        _run_git(clone, "apply", "--check", "--whitespace=error", str(patch_path))
        _run_git(clone, "apply", "--whitespace=error", str(patch_path))
        _run_git(clone, "add", "--", *paths)
        candidate_tree = _run_git(clone, "write-tree").strip()
        status = _run_git(clone, "status", "--porcelain", "--untracked-files=all")
        changed = []
        for line in status.splitlines():
            relative = line[3:]
            if not relative or not relative.startswith(_ALLOWED_ROOTS):
                raise PatchProposalError("applied patch touched a path outside the allowlist")
            changed.append(relative)
        if sorted(changed) != sorted(paths):
            raise PatchProposalError("applied patch paths differ from declared patch paths")

    return {
        "base_sha": base_sha,
        "patch_sha256": inspected["patch_sha256"],
        "changed_paths": paths,
        "patch_bytes": inspected["patch_bytes"],
        "candidate_tree": candidate_tree,
        "validated_in_disposable_clone": True,
        "applied_to_canonical_checkout": False,
    }
