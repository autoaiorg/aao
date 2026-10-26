import importlib.util
import json
import os
import subprocess
from pathlib import Path

from aao.manifest_audit import load_anchor
from aao.supervisor_service import load_config

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("maker", ROOT / "scripts/make_trust_root_files.py")
maker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(maker)
REV = "97ad4f13655aae2b736c7ba6b3d8d666e51d4680"


def _pub(tmp_path, name):
    key = tmp_path / f"{name}.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(key)], check=True)
    return subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout"], check=True,
                          capture_output=True, text=True).stdout


def test_generated_anchor_loads_with_the_real_loader(tmp_path):
    template = json.loads((ROOT / "docs/audit-runs/20261019-provisional/policy.json").read_text())
    files = maker.build(REV, template, _pub(tmp_path, "a"), _pub(tmp_path, "s"), os.getuid(), ["alessbarb"],
                        attribution_writer_uid=os.getuid(), repo="owner/project")
    trust = tmp_path / "trust"
    trust.mkdir(mode=0o755)
    policy = trust / "policy.json"
    policy.write_text(json.dumps(files["policy.json"]))
    policy.chmod(0o644)
    anchor = {**files["trust-anchor.json"], "policy_path": str(policy)}
    anchor_path = trust / "anchor.json"
    anchor_path.write_text(json.dumps(anchor))
    anchor_path.chmod(0o644)
    loaded = load_anchor(anchor_path, (os.getuid(),))
    assert loaded["policy"]["trusted_auditor_revisions"] == [REV]
    assert loaded["supervisor_intake_socket"] == "/run/aao-veto-intake/veto.sock"


def test_generated_supervisor_config_loads(tmp_path):
    files = maker.build(REV, {"version": "x"}, "A", "S", 1005, [], repo="owner/project")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"ledger_keys": {"k": {}}, "integrator_key_id": "k",
                                    "push_principals": {"aao-impl-codex[bot]": "codex"}}))
    registry.chmod(0o644)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({**files["supervisor-config.json"], "trust_registry": str(registry)}))
    config.chmod(0o644)
    loaded = load_config(config, (os.getuid(),), (os.getuid(),))
    assert loaded["integrator_key_id"] == "k"
    assert loaded["push_principals"] == {"aao-impl-codex[bot]": "codex"}
    assert loaded["push_receipts_dir"] == "/var/lib/aao-supervisor/push-receipts"
    assert loaded["webhook_secret_path"] == "/etc/aao-supervisor/github-webhook.secret"
    assert loaded["webhook_repositories"] == ["owner/project"]
    assert loaded["webhook_bind"] == "127.0.0.1" and loaded["webhook_port"] == 8765


def test_auditor_cannot_be_developer():
    try:
        maker.build(REV, {}, "A", "S", 1005, ["aao-auditor"])
    except ValueError:
        return
    raise AssertionError("auditor accepted as developer")


def test_registry_is_static_and_fail_closed():
    template = json.loads((ROOT / "docs/audit-runs/20261019-provisional/policy.json").read_text())
    files = maker.build(REV, template, "A", "S", 1005, ["alessbarb"])
    registry = maker.build_registry(files["policy.json"], files["trust-anchor.json"], auditor_models={},
                                    author_models={})
    assert not maker.PER_PR_FIELDS & set(registry)
    assert set(registry["ra_status"].values()) == {"PENDING"}
    assert registry["enabled_risk_classes"] == ["R1"]
    assert registry["trusted_auditor_revisions"] == [REV]
    assert registry["policy_sha256"] == files["trust-anchor.json"]["policy_sha256"]
    assert registry["protected_routes"] == files["policy.json"]["protected_routes"]
    assert registry["protected_routes_sha256"] == files["policy.json"]["protected_routes_sha256"]
    assert registry["protected_routes"]["docs/CONSTITUTION.md"] == "R3"
    assert registry["required_check_publishers"] == {"aao-audit": [5448107], "test": [15368]}
    assert registry["push_principals"] == {"aao-impl-claude[bot]": "claude",
                                            "aao-impl-codex[bot]": "codex",
                                            "aao-impl-agy[bot]": "antigravity"}
    try:
        maker.build_registry(files["policy.json"], files["trust-anchor.json"], auditor_models={},
                             author_models={}, ra_status={"RA-02": "YES"})
    except ValueError:
        return
    raise AssertionError("invalid RA status accepted")


def test_runtime_configs_match_the_service_loaders(tmp_path):
    from aao import auditor_dispatch, r1_pipeline
    configs = maker.build_runtime_configs("autoaiorg/aao-governance-trial")
    files = maker.build(REV, {"version": "x"}, "A", "S", 1005, [], repo="owner/project")
    assert files["supervisor-config.json"]["repository"] == "owner/project"
    assert configs["integrator-config.json"]["heartbeat_sequence"] == "/var/lib/aao-integrator/heartbeat.sequence"
    assert set(configs["integrator-config.json"]) == r1_pipeline._CONFIG_FIELDS
    assert configs["integrator-config.json"]["schema"] == r1_pipeline.CONFIG_SCHEMA
    assert set(configs["dispatch.json"]) == auditor_dispatch._CONFIG_FIELDS
    assert configs["dispatch.json"]["schema"] == auditor_dispatch.CONFIG_SCHEMA
    for bad in ("a/b/c", "x;rm/y", "noslash"):
        try:
            maker.build_runtime_configs(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def _run_main(tmp_path, monkeypatch, *extra):
    import pwd
    import sys
    tmp_path.mkdir(parents=True, exist_ok=True)
    template = ROOT / "docs/audit-runs/20261019-provisional/policy.json"
    a, s = tmp_path / "a.pub", tmp_path / "s.pub"
    a.write_text(_pub(tmp_path, "a"))
    s.write_text(_pub(tmp_path, "s"))
    me = pwd.getpwuid(os.getuid())
    monkeypatch.setattr(maker.pwd, "getpwnam", lambda name: me)
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["make", "--revision", REV, "--policy-template", str(template),
                                      "--auditor-public-key", str(a), "--supervisor-public-key", str(s),
                                      "--repo", "owner/project", "--out", str(out), *extra])
    assert maker.main() == 0
    return json.loads((out / "registry.json").read_text())


def test_ra_status_flag_records_ceo_decision_and_defaults_pending(tmp_path, monkeypatch):
    registry = _run_main(tmp_path, monkeypatch, "--ra-status", "RA-01=PASS", "--ra-status", "RA-07=PASS")
    assert registry["ra_status"] == {"RA-01": "PASS", "RA-02": "PENDING", "RA-03": "PENDING",
                                     "RA-07": "PASS", "RA-09": "PENDING"}
    assert registry["auditor_models"]["aao-auditor-alt"] == "gemini"  # Antigravity, not Codex


def test_ra_status_flag_rejects_unknown_or_duplicate(tmp_path, monkeypatch):
    import pytest
    with pytest.raises(ValueError):
        _run_main(tmp_path / "x", monkeypatch, "--ra-status", "RA-05=PASS")
    with pytest.raises(SystemExit):
        _run_main(tmp_path / "y", monkeypatch, "--ra-status", "RA-01=PASS", "--ra-status", "RA-01=PENDING")
