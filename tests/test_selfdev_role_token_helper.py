"""Tests for the root-installed, target-allowlisted token wrapper."""

from types import SimpleNamespace

import pytest

from scripts import selfdev_role_token_helper as helper


def test_wrapper_rejects_non_root_or_non_allowlisted_arguments(monkeypatch):
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper, "_installed_as_expected", lambda: True)
    assert helper.main(["--account", "root", "--token", "arbitrary", "--operation", "install"]) == 2
    assert (
        helper.main(
            [
                "--account",
                "aao-impl-codex",
                "--token",
                "selfdev-implementer",
                "--operation",
                "exec",
            ]
        )
        == 2
    )
    monkeypatch.setattr(helper.os, "geteuid", lambda: 1000)
    assert (
        helper.main(
            [
                "--account",
                "aao-impl-codex",
                "--token",
                "selfdev-implementer",
                "--operation",
                "check",
            ]
        )
        == 2
    )


def test_wrapper_uses_fixed_installer_and_never_puts_token_in_argv(monkeypatch):
    seen = {}
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper, "_installed_as_expected", lambda: True)
    monkeypatch.setattr(helper.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=1002))
    monkeypatch.setattr(
        helper,
        "sys",
        SimpleNamespace(stdin=SimpleNamespace(buffer=SimpleNamespace(read=lambda _n: b"secret\n"))),
    )
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda args, **kwargs: (
            seen.update(args=args, kwargs=kwargs) or SimpleNamespace(returncode=0)
        ),
    )
    assert (
        helper.main(
            [
                "--account",
                "aao-impl-codex",
                "--token",
                "selfdev-implementer",
                "--operation",
                "install",
            ]
        )
        == 0
    )
    assert seen["args"] == [
        "/usr/sbin/runuser",
        "-u",
        "aao-impl-codex",
        "--",
        "/usr/bin/python3",
        str(helper.INSTALLER),
        "--account",
        "aao-impl-codex",
        "--token",
        "selfdev-implementer",
    ]
    assert seen["kwargs"]["input"] == b"secret\n"
    assert "secret" not in str(seen["args"])
    assert seen["kwargs"]["env"] == {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": "/run/user/1002"}


def test_wrapper_refuses_oversized_stdin_without_invoking_installer(monkeypatch):
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper, "_installed_as_expected", lambda: True)
    monkeypatch.setattr(helper.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=1002))
    monkeypatch.setattr(
        helper,
        "sys",
        SimpleNamespace(stdin=SimpleNamespace(buffer=SimpleNamespace(read=lambda _n: b"x" * 4097))),
    )
    monkeypatch.setattr(
        helper.subprocess, "run", lambda *_a, **_kw: pytest.fail("oversized input must stop")
    )
    assert (
        helper.main(
            [
                "--account",
                "aao-impl-codex",
                "--token",
                "selfdev-implementer",
                "--operation",
                "install",
            ]
        )
        == 2
    )
