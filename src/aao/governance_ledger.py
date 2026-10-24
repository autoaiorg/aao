"""Append-only signed hash-chain ledger (file custody remains external)."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from aao.integration_authorization import canonical


def _verify(entry: dict[str, Any], public_key: str) -> bool:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        sig, msg = Path(d) / "sig", Path(d) / "msg"
        sig.write_bytes(base64.b64decode(entry["signature"], validate=True))
        payload = {k: v for k, v in entry.items() if k not in {"signature", "hash"}}
        msg.write_bytes(canonical(payload))
        return (
            subprocess.run(
                [
                    "openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    public_key,
                    "-sigfile",
                    str(sig),
                    "-in",
                    str(msg),
                    "-rawin",
                ],
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )


def append(path: Path, payload: dict[str, Any], key_id: str, private_key: str,
           trusted_keys: dict[str, Any], expected_head: str | None = None) -> dict[str, Any]:
    rows = verify(path, trusted_keys, expected_head) if path.exists() else []
    controls = {"sequence", "previous_hash", "key_id", "signature", "hash"}
    if controls.intersection(payload):
        raise ValueError("payload collides with ledger control fields")
    if key_id not in trusted_keys:
        raise ValueError("ledger signing key is not trusted")
    if "resolves_pending" in payload:
        values = payload["resolves_pending"]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("malformed resolves_pending ledger field")
        if not _authority(trusted_keys.get(key_id), "can_resolve_pending"):
            raise ValueError("resolves_pending signer is not an enabled authority")
    if payload.get("type") == "revocation":
        authority = trusted_keys[key_id]
        if not isinstance(authority, dict) or not authority.get("can_revoke"):
            raise ValueError("revocation signer is not an enabled authority")
        target = payload.get("target")
        if not target or not any(r.get("type") == "veto" and r.get("hash") == target for r in rows):
            raise ValueError("revocation must reference an exact existing veto")
    if payload.get("type") in {"incident", "integrator-incident"} and not _authority(trusted_keys.get(key_id), "can_record_incidents"):
        raise ValueError("incident signer is not an enabled authority")
    if payload.get("type") == "incident-resolution":
        if not _authority(trusted_keys.get(key_id), "can_resolve_incidents"):
            raise ValueError("incident-resolution signer is not an enabled authority")
        incident = next((r for r in rows if r.get("type") in {"incident", "integrator-incident"} and
                         r.get("id") == payload.get("target")), None)
        if not incident or incident.get("hash") != payload.get("incident_hash"):
            raise ValueError("incident-resolution must reference an exact existing incident")
    entry = {
        "sequence": len(rows) + 1,
        "previous_hash": rows[-1]["hash"] if rows else "0" * 64,
        "key_id": key_id,
        **payload,
    }
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        msg = Path(d) / "msg"
        msg.write_bytes(canonical(entry))
        sig = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", private_key, "-in", str(msg)],
            check=True,
            capture_output=True,
        ).stdout
    entry["signature"] = base64.b64encode(sig).decode()
    entry["hash"] = hashlib.sha256(canonical(entry)).hexdigest()
    with path.open("ab") as stream:
        stream.write(canonical(entry) + b"\n")
    return entry


def verify(
    path: Path, trusted_keys: dict[str, str], expected_head: str | None = None
) -> list[dict[str, Any]]:
    if not trusted_keys:
        raise ValueError("non-empty trusted key registry is required")
    rows = []
    previous = "0" * 64
    for number, line in enumerate(path.read_bytes().splitlines(), 1):
        e = json.loads(line)
        digest = e.pop("hash", None)
        if e.get("sequence") != number or e.get("previous_hash") != previous:
            raise ValueError("ledger reordered/truncated/chain mismatch")
        if digest != hashlib.sha256(canonical(e)).hexdigest():
            raise ValueError("ledger edited")
        key_entry = trusted_keys.get(e.get("key_id"))
        key = key_entry.get("public_key") if isinstance(key_entry, dict) else key_entry
        if not key or not _verify(e, key):
            raise ValueError("ledger signature invalid or key unknown")
        if "resolves_pending" in e:
            values = e["resolves_pending"]
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError("malformed resolves_pending ledger field")
            if not _authority(key_entry, "can_resolve_pending"):
                raise ValueError("resolves_pending signer is not an enabled authority")
        if e.get("type") == "revocation":
            if not isinstance(key_entry, dict) or not key_entry.get("can_revoke"):
                raise ValueError("revocation signer is not an enabled authority")
            if not e.get("target") or not any(r.get("type") == "veto" and r.get("hash") == e["target"] for r in rows):
                raise ValueError("revocation must reference an exact existing veto")
        if e.get("type") in {"incident", "integrator-incident"} and not _authority(key_entry, "can_record_incidents"):
            raise ValueError("incident signer is not an enabled authority")
        if e.get("type") == "authorization" and not _authority(key_entry, "can_authorize"):
            raise ValueError("authorization signer is not an enabled authority")
        if e.get("type") == "incident-resolution":
            incident = next((r for r in rows if r.get("type") in {"incident", "integrator-incident"} and
                             r.get("id") == e.get("target")), None)
            if (not _authority(key_entry, "can_resolve_incidents") or not incident or
                    incident.get("hash") != e.get("incident_hash")):
                raise ValueError("invalid incident-resolution authority or incident reference")
        e["hash"] = digest
        previous = digest
        rows.append(e)
    if expected_head is not None and previous != expected_head:
        raise ValueError("ledger truncated or unexpected terminal hash")
    return rows


def active_vetoes(rows: list[dict[str, Any]], trusted_keys: dict[str, Any]) -> list[dict[str, Any]]:
    if not trusted_keys:
        raise ValueError("non-empty trusted key registry is required")
    veto_hashes = {r.get("hash") for r in rows if r.get("type") == "veto"}
    revoked = set()
    for row in rows:
        if row.get("type") != "revocation":
            continue
        key_entry = trusted_keys.get(row.get("key_id"))
        key = key_entry.get("public_key") if isinstance(key_entry, dict) else key_entry
        if (
            not key
            or not _verify(row, key)
            or not isinstance(key_entry, dict)
            or not key_entry.get("can_revoke")
            or row.get("target") not in veto_hashes
        ):
            continue
        revoked.add(row["target"])
    return [r for r in rows if r.get("type") == "veto" and r.get("hash") not in revoked]


def _authority(entry: Any, capability: str) -> bool:
    return isinstance(entry, dict) and entry.get(capability) is True and bool(entry.get("public_key"))


def open_incidents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return incidents without a later valid resolution (verified when rows are read)."""
    resolved = {row.get("incident_hash") for row in rows if row.get("type") == "incident-resolution"}
    return [row for row in rows if row.get("type") in {"incident", "integrator-incident"}
            and row.get("hash") not in resolved]
