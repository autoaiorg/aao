"""Sign local Git-history alerts and heartbeats; this is not GitHub supervision."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import socket
import stat
import struct
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aao.governance_ledger import append, verify
from aao.integration_authorization import canonical
from aao.pending_veto import all_pending_vetoes


def _sign(event: dict[str, Any], private_key: str) -> dict[str, Any]:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        message = Path(directory) / "message"
        message.write_bytes(canonical(event))
        signature = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", private_key, "-in", str(message)],
            check=True, capture_output=True,
        ).stdout
    return {**event, "signature": base64.b64encode(signature).decode()}


def _public_key_der(path: str) -> bytes:
    result = subprocess.run(["openssl", "pkey", "-pubin", "-in", path, "-outform", "DER"],
                            check=True, capture_output=True)
    return result.stdout


def _read_state(path: Path, private_key: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {}
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or
            stat.S_IMODE(metadata.st_mode) != 0o600):
        raise ValueError("supervisor state must be owned by supervisor uid and mode 0600")
    state = json.loads(path.read_text())
    try:
        signature = base64.b64decode(state.pop("signature"), validate=True)
    except (KeyError, ValueError) as error:
        raise ValueError("supervisor state signature is missing or invalid") from error
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        public, sig, message = root / "public.pem", root / "sig", root / "message"
        subprocess.run(["openssl", "pkey", "-in", private_key, "-pubout", "-out", str(public)],
                       check=True, capture_output=True)
        sig.write_bytes(signature)
        message.write_bytes(canonical(state))
        result = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public),
            "-sigfile", str(sig), "-in", str(message), "-rawin"], check=False, capture_output=True)
    if result.returncode:
        raise ValueError("supervisor state signature is invalid")
    return state


def _write_state(path: Path, state: dict[str, Any], private_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(_sign(state, private_key), handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_attribution(path: Path, candidate_sha: str, principals: list[str]) -> None:
    """Atomically and monotonically union authenticated-push principals for a candidate."""
    if not isinstance(candidate_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha):
        raise ValueError("candidate_sha must be a full lowercase Git SHA")
    if (not isinstance(principals, list) or not principals or
            any(not isinstance(item, str) or not item.strip() for item in principals)):
        raise ValueError("principals must be a non-empty list of non-empty strings")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.with_name(path.name + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                existing = {"schema": "aao.implementer-attribution.v1", "candidates": {}}
            if (not isinstance(existing, dict) or existing.get("schema") != "aao.implementer-attribution.v1" or
                    not isinstance(existing.get("candidates"), dict)):
                raise ValueError("attribution file has an invalid schema")
            current = existing["candidates"].get(candidate_sha, [])
            if not isinstance(current, list) or any(not isinstance(item, str) or not item.strip() for item in current):
                raise ValueError("attribution entry has an invalid schema")
            updated = {**existing, "candidates": {**existing["candidates"],
                        candidate_sha: sorted(set(current) | set(principals))}}
            fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
            try:
                os.fchmod(fd, 0o644)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(updated, handle, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _sequence(path: Path, private_key: str) -> int:
    state = _read_state(path, private_key)
    return int(state.get("sequence", 0))


def _persist_sequence(path: Path, sequence: int, private_key: str, *, lock_held: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    def persist() -> None:
        state = _read_state(path, private_key)
        state["sequence"] = max(sequence, int(state.get("sequence", 0)))
        _write_state(path, state, private_key)
    if lock_held:
        persist()
        return
    with (path.with_name(path.name + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            persist()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def inspect(
    repository: Path,
    authorization_shas: set[str],
    sequence: int,
    private_key: str,
    *,
    key_id: str,
    state_path: Path,
    ledger_path: Path,
    trusted_keys: dict[str, str],
    push_attributions: dict[str, str] | None = None,
    integrator_identity: str | None = None,
    protected_path_registry: dict[str, str] | None = None,
    authorized_classes: dict[str, str] | None = None,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Return signed alerts for unauthorized, misattributed, or under-classed commits.

    Authorizations are derived only from the signature-verified ledger. ``sequence``
    is retained for call compatibility; persistent state is the sequence authority.
    """
    rows = verify(ledger_path, trusted_keys)
    ledger_authorizations = {
        row["commit"]: row for row in rows
        if row.get("type") == "authorization" and isinstance(row.get("commit"), str)
        and isinstance(trusted_keys.get(row.get("key_id")), dict)
        and trusted_keys[row["key_id"]].get("can_authorize") is True
    }
    authorized = set(ledger_authorizations)
    commits = subprocess.run(
        ["git", "-C", str(repository), "rev-list", "--first-parent", "main"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    protected = protected_path_registry or {".github/workflows/": "R2"}
    order = {"R1": 1, "R2": 2, "R3": 3}
    events = []
    seq = max(sequence, _sequence(state_path, private_key))
    timestamp = now or datetime.now().astimezone().isoformat()
    expiry = (datetime.fromisoformat(timestamp.replace("Z", "+00:00")) + timedelta(minutes=5)).isoformat()  # noqa: FURB162
    for sha in commits:
        parents = subprocess.run(
            ["git", "-C", str(repository), "show", "-s", "--format=%P", sha],
            check=True, capture_output=True, text=True,
        ).stdout.split()
        if parents:
            paths = subprocess.run(
                ["git", "-C", str(repository), "diff-tree", "-r", "--no-renames", "--no-commit-id", "--name-only",
                 parents[0], sha], check=True, capture_output=True, text=True,
            ).stdout.splitlines()
        else:
            paths = subprocess.run(
                ["git", "-C", str(repository), "diff-tree", "--root", "-r", "--no-commit-id",
                 "--name-only", sha], check=True, capture_output=True, text=True,
            ).stdout.splitlines()
        changed_rules = [(path, level) for path in paths for rule, level in protected.items()
                         if path == rule or (rule.endswith("/") and path.startswith(rule))]
        ledger_row = ledger_authorizations.get(sha)
        attestation = (ledger_row or {}).get("risk_class")
        insufficient = any(order.get(attestation, 0) < order.get(level, 4) for _, level in changed_rules)
        mismatch = bool(ledger_row and integrator_identity is not None and
                        (push_attributions or {}).get(sha) != integrator_identity)
        if sha not in authorized or insufficient or mismatch:
            seq += 1
            events.append(_sign({
                "sequence": seq, "key_id": key_id, "issued_at": timestamp, "expires_at": expiry,
                "type": "alert", "commit": sha, "unauthorized": sha not in authorized,
                "workflow_change": any(path.startswith(".github/workflows/") for path, _ in changed_rules),
                "protected_path_change": bool(changed_rules),
                "protected_path_unauthorized": insufficient, "identity_mismatch": mismatch,
            }, private_key))
    _persist_sequence(state_path, seq, private_key)
    return events


def verify_heartbeat(event: Any, public_key: str, key_id: str, now: datetime,
                     max_age_seconds: int = 3600) -> dict[str, Any]:
    """Read-only check of a supervisor heartbeat (F4-01b gate path). Raises ValueError if not valid.

    Unlike the integrator, a gate keeps no sequence file, so a still-valid older heartbeat is accepted
    within its validity window (declared limitation)."""
    if not isinstance(event, dict) or event.get("type") != "heartbeat" or event.get("key_id") != key_id:
        raise ValueError("heartbeat type or key id is not the anchored supervisor")
    hex64 = re.compile(r"[0-9a-f]{64}")
    for field in ("ledger_head", "state_sha256"):
        if not isinstance(event.get(field), str) or not hex64.fullmatch(event[field]):
            raise ValueError(f"heartbeat {field} is missing or malformed")
    markers = event.get("pending_markers")
    if not isinstance(markers, dict) or any(
            not isinstance(c, str) or not re.fullmatch(r"[0-9a-f]{40}", c) or not isinstance(d, list) or
            any(not isinstance(x, str) or not hex64.fullmatch(x) for x in d) for c, d in markers.items()):
        raise ValueError("heartbeat pending_markers is missing or malformed")
    try:
        issued = datetime.fromisoformat(event["issued_at"])
        expiry = datetime.fromisoformat(event["expires_at"])
        signature = base64.b64decode(event["signature"], validate=True)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"heartbeat timestamps or signature malformed: {error}") from error
    if issued.tzinfo is None or expiry.tzinfo is None or now.tzinfo is None:
        raise ValueError("heartbeat timestamps must be timezone-aware")
    if now >= expiry or issued > now + timedelta(seconds=60) or (now - issued).total_seconds() > min(3600, max_age_seconds):
        raise ValueError("heartbeat expired, too old or issued in the future")
    signed = {k: v for k, v in event.items() if k != "signature"}
    with tempfile.TemporaryDirectory() as directory:
        sig, msg = Path(directory) / "sig", Path(directory) / "msg"
        sig.write_bytes(signature)
        msg.write_bytes(canonical(signed))
        ok = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", public_key, "-sigfile", str(sig),
                             "-in", str(msg), "-rawin"], check=False, capture_output=True).returncode == 0
    if not ok:
        raise ValueError("heartbeat signature does not verify against the anchored supervisor key")
    return event


def signed_heartbeat(sequence: int, issued_at: str, private_key: str, *, key_id: str,
                     expires_at: str, ledger_path: Path,
                     state_path: Path, integrator_key_id: str,
                     trusted_keys: dict[str, Any] | None = None,
                     heartbeat_path: Path | None = None) -> dict[str, Any]:
    """Sign supervisor state; when given custody inputs, refresh the durable registry."""
    if ledger_path is None:
        raise ValueError("supervisor requires a ledger path")
    prior: dict[str, Any] = {}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with (state_path.with_name(state_path.name + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            prior = _read_state(state_path, private_key)
            prior_state_bytes = state_path.read_bytes() if state_path.exists() else canonical({})
            if not trusted_keys:
                raise ValueError("supervisor requires trusted ledger keys")
            if not isinstance(integrator_key_id, str) or not integrator_key_id:
                raise ValueError("supervisor requires an integrator key id")
            integrator = trusted_keys.get(integrator_key_id)
            if isinstance(integrator, dict) and integrator.get("public_key"):
                if integrator.get("can_resolve_pending") is True or integrator.get("can_authorize") is True:
                    raise ValueError("integrator key has a reserved ledger capability")
                integrator_der = _public_key_der(integrator["public_key"])
                for other_id, authority in trusted_keys.items():
                    if (other_id != integrator_key_id and isinstance(authority, dict) and
                            (authority.get("can_resolve_pending") is True or authority.get("can_authorize") is True) and
                            authority.get("public_key") and _public_key_der(authority["public_key"]) == integrator_der):
                        raise ValueError("integrator public key is shared with a reserved ledger authority")
            rows = verify(ledger_path, trusted_keys)
            previous_head = prior.get("ledger_head", "0" * 64)
            row_hashes = {row["hash"] for row in rows}
            if previous_head != "0" * 64 and previous_head not in row_hashes:
                message = "ledger truncated or rewritten since last heartbeat"
                incidents = list(prior.get("incidents", []))
                incidents.append({"type": "incident", "message": message, "issued_at": issued_at})
                _write_state(state_path, {**prior, "incidents": incidents}, private_key)
                incident_key = trusted_keys.get(key_id)
                if isinstance(incident_key, dict) and incident_key.get("can_record_incidents") is True:
                    append(ledger_path, {"type": "incident", "id": f"ledger-continuity-{sequence}",
                        "summary": message, "issued_at": issued_at}, key_id, private_key, trusted_keys)
                raise ValueError(message)
            head = rows[-1]["hash"] if rows else "0" * 64
            resolved = {digest for row in rows if "resolves_pending" in row
                        for digest in row["resolves_pending"]}
            markers = {key: list(values) for key, values in prior.get("pending_markers", {}).items()}
            markers = {candidate: [digest for digest in digests if digest not in resolved]
                       for candidate, digests in markers.items()}
            markers = {candidate: digests for candidate, digests in markers.items() if digests}
            current = all_pending_vetoes(Path(str(ledger_path) + ".pending-vetoes"), ledger_path.stat().st_uid)
            for candidate, digests in current.items():
                markers[candidate] = sorted(set(markers.get(candidate, [])) | set(digests))
            event = {"sequence": sequence, "key_id": key_id, "issued_at": issued_at,
                     "expires_at": expires_at, "type": "heartbeat", "ledger_head": head,
                     "pending_markers": markers, "state_sha256": hashlib.sha256(prior_state_bytes).hexdigest()}
            signed = _sign(event, private_key)
            state = {**prior, "sequence": max(sequence, int(prior.get("sequence", 0))),
                     "ledger_head": head, "pending_markers": markers}
            _write_state(state_path, state, private_key)
            if heartbeat_path is not None:
                # Publication happens under the same lock as the state, and never moves backwards (F4-03, A).
                if heartbeat_path.exists():
                    try:
                        published = int(json.loads(heartbeat_path.read_text()).get("sequence", 0))
                    except (OSError, ValueError, TypeError):
                        published = 0
                    if published >= signed["sequence"]:
                        raise ValueError("a heartbeat with an equal or newer sequence is already published")
                temporary = heartbeat_path.with_name(heartbeat_path.name + ".tmp")
                temporary.write_text(json.dumps(signed), encoding="utf-8")
                os.replace(temporary, heartbeat_path)
            return signed
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def handle_veto_report(conn: socket.socket, *, auditor_uid: int, state_path: Path, private_key: str, key_id: str,
                       ledger_path: Path, trusted_keys: dict[str, Any], integrator_key_id: str,
                       heartbeat_path: Path, validity_seconds: int = 600) -> dict[str, Any]:
    """F4-03: synchronous veto hand-off. The auditor process reports its pending-veto marker over a Unix
    socket; the supervisor (its own uid) checks the peer uid with SO_PEERCRED, records the digest in its
    signed state and emits a fresh signed heartbeat BEFORE acknowledging. A marker file deleted afterwards
    by any other process is then detected by the gate and the integrator."""
    def reply(payload: dict[str, Any]) -> dict[str, Any]:
        conn.sendall(json.dumps(payload).encode() + b"\n")
        return payload

    conn.settimeout(5)
    _pid, uid, _gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                           struct.calcsize("3i")))
    if uid != auditor_uid:
        return reply({"ok": False, "error": "peer is not the auditor uid"})
    data = b""
    try:
        while not data.endswith(b"\n"):
            chunk = conn.recv(4096 - len(data))
            if not chunk:
                break
            data += chunk
            if len(data) >= 4096:
                return reply({"ok": False, "error": "veto report too large"})
    except OSError as error:
        return reply({"ok": False, "error": f"veto report not received: {error}"})
    try:
        report = json.loads(data)
        if not isinstance(report, dict) or set(report) != {"candidate_sha", "marker_digest"}:
            raise ValueError("unexpected fields")
        candidate, digest = report["candidate_sha"], report["marker_digest"]
        if (not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate) or
                not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("malformed report")
    except (ValueError, KeyError, TypeError) as error:
        return reply({"ok": False, "error": f"invalid veto report: {error}"})
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with state_path.with_name(state_path.name + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                prior = _read_state(state_path, private_key)
                markers = {k: list(v) for k, v in prior.get("pending_markers", {}).items()}
                markers[candidate] = sorted(set(markers.get(candidate, [])) | {digest})
                _write_state(state_path, {**prior, "pending_markers": markers}, private_key)
                sequence = int(prior.get("sequence", 0)) + 1
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        now = datetime.now(UTC)
        event = signed_heartbeat(sequence, now.isoformat(), private_key, key_id=key_id,
                                 expires_at=(now + timedelta(seconds=validity_seconds)).isoformat(),
                                 ledger_path=ledger_path, state_path=state_path,
                                 integrator_key_id=integrator_key_id, trusted_keys=trusted_keys,
                                 heartbeat_path=heartbeat_path)
        if digest not in event["pending_markers"].get(candidate, []):
            raise ValueError("heartbeat does not include the reported marker")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return reply({"ok": False, "error": f"supervisor could not record the veto: {error}"})
    return reply({"ok": True, "heartbeat_sequence": event["sequence"]})


def serve_veto_intake(socket_path: Path, **handler_args: Any) -> None:  # pragma: no cover - service loop
    """Run as the supervisor uid (systemd service). One report per connection."""
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o660)
    server.listen(16)
    while True:
        try:
            conn, _ = server.accept()
            with conn:
                handle_veto_report(conn, **handler_args)
        except OSError:
            continue
