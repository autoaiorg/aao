import sys

from scripts import publish_candidate


def test_publisher_cli_requires_explicit_nonproduction_environment(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["publish_candidate.py", "--work-id", "w1", "--step", "push"])
    monkeypatch.delenv("AAO_ENV", raising=False)

    assert publish_candidate.main() == 1
    assert "requires explicit AAO_ENV" in capsys.readouterr().err


def test_publisher_cli_refuses_production_until_mtls_contract_exists(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["publish_candidate.py", "--work-id", "w1", "--step", "push"])
    monkeypatch.setenv("AAO_ENV", "production")

    assert publish_candidate.main() == 1
    assert "production publisher mTLS is not implemented" in capsys.readouterr().err
