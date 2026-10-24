import base64
import json
import os
import subprocess
from pathlib import Path

from aao import auditor_dispatch
from aao.governance_ledger import verify
from aao.integration_authorization import canonical


def _keypair(directory: Path, name: str):
    private, public = directory / f"{name}.pem", directory / f"{name}.pub"
    subprocess.run(["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private)],
                   check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                   check=True, capture_output=True)
    return private, public


def _signed(payload, private: Path):
    message = private.parent / "message"
    message.write_bytes(canonical(payload))
    signature = subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(private),
                                "-in", str(message)], check=True, capture_output=True).stdout
    return {**payload, "signature": base64.b64encode(signature).decode()}


def _incident(intended="a" * 40):
    return {"schema": "aao.integrator-incident.v1", "type": "incident", "id": "post-push-" + intended,
            "target_ref": "refs/heads/main", "detail": "verification failed", "intended_sha": intended,
            "observed_sha": None, "intended_tree_sha": "b" * 40, "observed_tree_sha": None,
            "intended_parents": ["c" * 40, "d" * 40], "observed_parents": None,
            "created_at": "2026-10-24T10:00:00+00:00", "key_id": "integrator"}


def _dispatch_fixture(tmp_path, monkeypatch):
    integrator_private, integrator_public = _keypair(tmp_path, "integrator")
    auditor_private, auditor_public = _keypair(tmp_path, "auditor")
    ledger = tmp_path / "governance.jsonl"
    ledger.write_bytes(b"")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"integrator_key_id": "integrator", "ledger_keys": {
        "integrator": {"public_key": str(integrator_public)}}}))
    registry.chmod(0o600)
    anchor = {"ledger_path": str(ledger), "policy": {"auditor_id": "auditor"}}
    monkeypatch.setattr(auditor_dispatch, "load_anchor", lambda *_: anchor)
    monkeypatch.setattr(auditor_dispatch, "_ledger", lambda _anchor: ledger)
    monkeypatch.setattr(auditor_dispatch, "_ledger_keys", lambda _anchor, _dir: {
        "auditor": {"public_key": str(auditor_public)}})
    monkeypatch.setattr(auditor_dispatch, "ledger_rows", lambda _anchor: verify(ledger, {
        "auditor": {"public_key": str(auditor_public)}}))
    inbox, reports = tmp_path / "inbox", tmp_path / "reports"
    inbox.mkdir()
    def submit(payload, name=None):
        signed = _signed(payload, integrator_private)
        path = inbox / (name or f"incident-{payload['intended_sha']}.json")
        path.write_text(json.dumps(signed))
        return path
    result = auditor_dispatch.dispatch_once(inbox, reports, auditor_private, object(),
        anchor_path=tmp_path / "unused-anchor", trust_registry_path=registry,
        trust_registry_owner_uids=(os.getuid(),))
    return result, ledger, auditor_public, integrator_private, integrator_public, submit, inbox, reports, auditor_private


def test_dispatch_appends_one_auditor_signed_incident_and_is_idempotent(tmp_path, monkeypatch):
    result, ledger, auditor_public, _, _, submit, inbox, reports, auditor_private = _dispatch_fixture(tmp_path, monkeypatch)
    payload = _incident()
    submit(payload)
    result = auditor_dispatch.dispatch_once(inbox, reports, auditor_private, object(),
        anchor_path=tmp_path / "unused-anchor", trust_registry_path=tmp_path / "registry.json",
        trust_registry_owner_uids=(os.getuid(),))
    assert result == [{"id": "a" * 40, "status": "recorded"}]
    rows = verify(ledger, {"auditor": str(auditor_public)})
    assert len(rows) == 1
    assert rows[0]["type"] == "integrator-incident"
    assert rows[0]["key_id"] == "auditor"
    assert rows[0]["incident"]["id"] == payload["id"]
    result = auditor_dispatch.dispatch_once(inbox, reports, auditor_private, object(),
        anchor_path=tmp_path / "unused-anchor", trust_registry_path=tmp_path / "registry.json",
        trust_registry_owner_uids=(os.getuid(),))
    assert result == [{"id": "a" * 40, "status": "ignored", "reason": "incident already recorded"}]
    assert len(verify(ledger, {"auditor": str(auditor_public)})) == 1


def test_invalid_incidents_never_reach_ledger(tmp_path, monkeypatch):
    result, ledger, _auditor_public, integrator_private, _integrator_public, _submit, inbox, reports, auditor_private = _dispatch_fixture(tmp_path, monkeypatch)
    assert not result
    valid = _incident()
    forged = _signed(valid, integrator_private)
    forged["detail"] = "altered after signing"
    (inbox / f"incident-{'a' * 40}.json").write_text(json.dumps(forged))
    wrong_key, _ = _keypair(tmp_path, "wrong")
    (inbox / f"incident-{'b' * 40}.json").write_text(json.dumps(_signed(_incident("b" * 40), wrong_key)))
    extra = {**_incident("c" * 40), "unexpected": True}
    (inbox / f"incident-{'c' * 40}.json").write_text(json.dumps(_signed(extra, integrator_private)))
    bad_sha = _incident("d" * 40); bad_sha["observed_sha"] = "bad"
    (inbox / f"incident-{'d' * 40}.json").write_text(json.dumps(_signed(bad_sha, integrator_private)))
    too_long = _incident("e" * 40); too_long["detail"] = "x" * 4097
    (inbox / f"incident-{'e' * 40}.json").write_text(json.dumps(_signed(too_long, integrator_private)))
    (inbox / "incident-..%2Fescape.json").write_text("{}")
    results = auditor_dispatch.dispatch_once(inbox, reports, auditor_private, object(),
        anchor_path=tmp_path / "unused-anchor", trust_registry_path=tmp_path / "registry.json",
        trust_registry_owner_uids=(os.getuid(),))
    assert all(item["status"] in {"failed", "ignored"} for item in results)
    assert ledger.read_bytes() == b""
